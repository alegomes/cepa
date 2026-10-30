#!/usr/bin/env python3
"""Regression tests for common/hooks/bounce-reason-gate.py (A4).

No third-party deps — run with `python3 tests/test_bounce_reason_gate.py`.
Exits non-zero on failure.

Guards the contracts of the bounce-reason gate:
  - a bounce-back comment WITH a labeled, non-empty reason passes;
  - a bounce-back with no reason, or with a bare/empty label, is BLOCKED;
  - an empty `Reason:` followed by another labeled field is still empty —
    the neighbouring field must not be read as the answer;
  - pt-BR labels (Motivo / Razão) and Jira wiki markup are accepted;
  - non-bounce comments (PROVEN summary, NEEDS-HUMAN, triage notes) are never
    gated — including a PROVEN summary that contains the word "proven";
  - other tools, missing bodies and unparseable payloads fail open.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "bounce-reason-gate.py"

FAILURES = []

CLOUD_TOOL = "mcp__claude_ai_Atlassian__addCommentToJiraIssue"
LOCAL_TOOL = "mcp__mcp-atlassian__jira_add_comment"


def run_hook(tool_name, tool_input):
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    return subprocess.run(
        [sys.executable, str(HOOK)], input=payload, capture_output=True, text=True
    )


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


# ── the shape prove.md produces on UNPROVEN ─────────────────────────────────
BOUNCE_WITH_REASON = """## Proof gate — UNPROVEN, returning for rework

The change is not demonstrably reflected at the external surface:

**Reason:** `PlugSignGateway.java:88` — the retry branch has no integration
test; a @QuarkusTest hitting POST /assinaturas with a 503 upstream would close it.

Artifact: `.claude/proof/WEGO-1.yaml`.
"""

BOUNCE_NO_REASON = """## Proof gate — UNPROVEN, returning for rework

The change is not demonstrably reflected at the external surface.

Artifact: `.claude/proof/WEGO-1.yaml`.
"""

BOUNCE_EMPTY_REASON = """## Proof gate — UNPROVEN, returning for rework

**Reason:**

**Artifact:** `.claude/proof/WEGO-1.yaml`.
"""

r = run_hook(CLOUD_TOOL, {"commentBody": BOUNCE_WITH_REASON})
check("bounce com razão passa", r.returncode == 0, r.stderr[:300])

r = run_hook(CLOUD_TOOL, {"commentBody": BOUNCE_NO_REASON})
check("bounce sem razão BLOQUEIA", r.returncode == 2, f"rc={r.returncode}")
check("o bloqueio nomeia o campo", "Reason" in r.stderr and "Motivo" in r.stderr,
      r.stderr[:300])

r = run_hook(CLOUD_TOOL, {"commentBody": BOUNCE_EMPTY_REASON})
check("label vazio BLOQUEIA", r.returncode == 2, f"rc={r.returncode}")
check("label vazio é reportado como vazio, não como ausente",
      "empty" in r.stderr.lower(), r.stderr[:300])

# ── the reason right below the label (heading style) counts ─────────────────
BLOCK_STYLE = """### Devolvendo para retrabalho

### Motivo

O teste de regressão não fica vermelho no base_commit — sem prova de que o bug existia.
"""
r = run_hook(CLOUD_TOOL, {"commentBody": BLOCK_STYLE})
check("razão em bloco abaixo do rótulo passa", r.returncode == 0, r.stderr[:300])

# ── pt-BR + wiki markup (the real format of Jira comments) ──────────────────
WIKI_BOUNCE = """h2. Devolvendo o card para In Progress

h3. Motivo
Cobertura externa ausente no endpoint tocado (POST /contratos).
"""
r = run_hook(LOCAL_TOOL, {"comment": WIKI_BOUNCE})
check("wiki + pt-BR com motivo passa", r.returncode == 0, r.stderr[:300])

WIKI_BOUNCE_BARE = """h2. Devolvendo o card para In Progress

h3. Artefato
.claude/proof/WEGO-2.yaml
"""
r = run_hook(LOCAL_TOOL, {"comment": WIKI_BOUNCE_BARE})
check("wiki + pt-BR sem motivo BLOQUEIA", r.returncode == 2, f"rc={r.returncode}")

# ── reason present but without markup → FORMAT problem, not omission ────────
UNLABELED = """## Proof gate — UNPROVEN, returning for rework

Reason: falta cobertura externa no endpoint tocado.
"""
r = run_hook(CLOUD_TOOL, {"commentBody": UNLABELED})
check("razão sem marcação bloqueia", r.returncode == 2, f"rc={r.returncode}")
check("...e é reportada como formato, não como ausência",
      "NOT in a recognized format" in r.stderr, r.stderr[:300])

# ── comments that are NOT a bounce are never gated ──────────────────────────
PROVEN_SUMMARY = """## Proof summary — change-driven gate PROVEN

- **L2 external coverage:** every changed line exercised by an integration test.

Artifact: `.claude/proof/WEGO-3.yaml`. Auto-advanced.
"""
NEEDS_HUMAN = """## Proof gate — NEEDS-HUMAN

Deterministic levels passed. Escalating because PIT is not configured.
"""
for name, body in [
    ("Proof summary PROVEN", PROVEN_SUMMARY),
    ("NEEDS-HUMAN", NEEDS_HUMAN),
    ("nota de triage", "Triage: card já implementado em abc1234, ver diff."),
    ("Implementation Summary", "## Implementation summary\n\n**Release needed:** no\n"),
]:
    r = run_hook(CLOUD_TOOL, {"commentBody": body})
    check(f"{name} passa intocado", r.returncode == 0, r.stderr[:200])

# ── "devolver um valor" is not "devolver um card" (2026-07-31) ──────────────
# A real approval comment was barred because its BODY said "devolveria 403".
# Two independent defects did it: the stem `devolv\w*` swallowed verb forms
# that talk about a returned VALUE, and `{MARKER}?` being optional meant the
# "heading only" rule matched any line at all. Both are guarded here.

APPROVAL_MENTIONING_A_RETURNED_VALUE = """**PROVEN**

