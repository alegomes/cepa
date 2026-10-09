#!/usr/bin/env python3
"""CS-4 (cepa-espiral-c1): o `/common:wrap-up` grava o próximo passo a partir do handoff.

O passo L7 do wrap-up chama `common/hooks/session-next.py` com o handoff e o
session_id. Ele lê a zona NOTE, acha a linha `**Próximo:** repo=… modo=…
comando=…` e escreve `<raiz>/.claude/sessions/<id>.next.json` com esses três
campos e o brief igual ao parágrafo `## Próximo passo`.

Contratos guardados aqui:
  - com a linha: o arquivo tem repo, modo, comando (com argumentos) e o brief
    verbatim, sem a linha `**Próximo:**` dentro dele;
  - sem a linha: nada é escrito, exit 0, e a saída diz que não gravou;
  - a linha fora da zona NOTE (no AUTO) não conta;
  - linha inutilizável (repo inexistente, modo desconhecido, reforma, campo
    faltando, seção vazia): nada é escrito, exit 2, e a saída diz o motivo;
  - o arquivo escrito é aceito pelo encadeamento do launcher (session-chain.py,
    CS-3): o cepa é reaberto em repo, com --modo e o brief;
  - o wrap-up.md manda o L7 chamar o script e levar a saída ao relatório, e o
    handoff.md documenta a linha.

Sem deps de terceiros — rode com `python3 tests/test_wrapup_proximo_passo.py`.
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


def handoff(linha, brief=BRIEF, auto_extra=""):
    secao = f"## Próximo passo\n{brief}\n" if brief is not None else ""
    lin = f"{linha}\n\n" if linha else ""
    return ("---\nbranch: session/x\n---\n\n<!-- HANDOFF:AUTO -->\n## Onde paramos\n"
            f"{auto_extra}\n<!-- /HANDOFF:AUTO -->\n\n<!-- HANDOFF:NOTE -->\n"
            "## Onde estamos\nCS-3 pronto.\n\n"
            f"{secao}{lin}"
            "## ⚠ Cuidados / pendências\n- nada\n<!-- /HANDOFF:NOTE -->\n")


class World:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name).resolve()
        self.root = t / "root"
        self.root.mkdir()
        self.alvo = t / "wego-product"
        self.alvo.mkdir()
        self.hf = t / "handoff.md"
        self.sid = "sess-abc"
        self.nxt = self.root / ".claude" / "sessions" / f"{self.sid}.next.json"
        return self

    def __exit__(self, *a):
        self.tmp.cleanup()

    def run(self, texto):
        self.hf.write_text(texto, encoding="utf-8")
        p = subprocess.run([sys.executable, str(NEXT), "--handoff", str(self.hf),
                            "--session-id", self.sid, "--root", str(self.root)],
                           capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr


def linha(w, repo=None, modo="descoberta", comando="/common:epic contratos-e-regras"):
    return f"**Próximo:** repo={repo or w.alvo} modo={modo} comando={comando}"


print("com a linha: grava os três campos e o brief")
with World() as w:
    rc, out = w.run(handoff(linha(w)))
    check("exit 0", rc == 0, out)
    check("arquivo existe", w.nxt.exists(), out)
    d = json.loads(w.nxt.read_text()) if w.nxt.exists() else {}
    check("repo", d.get("repo") == str(w.alvo), d)
    check("modo", d.get("modo") == "descoberta", d)
    check("comando com argumento", d.get("comando") == "/common:epic contratos-e-regras", d)
    check("brief = parágrafo Próximo passo", d.get("brief") == BRIEF, repr(d.get("brief")))
    check("saída diz que gravou", "gravado" in out and "não gravado" not in out, out)

print("a linha do critério, verbatim (repo real do dono)")
literal = "/Users/alegomes/coding/wego/wego-product"
if os.path.isdir(literal):
    with World() as w:
        rc, out = w.run(handoff(f"**Próximo:** repo={literal} modo=descoberta "
                                "comando=/common:epic contratos-e-regras"))
        d = json.loads(w.nxt.read_text()) if w.nxt.exists() else {}
        check("literal: campos", (d.get("repo"), d.get("modo"), d.get("comando"))
              == (literal, "descoberta", "/common:epic contratos-e-regras"), out)
else:
    print("  skip (repo do critério não existe nesta máquina)")

print("linha dentro da seção Próximo passo não vaza para o brief")
with World() as w:
    rc, out = w.run(handoff(None, brief=f"{BRIEF}\n\n{linha(w)}"))
    d = json.loads(w.nxt.read_text()) if w.nxt.exists() else {}
    check("brief sem a linha", d.get("brief") == BRIEF, repr(d.get("brief")))
    check("campos lidos", d.get("modo") == "descoberta", out)

print("ordem das chaves trocada")
with World() as w:
    rc, out = w.run(handoff(f"**Próximo:** comando=/common:spec x y modo=design repo={w.alvo}"))
    d = json.loads(w.nxt.read_text()) if w.nxt.exists() else {}
    check("comando até a próxima chave", d.get("comando") == "/common:spec x y", d)
    check("modo", d.get("modo") == "design", d)
    check("repo", d.get("repo") == str(w.alvo), d)

print("sem a linha: não escreve e diz")
with World() as w:
    rc, out = w.run(handoff(None))
    check("exit 0", rc == 0, out)
    check("nada escrito", not w.nxt.exists())
    check("saída diz que não gravou e por quê", "não gravado" in out and "Próximo:" in out, out)

print("linha só no AUTO não conta")
with World() as w:
    rc, out = w.run(handoff(None, auto_extra=linha(w)))
    check("nada escrito", not w.nxt.exists(), out)
    check("exit 0", rc == 0, out)

casos = [
    ("repo inexistente", lambda w: linha(w, repo=str(w.alvo) + "-nao"), BRIEF, "não existe"),
    ("modo desconhecido", lambda w: linha(w, modo="festa"), BRIEF, "festa"),
    ("modo reforma", lambda w: linha(w, modo="reforma"), BRIEF, "orcamento"),
    ("sem comando", lambda w: f"**Próximo:** repo={w.alvo} modo=descoberta", BRIEF, "comando"),
    ("sem modo", lambda w: f"**Próximo:** repo={w.alvo} comando=/x", BRIEF, "modo"),
    ("sem repo", lambda w: "**Próximo:** modo=descoberta comando=/x", BRIEF, "repo"),
    ("seção vazia", lambda w: linha(w), "   ", "vazia"),
    ("sem seção", lambda w: linha(w), None, "vazia"),
]
for nome, lf, brief, palavra in casos:
    print(f"inutilizável: {nome}")
    with World() as w:
        rc, out = w.run(handoff(lf(w), brief=brief))
        check(f"{nome}: exit 2", rc == 2, f"rc={rc} {out}")
        check(f"{nome}: nada escrito", not w.nxt.exists())
        check(f"{nome}: motivo na saída", "não gravado" in out and palavra in out, out)

print("o arquivo escrito é aceito pelo encadeamento do launcher (CS-3)")
with World() as w:
    subprocess.run(["git", "init", "-q", "."], cwd=w.root, check=True)
    rc, out = w.run(handoff(linha(w)))
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
    check("cwd = repo", got.get("cwd") == str(w.alvo), got)
    check("--modo descoberta + brief", got.get("args") == ["--modo", "descoberta", BRIEF], got)
    check("arquivo consumido", not w.nxt.exists())

print("o wrap-up e o handoff conhecem a linha")
wu = WRAPUP.read_text(encoding="utf-8")
check("wrap-up L7 chama session-next.py", "session-next.py" in wu and "--session-id" in wu)
check("wrap-up leva a saída ao relatório", "Próximo passo" in wu.split("### L8")[1].split("##")[0]
      if "### L8" in wu else False)
check("handoff.md documenta a linha", "**Próximo:** repo=" in HANDOFF_CMD.read_text(encoding="utf-8"))

print()
if failures:
    print(f"{len(failures)} FAIL")
    sys.exit(1)
print("todos ok")
