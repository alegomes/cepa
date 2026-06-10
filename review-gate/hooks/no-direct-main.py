#!/usr/bin/env python3
"""PreToolUse hook (Bash) — THE FENCE. Block merging/pushing straight to the
protected branch, redirect to the PR flow.

WHY THIS EXISTS
---------------
review-gate's whole point is: code reaches the main branch through a reviewed
pull request, not through a direct `git merge` / `git push`. The two commands
(/review-gate:open, /review-gate:merge) are the *path*; this hook is the
*fence* that makes the path non-optional. Without it the flow depends on
everyone remembering to use it — which is not a control.

SELF-SCOPING
------------
Only fires in repos that opted into review-gate (a `review-gate.yaml` exists at
project root). Every other repo is untouched — no false positives where the
flow isn't installed. The protected branch is `default_dest` from that config
(default "main").

WHAT IT BLOCKS (deliberately narrow, to keep false positives near zero)
-----------------------------------------------------------------------
  - `git push` whose target is the protected branch:
      git push <remote> <protected>            (explicit branch)
      git push <remote> HEAD:<protected>       (refspec)
      git push <remote> <src>:<protected>      (refspec)
      git push [<remote>]                       (bare) while ON the protected branch
  - `git merge <branch>` run WHILE ON the protected branch (local integration
    into main). NOT `git merge <protected>` on a feature branch (that updates
    your own branch — allowed). NOT `git pull` (syncing). NOT --abort/--continue.

The PR *merge* itself goes through the Bitbucket API (bin/merge-pr.sh → curl),
not `git push`/`git merge`, so it is invisible here and never blocked. Correct.

ESCAPE HATCH (deliberate, human-placed — never auto)
----------------------------------------------------
  - `.claude/allow-direct-main` marker file at project root, OR
  - env REVIEW_GATE_ALLOW_DIRECT=1
Either opts this repo (or this run) out of the fence — for bootstrap, hotfix,
or a repo where direct-to-main is genuinely the policy. Mirrors `.claude/
no-build`: the fence never decides on its own to step aside.

HONEST LIMITS (this is a guardrail, not a sandbox)
--------------------------------------------------
Parsing shell to know what git will push is undecidable. We deliberately do NOT
catch — and fail OPEN on — these (a determined caller can always reach git):
  - `git push` wrapped in a subshell `( ... )`, `bash -c '...'`, `xargs`, or
    fed through a pipe — the boundary regex won't see it.
  - env-prefixed invocations like `GIT_DIR=… git push`, or git aliases.
  - flag-value edge cases (`-o <value>`) where a value happens to equal the
    branch name.
  - when `git branch --show-current` fails (detached/broken state) the bare-push
    and local-merge checks fall open, though EXPLICIT refspec pushes to the
    protected branch are still caught (they don't depend on the current branch).
Layer A — your own discipline + the `/review-gate:open` habit — is the primary
control; this fence is defense-in-depth under it.

Exit codes:
  0 — allowed (out of scope, escape hatch, or not a direct-to-main op)
  2 — blocked: a direct merge/push to the protected branch
"""

import json
import os
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _rg_common as C  # noqa: E402


_PUSH_RE = re.compile(r"(?:^|\s|&&\s|;\s)git\s+push\b")
_MERGE_RE = re.compile(r"(?:^|\s|&&\s|;\s)git\s+merge\b")
_MERGE_CLEANUP = re.compile(r"--(?:abort|continue|quit)\b")


