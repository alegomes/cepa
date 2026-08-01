#!/usr/bin/env python3
"""Regression tests for common/hooks/merge-truth-gate.py.

Builds real throwaway git repos — the gate's whole claim is about what git
holds, so a mocked git would prove nothing.

Guards:
  - code merged into the integration branch -> ALLOW, and the sha is printed
    for the closing comment;
  - code exists only on a side branch -> BLOCK (the "pendente de merge" card
    that gets closed anyway, which is how the board starts lying);
  - no commit carries the key -> ALLOW (decision / spike / docs card);
  - non-closing transitions, unmapped ids, missing config, non-git dirs and
    unparseable payloads -> ALLOW (this gate fails OPEN by design).
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "merge-truth-gate.py"

FAILURES = []
KEY = "WEGO-1726"

BOARD_FLOW = """\
defaults:
  project_key: WEGO
  status_map:
    to_do: "To Do"
    in_progress: "In Progress"
    in_review: "In Review"
    done: "Done"
  transition_ids:
    "11": to_do
    "21": in_progress
    "31": done
    "351": in_review
"""


def sh(args, cwd):
    subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, check=True)


def make_repo(board_flow=BOARD_FLOW):
    d = Path(tempfile.mkdtemp(prefix="merge-truth-"))
    sh(["git", "init", "-q", "-b", "main"], d)
    sh(["git", "config", "user.email", "t@t"], d)
    sh(["git", "config", "user.name", "t"], d)
    (d / "seed.txt").write_text("seed\n")
    sh(["git", "add", "-A"], d)
    sh(["git", "commit", "-qm", "seed"], d)
    if board_flow is not None:
        (d / "board-flow.yaml").write_text(board_flow)
        sh(["git", "add", "-A"], d)
        sh(["git", "commit", "-qm", "config"], d)
    return d


def commit_on(d, branch, message):
    sh(["git", "checkout", "-q", "-B", branch], d)
    f = d / f"{branch.replace('/', '-')}.txt"
    f.write_text(message)
    sh(["git", "add", "-A"], d)
    sh(["git", "commit", "-qm", message], d)


def run_hook(cwd, tid="31", key=KEY,
             tool_name="mcp__mcp-atlassian__jira_transition_issue"):
    payload = json.dumps({
        "tool_name": tool_name,
        "tool_input": {"issue_key": key, "transition_id": tid},
        "cwd": str(cwd),
    })
    return subprocess.run([sys.executable, str(HOOK)], input=payload,
                          capture_output=True, text=True)


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


# ── merged: allow, and hand the agent the sha ──────────────────────────────
merged = make_repo()
commit_on(merged, "main", f"{KEY} corrige o vazamento do body cru")
r = run_hook(merged)
check("codigo na branch de integração → PASSA", r.returncode == 0, r.stderr[:200])
check("…e o sha vai para o agente usar no comentário",
      KEY in r.stdout and "State this in the closing comment" in r.stdout, r.stdout[:200])

# ── the lying card: real code, not merged, closing anyway ──────────────────
unmerged = make_repo()
commit_on(unmerged, "feature/x", f"{KEY} corrige o vazamento do body cru")
sh(["git", "checkout", "-q", "main"], unmerged)
r = run_hook(unmerged)
check("codigo só em branch lateral → BLOQUEIA", r.returncode == 2, f"rc={r.returncode}")
check("…e a mensagem oferece as duas saídas honestas",
      "merge the work into" in r.stderr and "leave the card open" in r.stderr,
      r.stderr[:200])

# ── card with no code at all ───────────────────────────────────────────────
nocode = make_repo()
commit_on(nocode, "main", "outra coisa qualquer")
r = run_hook(nocode)
check("card sem commit nenhum (decisão/spike) → PASSA", r.returncode == 0, r.stderr[:200])

# ── only the close is gated ────────────────────────────────────────────────
for tid, label in (("351", "In Review"), ("21", "In Progress"), ("11", "To Do")):
    r = run_hook(unmerged, tid=tid)
    check(f"transição para {label} não é fechamento → PASSA", r.returncode == 0)

# ── fails OPEN wherever it cannot know ─────────────────────────────────────
r = run_hook(unmerged, tid="999")
check("id fora do mapa → PASSA (fail open)", r.returncode == 0)

no_cfg = make_repo(board_flow=None)
commit_on(no_cfg, "feature/x", f"{KEY} algo")
sh(["git", "checkout", "-q", "main"], no_cfg)
r = run_hook(no_cfg)
check("sem board-flow.yaml → PASSA (fail open)", r.returncode == 0)

plain = Path(tempfile.mkdtemp(prefix="not-a-repo-"))
(plain / "board-flow.yaml").write_text(BOARD_FLOW)
r = run_hook(plain)
check("fora de repo git → PASSA", r.returncode == 0)

r = run_hook(unmerged, key="nao-e-uma-chave")
check("chave malformada → PASSA", r.returncode == 0)

r = run_hook(unmerged, tool_name="mcp__claude_ai_Atlassian__addCommentToJiraIssue")
check("outra tool é ignorada", r.returncode == 0)

r = subprocess.run([sys.executable, str(HOOK)], input="{not json",
                   capture_output=True, text=True)
check("payload ilegível → PASSA", r.returncode == 0)

# ── the cloud dialect reaches the same verdict ─────────────────────────────
payload = json.dumps({
    "tool_name": "mcp__claude_ai_Atlassian__transitionJiraIssue",
    "tool_input": {"issueIdOrKey": KEY, "transition": {"id": "31"}},
    "cwd": str(unmerged),
})
r = subprocess.run([sys.executable, str(HOOK)], input=payload,
                   capture_output=True, text=True)
check("dialeto cloud bloqueia igual", r.returncode == 2, f"rc={r.returncode}")

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {FAILURES}")
    sys.exit(1)
print("all merge-truth-gate tests passed")
