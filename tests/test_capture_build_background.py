#!/usr/bin/env python3
"""Background build records the baseline when it finishes
(`common/hooks/capture-build-result.py`, 2026-10-02).

No third-party deps — run with `python3 tests/test_capture_build_background.py`.
Exits non-zero on failure.

wego's `./mvnw verify` takes ~25 min and never fits in the foreground. Bash
returns only `backgroundTaskId`, with no output, and the hook had nothing to classify:
`last-build.json` was never written and `gate-advance` blocked the commit of a
build that had passed. Measured on claude 2.1.287: CC writes the output to
`<tmp>/claude-<uid>/<project>/<session_id>/tasks/<id>.output` and appends
`[exited with code N]` at the end. The test builds that tree in a fake `TMPDIR`.

Guards the contract:
  - launching a background build leaves `<id>.cepa-build.json` and records no
    baseline;
  - while the `.output` has no end line, nothing is recorded;
  - once finished, the next Bash call records SUCCESS/FAILURE by the markers;
  - exit code != 0 beats the success marker;
  - a test filter with no test executed becomes EMPTY, as in the foreground;
  - a code edit after the launch discards the result (STALE stays);
  - `gate-advance` harvests before judging: the commit passes without another Bash in between;
  - a command that is not a background build leaves no record;
  - session continued after a context overflow (fb-20261005-1): the payload carries
    a new session_id (B) but CC keeps writing into the original's (A) `tasks/`.
    The launch finds the `.output` in A's folder and leaves the pending record there; the harvest
    under B records the baseline; gate-advance under B releases the commit; a build launched
    under A before the overflow is also harvested under B (same cwd); a pending record of ANOTHER
    tree is not harvested; with no `.output` anywhere, it stays "NOT be recorded".
  - build stopped by CC (item build-segundo-plano-morre-aos-30-min, measured on
    claude 2.1.301 on 2026-10-15): the `.output` ends in `[killed]`, not in
    `[exited with code N]`. That is an end: records FAILURE with `reason` and
    `stopped_by: claude-code` instead of staying pending until the 6 h discard;
    gate-advance blocks stating the reason and suggests a `timeout` that fits;
    `[killed]` in the middle of the output does not count; an edit after the launch discards
    the result as in any other end.
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


class Session:
    """A fake session: project with pom.xml and CC's `tasks/` under a TMPDIR."""

    def __init__(self, base: Path, given_name: str, continued=False, tmp_of=None):
        # continued: the `tasks/` stays under the ORIGINAL sid (A) but the payloads
        # carry a NEW sid (B), as after a context overflow.
        # tmp_of: another Session whose TMPDIR this one shares (sweep of siblings).
        self.sid_original = str(uuid.uuid4())
        self.sid = str(uuid.uuid4()) if continued else self.sid_original
        self.tmp = tmp_of.tmp if tmp_of else base / f"tmp-{given_name}"
        self.tasks = self.tmp / "claude-501" / "-proj" / self.sid_original / "tasks"
        self.tasks.mkdir(parents=True)
        self.root = base / given_name
        self.root.mkdir()
        (self.root / "pom.xml").write_text("<project/>")
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.env = {**os.environ, "TMPDIR": str(self.tmp)}

    def _run(self, hook, payload):
        payload = {"cwd": str(self.root), "session_id": self.sid, **payload}
        return subprocess.run([sys.executable, str(hook)], input=json.dumps(payload),
                              capture_output=True, text=True, env=self.env)

    def raises(self, command, task_id, creates_output=True):
        if creates_output:
            (self.tasks / f"{task_id}.output").write_text("")
        return self._run(CAPTURE, {
            "tool_name": "Bash",
            "tool_input": {"command": command, "run_in_background": True},
            "tool_response": {"stdout": "", "stderr": "", "interrupted": False,
                              "backgroundTaskId": task_id},
        })

    def finishes(self, task_id, output, code):
        (self.tasks / f"{task_id}.output").write_text(
            f"{output}\n\n[exited with code {code}]\n")

    def kills(self, task_id, output):
        # The trailer CC writes when IT stops the task (background time ceiling
        # or low memory), measured on 2.1.301.
        (self.tasks / f"{task_id}.output").write_text(f"{output}\n\n[killed]\n")

    def other_bash(self, command="ls", stdout="pom.xml", **extra):
        return self._run(CAPTURE, {"tool_name": "Bash", "tool_input": {"command": command},
                                   "tool_response": {"stdout": stdout}, **extra})

    def commit(self, hook=GATE, **extra):
        return self._run(hook, {"tool_name": "Bash", "hook_event_name": "PreToolUse",
                                "tool_input": {"command": "git commit -m x"}, **extra})

    def ages(self, task_id, hours):
        p = self.tasks / f"{task_id}.cepa-build.json"
        entry = json.loads(p.read_text())
        entry["started_at"] = iso(-hours * 3600)
        p.write_text(json.dumps(entry))

    def pending(self, task_id):
        return (self.tasks / f"{task_id}.cepa-build.json").exists()

    def baseline(self):
        p = self.root / ".claude" / "last-build.json"
        return json.loads(p.read_text()) if p.exists() else None

    def write_baseline(self, state):
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

        # ── launch + build still running + green end ────────────────────────
        s = Session(base, "verde")
        res = s.raises("./mvnw verify", "bverde01")
        check("hook sai 0 no lançamento", res.returncode == 0, res.stderr)
        check("lançamento deixa o registro pendente", s.pending("bverde01"), res.stderr)
        check("lançamento não grava baseline", s.baseline() is None, str(s.baseline()))

        (s.tasks / "bverde01.output").write_text("[INFO] Building...\n" + MVN_OK)
        s.other_bash()
        check("sem a linha de fim, nada é gravado (Maven pode ter mais módulos)",
              s.baseline() is None and s.pending("bverde01"), str(s.baseline()))

        (s.tasks / "bverde01.output").write_text(
            "[exited with code 0]\n[INFO] Building module 2/5...\n")
        s.other_bash()
        check("linha de fim no meio da saída não conta como fim (só a última linha)",
              s.baseline() is None and s.pending("bverde01"), str(s.baseline()))

        s.finishes("bverde01", MVN_OK, 0)
        s.other_bash()
        b = s.baseline() or {}
        check("build terminado grava SUCCESS na próxima chamada de Bash",
              b.get("status") == "SUCCESS", str(b))
        check("baseline aponta a tarefa e o lançamento",
              b.get("background_task") == "bverde01" and b.get("started_at"), str(b))
        check("baseline grava o comando do build, não o `ls`",
              b.get("command") == "./mvnw verify", str(b))
        check("registro pendente some depois de colhido", not s.pending("bverde01"))

        # ── red end ─────────────────────────────────────────────────────────
        s = Session(base, "vermelho")
        s.raises("./mvnw verify", "bverm001")
        s.finishes("bverm001", MVN_FAIL, 1)
        s.other_bash()
        check("BUILD FAILURE grava FAILURE",
              (s.baseline() or {}).get("status") == "FAILURE", str(s.baseline()))

        # ── exit code beats the marker ──────────────────────────────────────
        s = Session(base, "exit")
        s.raises("./mvnw verify && ./scripts/smoke.sh", "bexit001")
        s.finishes("bexit001", MVN_OK + "\nsmoke: falhou", 3)
        s.other_bash()
        check("exit != 0 grava FAILURE mesmo com BUILD SUCCESS na saída",
              (s.baseline() or {}).get("status") == "FAILURE", str(s.baseline()))

        # ── test filter with no test executed ───────────────────────────────
        s = Session(base, "vazio")
        s.raises("./mvnw test -Dtest=NaoExisteTest", "bvazio01")
        s.finishes("bvazio01", "[INFO] BUILD SUCCESS", 0)
        s.other_bash()
        check("-Dtest sem teste executado grava EMPTY",
              (s.baseline() or {}).get("status") == "EMPTY", str(s.baseline()))

        # ── edit after the launch discards the result ───────────────────────
        s = Session(base, "editado")
        s.raises("./mvnw verify", "bedit001")
        stale = {"status": "STALE", "since": iso(+5), "after_edit_to": "src/A.java"}
        s.write_baseline(stale)
        s.finishes("bedit001", MVN_OK, 0)
        s.other_bash()
        check("edição depois do lançamento mantém STALE",
              (s.baseline() or {}).get("status") == "STALE", str(s.baseline()))
        check("registro do build descartado é removido", not s.pending("bedit001"))

        # ── STALE from BEFORE the launch is cleared by the build ────────────
        # ── and gate-advance harvests by itself before judging ──────────────
        s = Session(base, "gate")
        s.write_baseline({"status": "STALE", "since": iso(-3600), "after_edit_to": "src/A.java"})
        s.raises("./mvnw verify", "bgate001")
        s.finishes("bgate001", MVN_OK, 0)
        res = s.commit()
        check("gate-advance libera o commit com o build de fundo terminado",
              res.returncode == 0, res.stderr[-400:])
        check("gate-advance gravou o SUCCESS colhido",
              (s.baseline() or {}).get("status") == "SUCCESS", str(s.baseline()))

        s = Session(base, "gate-rodando")
        s.write_baseline({"status": "STALE", "since": iso(-3600), "after_edit_to": "src/A.java"})
        s.raises("./mvnw verify", "bgate002")
        res = s.commit()
        check("gate-advance continua barrando enquanto o build roda",
              res.returncode == 2, f"rc={res.returncode}")

        # ── background that is not a build ──────────────────────────────────
        s = Session(base, "nao-build")
        s.raises("python3 -m http.server", "bserv001")
        check("comando que não é build não deixa registro", not s.pending("bserv001"))

        # ── cases requested by the proof-reviewer (2026-10-02) ──────────────
        s = Session(base, "mais-novo")
        s.raises("./mvnw verify", "bnovo001")
        s.write_baseline({"status": "SUCCESS", "at": iso(+5), "command": "./mvnw -pl x verify"})
        s.finishes("bnovo001", MVN_FAIL, 1)
        s.other_bash()
        b = s.baseline() or {}
        check("build mais novo em primeiro plano não é sobrescrito pelo antigo",
              b.get("status") == "SUCCESS" and b.get("command") == "./mvnw -pl x verify", str(b))

        s = Session(base, "marcador-falha")
        s.raises("./mvnw verify", "bmfal001")
        s.finishes("bmfal001", MVN_FAIL, 0)
        s.other_bash()
        check("exit 0 com BUILD FAILURE na saída grava FAILURE",
              (s.baseline() or {}).get("status") == "FAILURE", str(s.baseline()))

        s = Session(base, "exit-negativo")
        s.raises("./mvnw verify", "bneg0001")
        s.finishes("bneg0001", "[INFO] Building...", -9)
        s.other_bash()
        check("exit negativo (processo morto por sinal) grava FAILURE",
              (s.baseline() or {}).get("status") == "FAILURE", str(s.baseline()))

        s = Session(base, "abandonado")
        s.raises("./mvnw verify", "babnd001")
        s.ages("babnd001", 7)
        s.other_bash()
        check("pendente sem fim há mais de 6 h é removido", not s.pending("babnd001"))
        check("pendente abandonado não grava baseline", s.baseline() is None, str(s.baseline()))

        s = Session(base, "recente")
        s.raises("./mvnw verify", "brcnt001")
        s.ages("brcnt001", 5)
        s.other_bash()
        check("pendente sem fim há menos de 6 h continua", s.pending("brcnt001"))

        s = Session(base, "sem-output")
        res = s.raises("./mvnw verify", "bsout001", creates_output=False)
        check("sem o .output do CC, não deixa registro", not s.pending("bsout001"))
        check("sem o .output do CC, avisa que não vai gravar",
              "will NOT be recorded" in res.stderr, res.stderr)

        s = Session(base, "pendente-corrompido")
        (s.tasks / "bcorr001.cepa-build.json").write_text("{nao é json")
        res = s.other_bash("./mvnw verify", MVN_OK)
        check("pendente corrompido não derruba o hook",
              res.returncode == 0 and (s.baseline() or {}).get("status") == "SUCCESS",
              f"rc={res.returncode} {res.stderr[-300:]}")
        res = s.other_bash("./mvnw verify", MVN_OK, session_id=12345)
        check("session_id que não é texto não derruba o hook", res.returncode == 0,
              res.stderr[-300:])

        # The gate loads the capture by path. If it does not load, the gate
        # keeps judging the baseline instead of dying and releasing the commit.
        hooks = base / "hooks-quebrados"
        shutil.copytree(GATE.parent, hooks)
        (hooks / "capture-build-result.py").write_text("raise RuntimeError('quebrado')\n")
        s = Session(base, "capture-quebrado")
        s.write_baseline({"status": "STALE", "since": iso(-60), "after_edit_to": "src/A.java"})
        res = s.commit(hook=hooks / "gate-advance.py")
        check("capture que não carrega não derruba o gate: ele ainda barra o STALE",
              res.returncode == 2 and "harvest failed" in res.stderr,
              f"rc={res.returncode} {res.stderr[-300:]}")

        s = Session(base, "root-install")
        s.raises("./mvnw install", "binst001")
        s.finishes("binst001", MVN_OK, 0)
        s.other_bash()
        check("install da raiz em segundo plano grava last-root-install.json",
              (s.root / ".claude" / "last-root-install.json").exists())

        # The record keeps build_dir and marker_root separate: on a `cd` into a
        # submodule they diverge, and swapping one for the other at harvest marked
        # the root as installed when only the submodule was.
        s = Session(base, "install-submodulo")
        (s.root / "domain").mkdir()
        s.raises("cd domain && ./mvnw install", "bsubm001")
        s.finishes("bsubm001", MVN_OK, 0)
        s.other_bash()
        check("install de submódulo em segundo plano grava o SUCCESS na raiz da sessão",
              (s.baseline() or {}).get("status") == "SUCCESS", str(s.baseline()))
        check("install de submódulo em segundo plano NÃO marca a raiz como instalada",
              not (s.root / ".claude" / "last-root-install.json").exists())

        # ── session continued after context overflow (fb-20261005-1) ────────
        s = Session(base, "continuada", continued=True)
        res = s.raises("./mvnw verify", "bcont001")
        check("continuada: pendente fica ao lado do .output da sessão original",
              s.pending("bcont001"), res.stderr)
        check("continuada: avisa que achou na pasta de outra sessão",
              s.sid_original in res.stderr and "context overflow" in res.stderr, res.stderr)
        check("continuada: lançamento não grava baseline", s.baseline() is None, str(s.baseline()))
        s.finishes("bcont001", MVN_OK, 0)
        s.other_bash()
        b = s.baseline() or {}
        check("continuada: build terminado grava SUCCESS sob o sid novo",
              b.get("status") == "SUCCESS" and b.get("background_task") == "bcont001", str(b))

        s = Session(base, "continuada-gate", continued=True)
        s.write_baseline({"status": "STALE", "since": iso(-3600), "after_edit_to": "src/A.java"})
        s.raises("./mvnw verify", "bcgt0001")
        s.finishes("bcgt0001", MVN_OK, 0)
        res = s.commit()
        check("continuada: gate-advance libera o commit com o build terminado",
              res.returncode == 0, res.stderr[-400:])
        check("continuada: gate-advance gravou o SUCCESS colhido",
              (s.baseline() or {}).get("status") == "SUCCESS", str(s.baseline()))

        s = Session(base, "lancado-antes")
        s.raises("./mvnw verify", "bpre0001")
        s.finishes("bpre0001", MVN_OK, 0)
        s.other_bash(session_id=str(uuid.uuid4()))
        b = s.baseline() or {}
        check("build lançado sob A antes do estouro é colhido por payload com sid B",
              b.get("status") == "SUCCESS" and b.get("background_task") == "bpre0001", str(b))

        other = Session(base, "outra-arvore")
        other.raises("./mvnw verify", "boutra01")
        other.finishes("boutra01", MVN_OK, 0)
        s = Session(base, "esta-arvore", tmp_of=other)
        res = s.other_bash(session_id=str(uuid.uuid4()))
        check("pendente de OUTRA árvore não é colhido (fica o registro)",
              other.pending("boutra01"), res.stderr)
        check("pendente de OUTRA árvore não grava o baseline dela",
              other.baseline() is None, str(other.baseline()))

        # ── build stopped by CC: `[killed]` at the end of the .output ───────
        s = Session(base, "killed")
        s.raises("./mvnw verify", "bkill001")
        s.kills("bkill001", "[INFO] Building module 3/5...")
        res = s.other_bash()
        b = s.baseline() or {}
        check("[killed] no fim grava FAILURE (não fica pendente até o descarte de 6 h)",
              b.get("status") == "FAILURE" and not s.pending("bkill001"), str(b))
        check("[killed] grava o motivo e quem parou",
              "stopped by Claude Code" in b.get("reason", "")
              and b.get("stopped_by") == "claude-code", str(b))
        check("[killed] aponta a tarefa e o comando",
              b.get("background_task") == "bkill001" and b.get("command") == "./mvnw verify",
              str(b))
        check("[killed] avisa no stderr que gravou FAILURE com o motivo",
              "recorded: FAILURE" in res.stderr and "[killed]" in res.stderr, res.stderr)
        check("[killed] não é EMPTY: a mensagem 'EMPTY, not green' não sai",
              "EMPTY, not green" not in res.stderr, res.stderr)

        s = Session(base, "killed-gate")
        s.write_baseline({"status": "STALE", "since": iso(-3600), "after_edit_to": "src/A.java"})
        s.raises("./mvnw verify", "bkill002")
        s.kills("bkill002", "[INFO] Building...")
        res = s.commit()
        check("gate-advance barra o commit do build parado pelo CC",
              res.returncode == 2, f"rc={res.returncode}")
        # The capture prints the same reason when harvesting; what is charged here is the
        # gate's blocking LINE (proof-reviewer 2026-10-15: without this, deleting
        # the reason addition in gate-advance left no test red).
        block_line = next((l for l in res.stderr.splitlines()
                               if "build is FAILURE" in l), "")
        check("gate-advance diz POR QUE barra, na própria linha do bloqueio",
              "stopped by Claude Code" in block_line, res.stderr[-600:])
        check("gate-advance sugere um timeout que caiba, não 'fix the failing tests'",
              "timeout" in res.stderr and "Fix the failing tests" not in res.stderr,
              res.stderr[-600:])

        s = Session(base, "failure-comum-com-reason")
        s.write_baseline({"status": "FAILURE", "at": iso(-60), "command": "./mvnw verify",
                          "reason": "surefire: 2 tests failed"})
        res = s.commit()
        block_line = next((l for l in res.stderr.splitlines()
                               if "build is FAILURE" in l), "")
        check("FAILURE comum com reason: o motivo entra na linha do bloqueio",
              res.returncode == 2 and "surefire: 2 tests failed" in block_line,
              res.stderr[-600:])
        check("FAILURE comum (sem stopped_by) mantém a sugestão 'Fix the failing tests'",
              "Fix the failing tests" in res.stderr and "BASH_MAX_TIMEOUT_MS" not in res.stderr,
              res.stderr[-600:])

        s = Session(base, "killed-no-meio")
        s.raises("./mvnw verify", "bkill003")
        (s.tasks / "bkill003.output").write_text("[killed]\n[INFO] Building module 2/5...\n")
        s.other_bash()
        check("[killed] no meio da saída não conta como fim (só a última linha)",
              s.baseline() is None and s.pending("bkill003"), str(s.baseline()))

        s = Session(base, "killed-colado")
        s.raises("./mvnw verify", "bkill005")
        (s.tasks / "bkill005.output").write_text("[INFO] Building...\nfoo[killed]\n")
        s.other_bash()
        check("`foo[killed]` colado em outro texto não é o trailer do CC (segue pendente)",
              s.baseline() is None and s.pending("bkill005"), str(s.baseline()))

        s = Session(base, "killed-so")
        s.raises("./mvnw verify", "bkill006")
        (s.tasks / "bkill006.output").write_text("[killed]\n")
        s.other_bash()
        check("arquivo só com `[killed]` (primeira linha) grava FAILURE",
              (s.baseline() or {}).get("status") == "FAILURE" and not s.pending("bkill006"),
              str(s.baseline()))

        s = Session(base, "killed-editado")
        s.raises("./mvnw verify", "bkill004")
        s.write_baseline({"status": "STALE", "since": iso(+5), "after_edit_to": "src/A.java"})
        s.kills("bkill004", "[INFO] Building...")
        s.other_bash()
        check("[killed] depois de uma edição mantém STALE (resultado descartado)",
              (s.baseline() or {}).get("status") == "STALE" and not s.pending("bkill004"),
              str(s.baseline()))

        s = Session(base, "continuada-sem-output", continued=True)
        res = s.raises("./mvnw verify", "bcso0001", creates_output=False)
        check("continuada sem .output em lugar nenhum: avisa que não vai gravar",
              "will NOT be recorded" in res.stderr, res.stderr)
        check("continuada sem .output em lugar nenhum: sem registro", not s.pending("bcso0001"))

    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\ntodos ok")


if __name__ == "__main__":
    main()
