#!/usr/bin/env python3
"""Telemetria `intent.*` do ciclo 1 da intenção da sessão (C1-6).

Cobre: o casador de "onde estamos / próximo passo" (acerta e erra), o hook
session-log emitindo `intent.asked`, o `cepa-intencao encerrar` emitindo
`intent.finished_at_last_step` só com o cursor no último passo, o campo
`session` nos eventos do escritor e a seção "Intenção da sessão" do
cepa-metrics sobre um ledger sintético contado à mão.

Run: python3 tests/test_intent_telemetria.py
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
BIN = REPO / "common" / "bin" / "cepa-intencao"
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

# ── 1. o casador ────────────────────────────────────────────────────────────
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
    check(f"casa: {h!r}", SL.pergunta_onde_estamos(h))
for m in MISSES:
    check(f"não casa: {m[:40]!r}", not SL.pergunta_onde_estamos(m))


# ── 2. o hook emite intent.asked ────────────────────────────────────────────
def ledger(d):
    out = []
    for f in sorted(Path(d).glob("events-*.jsonl")):
        out += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return out


def roda_hook(prompt, tel, sid="abcdef123456"):
    repo = TMP / "hook-repo"
    repo.mkdir(exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    env = {**os.environ, "CEPA_TELEMETRY_DIR": str(tel)}
    return subprocess.run([sys.executable, str(HOOK)], capture_output=True, text=True, env=env,
                          input=json.dumps({"prompt": prompt, "cwd": str(repo), "session_id": sid}))


tel1 = TMP / "tel-hook"
r = roda_hook("onde estamos?", tel1)
ev = ledger(tel1)
asked = [e for e in ev if e["event"] == "intent.asked"]
check("hook sai 0", r.returncode == 0, r.stderr)
check("hook emite 1 intent.asked com session de 8 chars",
      len(asked) == 1 and asked[0].get("session") == "abcdef12", str(asked))
check("o prompt continua virando evento prompt", any(e["event"] == "prompt" for e in ev))
check("intent.asked não carrega o texto do prompt", "onde estamos" not in json.dumps(asked))
tel2 = TMP / "tel-hook2"
roda_hook("refatore o módulo de pagamento", tel2)
check("prompt comum não emite intent.asked",
      not [e for e in ledger(tel2) if e["event"] == "intent.asked"])

# ── 3. encerrar e o campo session ───────────────────────────────────────────
tel3 = TMP / "tel-bin"


def novo_repo(nome):
    r = TMP / nome
    r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
    return r


def cli(repo, *args, sid="sess-1234-abcd"):
    env = {**os.environ, "CEPA_TELEMETRY_DIR": str(tel3), "CLAUDE_CODE_SESSION_ID": sid}
    env.pop("CEPA_UNTIL_RUN", None)
    return subprocess.run([sys.executable, str(BIN), *args], cwd=repo, env=env,
                          capture_output=True, text=True)


def finais():
    return [e for e in ledger(tel3) if e["event"] == "intent.finished_at_last_step"]


repo = novo_repo("r-enc")
r = cli(repo, "encerrar")
check("encerrar sem intenção: sai 0 e não emite", r.returncode == 0 and not finais(), r.stdout + r.stderr)
cli(repo, "gravar", "--proposito", "p", "--para-quando", "q", "--plano", "a", "b", "c")
w = [e for e in ledger(tel3) if e["event"] == "intent.written"]
check("intent.written leva session de 8 chars", len(w) == 1 and w[0].get("session") == "sess-123", str(w))
cli(repo, "encerrar")
check("cursor no passo 1 de 3: não emite", not finais())
cli(repo, "--passo", "2")
cli(repo, "encerrar")
check("cursor no passo 2 de 3: não emite", not finais())
adv = [e for e in ledger(tel3) if e["event"] == "intent.cursor_advanced"]
check("intent.cursor_advanced leva session", adv and adv[0].get("session") == "sess-123", str(adv))
cli(repo, "--passo", "3")
r = cli(repo, "encerrar")
f = finais()
check("cursor no último passo (3 de 3): emite 1", len(f) == 1 and r.returncode == 0, str(f))
check("evento leva passo, passos e session",
      f and f[0].get("passo") == 3 and f[0].get("passos") == 3 and f[0].get("session") == "sess-123", str(f))
cli(repo, "--passo", "4")
cli(repo, "encerrar")
check("plano cumprido (4 de 3): emite", len(finais()) == 2, str(finais()))
check("plano cumprido: o evento guarda passo == 4 (não M)",
      finais()[-1].get("passo") == 4 and finais()[-1].get("passos") == 3, str(finais()[-1]))
r = cli(repo, "encerrar", sid="outra-sessao-zzz")
check("intenção de outra sessão: não emite", len(finais()) == 2 and r.returncode == 0, r.stdout)
r = cli(repo, "encerrar", "--passo", "1")
check("encerrar recusa opções de escrita", r.returncode == 2, str(r.returncode))

# ── 4. o cepa-metrics imprime a linha, com a conta ──────────────────────────
tel4 = TMP / "tel-metrics"
tel4.mkdir()
agora = datetime.now(timezone.utc).isoformat()
L = []


def add(ev, **kw):
    L.append({"ts": agora, "event": ev, "repo": "x", **kw})


# 4 sessões gravaram (s1..s4); s1 e s2 avançaram (s2 duas vezes); s2 e s3 no
# último passo; 3 perguntas (2 em s1, 1 em s9 que nem gravou).
for s in ("s1", "s2", "s3", "s4"):
    add("intent.written", session=s, acao="gravar", passos=3)
add("intent.cursor_advanced", session="s1", de=1, para=2, passos=3)
add("intent.cursor_advanced", session="s2", de=1, para=2, passos=3)
add("intent.cursor_advanced", session="s2", de=2, para=3, passos=3)
add("intent.written", session="s2", acao="plano", passos=3)  # regravou: ainda 1 sessão
add("intent.finished_at_last_step", session="s2", passo=3, passos=3)
add("intent.finished_at_last_step", session="s3", passo=3, passos=3)
add("intent.asked", session="s1")
add("intent.asked", session="s1")
add("intent.asked", session="s9")
(tel4 / f"events-{agora[:7]}.jsonl").write_text("\n".join(json.dumps(e) for e in L) + "\n")


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

vazio = TMP / "tel-vazio"
vazio.mkdir()
(vazio / f"events-{agora[:7]}.jsonl").write_text(
    json.dumps({"ts": agora, "event": "prompt", "session": "a", "kind": "prosa"}) + "\n")
check("sem eventos intent.* a seção não aparece", "## Intenção da sessão" not in metrics(vazio).stdout)

# 10 sessões, 6 nunca avançaram: C2 entra
tel5 = TMP / "tel-c2"
tel5.mkdir()
L = []
for i in range(10):
    add("intent.written", session=f"t{i}", acao="gravar", passos=2)
for i in range(4):
    add("intent.cursor_advanced", session=f"t{i}", de=1, para=2, passos=2)
(tel5 / f"events-{agora[:7]}.jsonl").write_text("\n".join(json.dumps(e) for e in L) + "\n")
o = metrics(tel5).stdout
check("10 sessões, 6 sem avançar: C2 entra", "C2 entra." in o and "NUNCA avançado: 6 de 10" in o, o[-700:])

# ── 4b. fronteiras e sobreviventes ──────────────────────────────────────────
def ledger_de(nome, sessoes_gravadas, sessoes_avancadas, extra=()):
    """Ledger sintético: `sessoes_gravadas` sessões com intent.written, as
    primeiras `sessoes_avancadas` delas com cursor_advanced; `extra` são
    eventos já prontos (dicts sem ts/repo)."""
    d = TMP / nome
    d.mkdir()
    ev = []
    for i in range(sessoes_gravadas):
        ev.append({"event": "intent.written", "session": f"{nome[:3]}{i}", "acao": "gravar", "passos": 2})
    for i in range(sessoes_avancadas):
        ev.append({"event": "intent.cursor_advanced", "session": f"{nome[:3]}{i}", "de": 1, "para": 2, "passos": 2})
    ev += list(extra)
    ev = [{"ts": agora, "repo": "x", **e} for e in ev]
    (d / f"events-{agora[:7]}.jsonl").write_text("\n".join(json.dumps(e) for e in ev) + "\n")
    return metrics(d).stdout


o = ledger_de("fronteira5", 10, 5)
check("5 de 10 nunca avançaram (exatamente metade): C2 NÃO entra",
      "NUNCA avançado: 5 de 10" in o and "C2 entra." not in o, o[-600:])
o = ledger_de("fronteira10", 10, 0)
check("10 de 10 nunca avançaram: C2 entra", "NUNCA avançado: 10 de 10" in o and "C2 entra." in o, o[-600:])
o = ledger_de("nove", 9, 0)
check("9 sessões, todas sem avançar: ainda faltam 1 e C2 não entra",
      "faltam 1 sessão(ões)" in o and "C2 entra." not in o, o[-600:])

# cursor_advanced / finished_at_last_step numa sessão SEM intent.written não contam
o = ledger_de("orfas", 2, 1, extra=[
    {"event": "intent.cursor_advanced", "session": "orfa", "de": 1, "para": 2, "passos": 2},
    {"event": "intent.finished_at_last_step", "session": "orfa", "passo": 2, "passos": 2}])
check("sessão sem intent.written não entra em 'avançou'",
      "avançado ao menos uma vez: 1 de 2 (1 ÷ 2 × 100 = 50.0%)" in o, o)
check("sessão sem intent.written não entra em 'último passo'", "cursor em M ou M+1): 0 de 2" in o, o)

# evento intent.* sem session: fora das contagens, com o aviso e o N certo
o = ledger_de("semsess", 2, 1, extra=[
    {"event": "intent.written", "acao": "gravar", "passos": 2},
    {"event": "intent.cursor_advanced", "session": "", "de": 1, "para": 2, "passos": 2},
    {"event": "intent.finished_at_last_step", "passo": 2, "passos": 2}])
check("sem session: aviso com N=3", "(3 evento(s) intent.* sem session, fora das contagens por sessão)" in o, o)
check("sem session: não infla as sessões gravadas", "sessões com intenção gravada: 2" in o, o)
check("sem session: não infla 'último passo'", "cursor em M ou M+1): 0 de 2" in o, o)

# `encerrar` é palavra reservada: item de plano com esse nome é recusado
# (o subcomando consome o argumento; ver a guarda no topo de main()).
rr = novo_repo("r-reservada")
r = cli(rr, "gravar", "--proposito", "p", "--para-quando", "q", "--plano", "levantar", "encerrar")
check("item de plano `encerrar` é recusado (sai 2, nada escrito)",
      r.returncode == 2 and not (rr / ".claude" / "session-intent").exists(), r.stdout + r.stderr)

# ── 5. contrato do wrap-up.md: a prosa que chama o comando ──────────────────
WRAP = (REPO / "common" / "commands" / "wrap-up.md").read_text(encoding="utf-8")
check("wrap-up.md manda rodar `cepa-intencao` `encerrar`",
      'bin/cepa-intencao" encerrar' in WRAP, "frase do comando sumiu")
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
