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
    with their differing body field names.
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
