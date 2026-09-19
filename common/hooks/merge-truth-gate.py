#!/usr/bin/env python3
"""PreToolUse hook: don't let a card close while its code sits unmerged.

The board lies about the state of the code, and it lies in one specific,
repeatable way. The Implementation Summary is written the moment the work is
done — necessarily BEFORE the merge exists — so it says "pending merge". Then
nobody ever revisits it. On 2026-08-01 a review of the WEGO board found six
cards (1646, 1657, 1726, 1763, 1779, 1732) whose comment still said "pendente
de merge" while the code had been on the integration branch for weeks. Whoever
reads the board afterwards decides on false information, and — worse — future
agents repeat the claim as fact, because a Jira comment reads like a record.

The stale comment is a symptom. The disease is that closing a card verifies
nothing: the summary is a snapshot, and no step ever reconciles it with what
git actually holds. This gate makes the close the reconciliation point.

Mechanism (git is the witness, not the comment):

  When a transition targets `done` (resolved via `defaults.transition_ids` in
  board-flow.yaml — the same map acceptance-gate uses):

    commits mentioning <KEY> reachable from the integration branch
        -> ALLOW. The work is genuinely in. This is the truth the closing
           comment should state, and it is printed for the agent to quote.
    commits mentioning <KEY> exist, but NONE on the integration branch
        -> BLOCK. This is the exact case the board keeps lying about: real
           code, really not merged, card about to be closed anyway.
    no commit mentions <KEY> anywhere
        -> ALLOW. Not a code card (decision, spike, docs). Nothing to
           reconcile, and inventing a requirement here would only teach people
           to route around the gate.

  Direction unresolvable, not a `done` target, no git, no config -> ALLOW.
  Unlike acceptance-gate this one fails OPEN: it asserts a positive fact about
  git rather than withholding a privilege, and a false block here would stop
  legitimate closes on every repo that never configured the map.

Exit codes:
  0 — allowed (a merged card prints its sha to stdout for the closing comment)
  2 — blocked (stderr reaches the agent so it can self-correct)
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _jiramut as J  # noqa: E402

KEY_FIELDS = ("issueIdOrKey", "issueKey", "issue_key", "issueId", "issue_id",
              "issue", "key")
CONFIG_NAMES = ("board-flow.yaml", ".claude/board-flow.lifecycle.yaml")
CLOSING_TARGETS = {"done"}
KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")


def git(args, cwd):
    try:
        p = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True,
                           text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def extract_key(tool_input: dict):
    for f in KEY_FIELDS:
        v = tool_input.get(f)
        if isinstance(v, str) and KEY_RE.match(v.strip()):
            return v.strip()
    return None


def extract_transition_id(tool_input: dict):
    t = tool_input.get("transition")
    if isinstance(t, dict) and t.get("id") is not None:
        return str(t["id"]).strip()
    for f in ("transition_id", "transitionId"):
        v = tool_input.get(f)
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def transition_map(cwd: Path) -> dict:
    for name in CONFIG_NAMES:
        path = cwd / name
        if not path.is_file():
            continue
        try:
            import yaml  # noqa: deferred so absence falls back instead of crashing

            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            raw = (data.get("defaults") or {}).get("transition_ids")
        except Exception:
            return {}
        if not isinstance(raw, dict):
            return {}
        return {str(k).strip(): str(v).strip().lower() for k, v in raw.items()}
    return {}


def integration_branch(cwd: Path) -> str | None:
    """The branch a merge is supposed to land on."""
    head = git(["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], cwd)
    if head:
        return head  # e.g. origin/main
    for cand in ("origin/main", "origin/master", "main", "master"):
        if git(["rev-parse", "--verify", "--quiet", cand], cwd):
            return cand
    return None


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    # Reconhecimento por EFEITO, nao por nome de ferramenta. O nome MCP so
    # cobria MCP; a CLI `twg` chega como Bash e passava calada por aqui.
    _mut = J.classify(payload)
    if _mut is None:
        sys.exit(0)
    # A opacidade se checa ANTES de filtrar por tipo: uma mutacao que nao da
    # para ler pode ser justamente a que este gate guarda. Filtrar primeiro
    # deixava `twg api ... -X POST` escapar por nao ser classificavel.
    if _mut["opaque"]:
        J.block(_mut, "merge-truth-gate")
    if _mut["kind"] != "transition":
        sys.exit(0)

    tool_input = _mut["tool_input"]
    key = extract_key(tool_input)
    if not key:
        sys.exit(0)

    cwd = Path(payload.get("cwd") or os.getcwd()).resolve()
    tid = extract_transition_id(tool_input)
    # A CLI aceita o NOME do status no lugar do id. O nome vira chave lógica
    # pelo status_map ("Concluído" -> done); so baixar a caixa deixava passar
    # qualquer fechamento cujo nome nao fosse literalmente "done".
    if _mut["target_status"]:
        target = J.logical_status(_mut["target_status"], cwd)
    else:
        target = transition_map(cwd).get(tid) if tid else None
    if target not in CLOSING_TARGETS:
        # Not a close. Every other movement is somebody else's gate.
        sys.exit(0)

    if git(["rev-parse", "--git-dir"], cwd) is None:
        sys.exit(0)

    branch = integration_branch(cwd)
    if not branch:
        sys.exit(0)

    on_branch = git(["log", branch, "--grep", key, "--oneline", "-n", "5"], cwd)
    if on_branch:
        # Merged. Hand the agent the fact the closing comment should carry,
        # so the summary stops being a snapshot nobody revisits.
        print(
            f"[merge-truth-gate] {key} is on {branch}:\n{on_branch}\n"
            f"State this in the closing comment — the sha, not 'pending merge'.",
        )
        sys.exit(0)

    anywhere = git(["log", "--all", "--grep", key, "--oneline", "-n", "5"], cwd)
    if not anywhere:
        # No code carries this key. A decision/spike/docs card closes freely.
        sys.exit(0)

    print(
        f"[merge-truth-gate] BLOCKED: closing {key}, but its code is NOT on {branch}.\n"
        f"  Commits carrying {key} exist only outside the integration branch:\n"
        + "".join(f"    {line}\n" for line in anywhere.splitlines())
        + f"  A card closed here is exactly how the board starts lying: the Implementation\n"
        f"  Summary was written before the merge, says 'pending merge' forever, and the\n"
        f"  next reader — human or agent — repeats it as fact.\n"
        f"  Do ONE of:\n"
        f"    - merge the work into {branch}, then close (the gate will then print the sha\n"
        f"      for your closing comment);\n"
        f"    - leave the card open, which is the truth while the code is unmerged.\n"
        f"  Do not close it and 'fix the comment later'. Later is what produced the six\n"
        f"  stale cards this gate exists for.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
