#!/usr/bin/env python3
"""Regression tests for the double-substitution rule in
build-hex/hooks/proof-verdict-guard.py.

The false-green this guards against: the test offered as end-to-end proof
replaces the very class the card changed with a double, so breaking production
on purpose leaves the suite green (WEGO-1726, 1770, 1779, 1783 — 2026-08-01).

Guards:
  - `verdict: proven` + a changed class substituted by a double -> BLOCK;
  - `verdict: proven` + a changed class with the field OMITTED -> BLOCK
    (explicit-null discipline: silence is not an answer);
  - `verdict: proven` + every changed class declaring null/none -> ALLOW;
  - a double declared on a NON-proven verdict -> ALLOW (the guard only ever
    contradicts an over-claimed `proven`);
  - the pre-existing level-status rule still fires.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Este teste executa hook que emite telemetria; sem isto os eventos cairiam
# em ~/.claude/cepa-telemetry/ e entrariam no relatório do /common:metrics
# como se fossem uso real. Ver tests/_telemetria_isolada.py.
from _telemetria_isolada import isola

isola()


REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "build-hex" / "hooks" / "proof-verdict-guard.py"

FAILURES = []
ARTIFACT = str(Path(tempfile.gettempdir()) / "proj" / ".claude" / "proof" / "WEGO-1726.yaml")

CLEAN_LEVELS = """\
levels:
  l3_load_bearing:
    perturbation:
      status: pass
  l2_coverage:
    status: pass
  l4_adversarial_input:
    status: clean
"""


def artifact(verdict, classes, levels=CLEAN_LEVELS):
    body = f"schema_version: 2\ncard: WEGO-1726\nverdict: {verdict}\nscope:\n  changed_classes:\n"
    for c in classes:
        body += f"    - class: \"{c['class']}\"\n      module: infrastructure\n"
        body += "      external_observable: true\n"
        if "double" in c:
            v = c["double"]
            body += f"      substituted_by_double: {v}\n"
    return body + levels


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


# ── the false-green ────────────────────────────────────────────────────────
r = run(artifact("proven", [
    {"class": "com.wego.PlugSignAdapter", "double": '"MockPlugSignAlternative (@Alternative)"'},
]))
check("proven + dublê no lugar da classe alterada → BLOQUEIA", r.returncode == 2,
      f"rc={r.returncode}")
check("…e a mensagem manda rodar com o adapter real",
      "mock.enabled=false" in r.stderr and "WireMock" in r.stderr, r.stderr[:200])

# ── silence is not an answer ───────────────────────────────────────────────
r = run(artifact("proven", [{"class": "com.wego.PlugSignAdapter"}]))
check("proven + campo omitido → BLOQUEIA", r.returncode == 2, f"rc={r.returncode}")
check("…e a mensagem diz que o campo faltou",
      "não declarado" in r.stderr or "nao declarado" in r.stderr, r.stderr[:300])

# ── declared clean ─────────────────────────────────────────────────────────
for decl in ("null", "none", "~"):
    r = run(artifact("proven", [{"class": "com.wego.PlugSignAdapter", "double": decl}]))
    check(f"proven + substituted_by_double: {decl} → PASSA", r.returncode == 0,
          r.stderr[:200])

r = run(artifact("proven", [
    {"class": "com.wego.PlugSignAdapter", "double": "null"},
    {"class": "com.wego.AssinaturaUseCase", "double": "none"},
]))
check("proven + várias classes limpas → PASSA", r.returncode == 0, r.stderr[:200])

# ── only an over-claimed `proven` is ever contradicted ─────────────────────
for v in ("unproven", "needs-human"):
    r = run(artifact(v, [
        {"class": "com.wego.PlugSignAdapter", "double": '"MockPlugSign"'},
    ]))
    check(f"verdict {v} + dublê → PASSA (nada a contradizer)", r.returncode == 0,
          r.stderr[:200])

# ── the pre-existing rule still fires ──────────────────────────────────────
r = run(artifact("proven", [{"class": "com.wego.PlugSignAdapter", "double": "null"}],
                 levels="levels:\n  l3_load_bearing:\n    perturbation:\n      status: survived\n"))
check("regra antiga (status survived) segue bloqueando", r.returncode == 2,
      f"rc={r.returncode}")

# ── fail-open paths ────────────────────────────────────────────────────────
r = run(artifact("proven", [{"class": "X", "double": '"Mock"'}]),
        file_path=str(Path(tempfile.gettempdir()) / "notes.yaml"))
check("arquivo fora de qualquer diretório de prova → PASSA", r.returncode == 0)

# ── docs/proof é o destino de escrita desde 22/08/2026 ─────────────────────
# Ver o comentário longo em tests/test_proof_status_enum.py: o proof-reviewer
# grava em docs/proof/ porque `.claude/` é gitignored, e um guarda cego para o
# destino novo deixaria de checar exatamente os vereditos que passam a existir.
r = run(artifact("proven", [{"class": "X", "double": '"Mock"'}]),
        file_path=str(Path(tempfile.gettempdir()) / "repo" / "docs" / "proof" / "WEGO-1.yaml"))
check("dublê em docs/proof → BLOQUEIA", r.returncode == 2, f"rc={r.returncode}")

r = run("::: not yaml :::\nverdict: proven\n")
check("conteúdo ilegível → PASSA (fallback não vê estrutura)", r.returncode == 0)

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {FAILURES}")
    sys.exit(1)
print("all proof double-substitution tests passed")
