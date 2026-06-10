#!/usr/bin/env python3
"""PostToolUse hook (Bash) — THE NUDGE. After you push a feature branch,
gently suggest opening a PR. Never blocks; never acts on its own.

WHY THIS EXISTS
---------------
The fence (no-direct-main.py) stops the WRONG path. This removes the friction
on the RIGHT one: it spots a feature-branch push and reminds you that
/review-gate:open is right there — so opening a PR stops depending on you
remembering. It's a suggestion, not an action: "lexical proposes, model
disposes" — the hook injects a discreet note, the model decides whether to
surface it given the live conversation.

SELF-SCOPING & QUIET
--------------------
  - Only fires in repos with a review-gate.yaml at project root.
  - Only on a push of a FEATURE branch (not the protected default_dest).
  - One nudge per branch+commit: a tiny .claude/review-gate-nudge.json records
    what was last nudged, so re-pushing the same tip doesn't nag.
  - env REVIEW_GATE_NUDGE=off disables it.

Always exit 0.
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _rg_common as C  # noqa: E402


_PUSH_RE = re.compile(r"(?:^|\s|&&\s|;\s)git\s+push\b")

# Markers that mean the push did NOT land new commits on the remote. PostToolUse
# fires regardless of outcome; nudging (and recording dedup state) on a failed or
# no-op push would suppress the nudge on the successful retry (same sha).
_PUSH_FAILED = (
    "[rejected]", "failed to push", "error: src refspec", "fatal:",
    "Permission denied", "Could not read from remote", "Everything up-to-date",
)


def main():
    if os.environ.get("REVIEW_GATE_NUDGE", "").lower() == "off":
        sys.exit(0)
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        sys.exit(0)

    if payload.get("tool_name") != "Bash":
        sys.exit(0)
    command = (payload.get("tool_input") or {}).get("command", "")
    if not command.strip() or not _PUSH_RE.search(command):
        sys.exit(0)

    # Bail if the push failed or was a no-op — don't nudge, don't record state
    # (recording a failed push's sha would mute the nudge on the retry).
    resp = payload.get("tool_response")
    blob = json.dumps(resp, ensure_ascii=False) if resp is not None else ""
    if any(m in blob for m in _PUSH_FAILED):
        sys.exit(0)

    cwd = Path(payload.get("cwd") or os.getcwd()).resolve()
    if not (cwd / "review-gate.yaml").exists():
        sys.exit(0)

    protected = C.protected_branch(cwd)
    branch = C.current_branch(cwd)
    if not branch or branch == protected:
        sys.exit(0)  # detached, error, or on protected → not a feature push

    _, sha = C.git(["rev-parse", "HEAD"], cwd)

    # One nudge per branch+commit — don't nag on re-push of the same tip.
    state = cwd / ".claude" / "review-gate-nudge.json"
    try:
        last = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        last = {}
    if last.get("branch") == branch and last.get("sha") == sha:
        sys.exit(0)
    try:
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps({"branch": branch, "sha": sha}), encoding="utf-8")
    except OSError:
        pass

    msg = (
        f"[review-gate] Você acabou de empurrar a branch de feature '{branch}'. "
        f"Se ela está pronta pra revisão, o caminho é abrir um PR: sugira ao "
        f"usuário rodar /review-gate:open (roda o gate de higiene e abre o PR "
        f"para '{protected}'). É sugestão, não obrigação — se a branch ainda é "
        f"trabalho-em-progresso, ignore em silêncio. (Desliga com "
        f"REVIEW_GATE_NUDGE=off.)"
    )
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse", "additionalContext": msg}}))
    sys.exit(0)


if __name__ == "__main__":
    main()
