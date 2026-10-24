#!/usr/bin/env python3
"""`intent.*` telemetry of cycle 1 of the session intent (C1-6).

Covers: the matcher of "where are we / next step" (hits and misses), the session-log
hook emitting `intent.asked`, `cepa-intent close` emitting
`intent.finished_at_last_step` only with the cursor on the last step, the `session`
field in the writer's events and the "Intenção da sessão" section of
cepa-metrics over a synthetic ledger counted by hand.

Run: python3 tests/test_intent_telemetry.py
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from _telemetria_isolada import isola
isola()

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "common" / "bin" / "cepa-intent"
METRICS = REPO / "common" / "bin" / "cepa-metrics"
HOOK = REPO / "common" / "hooks" / "session-log.py"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


TMP = Path(tempfile.mkdtemp(prefix="cepa-intent-tel-"))

# ── 1. the matcher ──────────────────────────────────────────────────────────
spec = importlib.util.spec_from_file_location("session_log", HOOK)
SL = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SL)

HITS = ["o que estamos fazendo?", "O que estamos fazendo", "o que a gente estamos fazendo",
        "onde estamos?", "onde paramos?", "em que passo estamos", "qual o próximo passo?",
        "qual é o próximo passo", "e o próximo passo?", "próximo passo", "proximo passo?",
        "where are we?", "what are we doing", "what's next?", "what is the next step",
        "/common:whereami", "  /common:whereami  ", "então, onde estamos?"]
MISSES = ["", "   ", "o próximo passo do deploy exige revisar o pipeline inteiro e depois o rollback",
          "implemente o próximo passo do plano", "onde está o arquivo de config?",
          "o que estamos fazendo de errado nesse teste que falha toda vez que eu rodo a suíte inteira no CI?",
          "/common:next", "/common:wrap-up", "oi"]
for h in HITS:
    check(f"casa: {h!r}", SL.asks_where_we_are(h))
for m in MISSES:
    check(f"não casa: {m[:40]!r}", not SL.asks_where_we_are(m))


# ── 2. the hook emits intent.asked ──────────────────────────────────────────
def ledger(d):
    out = []
    for f in sorted(Path(d).glob("events-*.jsonl")):
        out += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return out


def run_hook(prompt, tel, sid="abcdef123456"):
    repo = TMP / "hook-repo"
    repo.mkdir(exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    env = {**os.environ, "CEPA_TELEMETRY_DIR": str(tel)}
    return subprocess.run([sys.executable, str(HOOK)], capture_output=True, text=True, env=env,
                          input=json.dumps({"prompt": prompt, "cwd": str(repo), "session_id": sid}))


tel1 = TMP / "tel-hook"
r = run_hook("onde estamos?", tel1)
ev = ledger(tel1)
asked = [e for e in ev if e["event"] == "intent.asked"]
check("hook sai 0", r.returncode == 0, r.stderr)
check("hook emite 1 intent.asked com session de 8 chars",
      len(asked) == 1 and asked[0].get("session") == "abcdef12", str(asked))
check("o prompt continua virando evento prompt", any(e["event"] == "prompt" for e in ev))
check("intent.asked não carrega o texto do prompt", "onde estamos" not in json.dumps(asked))
tel2 = TMP / "tel-hook2"
run_hook("refatore o módulo de pagamento", tel2)
check("prompt comum não emite intent.asked",
      not [e for e in ledger(tel2) if e["event"] == "intent.asked"])

# ── 3. close (formerly `encerrar`) and the session field ────────────────────────────────────
tel3 = TMP / "tel-bin"


def new_repo(name):
    r = TMP / name
    r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
    return r


def cli(repo, *args, sid="sess-1234-abcd"):
    env = {**os.environ, "CEPA_TELEMETRY_DIR": str(tel3), "CLAUDE_CODE_SESSION_ID": sid}
    env.pop("CEPA_UNTIL_RUN", None)
    return subprocess.run([sys.executable, str(BIN), *args], cwd=repo, env=env,
                          capture_output=True, text=True)


def finals():
    return [e for e in ledger(tel3) if e["event"] == "intent.finished_at_last_step"]


repo = new_repo("r-enc")
r = cli(repo, "close")
check("close sem intenção: sai 0 e não emite", r.returncode == 0 and not finals(), r.stdout + r.stderr)
cli(repo, "write", "--purpose", "p", "--by-when", "q", "--plan", "a", "b", "c")
w = [e for e in ledger(tel3) if e["event"] == "intent.written"]
check("intent.written leva session de 8 chars", len(w) == 1 and w[0].get("session") == "sess-123", str(w))
cli(repo, "close")
check("cursor no passo 1 de 3: não emite", not finals())
cli(repo, "--step", "2")
cli(repo, "close")
check("cursor no passo 2 de 3: não emite", not finals())
adv = [e for e in ledger(tel3) if e["event"] == "intent.cursor_advanced"]
check("intent.cursor_advanced leva session", adv and adv[0].get("session") == "sess-123", str(adv))
cli(repo, "--step", "3")
r = cli(repo, "close")
f = finals()
check("cursor no último passo (3 de 3): emite 1", len(f) == 1 and r.returncode == 0, str(f))
check("evento leva passo, passos e session",
      f and f[0].get("passo") == 3 and f[0].get("passos") == 3 and f[0].get("session") == "sess-123", str(f))
cli(repo, "--step", "4")
cli(repo, "close")
check("plano cumprido (4 de 3): emite", len(finals()) == 2, str(finals()))
check("plano cumprido: o evento guarda passo == 4 (não M)",
      finals()[-1].get("passo") == 4 and finals()[-1].get("passos") == 3, str(finals()[-1]))
r = cli(repo, "close", sid="outra-sessao-zzz")
check("intenção de outra sessão: não emite", len(finals()) == 2 and r.returncode == 0, r.stdout)
r = cli(repo, "close", "--step", "1")
check("close recusa opções de escrita", r.returncode == 2, str(r.returncode))

# old names: `encerrar`, `gravar --proposito ...`, `--passo` and the `cepa-intencao` shortcut
# emit the same events
repo_a = new_repo("r-antigo")
BIN_OLD = REPO / "common" / "bin" / "cepa-intencao"
env_a = {**os.environ, "CEPA_TELEMETRY_DIR": str(tel3), "CLAUDE_CODE_SESSION_ID": "sess-1234-abcd"}
env_a.pop("CEPA_UNTIL_RUN", None)
def cli_old(repo, *args):
    return subprocess.run([sys.executable, str(BIN_OLD), *args], cwd=repo, env=env_a,
                          capture_output=True, text=True)
before_n = len(finals())
r = cli_old(repo_a, "gravar", "--proposito", "p", "--para-quando", "q", "--plano", "a", "b")
check("antigo: `cepa-intencao gravar --proposito ...` grava", r.returncode == 0, r.stderr)
cli_old(repo_a, "--passo", "2")
r = cli_old(repo_a, "encerrar")
check("antigo: `encerrar` emite intent.finished_at_last_step no último passo",
      r.returncode == 0 and len(finals()) == before_n + 1, r.stdout + r.stderr)

# ── 4. cepa-metrics prints the line, with the calculation ───────────────────
tel4 = TMP / "tel-metrics"
tel4.mkdir()
now = datetime.now(timezone.utc).isoformat()
L = []


def add(ev, **kw):
    L.append({"ts": now, "event": ev, "repo": "x", **kw})


# 4 sessions recorded (s1..s4); s1 and s2 advanced (s2 twice); s2 and s3 at the
# last step; 3 questions (2 in s1, 1 in s9 which did not even record).
for s in ("s1", "s2", "s3", "s4"):
    add("intent.written", session=s, action="gravar", steps=3)
add("intent.cursor_advanced", session="s1", src=1, dst=2, steps=3)
add("intent.cursor_advanced", session="s2", src=1, dst=2, steps=3)
add("intent.cursor_advanced", session="s2", src=2, dst=3, steps=3)
add("intent.written", session="s2", action="plano", steps=3)  # rewrote: still 1 session
add("intent.finished_at_last_step", session="s2", step=3, steps=3)
add("intent.finished_at_last_step", session="s3", step=3, steps=3)
add("intent.asked", session="s1")
add("intent.asked", session="s1")
add("intent.asked", session="s9")
(tel4 / f"events-{now[:7]}.jsonl").write_text("\n".join(json.dumps(e) for e in L) + "\n")


def metrics(tel):
    env = {**os.environ, "CEPA_TELEMETRY_DIR": str(tel)}
    return subprocess.run([sys.executable, str(METRICS), "--days", "30"],
                          capture_output=True, text=True, env=env)


r = metrics(tel4)
out = r.stdout
check("cepa-metrics sai 0", r.returncode == 0, r.stderr)
check("seção Intenção da sessão aparece", "## Intenção da sessão" in out, out[-600:])
check("sessões gravadas = 4", "sessões com intenção gravada: 4" in out)
check("avançou = 2 de 4 com a conta", "2 de 4 (2 ÷ 4 × 100 = 50.0%)" in out and "avançado ao menos uma vez" in out)
check("nunca avançou = 2 de 4", "NUNCA avançado: 2 de 4 (2 ÷ 4 × 100 = 50.0%)" in out)
check("último passo = 2 de 4", "último passo (wrap-up com cursor em M ou M+1): 2 de 4" in out)
check("perguntas = 3", "(intent.asked): 3" in out)
check("falta amostra: 6 sessões para o mínimo", "faltam 6 sessão(ões)" in out)
check("memória de cálculo presente", "memória de cálculo: conta-se SESSÕES" in out)
check("eventos intent não aparecem como custom", "## Eventos custom" not in out, out[-300:])

empty = TMP / "tel-vazio"
empty.mkdir()
(empty / f"events-{now[:7]}.jsonl").write_text(
    json.dumps({"ts": now, "event": "prompt", "session": "a", "kind": "prosa"}) + "\n")
check("sem eventos intent.* a seção não aparece", "## Intenção da sessão" not in metrics(empty).stdout)

# 10 sessions, 6 never advanced: C2 enters
tel5 = TMP / "tel-c2"
tel5.mkdir()
L = []
for i in range(10):
    add("intent.written", session=f"t{i}", action="gravar", steps=2)
for i in range(4):
    add("intent.cursor_advanced", session=f"t{i}", src=1, dst=2, steps=2)
(tel5 / f"events-{now[:7]}.jsonl").write_text("\n".join(json.dumps(e) for e in L) + "\n")
o = metrics(tel5).stdout
check("10 sessões, 6 sem avançar: C2 entra", "C2 entra." in o and "NUNCA avançado: 6 de 10" in o, o[-700:])

# ── 4b. boundaries and survivors ────────────────────────────────────────────
def ledger_of(name, recorded_sessions, advanced_sessions, extra=()):
    """Synthetic ledger: `recorded_sessions` sessions with intent.written, the first
    `advanced_sessions` of them with cursor_advanced; `extra` are
    ready-made events (dicts without ts/repo).
    """
    d = TMP / name
    d.mkdir()
    ev = []
    for i in range(recorded_sessions):
        ev.append({"event": "intent.written", "session": f"{name[:3]}{i}", "acao": "gravar", "passos": 2})
    for i in range(advanced_sessions):
        ev.append({"event": "intent.cursor_advanced", "session": f"{name[:3]}{i}", "de": 1, "para": 2, "passos": 2})
    ev += list(extra)
    ev = [{"ts": now, "repo": "x", **e} for e in ev]
    (d / f"events-{now[:7]}.jsonl").write_text("\n".join(json.dumps(e) for e in ev) + "\n")
    return metrics(d).stdout


o = ledger_of("fronteira5", 10, 5)
check("5 de 10 nunca avançaram (exatamente metade): C2 NÃO entra",
      "NUNCA avançado: 5 de 10" in o and "C2 entra." not in o, o[-600:])
o = ledger_of("fronteira10", 10, 0)
check("10 de 10 nunca avançaram: C2 entra", "NUNCA avançado: 10 de 10" in o and "C2 entra." in o, o[-600:])
o = ledger_of("nove", 9, 0)
check("9 sessões, todas sem avançar: ainda faltam 1 e C2 não entra",
      "faltam 1 sessão(ões)" in o and "C2 entra." not in o, o[-600:])

# cursor_advanced / finished_at_last_step in a session WITHOUT intent.written do not count
o = ledger_of("orfas", 2, 1, extra=[
    {"event": "intent.cursor_advanced", "session": "orfa", "de": 1, "para": 2, "passos": 2},
    {"event": "intent.finished_at_last_step", "session": "orfa", "passo": 2, "passos": 2}])
check("sessão sem intent.written não entra em 'avançou'",
      "avançado ao menos uma vez: 1 de 2 (1 ÷ 2 × 100 = 50.0%)" in o, o)
check("sessão sem intent.written não entra em 'último passo'", "cursor em M ou M+1): 0 de 2" in o, o)

# intent.* event without a session: out of the counts, with the warning and the right N
o = ledger_of("semsess", 2, 1, extra=[
    {"event": "intent.written", "acao": "gravar", "passos": 2},
    {"event": "intent.cursor_advanced", "session": "", "de": 1, "para": 2, "passos": 2},
    {"event": "intent.finished_at_last_step", "passo": 2, "passos": 2}])
check("sem session: aviso com N=3", "(3 evento(s) intent.* sem session, fora das contagens por sessão)" in o, o)
check("sem session: não infla as sessões gravadas", "sessões com intenção gravada: 2" in o, o)
check("sem session: não infla 'último passo'", "cursor em M ou M+1): 0 de 2" in o, o)

# `close` is a reserved word: a plan item with that name is refused
# (the subcommand consumes the argument; see the guard at the top of main()).
rr = new_repo("r-reservada")
r = cli(rr, "write", "--purpose", "p", "--by-when", "q", "--plan", "levantar", "close")
check("item de plano `close` é recusado (sai 2, nada escrito)",
      r.returncode == 2 and not (rr / ".claude" / "session-intent").exists(), r.stdout + r.stderr)

# ── 5. contract of wrap-up.md: the prose that calls the command ──────────────
WRAP = (REPO / "common" / "commands" / "wrap-up.md").read_text(encoding="utf-8")
check("wrap-up.md manda rodar `cepa-intent` `close`",
      'bin/cepa-intent" close' in WRAP, "frase do comando sumiu")
check("wrap-up.md nomeia o evento intent.finished_at_last_step",
      "intent.finished_at_last_step" in WRAP)
check("wrap-up.md pula o encerrar no --discard",
      "Skip it on the `--discard` path" in WRAP)

check("wrap-up.md: só leitura e nunca bloqueia",
      "read-only, never blocks" in WRAP and "ignore the output" in WRAP)
METRICS_MD = (REPO / "common" / "commands" / "metrics.md").read_text(encoding="utf-8")
check("metrics.md descreve a seção Intenção da sessão",
      "**Intenção da sessão**" in METRICS_MD and "intent.*" in METRICS_MD)

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {FAILURES}")
    sys.exit(1)
print("all intent telemetria tests passed")