def _push_targets_protected(command, protected, current, cwd):
    """True if a `git push` in this command targets the protected branch."""
    for seg in re.split(r"(?:\|\||&&|[;|\n])", command):
        if not _PUSH_RE.search(seg):
            continue
        try:
            argv = shlex.split(seg, posix=True)
        except ValueError:
            argv = seg.split()
        # narrow to the part after 'push'
        if "push" not in argv:
            continue
        rest = argv[argv.index("push") + 1:]
        # --all / --mirror push EVERY branch (including the protected one),
        # with no refspec — they'd otherwise slip through the bare-push path.
        if any(t in ("--all", "--mirror") for t in rest):
            return True
        nonflags = [t for t in rest if not (t.startswith("-") and t != "-")]
        # remote is the first non-flag (if present); refspecs follow.
        refspecs = nonflags[1:] if len(nonflags) >= 1 else []
        if not refspecs:
            # bare `git push` / `git push <remote>` — pushes the current branch
            # to its configured push target.
            if current is not None and current == protected:
                return True
            if current is not None:
                # a feature branch whose push target IS the protected branch
                # (push.default=upstream, branch.<x>.merge=refs/heads/main).
                rc, dst = C.git(
                    ["rev-parse", "--abbrev-ref", f"{current}@{{push}}"], cwd)
                if rc == 0 and dst and (
                        dst == protected or dst.endswith(f"/{protected}")):
                    return True
            continue
        for ref in refspecs:
            # dst side of an explicit refspec, or a bare branch name == dst
            dst = ref.split(":", 1)[1] if ":" in ref else ref
            dst = dst.lstrip("+")  # force-with-lease/force prefix
            if dst in (protected, f"refs/heads/{protected}"):
                return True
    return False


def _merge_into_protected(command, protected, current):
    """True if a `git merge <branch>` runs while ON the protected branch."""
    if current is None or current != protected:
        return False
    for seg in re.split(r"(?:\|\||&&|[;|\n])", command):
        if not _MERGE_RE.search(seg):
            continue
        if _MERGE_CLEANUP.search(seg):
            continue  # --abort/--continue/--quit are cleanup, allowed
        try:
            argv = shlex.split(seg, posix=True)
        except ValueError:
            argv = seg.split()
        if "merge" not in argv:
            continue
        rest = argv[argv.index("merge") + 1:]
        nonflags = [t for t in rest if not (t.startswith("-") and t != "-")]
        # allow syncing from the remote tracking branch of protected
        if nonflags and all(
            n in (protected, f"origin/{protected}", f"refs/heads/{protected}")
            for n in nonflags
        ):
            continue
        return True
    return False


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        sys.exit(0)  # fail-open

    if payload.get("tool_name") != "Bash":
        sys.exit(0)
    command = (payload.get("tool_input") or {}).get("command", "")
    if not command.strip():
        sys.exit(0)

    cwd = Path(payload.get("cwd") or os.getcwd()).resolve()

    # Self-scoping: only repos that opted into review-gate.
    if not (cwd / "review-gate.yaml").exists():
        sys.exit(0)

    # Escape hatch.
    if (cwd / ".claude" / "allow-direct-main").exists() \
            or os.environ.get("REVIEW_GATE_ALLOW_DIRECT") == "1":
        sys.exit(0)

    protected = C.protected_branch(cwd)
    current = C.current_branch(cwd)

    push_hit = _push_targets_protected(command, protected, current, cwd)
    merge_hit = _merge_into_protected(command, protected, current)
    if not (push_hit or merge_hit):
        sys.exit(0)

    op = "push to" if push_hit else "local merge into"
    verb = "push" if push_hit else "merge"
    print(
        f"[review-gate fence] BLOCKED: direct {op} '{protected}'.\n"
        f"  Command: {command[:200]}\n"
        f"  This repo uses review-gate — code reaches '{protected}' through a\n"
        f"  reviewed pull request, not a direct {verb}.\n"
        f"  → Open the PR instead:  /review-gate:open\n"
        f"  → Merge a reviewed PR:  /review-gate:merge  (runs the QA gate first)\n"
        f"  Genuinely need the direct path (bootstrap / hotfix)? Opt out honestly:\n"
        f"  create .claude/allow-direct-main, or set REVIEW_GATE_ALLOW_DIRECT=1.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