O teste exercita o endpoint e confirma que devolveria 403 para token expirado.
"""

APPROVAL_PROSE_ONLY = """Resumo da verificação

Verifiquei que o adapter devolveria 403 nesse caminho, e que devolver o
recurso ao pool não vaza conexão.
"""

APPROVAL_BODY_SAYS_SENDING_BACK = """**PROVEN**

The gateway is sending back a 429 with Retry-After, as the card asked.
"""

# Isolates the STEM half of the fix: this line does open with a marker (a
# bullet), so the heading rule alone would not save it — only `devolv\w*` no
# longer matching `devolveria` does.
APPROVAL_BULLET_RETURNED_VALUE = """**PROVEN**

- o adapter devolveria 403 quando o token expira
- o retry devolve a conexão ao pool
"""

# ── mentioning the verdict is not declaring the verdict (2026-08-03) ────────
# Three comments barred in a real session for saying, in the body, NOT to
# reject the card. Each lives on a line that opens with a marker — bullet or
# bold — which the old rule counted as a heading in any position.
APPROVAL_BULLET_SAYS_NOT_UNPROVEN = """h3. Proof gate — PROVEN

O card segue aprovado.
* Não marcar como UNPROVEN: a cobertura externa existe.
"""
APPROVAL_BOLD_SAYS_NOT_UNPROVEN = """## Resumo de implementação

**Nota:** não devolver como UNPROVEN — o teste externo cobre.
"""
# The same in loose prose. It already passed before the fix; it stays as a control pair,
# so that a future regression shows whether it broke the marker or the position.
APPROVAL_PROSE_SAYS_NOT_UNPROVEN = """h3. Proof gate — PROVEN

Não há motivo para marcar UNPROVEN aqui.
"""

for name, body in (
    ("aprovação com 'devolveria 403' no corpo", APPROVAL_MENTIONING_A_RETURNED_VALUE),
    ("prosa com 'devolveria'/'devolver' sem marcador", APPROVAL_PROSE_ONLY),
    ("'sending back' no corpo, não no heading", APPROVAL_BODY_SAYS_SENDING_BACK),
    ("bullet com 'devolveria'/'devolve' um valor", APPROVAL_BULLET_RETURNED_VALUE),
    ("bullet dizendo para NÃO marcar UNPROVEN", APPROVAL_BULLET_SAYS_NOT_UNPROVEN),
    ("negrito dizendo para NÃO devolver", APPROVAL_BOLD_SAYS_NOT_UNPROVEN),
    ("prosa dizendo para NÃO marcar UNPROVEN", APPROVAL_PROSE_SAYS_NOT_UNPROVEN),
):
    r = run_hook(CLOUD_TOOL, {"commentBody": body})
    check(f"{name} passa", r.returncode == 0, r.stderr[:300])

# …and the real bounces are still caught, in every heading shape.
BOUNCE_PT_MARKED = """**UNPROVEN** — devolvendo para In Progress

Sem motivo estruturado aqui.
"""
BOUNCE_PT_UNMARKED_FIRST_LINE = """Devolução para In Progress

Sem motivo estruturado aqui.
"""
BOUNCE_UNMARKED_FIRST_LINE = """UNPROVEN, returning for rework

Sem motivo estruturado aqui.
"""
# Heading with a bullet marker: it is still a heading because it is the first
# non-empty line, not because it opens with `-`.
BOUNCE_BULLET_FIRST_LINE = """- UNPROVEN, returning for rework

Sem motivo estruturado aqui.
"""
# A blank line before the heading does not push it into the body.
BOUNCE_AFTER_BLANK_LINES = """

## Proof gate — UNPROVEN, returning for rework

Sem motivo estruturado aqui.
"""

for name, body in (
    ("bounce pt-BR com marcador", BOUNCE_PT_MARKED),
    ("bounce pt-BR em heading sem markup", BOUNCE_PT_UNMARKED_FIRST_LINE),
    ("bounce em heading sem markup", BOUNCE_UNMARKED_FIRST_LINE),
    ("bounce em heading com bullet", BOUNCE_BULLET_FIRST_LINE),
    ("bounce após linhas em branco", BOUNCE_AFTER_BLANK_LINES),
):
    r = run_hook(CLOUD_TOOL, {"commentBody": body})
    check(f"{name} sem razão → BLOCKED", r.returncode == 2, f"rc={r.returncode}")

r = run_hook(CLOUD_TOOL, {"commentBody": BOUNCE_PT_MARKED.replace(
    "Sem motivo estruturado aqui.",
    "**Motivo:** o teste de aceite usa dublê no lugar do adapter corrigido.")})
check("bounce pt-BR com Motivo passa", r.returncode == 0, r.stderr[:300])

# ── fail-open ───────────────────────────────────────────────────────────────
r = run_hook("mcp__claude_ai_Atlassian__transitionJiraIssue", {"issueIdOrKey": "X-1"})
check("outra tool é ignorada", r.returncode == 0)

r = run_hook(CLOUD_TOOL, {"issueIdOrKey": "X-1"})
check("sem campo de corpo → fail open", r.returncode == 0)

r = subprocess.run(
    [sys.executable, str(HOOK)], input="{not json", capture_output=True, text=True
)
check("payload ilegível → fail open", r.returncode == 0)

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {FAILURES}")
    sys.exit(1)
print("all bounce-reason-gate tests passed")
