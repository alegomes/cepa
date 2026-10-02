#!/usr/bin/env python3
"""Build em segundo plano grava o baseline quando termina
(`common/hooks/capture-build-result.py`, 2026-10-02).

No third-party deps — run with `python3 tests/test_capture_build_background.py`.
Exits non-zero on failure.

O `./mvnw verify` do wego leva ~25 min e nunca cabe em primeiro plano. O Bash
devolve só `backgroundTaskId`, sem saída, e o hook não tinha o que classificar:
o `last-build.json` nunca era gravado e o `gate-advance` barrava o commit de um
build que tinha passado. Medido no claude 2.1.287: o CC escreve a saída em
`<tmp>/claude-<uid>/<projeto>/<session_id>/tasks/<id>.output` e acrescenta
`[exited with code N]` no fim. O teste monta essa árvore num `TMPDIR` falso.

Guards the contract:
  - lançar um build em segundo plano deixa `<id>.cepa-build.json` e não grava
    baseline;
  - enquanto o `.output` não tem a linha de fim, nada é gravado;
  - terminado, a próxima chamada de Bash grava SUCCESS/FAILURE pelos marcadores;
  - código de saída != 0 vence o marcador de sucesso;
  - filtro de teste sem teste executado vira EMPTY, como em primeiro plano;
  - edição de código depois do lançamento descarta o resultado (STALE fica);
  - o `gate-advance` colhe antes de julgar: o commit passa sem outro Bash no meio;
  - comando que não é build em segundo plano não deixa registro.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from _telemetria_isolada import isola

isola()

REPO = Path(__file__).resolve().parent.parent
CAPTURE = REPO / "common" / "hooks" / "capture-build-result.py"
GATE = REPO / "common" / "hooks" / "gate-advance.py"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


class Sessao:
    """Uma sessão falsa: projeto com pom.xml e o `tasks/` do CC sob um TMPDIR."""

    def __init__(self, base: Path, nome: str):
        self.sid = str(uuid.uuid4())
        self.tmp = base / f"tmp-{nome}"
        self.tasks = self.tmp / "claude-501" / "-proj" / self.sid / "tasks"
        self.tasks.mkdir(parents=True)
        self.root = base / nome
        self.root.mkdir()
        (self.root / "pom.xml").write_text("<project/>")
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.env = {**os.environ, "TMPDIR": str(self.tmp)}

    def _run(self, hook, payload):
        payload = {"cwd": str(self.root), "session_id": self.sid, **payload}
        return subprocess.run([sys.executable, str(hook)], input=json.dumps(payload),
                              capture_output=True, text=True, env=self.env)

    def lanca(self, command, task_id, cria_output=True):
        if cria_output:
            (self.tasks / f"{task_id}.output").write_text("")
        return self._run(CAPTURE, {
            "tool_name": "Bash",
            "tool_input": {"command": command, "run_in_background": True},
            "tool_response": {"stdout": "", "stderr": "", "interrupted": False,
                              "backgroundTaskId": task_id},
        })

    def termina(self, task_id, saida, codigo):
        (self.tasks / f"{task_id}.output").write_text(
            f"{saida}\n\n[exited with code {codigo}]\n")

    def outro_bash(self, command="ls", stdout="pom.xml", **extra):
        return self._run(CAPTURE, {"tool_name": "Bash", "tool_input": {"command": command},
                                   "tool_response": {"stdout": stdout}, **extra})

    def commit(self, hook=GATE, **extra):
        return self._run(hook, {"tool_name": "Bash", "hook_event_name": "PreToolUse",
                                "tool_input": {"command": "git commit -m x"}, **extra})

    def envelhece(self, task_id, horas):
        p = self.tasks / f"{task_id}.cepa-build.json"
        entry = json.loads(p.read_text())
        entry["started_at"] = iso(-horas * 3600)
        p.write_text(json.dumps(entry))

    def pendente(self, task_id):
        return (self.tasks / f"{task_id}.cepa-build.json").exists()

    def baseline(self):
        p = self.root / ".claude" / "last-build.json"
        return json.loads(p.read_text()) if p.exists() else None

    def grava_baseline(self, state):
        p = self.root / ".claude" / "last-build.json"
        p.parent.mkdir(exist_ok=True)
        p.write_text(json.dumps(state))


def iso(delta_s=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_s)).isoformat(timespec="seconds")


MVN_OK = "[INFO] Tests run: 2352, Failures: 0, Errors: 0, Skipped: 0\n[INFO] BUILD SUCCESS"
MVN_FAIL = "[ERROR] Tests run: 10, Failures: 1, Errors: 0, Skipped: 0\n[INFO] BUILD FAILURE"


def main():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)

        # ── lançamento + build ainda rodando + fim verde ────────────────────
        s = Sessao(base, "verde")
        res = s.lanca("./mvnw verify", "bverde01")
        check("hook sai 0 no lançamento", res.returncode == 0, res.stderr)
        check("lançamento deixa o registro pendente", s.pendente("bverde01"), res.stderr)
        check("lançamento não grava baseline", s.baseline() is None, str(s.baseline()))

        (s.tasks / "bverde01.output").write_text("[INFO] Building...\n" + MVN_OK)
        s.outro_bash()
        check("sem a linha de fim, nada é gravado (Maven pode ter mais módulos)",
              s.baseline() is None and s.pendente("bverde01"), str(s.baseline()))

        (s.tasks / "bverde01.output").write_text(
            "[exited with code 0]\n[INFO] Building module 2/5...\n")
        s.outro_bash()
        check("linha de fim no meio da saída não conta como fim (só a última linha)",
              s.baseline() is None and s.pendente("bverde01"), str(s.baseline()))

        s.termina("bverde01", MVN_OK, 0)
        s.outro_bash()
        b = s.baseline() or {}
        check("build terminado grava SUCCESS na próxima chamada de Bash",
              b.get("status") == "SUCCESS", str(b))
        check("baseline aponta a tarefa e o lançamento",
              b.get("background_task") == "bverde01" and b.get("started_at"), str(b))
        check("baseline grava o comando do build, não o `ls`",
              b.get("command") == "./mvnw verify", str(b))
        check("registro pendente some depois de colhido", not s.pendente("bverde01"))

        # ── fim vermelho ────────────────────────────────────────────────────
        s = Sessao(base, "vermelho")
        s.lanca("./mvnw verify", "bverm001")
        s.termina("bverm001", MVN_FAIL, 1)
        s.outro_bash()
        check("BUILD FAILURE grava FAILURE",
              (s.baseline() or {}).get("status") == "FAILURE", str(s.baseline()))

        # ── código de saída vence o marcador ────────────────────────────────
        s = Sessao(base, "exit")
        s.lanca("./mvnw verify && ./scripts/smoke.sh", "bexit001")
        s.termina("bexit001", MVN_OK + "\nsmoke: falhou", 3)
        s.outro_bash()
        check("exit != 0 grava FAILURE mesmo com BUILD SUCCESS na saída",
              (s.baseline() or {}).get("status") == "FAILURE", str(s.baseline()))

        # ── filtro de teste sem teste executado ─────────────────────────────
        s = Sessao(base, "vazio")
        s.lanca("./mvnw test -Dtest=NaoExisteTest", "bvazio01")
        s.termina("bvazio01", "[INFO] BUILD SUCCESS", 0)
        s.outro_bash()
        check("-Dtest sem teste executado grava EMPTY",
              (s.baseline() or {}).get("status") == "EMPTY", str(s.baseline()))

        # ── edição depois do lançamento descarta o resultado ────────────────
        s = Sessao(base, "editado")
        s.lanca("./mvnw verify", "bedit001")
        stale = {"status": "STALE", "since": iso(+5), "after_edit_to": "src/A.java"}
        s.grava_baseline(stale)
        s.termina("bedit001", MVN_OK, 0)
        s.outro_bash()
        check("edição depois do lançamento mantém STALE",
              (s.baseline() or {}).get("status") == "STALE", str(s.baseline()))
        check("registro do build descartado é removido", not s.pendente("bedit001"))

        # ── STALE de ANTES do lançamento é limpo pelo build ─────────────────
        # ── e o gate-advance colhe sozinho antes de julgar ──────────────────
        s = Sessao(base, "gate")
        s.grava_baseline({"status": "STALE", "since": iso(-3600), "after_edit_to": "src/A.java"})
        s.lanca("./mvnw verify", "bgate001")
        s.termina("bgate001", MVN_OK, 0)
        res = s.commit()
        check("gate-advance libera o commit com o build de fundo terminado",
              res.returncode == 0, res.stderr[-400:])
        check("gate-advance gravou o SUCCESS colhido",
              (s.baseline() or {}).get("status") == "SUCCESS", str(s.baseline()))

        s = Sessao(base, "gate-rodando")
        s.grava_baseline({"status": "STALE", "since": iso(-3600), "after_edit_to": "src/A.java"})
        s.lanca("./mvnw verify", "bgate002")
        res = s.commit()
        check("gate-advance continua barrando enquanto o build roda",
              res.returncode == 2, f"rc={res.returncode}")

        # ── segundo plano que não é build ───────────────────────────────────
        s = Sessao(base, "nao-build")
        s.lanca("python3 -m http.server", "bserv001")
        check("comando que não é build não deixa registro", not s.pendente("bserv001"))

        # ── casos pedidos pelo proof-reviewer (2026-10-02) ──────────────────
        s = Sessao(base, "mais-novo")
        s.lanca("./mvnw verify", "bnovo001")
        s.grava_baseline({"status": "SUCCESS", "at": iso(+5), "command": "./mvnw -pl x verify"})
        s.termina("bnovo001", MVN_FAIL, 1)
        s.outro_bash()
        b = s.baseline() or {}
        check("build mais novo em primeiro plano não é sobrescrito pelo antigo",
              b.get("status") == "SUCCESS" and b.get("command") == "./mvnw -pl x verify", str(b))

        s = Sessao(base, "marcador-falha")
        s.lanca("./mvnw verify", "bmfal001")
        s.termina("bmfal001", MVN_FAIL, 0)
        s.outro_bash()
        check("exit 0 com BUILD FAILURE na saída grava FAILURE",
              (s.baseline() or {}).get("status") == "FAILURE", str(s.baseline()))

        s = Sessao(base, "exit-negativo")
        s.lanca("./mvnw verify", "bneg0001")
        s.termina("bneg0001", "[INFO] Building...", -9)
        s.outro_bash()
        check("exit negativo (processo morto por sinal) grava FAILURE",
              (s.baseline() or {}).get("status") == "FAILURE", str(s.baseline()))

        s = Sessao(base, "abandonado")
        s.lanca("./mvnw verify", "babnd001")
        s.envelhece("babnd001", 7)
        s.outro_bash()
        check("pendente sem fim há mais de 6 h é removido", not s.pendente("babnd001"))
        check("pendente abandonado não grava baseline", s.baseline() is None, str(s.baseline()))

        s = Sessao(base, "recente")
        s.lanca("./mvnw verify", "brcnt001")
        s.envelhece("brcnt001", 5)
        s.outro_bash()
        check("pendente sem fim há menos de 6 h continua", s.pendente("brcnt001"))

        s = Sessao(base, "sem-output")
        res = s.lanca("./mvnw verify", "bsout001", cria_output=False)
        check("sem o .output do CC, não deixa registro", not s.pendente("bsout001"))
        check("sem o .output do CC, avisa que não vai gravar",
              "will NOT be recorded" in res.stderr, res.stderr)

        s = Sessao(base, "pendente-corrompido")
        (s.tasks / "bcorr001.cepa-build.json").write_text("{nao é json")
        res = s.outro_bash("./mvnw verify", MVN_OK)
        check("pendente corrompido não derruba o hook",
              res.returncode == 0 and (s.baseline() or {}).get("status") == "SUCCESS",
              f"rc={res.returncode} {res.stderr[-300:]}")
        res = s.outro_bash("./mvnw verify", MVN_OK, session_id=12345)
        check("session_id que não é texto não derruba o hook", res.returncode == 0,
              res.stderr[-300:])

        # O gate carrega o capture pelo caminho. Se ele não carregar, o gate
        # continua julgando o baseline em vez de morrer e liberar o commit.
        hooks = base / "hooks-quebrados"
        shutil.copytree(GATE.parent, hooks)
        (hooks / "capture-build-result.py").write_text("raise RuntimeError('quebrado')\n")
        s = Sessao(base, "capture-quebrado")
        s.grava_baseline({"status": "STALE", "since": iso(-60), "after_edit_to": "src/A.java"})
        res = s.commit(hook=hooks / "gate-advance.py")
        check("capture que não carrega não derruba o gate: ele ainda barra o STALE",
              res.returncode == 2 and "harvest failed" in res.stderr,
              f"rc={res.returncode} {res.stderr[-300:]}")

        s = Sessao(base, "root-install")
        s.lanca("./mvnw install", "binst001")
        s.termina("binst001", MVN_OK, 0)
        s.outro_bash()
        check("install da raiz em segundo plano grava last-root-install.json",
              (s.root / ".claude" / "last-root-install.json").exists())

        # O registro guarda build_dir e marker_root separados: num `cd` para
        # submódulo eles divergem, e trocar um pelo outro na colheita marcava
        # a raiz como instalada quando só o submódulo foi.
        s = Sessao(base, "install-submodulo")
        (s.root / "domain").mkdir()
        s.lanca("cd domain && ./mvnw install", "bsubm001")
        s.termina("bsubm001", MVN_OK, 0)
        s.outro_bash()
        check("install de submódulo em segundo plano grava o SUCCESS na raiz da sessão",
              (s.baseline() or {}).get("status") == "SUCCESS", str(s.baseline()))
        check("install de submódulo em segundo plano NÃO marca a raiz como instalada",
              not (s.root / ".claude" / "last-root-install.json").exists())

    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\ntodos ok")


if __name__ == "__main__":
    main()
