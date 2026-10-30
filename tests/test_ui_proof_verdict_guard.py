#!/usr/bin/env python3
"""Regression of `common/hooks/ui-proof-verdict-guard.py`.

No dependencies — run with `python3 tests/test_ui_proof_verdict_guard.py`.
Exits non-zero on failure.

## What this hook does, and what this file proves

The `ui-proof-reviewer` records the screen-proof verdict in a YAML. Two things
can go wrong in that file, and the hook catches both:

1. **The verdict lies about its own flows.** `verdict: proven` next to a
   `skipped` / `pass-visual-only` / `fail` flow is a waiver the agent gave
   itself. The hook recomputes the verdict from the statuses and blocks.
2. **The verdict is written where it does not survive.** Until 2026-08-22 the destination
   was `.claude/proof/ui-<slug>.yaml`. In the projects that run the gate,
   `.claude/` is gitignored: the file is invisible to git and vanishes with the
   session's disposable worktree, without anyone noticing. The destination is now
   `docs/proof/`, and the old path BLOCKS.

The second block lives here, and not in `path-lock`, for a mechanical reason: the
`path-lock` only acts on an agent whose plugin prefix matches a topology
that carries the lock, and the `ui-proof-reviewer` is an agent of `common`, which does not
carry it. This hook is the only point able to hold the destination of the screen
gate — which also means that, if it stops recognizing a path, it does not
become stricter: it becomes mute.

## Perturbation (how to know this test proves something)

Make `_LEGACY_PROOF_DIR_RE` never match, or remove `docs` from
`_UI_PROOF_DIR_RE`, and this file turns red naming the case.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

# This test executes a hook that emits telemetry; without this the events would fall
# in ~/.claude/cepa-telemetry/ and enter the /common:metrics report
# as if they were real use. See tests/_isolated_telemetry.py.
from _isolated_telemetry import isolate

isolate()


HOOK = Path(__file__).resolve().parent.parent / "common" / "hooks" / "ui-proof-verdict-guard.py"
TMP = Path(tempfile.gettempdir()) / "repo"
NEW = str(TMP / "docs" / "proof" / "ui-wego-acesso.yaml")
OLD = str(TMP / ".claude" / "proof" / "ui-wego-acesso.yaml")

FAILURES = []


def artifact(verdict="proven", status="pass", perturbation="red"):
    return (
        "schema_version: 1\n"
        "slug: wego-acesso-registro\n"
        f"verdict: {verdict}\n"
        "manifest: docs/ui-proof.yaml\n"
        "flows:\n"
        "  registrar-acesso:\n"
        f"    status: {status}\n"
        "    script: docs/ui-proof/runs/registrar-acesso.spec.ts\n"
        '    run: "npx playwright test ... → OK; backend check contém o nonce"\n'
        "    perturbation:\n"
        f"      status: {perturbation}\n"
        '      run: "worktree @a47c52f, revert, re-run → FAILED — RED como exigido"\n'
    )


def run(content, file_path=NEW):
    payload = json.dumps({
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": content},
        "cwd": str(TMP),
    })
    return subprocess.run([sys.executable, str(HOOK)], input=payload,
                          capture_output=True, text=True)


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


# ── destination: the old path blocks, with ANY verdict ─────────────────────
for v in ("proven", "unproven", "needs-human"):
    r = run(artifact(verdict=v), file_path=OLD)
    check(f"veredito {v} em .claude/proof → BLOQUEIA (destino)", r.returncode == 2,
          f"rc={r.returncode}")

r = run(artifact(), file_path=OLD)
check("…e a mensagem nomeia o destino que sobrevive",
      "docs/proof/ui-wego-acesso.yaml" in r.stderr, r.stderr[:300])
check("…e diz por que o arquivo morria", "gitignored" in r.stderr, r.stderr[:300])

# ── content: the rule that already existed remains in force, now in docs/proof ──
r = run(artifact())
check("proven coerente com os fluxos em docs/proof → PASSA", r.returncode == 0,
      r.stderr[:300])

for bad in ("skipped", "pass-visual-only", "pass-stale", "not-executable"):
    r = run(artifact(status=bad))
    check(f"proven + fluxo {bad} → BLOQUEIA", r.returncode == 2, f"rc={r.returncode}")

r = run(artifact(perturbation="survived"))
check("proven + perturbação survived → BLOQUEIA", r.returncode == 2,
      f"rc={r.returncode}")
check("…e o bloqueio computa unproven", "verdict: unproven" in r.stderr,
      r.stderr[:400])

r = run(artifact(status="skipped", perturbation="n/a"))
check("fluxo skipped computa needs-human", "verdict: needs-human" in r.stderr,
      r.stderr[:400])

# ── only `proven` can be contradicted by the content ───────────────────────
for v in ("unproven", "needs-human"):
    r = run(artifact(verdict=v, status="skipped"))
    check(f"veredito {v} + fluxo skipped em docs/proof → PASSA", r.returncode == 0,
          r.stderr[:200])

# ── what is not this hook's business ──────────────────────────────────────
r = run(artifact(), file_path=str(TMP / "docs" / "proof" / "WEGO-1.yaml"))
check("artefato sem prefixo ui- → PASSA (é do guarda de backend)",
      r.returncode == 0, r.stderr[:200])

r = run(artifact(), file_path=str(TMP / "notas" / "ui-qualquer.yaml"))
check("fora de qualquer diretório de prova → PASSA", r.returncode == 0,
      r.stderr[:200])

r = run("::: isto não é yaml :::\nverdict: proven\n")
check("conteúdo ilegível → PASSA (nunca bloqueia no escuro)", r.returncode == 0,
      r.stderr[:200])

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {FAILURES}")
    sys.exit(1)
print("all ui-proof verdict-guard tests passed")
