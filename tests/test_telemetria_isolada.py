#!/usr/bin/env python3
"""A suíte não escreve no ledger de telemetria de quem a roda.

O defeito (26/08/2026): os hooks gravam eventos em ~/.claude/cepa-telemetry/ e
esta suíte executa os hooks. Só 3 dos 53 arquivos definiam CEPA_TELEMETRY_DIR,
então rodar os testes inventava repos no relatório do /common:metrics —
`main-repo` com 206 verdes e 206 vermelhos, `r3`, `sem-git`, `pert2` — e as duas
linhas de maior volume das "Leituras sugeridas" daquele relatório eram ensaio,
não uso. Métrica que mistura ensaio com uso mede o ensaio.

O que se prova aqui, e por que assim:

  - a prova roda os testes REAIS que emitem telemetria, cada um com o HOME
    apontado para um diretório descartável, e exige que esse HOME fique
    intocado. Um dublê que só chamasse `isola()` provaria a função, não a
    suíte — e o defeito era a suíte, não a função;
  - o mesmo teste, com CEPA_TELEMETRY_DIR já definido, tem de respeitar o
    destino pedido: vários testes conferem o que escreveram no próprio tmpdir, e
    um isolamento que sobrescrevesse isso os quebraria em silêncio;
  - uma varredura estática pega o PRÓXIMO poluidor: todo tests/test_*.py que
    executa um hook emissor tem de isolar. Sem ela, o conserto vale para os 7 de
    hoje e o 8º volta a poluir calado — que é exatamente como o defeito nasceu.

Vermelho esperado sem o conserto: tirar a chamada a `isola()` de qualquer um dos
emissores faz o primeiro caso escrever em <HOME>/.claude/cepa-telemetry/.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTES = REPO / "tests"

# Os testes que executam hook emissor. Medidos, não supostos: cada um destes,
# rodado com HOME descartável ANTES do conserto de 26/08/2026, criava
# <HOME>/.claude/cepa-telemetry/ (81 eventos somados).
EMISSORES = [
    "test_baseline_worktree_poisoning.py",
    "test_loop_budget.py",
    "test_maven_reactor_guard.py",
    "test_proof_double_substitution.py",
    "test_proof_status_enum.py",
    "test_session_anchor_root.py",
    "test_ui_proof_verdict_guard.py",
    "test_modo_escrita_gate.py",
]
COBAIA = TESTES / "test_proof_status_enum.py"

# Os hooks e binários que escrevem no ledger. Um teste que cite qualquer um
# destes e não isole é o próximo poluidor.
HOOKS_EMISSORES = [
    "capture-build-result", "gate-advance", "loop-budget", "maven-reactor-guard",
    "modo-escrita-gate", "proof-verdict-guard", "report-style-lint", "session-log",
    "session-registry", "ui-proof-verdict-guard",
]


def isola_de_algum_jeito(texto: str) -> bool:
    """O teste manda a telemetria para longe do ledger real, de um dos dois
    jeitos aceitos: a chamada compartilhada, ou o próprio destino no env."""
    return "isola()" in texto or "CEPA_TELEMETRY_DIR" in texto

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def roda(cobaia, home, **env_extra):
    """Roda um teste da suíte com HOME descartável. Devolve o CompletedProcess."""
    env = {k: v for k, v in os.environ.items() if k != "CEPA_TELEMETRY_DIR"}
    env["HOME"] = str(home)
    env.update(env_extra)
    return subprocess.run([sys.executable, str(cobaia)], capture_output=True,
                          text=True, env=env, cwd=str(REPO))


def ledger_do_home(home):
    return Path(home) / ".claude" / "cepa-telemetry"


for nome in EMISSORES:
    check(f"{nome} ainda existe (renomeado, este teste vira decoração)",
          (TESTES / nome).is_file(), nome)

# ── 1. nenhum emissor toca o ledger de quem roda ───────────────────────────
destino = Path(tempfile.gettempdir()) / "cepa-telemetry-tests"
antes = set(destino.glob("events-*.jsonl")) if destino.is_dir() else set()
tamanho_antes = {f: f.stat().st_size for f in antes}

for nome in EMISSORES:
    with tempfile.TemporaryDirectory(prefix="tele-home-") as home:
        r = roda(TESTES / nome, home)
        check(f"{nome} continua passando com HOME descartável",
              r.returncode == 0, f"rc={r.returncode} {r.stderr[-300:]}")
        check(f"{nome} NÃO cria ledger no HOME de quem roda",
              not ledger_do_home(home).exists(),
              f"criou {ledger_do_home(home)}: "
              f"{[p.name for p in ledger_do_home(home).glob('*')][:5]}")

depois = set(destino.glob("events-*.jsonl")) if destino.is_dir() else set()
cresceu = bool(depois - antes) or any(
    f.stat().st_size > tamanho_antes.get(f, 0) for f in depois)
check("…e os eventos foram para o ledger descartável, não sumiram",
      cresceu, f"destino={destino} arquivos={[p.name for p in depois]}")

# ── 2. destino pedido explicitamente é respeitado ──────────────────────────
with tempfile.TemporaryDirectory(prefix="tele-home-") as home, \
        tempfile.TemporaryDirectory(prefix="tele-dir-") as pedido:
    r = roda(COBAIA, home, CEPA_TELEMETRY_DIR=pedido)
    check("teste que pede o próprio destino continua sendo obedecido",
          r.returncode == 0, f"rc={r.returncode} {r.stderr[-300:]}")
    check("…e escreve lá, não no descartável",
          any(Path(pedido).glob("events-*.jsonl")),
          f"{[p.name for p in Path(pedido).glob('*')]}")
    check("…e segue sem tocar o HOME",
          not ledger_do_home(home).exists(), str(ledger_do_home(home)))

# ── 3. o runner isola por conta própria ────────────────────────────────────
runner = (REPO / "tests" / "run-all.sh").read_text(encoding="utf-8")
check("run-all.sh exporta CEPA_TELEMETRY_DIR",
      "export CEPA_TELEMETRY_DIR=" in runner)
check("…sem atropelar um destino já escolhido por quem chamou",
      "${CEPA_TELEMETRY_DIR:-" in runner)

# ── 4. a família pytest também isola ───────────────────────────────────────
conf = (REPO / "tests" / "conftest.py")
check("tests/conftest.py chama isola() (a família pytest não roda pelo caminho "
      "de script)", "isola()" in conf.read_text(encoding="utf-8"))

# ── 5. o próximo poluidor não passa calado ─────────────────────────────────
# Varredura estática: quem CITA hook emissor tem de isolar. A regra é
# deliberadamente conservadora — citar não é executar, e 5 dos arquivos que ela
# cobre hoje não emitem nada. Mas a distância entre citar e executar é de um
# commit, e foi justamente ela que deixou 7 testes poluindo o ledger por um mês.
# Isolar quem não emite não custa nada; descobrir o 8º poluidor pela métrica
# torta custou este dia de trabalho.
faltantes = []
for f in sorted(TESTES.glob("test_*.py")):
    texto = f.read_text(encoding="utf-8")
    if any(h in texto for h in HOOKS_EMISSORES) and not isola_de_algum_jeito(texto):
        faltantes.append(f.name)
check("todo teste que executa hook emissor isola a telemetria",
      not faltantes, f"sem isolamento: {faltantes}")

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {FAILURES}")
    sys.exit(1)
print("all telemetria-isolada tests passed")
