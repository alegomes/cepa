#!/usr/bin/env python3
"""CS-4 (cepa-espiral-c1): `/common:wrap-up` records the next step from the handoff.

Step L7 of the wrap-up calls `common/hooks/session-next.py` with the handoff and the
session_id. It reads the NOTE zone, finds the line `**Próximo:** repo=… mode=…
comando=…` and writes `<root>/.claude/sessions/<id>.next.json` with those three
fields and the brief equal to the paragraph `## Próximo passo`.

Contracts guarded here:
  - with the line: the file has repo, mode, command (with arguments) and the brief
    verbatim, without the `**Próximo:**` line inside it;
  - without the line: nothing is written, exit 0, and the output says it did not record;
  - the line outside the NOTE zone (in AUTO) does not count;
  - an unusable line (nonexistent repo, unknown mode, reform, missing field,
    empty section): nothing is written, exit 2, and the output states the reason;
  - with `**Intenção:**`, `**Meta:**` and `**Plano:** a | b`: the file gains
    `intencao` and the three lines do not enter the brief; only part of them: nothing
    written, exit 2; none: a file without `intencao`;
  - the written file is accepted by the launcher chaining (session-chain.py,
    CS-3): cepa is reopened in the repo, with --mode and the brief, and with the intent
    flags only when it exists;
  - wrap-up.md orders L7 to call the script and carry the output to the report, and
    handoff.md documents the line.

No third-party deps — run with `python3 tests/test_wrapup_next_step.py`.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

for _k in ("CEPA_ENCADEAR", "CEPA_LAUNCH_ID"):
    os.environ.pop(_k, None)

REPO = Path(__file__).resolve().parent.parent
NEXT = REPO / "common" / "hooks" / "session-next.py"
CHAIN = REPO / "common" / "hooks" / "session-chain.py"
WRAPUP = REPO / "common" / "commands" / "wrap-up.md"
HANDOFF_CMD = REPO / "common" / "commands" / "handoff.md"

BRIEF = ('Abrir o `/common:epic contratos-e-regras` no wego-product e grelhar o dono\n'
         'até cada ciclo ter roteiro com efeito em tela e em backend.')

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def handoff(line, brief=BRIEF, auto_extra=""):
    section = f"## Próximo passo\n{brief}\n" if brief is not None else ""
    line_ = f"{line}\n\n" if line else ""
    return ("---\nbranch: session/x\n---\n\n<!-- HANDOFF:AUTO -->\n## Onde paramos\n"
            f"{auto_extra}\n<!-- /HANDOFF:AUTO -->\n\n<!-- HANDOFF:NOTE -->\n"
            "## Onde estamos\nCS-3 pronto.\n\n"
            f"{section}{line_}"
            "## ⚠ Cuidados / pendências\n- nada\n<!-- /HANDOFF:NOTE -->\n")


class World:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name).resolve()
        self.root = t / "root"
        self.root.mkdir()
        self.target = t / "wego-product"
        self.target.mkdir()
        self.hf = t / "handoff.md"
        self.sid = "sess-abc"
        self.nxt = self.root / ".claude" / "sessions" / f"{self.sid}.next.json"
        return self

    def __exit__(self, *a):
        self.tmp.cleanup()

    def run(self, text):
        self.hf.write_text(text, encoding="utf-8")
        p = subprocess.run([sys.executable, str(NEXT), "--handoff", str(self.hf),
                            "--session-id", self.sid, "--root", str(self.root)],
                           capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr


def line(w, repo=None, mode="discovery", command="/common:epic contratos-e-regras", key="mode"):
    return f"**Próximo:** repo={repo or w.target} {key}={mode} comando={command}"


print("com a linha: grava os três campos e o brief")
with World() as w:
    rc, out = w.run(handoff(line(w)))
    check("exit 0", rc == 0, out)
    check("arquivo existe", w.nxt.exists(), out)
    d = json.loads(w.nxt.read_text()) if w.nxt.exists() else {}
    check("repo", d.get("repo") == str(w.target), d)
    check("mode", d.get("mode") == "discovery" and "modo" not in d, d)
    check("comando com argumento", d.get("comando") == "/common:epic contratos-e-regras", d)
    check("brief = parágrafo Próximo passo", d.get("brief") == BRIEF, repr(d.get("brief")))
    check("saída diz que gravou", "gravado" in out and "não gravado" not in out, out)
    check("sem as linhas da intenção, nada de `intent`", "intent" not in d and "intencao" not in d, d)
    check("saída diz que vai sem intenção", "sem intenção" in out, out)

PORQUE = ('o dono abriu a spec e não reconheceu o assunto; a pergunta original '
          'era "como o handoff grava o porquê?"')

print("a linha `porque:` do Próximo passo vai no brief da próxima sessão (fb-20261104-2)")
with World() as w:
    rc, out = w.run(handoff(line(w), brief=f"{BRIEF}\nporque: {PORQUE}"))
    check("exit 0", rc == 0, out)
    d = json.loads(w.nxt.read_text()) if w.nxt.exists() else {}
    check("brief traz a frase do porque literalmente", PORQUE in (d.get("brief") or ""),
          repr(d.get("brief")))
    check("brief traz a linha `porque:` e o parágrafo",
          f"porque: {PORQUE}" in d.get("brief", "") and BRIEF in d.get("brief", ""),
          repr(d.get("brief")))
    check("brief sem a linha **Próximo:**", "**Próximo:**" not in d.get("brief", ""),
          repr(d.get("brief")))

INTENT_LINES = ("**Intenção:** Grelhar o dono no epic contratos-e-regras\n"
                   "**Meta:** cada ciclo com roteiro em tela e em backend\n"
                   "**Plano:** abrir o epic | grelhar ciclo a ciclo\n")

print("com as três linhas: grava a intenção e tira as linhas do brief")
with World() as w:
    rc, out = w.run(handoff(line(w), brief=f"{BRIEF}\n\n{INTENT_LINES}"))
    check("exit 0", rc == 0, out)
    d = json.loads(w.nxt.read_text()) if w.nxt.exists() else {}
    check("intent", d.get("intent") == {
        "purpose": "Grelhar o dono no epic contratos-e-regras",
        "by_when": "cada ciclo com roteiro em tela e em backend",
        "plan": ["abrir o epic", "grelhar ciclo a ciclo"]}, d)
    check("brief sem as linhas da intenção", d.get("brief") == BRIEF, repr(d.get("brief")))
    check("saída cita a intenção", "Grelhar o dono" in out, out)

print("passo vazio entre barras é descartado")
with World() as w:
    rc, out = w.run(handoff(line(w), brief=f"{BRIEF}\n\n**Intenção:** p\n**Meta:** m\n**Plano:** a | | b\n"))
    d = json.loads(w.nxt.read_text()) if w.nxt.exists() else {}
    check("plano sem o passo vazio", (d.get("intent") or {}).get("plan") == ["a", "b"], d)

print("as três linhas sem texto contam como ausentes")
with World() as w:
    rc, out = w.run(handoff(line(w), brief=f"{BRIEF}\n\n**Intenção:**\n**Meta:**   \n**Plano:**\n"))
    check("exit 0", rc == 0, f"rc={rc} {out}")
    d = json.loads(w.nxt.read_text()) if w.nxt.exists() else {}
    check("arquivo sem `intent`", w.nxt.exists() and "intent" not in d, d)

print("intenção pela metade: não escreve e diz o que falta")
with World() as w:
    rc, out = w.run(handoff(line(w), brief=f"{BRIEF}\n\n**Intenção:** algo\n**Plano:** a\n"))
    check("exit 2", rc == 2, f"rc={rc} {out}")
    check("nada escrito", not w.nxt.exists())
    check("motivo cita a Meta", "não gravado" in out and "Meta" in out, out)

print("a linha do critério, verbatim (repo real do dono)")
literal = "/Users/alegomes/coding/wego/wego-product"
if os.path.isdir(literal):
    with World() as w:
        rc, out = w.run(handoff(f"**Próximo:** repo={literal} mode=discovery "
                                "comando=/common:epic contratos-e-regras"))
        d = json.loads(w.nxt.read_text()) if w.nxt.exists() else {}
        check("literal: campos", (d.get("repo"), d.get("mode"), d.get("comando"))
              == (literal, "discovery", "/common:epic contratos-e-regras"), out)
else:
    print("  skip (repo do critério não existe nesta máquina)")

print("linha dentro da seção Próximo passo não vaza para o brief")
with World() as w:
    rc, out = w.run(handoff(None, brief=f"{BRIEF}\n\n{line(w)}"))
    d = json.loads(w.nxt.read_text()) if w.nxt.exists() else {}
    check("brief sem a linha", d.get("brief") == BRIEF, repr(d.get("brief")))
    check("campos lidos", d.get("mode") == "discovery", out)

print("ordem das chaves trocada")
with World() as w:
    rc, out = w.run(handoff(f"**Próximo:** comando=/common:spec x y mode=design repo={w.target}"))
    d = json.loads(w.nxt.read_text()) if w.nxt.exists() else {}
    check("comando até a próxima chave", d.get("comando") == "/common:spec x y", d)
    check("mode", d.get("mode") == "design", d)
    check("repo", d.get("repo") == str(w.target), d)

print("sem a linha: não escreve e diz")
with World() as w:
    rc, out = w.run(handoff(None))
    check("exit 0", rc == 0, out)
    check("nada escrito", not w.nxt.exists())
    check("saída diz que não gravou e por quê", "não gravado" in out and "Próximo:" in out, out)

print("linha só no AUTO não conta")
with World() as w:
    rc, out = w.run(handoff(None, auto_extra=line(w)))
    check("nada escrito", not w.nxt.exists(), out)
    check("exit 0", rc == 0, out)

cases = [
    ("repo inexistente", lambda w: line(w, repo=str(w.target) + "-nao"), BRIEF, "não existe"),
    ("modo desconhecido", lambda w: line(w, mode="festa"), BRIEF, "festa"),
    ("modo refactor", lambda w: line(w, mode="refactor"), BRIEF, "budget"),
    ("sem comando", lambda w: f"**Próximo:** repo={w.target} mode=discovery", BRIEF, "comando"),
    ("sem modo", lambda w: f"**Próximo:** repo={w.target} comando=/x", BRIEF, "mode"),
    ("sem repo", lambda w: "**Próximo:** mode=discovery comando=/x", BRIEF, "repo"),
    ("seção vazia", lambda w: line(w), "   ", "vazia"),
    ("sem seção", lambda w: line(w), None, "vazia"),
]
for name, lf, brief, word in cases:
    print(f"inutilizável: {name}")
    with World() as w:
        rc, out = w.run(handoff(lf(w), brief=brief))
        check(f"{name}: exit 2", rc == 2, f"rc={rc} {out}")
        check(f"{name}: nada escrito", not w.nxt.exists())
        check(f"{name}: motivo na saída", "não gravado" in out and word in out, out)

print("o arquivo escrito é aceito pelo encadeamento do launcher (CS-3)")
with World() as w:
    subprocess.run(["git", "init", "-q", "."], cwd=w.root, check=True)
    rc, out = w.run(handoff(line(w)))
    sdir = w.root / ".claude" / "sessions"
    (sdir / "launch-1.launch").write_text(w.sid + "\n")
    log = Path(w.tmp.name) / "cepa.log"
    fake = Path(w.tmp.name) / "fakecepa"
    fake.write_text("#!/usr/bin/env python3\nimport json, os, sys\n"
                    f"open({str(log)!r}, 'w').write(json.dumps({{'args': sys.argv[1:], 'cwd': os.getcwd()}}))\n")
    fake.chmod(0o755)
    p = subprocess.run([sys.executable, str(CHAIN), "launch-1", str(fake), "0"],
                       cwd=w.root, capture_output=True, text=True)
    got = json.loads(log.read_text()) if log.exists() else {}
    check("cepa reaberto", bool(got), p.stderr)
    check("cwd = repo", got.get("cwd") == str(w.target), got)
    check("--mode discovery + brief, sem intenção", got.get("args") == ["--mode", "discovery", BRIEF], got)
    check("arquivo consumido", not w.nxt.exists())

print("com a intenção, o encadeamento passa as três flags ao cepa")
with World() as w:
    subprocess.run(["git", "init", "-q", "."], cwd=w.root, check=True)
    rc, out = w.run(handoff(line(w), brief=f"{BRIEF}\n\n{INTENT_LINES}"))
    sdir = w.root / ".claude" / "sessions"
    (sdir / "launch-1.launch").write_text(w.sid + "\n")
    log = Path(w.tmp.name) / "cepa.log"
    fake = Path(w.tmp.name) / "fakecepa"
    fake.write_text("#!/usr/bin/env python3\nimport json, os, sys\n"
                    f"open({str(log)!r}, 'w').write(json.dumps({{'args': sys.argv[1:], 'cwd': os.getcwd()}}))\n")
    fake.chmod(0o755)
    p = subprocess.run([sys.executable, str(CHAIN), "launch-1", str(fake), "0"],
                       cwd=w.root, capture_output=True, text=True)
    got = json.loads(log.read_text()) if log.exists() else {}
    check("flags da intenção + brief", got.get("args") == [
        "--mode", "discovery",
        "--purpose", "Grelhar o dono no epic contratos-e-regras",
        "--by-when", "cada ciclo com roteiro em tela e em backend",
        "--plan", "abrir o epic\ngrelhar ciclo a ciclo", BRIEF], got)

print("o wrap-up e o handoff conhecem a linha")
wu = WRAPUP.read_text(encoding="utf-8")
check("wrap-up L7 chama session-next.py", "session-next.py" in wu and "--session-id" in wu)
check("wrap-up leva a saída ao relatório", "Próximo passo" in wu.split("### L8")[1].split("##")[0]
      if "### L8" in wu else False)
check("handoff.md documenta a linha", "**Próximo:** repo=" in HANDOFF_CMD.read_text(encoding="utf-8"))
check("handoff.md documenta a intenção da sessão seguinte",
      all(r in HANDOFF_CMD.read_text(encoding="utf-8") for r in ("**Intenção:**", "**Meta:**", "**Plano:**")))

print("nomes antigos: `modo=descoberta` na linha do handoff ainda é aceito")
with World() as w:
    rc, out = w.run(handoff(line(w, mode="descoberta", key="modo")))
    d = json.loads(w.nxt.read_text()) if w.nxt.exists() else {}
    check("antigo: exit 0 e arquivo escrito", rc == 0 and w.nxt.exists(), out)
    check("antigo: o arquivo sai com `mode: discovery` (só nomes novos)",
          d.get("mode") == "discovery" and "modo" not in d, d)
with World() as w:
    rc, out = w.run(handoff(line(w, mode="reforma", key="modo")))
    check("antigo: modo=reforma recusa como refactor (exit 2, cita --budget)",
          rc == 2 and "refactor" in out and "budget" in out, out)

print("nomes antigos: um .next.json antigo (modo/intencao em pt-BR) ainda encadeia")
with World() as w:
    subprocess.run(["git", "init", "-q", "."], cwd=w.root, check=True)
    sdir = w.root / ".claude" / "sessions"
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "launch-1.launch").write_text(w.sid + "\n")
    (sdir / f"{w.sid}.next.json").write_text(json.dumps({
        "repo": str(w.target), "modo": "descoberta", "comando": "/common:epic x", "brief": BRIEF,
        "intencao": {"proposito": "p antigo", "para_quando": "q antigo", "plano": ["a", "b"]}}))
    log = Path(w.tmp.name) / "cepa.log"
    fake = Path(w.tmp.name) / "fakecepa"
    fake.write_text("#!/usr/bin/env python3\nimport json, os, sys\n"
                    f"open({str(log)!r}, 'w').write(json.dumps({{'args': sys.argv[1:], 'cwd': os.getcwd()}}))\n")
    fake.chmod(0o755)
    p = subprocess.run([sys.executable, str(CHAIN), "launch-1", str(fake), "0"],
                       cwd=w.root, capture_output=True, text=True)
    got = json.loads(log.read_text()) if log.exists() else {}
    check("antigo: o cepa recebe --mode discovery e as flags novas", got.get("args") == [
        "--mode", "discovery", "--purpose", "p antigo", "--by-when", "q antigo",
        "--plan", "a\nb", BRIEF], (got, p.stderr))

print()
if failures:
    print(f"{len(failures)} FAIL")
    sys.exit(1)
print("todos ok")
