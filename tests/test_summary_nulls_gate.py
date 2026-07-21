#!/usr/bin/env python3
"""Regression tests for common/hooks/summary-nulls-gate.py (explicit nulls).

No third-party deps — run with `python3 tests/test_summary_nulls_gate.py`.
Exits non-zero on first failure.

Guards the contracts of the explicit-null gate (imported from Ariad):
  - a complete Implementation Summary (all four fields) passes;
  - each missing field blocks, and the block names it;
  - pt-BR labels are accepted as equivalents;
  - non-summary comments are never gated (NOT-A-BUG, triage, block reasons);
  - other tools and unparseable payloads fail open;
  - both MCP server variants (cloud connector / mcp-atlassian) are matched,
    with their differing body field names;
  - the conditional Revisit trigger (A6): declared debt requires it, "none" /
    "unknown" do not, and the block names it.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "summary-nulls-gate.py"

FAILURES = []


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


CLOUD_TOOL = "mcp__claude_ai_Atlassian__addCommentToJiraIssue"
LOCAL_TOOL = "mcp__mcp-atlassian__jira_add_comment"

FULL_SUMMARY = """## Implementation summary

**Files touched:**
- `src/a.py`

**Tests added/updated:**
- `tests/test_a.py`

**Build verification:** `./mvnw verify` → BUILD SUCCESS (commit `abc1234`)

**New debt introduced:** none

**Scope captured outside the card:** none

**Release needed:** no

**Human validation route:** not applicable (internal substrate — automated evidence above suffices)

**Caveats / follow-ups:**
- none
"""

FIELDS = [
    ("New debt introduced", "**New debt introduced:** none"),
    ("Scope captured outside the card", "**Scope captured outside the card:** none"),
    ("Release needed", "**Release needed:** no"),
    ("Human validation route", "**Human validation route:** not applicable (internal substrate — automated evidence above suffices)"),
]

# ── complete summary passes, on both server variants / body fields ──────────
r = run_hook(CLOUD_TOOL, {"commentBody": FULL_SUMMARY})
check("full summary passes (cloud connector, commentBody)", r.returncode == 0, r.stderr)

r = run_hook(LOCAL_TOOL, {"comment": FULL_SUMMARY})
check("full summary passes (mcp-atlassian, comment)", r.returncode == 0, r.stderr)

# ── each missing field blocks and is named ──────────────────────────────────
for label, line in FIELDS:
    body = FULL_SUMMARY.replace(line + "\n\n", "")
    assert label not in body, f"test setup broken for {label}"
    r = run_hook(CLOUD_TOOL, {"commentBody": body})
    check(f"missing '{label}' blocks", r.returncode == 2, f"rc={r.returncode}")
    check(f"missing '{label}' is named in stderr", label in r.stderr, r.stderr[:200])

# ── all four missing → blocked, all named ────────────────────────────────────
bare = "## Implementation summary\n\n**Files touched:**\n- `src/a.py`\n"
r = run_hook(CLOUD_TOOL, {"commentBody": bare})
check("bare summary blocks", r.returncode == 2)
check(
    "bare summary names all four fields",
    all(label in r.stderr for label, _ in FIELDS),
    r.stderr[:300],
)

# ── pt-BR labels are accepted ────────────────────────────────────────────────
ptbr = """## Implementation summary (bug fix)

**Fix:** `src/a.py`

**Dívida nova introduzida:** nenhuma

**Escopo capturado fora do card:** nenhum

**Release necessária:** não

**Rota de validação humana:** não aplicável (substrato interno)
"""
r = run_hook(CLOUD_TOOL, {"commentBody": ptbr})
check("pt-BR labels pass", r.returncode == 0, r.stderr)

# ── pt-BR word order is loose ────────────────────────────────────────────────
# The gate proves the QUESTION was answered; it does not police phrasing.
r = run_hook(CLOUD_TOOL, {"commentBody": ptbr.replace(
    "**Dívida nova introduzida:**", "**Nova dívida introduzida:**")})
check("pt-BR alternate word order passes", r.returncode == 0, r.stderr)

# ── Jira WIKI markup (regression: WEGO-1948, 2026-07-21) ─────────────────────
# Jira comments are written in wiki markup, not markdown. Before the fix the
# gate was blind to it in BOTH directions: a wiki summary with zero fields
# passed silently, and a wiki summary with all four was blocked as if empty.
WIKI_BARE = """h2. Implementation summary

h3. Arquivos tocados
* `src/a.py`
"""
r = run_hook(LOCAL_TOOL, {"comment": WIKI_BARE})
check("wiki-heading summary with no fields BLOCKS", r.returncode == 2, f"rc={r.returncode}")
check(
    "wiki-heading bare summary names all four",
    all(label in r.stderr for label, _ in FIELDS),
    r.stderr[:300],
)

WIKI_FULL = """h2. Implementation summary

h3. Arquivos tocados
* `src/a.py`

h3. Nova dívida introduzida
nenhuma

h3. Escopo capturado fora do card
nenhum

h3. Release necessária
não

h3. Rota de validação humana
não se aplica (substrato interno)
"""
r = run_hook(LOCAL_TOOL, {"comment": WIKI_FULL})
check("wiki-heading summary with all four passes", r.returncode == 0, r.stderr[:400])

# ── markdown heading fields (### Label) also count ───────────────────────────
MD_HEADINGS = """## Implementation summary

### New debt introduced
none

### Scope captured outside the card
none

### Release needed
no

