#!/usr/bin/env python3
"""`cepa-intent remind` / `reminders` and the listing in `state` (item
`whereami-recapitula-decisoes-do-dono`, feedback fb-20261104-3).

Run with `python3 tests/test_cepa_intent_reminders.py`. Exits non-zero on failure.

Why it exists: on 2026-11-04 the agent cited an owner reminder from 2026-10-31
as if the owner had it in mind ("eu disse? nem lembrava"). The reminders file
(`.claude/reminders`, in the MAIN clone, written only by `cepa-intent remind`)
stores each reminder with its date and a context sentence, and `state` /
`/common:whereami` / the session hook list it back. The parse/render round-trip
of the `reminders` list of maps is tested here too (not in test_cepa_intent.py).
"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from _isolated_telemetry import isolate
isolate()

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "common" / "bin" / "cepa-intent"
HOOK = REPO / "common" / "hooks" / "session-mode.py"
sys.path.insert(0, str(REPO / "common" / "hooks"))
import _modes as M  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


TMP = Path(tempfile.mkdtemp(prefix="cepa-reminders-test-"))
TEL = TMP / "tel"
ENV = {k: v for k, v in os.environ.items() if k != "CEPA_UNTIL_RUN"}
ENV.update({"CEPA_TELEMETRY_DIR": str(TEL), "CLAUDE_CODE_SESSION_ID": "sess-1234567890",
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def new_repo(name):
    r = TMP / name
    r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "init"],
                   cwd=r, check=True, env=ENV)
    return r


def cepa(cwd, *args, env=None):
    return subprocess.run([sys.executable, str(BIN), *args], cwd=cwd,
                          env={**ENV, **(env or {})}, capture_output=True, text=True)


TEXT = "revisitar o ADR 0014 e a extensão do ADR 0006, talvez marcar deprecated"
CTX = "fronteiras da spec de contratos: o dono duvidou se ainda valem os dois"

# --- refusals -------------------------------------------------------------
r = new_repo("a")
p = cepa(r, "remind", TEXT)
check("remind sem --context recusa (exit 2)", p.returncode == 2, p.stderr)
check("remind sem --context não cria arquivo", not (r / ".claude" / "reminders").exists())
check("recusa explica a frase de contexto", "frase de contexto" in p.stderr, p.stderr)
p = cepa(r, "remind", TEXT, "--context", "   ")
check("--context em branco recusa", p.returncode == 2
      and not (r / ".claude" / "reminders").exists(), p.stderr)
p = cepa(r, "remind", "  ", "--context", CTX)
check("texto vazio recusa", p.returncode == 2 and not (r / ".claude" / "reminders").exists())
p = cepa(r, "remind", TEXT, "--context", CTX, "--at", "31/10/2026")
check("--at com formato ruim recusa", p.returncode == 2
      and not (r / ".claude" / "reminders").exists(), p.stderr)
p = cepa(r, "remind", TEXT, "--context", CTX, "--step", "2")
check("remind recusa --step", p.returncode == 2 and not (r / ".claude" / "reminders").exists())

# --- write, append ----------------------------------------------------------
p = cepa(r, "remind", TEXT, "--context", CTX)
got = M.read_reminders(r)
check("remind com contexto grava (exit 0)", p.returncode == 0, p.stderr)
check("confirmação em pt-BR", f"lembrete gravado ({TODAY}): {TEXT}" in p.stdout, p.stdout)
check("uma entrada com at/text/context/session/branch",
      len(got) == 1 and got[0] == {"at": TODAY, "text": TEXT, "context": CTX,
                                   "session": "sess-123", "branch": "main"}, got)
first = got[0] if got else None
p = cepa(r, "lembrar", "segundo lembrete", "--context", "outro contexto", "--at", "2026-10-31")
got = M.read_reminders(r)
check("segundo remind acrescenta (alias lembrar)", p.returncode == 0 and len(got) == 2
      and got[0] == first and got[1]["at"] == "2026-10-31"
      and got[1]["text"] == "segundo lembrete", got)
check("telemetria reminder.written sem texto",
      "reminder.written" in "".join(f.read_text() for f in TEL.rglob("*") if f.is_file())
      and TEXT not in "".join(f.read_text() for f in TEL.rglob("*") if f.is_file()))

# --- hand-broken file is refused, untouched -----------------------------------
rb = new_repo("broken")
(rb / ".claude").mkdir()
junk = b"isto nao e um lembrete\nlixo: sem lista\n"
(rb / ".claude" / "reminders").write_bytes(junk)
p = cepa(rb, "remind", "x", "--context", "y")
check("arquivo quebrado à mão: remind recusa (exit 2) e cita o arquivo",
      p.returncode == 2 and "reminders" in p.stderr and "conserte" in p.stderr, p.stderr)
check("arquivo quebrado: bytes intactos", (rb / ".claude" / "reminders").read_bytes() == junk)

# --- read tolerance ---------------------------------------------------------
check("read_reminders sem arquivo: []", M.read_reminders(TMP / "nao-existe") == [])

# --- linked worktree --------------------------------------------------------
wt = TMP / "wt"
subprocess.run(["git", "worktree", "add", "-q", "-b", "outra", str(wt)], cwd=r, check=True, env=ENV)
p = cepa(wt, "remind", "do worktree", "--context", "veio do worktree")
main_list = M.read_reminders(r)
check("no worktree, remind grava no clone principal",
      p.returncode == 0 and len(main_list) == 3 and main_list[2]["branch"] == "outra"
      and not (wt / ".claude" / "reminders").exists(), (p.stderr, main_list))
p = cepa(wt, "state")
check("state no worktree lista os lembretes do principal",
      "lembretes do dono (3):" in p.stdout and "do worktree" in p.stdout, p.stdout)
p = cepa(wt, "lembretes")
check("reminders (alias lembretes) no worktree", p.returncode == 0
      and "lembretes do dono (3):" in p.stdout, p.stdout)

# --- state listing ----------------------------------------------------------
LINE = f"  - 2026-10-31 · segundo lembrete (contexto: outro contexto)"
p = cepa(r, "state")
check("state vazio termina com o bloco", p.stdout.startswith("state: empty")
      and "lembretes do dono (3):" in p.stdout and LINE in p.stdout
      and p.stdout.rstrip().endswith("pergunte se ainda vale."), p.stdout)
check("state: ordem do arquivo (mais antigo gravado primeiro)",
      p.stdout.index(TEXT) < p.stdout.index("segundo lembrete"), p.stdout)
cepa(r, "write", "--purpose", "p", "--by-when", "q", "--plan", "a", "b")
p = cepa(r, "state")
check("state normal termina com o bloco", "state: normal" in p.stdout
      and "passo atual:" in p.stdout and "lembretes do dono (3):" in p.stdout
      and p.stdout.index("passo atual:") < p.stdout.index("lembretes do dono"), p.stdout)
cepa(r, "--step", "3")
p = cepa(r, "state")
check("state fulfilled traz o bloco", "state: fulfilled" in p.stdout
      and "lembretes do dono (3):" in p.stdout, p.stdout)
p = cepa(r, "state", env={"CLAUDE_CODE_SESSION_ID": "outra-sessao"})
check("state other-session traz o bloco", "state: other-session" in p.stdout
      and "lembretes do dono (3):" in p.stdout, p.stdout)
p = cepa(r, "state", env={"CEPA_UNTIL_RUN": "1"})
check("state em run do cepa-until traz o bloco", "delegate: /common:next" in p.stdout
      and "lembretes do dono (3):" in p.stdout and LINE in p.stdout, p.stdout)

r2 = new_repo("b")
p = cepa(r2, "state")
check("sem lembretes: bloco ausente", "lembretes" not in p.stdout, p.stdout)
p = cepa(r2, "state", env={"CEPA_UNTIL_RUN": "1"})
check("sem lembretes no cepa-until: bloco ausente", "lembretes" not in p.stdout, p.stdout)
p = cepa(r2, "reminders")
check("reminders sem nenhum: mensagem", p.returncode == 0
      and p.stdout.strip() == "nenhum lembrete gravado.", p.stdout)

# --- hook -------------------------------------------------------------------
def run_hook(cwd, env=None, **payload):
    e = {k: v for k, v in os.environ.items() if k != "CEPA_UNTIL_RUN"}
    e["CEPA_TELEMETRY_DIR"] = str(TEL)
    e.update(env or {})
    return subprocess.run([sys.executable, str(HOOK)],
                          input=json.dumps({"cwd": str(cwd), **payload}),
                          capture_output=True, text=True, timeout=30, env=e)


def ctx(proc):
    return json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"] if proc.stdout.strip() else ""


def write_log(repo, entries):
    out, day = ["# Session log", ""], None
    for d, h, t in entries:
        if d != day:
            out += [f"## {d}", ""]
            day = d
        out += [f"### {h} UTC", "", t, ""]
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude" / "session-log.md").write_text("\n".join(out), encoding="utf-8")


p = run_hook(r, session_id="s1", prompt="oi")
line = [l for l in ctx(p).splitlines() if l.startswith("[lembretes]")]
check("hook 1o turno: linha [lembretes] com contagem e data mais antiga",
      len(line) == 1 and "3 lembrete(s)" in line[0] and "o mais antigo de 2026-10-31" in line[0]
      and "/common:whereami lista todos." in line[0], (ctx(p), p.stderr))
p = run_hook(wt, session_id="s1", prompt="oi")
check("hook 1o turno no worktree: também", "[lembretes]" in ctx(p), ctx(p))
write_log(r, [(TODAY, "10:00:00", "primeiro"), (TODAY, "10:05:00", "segundo")])
p = run_hook(r, session_id="s1", prompt="terceiro")
check("hook com 2 prompts antes: sem [lembretes]", "[lembretes]" not in ctx(p), ctx(p))
write_log(r, [])
p = run_hook(r, env={"CEPA_UNTIL_RUN": "1"}, session_id="s1", prompt="oi")
check("hook em run do cepa-until: sem [lembretes]", "[lembretes]" not in ctx(p), ctx(p))
p = run_hook(r2, session_id="s1", prompt="oi")
check("hook sem lembretes: sem [lembretes]", "[lembretes]" not in ctx(p), ctx(p))

# --- parse/render round trip -------------------------------------------------
d = {"reminders": [{"at": "2026-10-31", "text": 'com "aspas" e \\ barra',
                    "context": "ctx", "session": "", "branch": "b"},
                   {"at": "2026-11-01", "text": "dois", "context": "c2",
                    "session": "abc", "branch": "x"}]}
check("render/parse: reminders é lista de mapas (round-trip)",
      M.parse_intent(M.render_intent(d)) == d, M.render_intent(d))

# --- docs -------------------------------------------------------------------
w = (REPO / "common" / "commands" / "whereami.md").read_text(encoding="utf-8")
h = (REPO / "common" / "commands" / "handoff.md").read_text(encoding="utf-8")
check("whereami.md: 'ainda vale' e fb-20261104-3", "ainda vale" in w and "fb-20261104-3" in w)
check("handoff.md menciona cepa-intent remind", "cepa-intent remind" in h)

if FAILURES:
    print(f"\n{len(FAILURES)} falha(s): {FAILURES}")
    sys.exit(1)
print("\ntudo ok")
