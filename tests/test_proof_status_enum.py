#!/usr/bin/env python3
"""Regression tests for the closed status enum in
build-hex/hooks/proof-verdict-guard.py.

The hole this guards against (2026-08-03): the guard compared level statuses
against a DENYLIST of forbidden values, so any string outside it passed. WEGO-1779
and WEGO-1793 reached `proven` with `l4_adversarial_input.status: n/a` — a value
the L4 schema never offered — while WEGO-1962 encoded the same scenario as
`skipped` and was routed to NEEDS-HUMAN. Same situation, opposite verdicts, and
a typo would have passed just as easily.

Guards:
  - `proven` + a status outside the level's enum (invented value or typo) -> BLOCK;
  - `proven` + `n/a` on a level that DOES offer it (pit, regression) -> ALLOW;
  - `proven` + L4 `n/a` with a reason and no input-module class -> ALLOW;
  - `proven` + L4 `n/a` without `reason:` -> BLOCK;
  - `proven` + L4 `n/a` while the diff touches api-rest -> BLOCK;
  - `n/a` under a non-YAML-parseable artifact -> BLOCK (justification unverifiable);
  - a bogus status on a NON-proven verdict -> ALLOW (only `proven` is contradicted);
  - the pre-existing rules (forbidding status, double substitution) still fire.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "build-hex" / "hooks" / "proof-verdict-guard.py"

FAILURES = []
ARTIFACT = str(Path(tempfile.gettempdir()) / "proj" / ".claude" / "proof" / "WEGO-1779.yaml")

CLEAN_CLASS = """\
scope:
  changed_classes:
    - class: "com.wego.AssinaturaUseCase"
      module: application
      external_observable: true
      substituted_by_double: none
"""

API_CLASS = """\
scope:
  changed_classes:
    - class: "com.wego.AssinaturaController"
      module: api-rest
      external_observable: true
      substituted_by_double: none
"""


def artifact(verdict="proven", scope=CLEAN_CLASS, l4="    status: clean\n",
             pit="      status: ran\n", regression=None):
    body = f"schema_version: 2\ncard: WEGO-1779\nverdict: {verdict}\n{scope}"
    body += "levels:\n  l3_load_bearing:\n    pit:\n" + pit
    body += "    perturbation:\n      status: pass\n"
    body += "  l2_coverage:\n    status: pass\n"
    body += "  l4_adversarial_input:\n" + l4
    if regression:
        body += "  bugfix_regression_red_at_base:\n" + regression
    return body


def run(content, file_path=ARTIFACT):
    payload = json.dumps({
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": content},
        "cwd": str(Path(tempfile.gettempdir())),
    })
    return subprocess.run([sys.executable, str(HOOK)], input=payload,
                          capture_output=True, text=True)


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


# ── the hole: a value the enum never offered ───────────────────────────────
r = run(artifact(l4="    status: n/a\n"))
check("proven + L4 n/a sem reason → BLOQUEIA", r.returncode == 2, f"rc={r.returncode}")

r = run(artifact(l4="    status: banana\n"))
check("proven + status inventado → BLOQUEIA", r.returncode == 2, f"rc={r.returncode}")
check("…e a mensagem mostra o enum legítimo do nível",
      "clean" in r.stderr and "findings" in r.stderr, r.stderr[:300])

r = run(artifact(l4="    status: pass\n"))
check("proven + status válido em OUTRO nível → BLOQUEIA (enum é por nível)",
      r.returncode == 2, f"rc={r.returncode}")

r = run(artifact(pit="      status: skipped\n"))
check("proven + pit com status de outro nível → BLOQUEIA", r.returncode == 2,
      f"rc={r.returncode}")

# ── n/a onde o esquema sempre ofereceu ─────────────────────────────────────
r = run(artifact(pit="      status: n/a\n"))
check("proven + pit n/a → PASSA (o esquema oferece)", r.returncode == 0, r.stderr[:300])

r = run(artifact(regression="    status: n/a\n"))
check("proven + regressão n/a → PASSA", r.returncode == 0, r.stderr[:300])

# ── L4 n/a: legítimo com justificativa e diff compatível ───────────────────
GOOD_NA = ('    status: n/a\n'
           '    reason: "rodada só de teste; o diff não toca nada que leia entrada externa"\n')
r = run(artifact(l4=GOOD_NA))
check("proven + L4 n/a com reason e sem módulo de entrada → PASSA",
      r.returncode == 0, r.stderr[:400])

r = run(artifact(l4='    status: n/a\n    reason: "n/a"\n'))
check("proven + L4 n/a com reason vazio de conteúdo → BLOQUEIA",
      r.returncode == 2, f"rc={r.returncode}")

r = run(artifact(scope=API_CLASS, l4=GOOD_NA))
check("proven + L4 n/a com classe em api-rest → BLOQUEIA", r.returncode == 2,
      f"rc={r.returncode}")
check("…e a mensagem nomeia a classe que contradiz o n/a",
      "AssinaturaController" in r.stderr, r.stderr[:400])

# ── o fallback sem YAML não pode validar o n/a ─────────────────────────────
r = run("verdict: proven\nlevels:\n  l4_adversarial_input:\n"
        "    status: n/a\n  broken: [unclosed\n")
check("n/a em artefato ilegível como YAML → BLOQUEIA", r.returncode == 2,
      f"rc={r.returncode}")

# ── só um `proven` sobre-declarado é contradito ────────────────────────────
for v in ("unproven", "needs-human"):
    r = run(artifact(verdict=v, l4="    status: banana\n"))
    check(f"verdict {v} + status inventado → PASSA", r.returncode == 0, r.stderr[:200])

# ── as regras antigas seguem valendo ───────────────────────────────────────
r = run(artifact(l4="    status: skipped\n"))
check("regra antiga (skipped) segue bloqueando", r.returncode == 2, f"rc={r.returncode}")

r = run(artifact(scope=CLEAN_CLASS.replace("      substituted_by_double: none\n",
                                           '      substituted_by_double: "MockUseCase"\n')))
check("regra do dublê segue bloqueando", r.returncode == 2, f"rc={r.returncode}")

r = run(artifact(), file_path=str(Path(tempfile.gettempdir()) / "notes.yaml"))
check("arquivo fora de .claude/proof → PASSA", r.returncode == 0, r.stderr[:200])

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {FAILURES}")
    sys.exit(1)
print("all proof status-enum tests passed")