### Human validation route
not applicable (internal substrate)
"""
r = run_hook(CLOUD_TOOL, {"commentBody": MD_HEADINGS})
check("markdown-heading fields pass", r.returncode == 0, r.stderr[:400])

# ── present but unlabeled → blocked, and SAID to be a formatting problem ─────
# Reporting this as "missing" is what teaches agents the gate is noise.
UNLABELED = """## Implementation summary

New debt introduced: none
Scope captured outside the card: none
Release needed: no
Human validation route: not applicable
"""
r = run_hook(CLOUD_TOOL, {"commentBody": UNLABELED})
check("unlabeled fields still block", r.returncode == 2, f"rc={r.returncode}")
check(
    "unlabeled fields are reported as a FORMAT problem, not as missing",
    "NOT in a recognized format" in r.stderr,
    r.stderr[:400],
)
check(
    "unlabeled fields are not called missing",
    "is missing explicit-null" not in r.stderr,
    r.stderr[:400],
)

# ── A6: dívida declarada exige Revisit trigger ───────────────────────────────
DEBT_NO_TRIGGER = FULL_SUMMARY.replace(
    "**New debt introduced:** none",
    "**New debt introduced:** PlugSignGateway duplica a normalização de CPF",
)
r = run_hook(CLOUD_TOOL, {"commentBody": DEBT_NO_TRIGGER})
check("dívida declarada sem Revisit trigger BLOQUEIA", r.returncode == 2,
      f"rc={r.returncode}")
check("o bloqueio nomeia o Revisit trigger", "Revisit trigger" in r.stderr,
      r.stderr[:400])
check("o bloqueio ecoa a dívida declarada", "PlugSign" in r.stderr,
      r.stderr[:400])

DEBT_WITH_TRIGGER = DEBT_NO_TRIGGER.replace(
    "**Scope captured outside the card:** none",
    "**Revisit trigger:** quando o contrato do PlugSign mudar a validação\n\n"
    "**Scope captured outside the card:** none",
)
r = run_hook(CLOUD_TOOL, {"commentBody": DEBT_WITH_TRIGGER})
check("dívida declarada COM Revisit trigger passa", r.returncode == 0,
      r.stderr[:400])

# "none" e "unknown" não exigem trigger — unknown é o que o triage escreve
r = run_hook(CLOUD_TOOL, {"commentBody": FULL_SUMMARY})
check("dívida 'none' não exige trigger", r.returncode == 0, r.stderr[:200])

TRIAGE_UNKNOWN = FULL_SUMMARY.replace(
    "**New debt introduced:** none",
    "**New debt introduced:** unknown (triage-routed — assess at proof)",
)
r = run_hook(CLOUD_TOOL, {"commentBody": TRIAGE_UNKNOWN})
check("dívida 'unknown' (rota do triage) não exige trigger",
      r.returncode == 0, r.stderr[:300])

# pt-BR: "nenhuma" isenta; dívida real em pt-BR exige o gatilho
PTBR_SEM_DIVIDA = ptbr
r = run_hook(CLOUD_TOOL, {"commentBody": PTBR_SEM_DIVIDA})
check("pt-BR 'nenhuma' não exige trigger", r.returncode == 0, r.stderr[:200])

PTBR_COM_DIVIDA = ptbr.replace(
    "**Dívida nova introduzida:** nenhuma",
    "**Dívida nova introduzida:** o adapter ainda faz parsing manual de data",
)
r = run_hook(CLOUD_TOOL, {"commentBody": PTBR_COM_DIVIDA})
check("pt-BR com dívida real exige trigger", r.returncode == 2,
      f"rc={r.returncode}")
r = run_hook(CLOUD_TOOL, {"commentBody": PTBR_COM_DIVIDA.replace(
    "**Release necessária:** não",
    "**Gatilho de revisita:** na próxima mudança do adapter\n\n"
    "**Release necessária:** não")})
check("pt-BR com dívida + gatilho de revisita passa", r.returncode == 0,
      r.stderr[:400])

# wiki markup: dívida em bloco também dispara a exigência
WIKI_DEBT = WIKI_FULL.replace("h3. Nova dívida introduzida\nnenhuma",
                              "h3. Nova dívida introduzida\nfalta índice na tabela de contratos")
r = run_hook(LOCAL_TOOL, {"comment": WIKI_DEBT})
check("wiki com dívida real exige trigger", r.returncode == 2, f"rc={r.returncode}")
r = run_hook(LOCAL_TOOL, {"comment": WIKI_DEBT + "\nh3. Revisit trigger\nquando a tabela passar de 1M linhas\n"})
check("wiki com dívida + trigger passa", r.returncode == 0, r.stderr[:400])

# ── non-summary comments are never gated ─────────────────────────────────────
for name, body in [
    ("NOT-A-BUG comment", "[automated] /board-flow:fix concluded NOT-A-BUG. Reason: ..."),
    ("block-reason comment", "validation-lead BLOCKED: failing test at tests/x.py"),
    ("plain text mentioning summary", "see the implementation summary posted earlier"),
]:
    r = run_hook(CLOUD_TOOL, {"commentBody": body})
    check(f"{name} passes untouched", r.returncode == 0, r.stderr)

# ── fail-open paths ──────────────────────────────────────────────────────────
r = run_hook("mcp__claude_ai_Atlassian__transitionJiraIssue", {"issueIdOrKey": "X-1"})
check("other tool ignored", r.returncode == 0)

r = run_hook(CLOUD_TOOL, {"issueIdOrKey": "X-1"})
check("no body field → fail open", r.returncode == 0)

r = subprocess.run(
    [sys.executable, str(HOOK)], input="{not json", capture_output=True, text=True
)
check("unparseable payload → fail open", r.returncode == 0)

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {FAILURES}")
    sys.exit(1)
print("all summary-nulls-gate tests passed")
