#!/usr/bin/env python3
"""Regression tests: the feedback-nudge hook's marker is not versioned.

## Why this test exists

The hook `common/hooks/feedback-nudge.py` writes to `.claude/feedback-nudge` the id
of the session that already received the warning, to warn only once per session. It is
runtime state of this machine, rewritten every session — but it was versioned, and
two worktrees that rewrote it caused a conflict in merge 3f4fe2e (deviations.md,
2026-09-26).

The test charges for both halves of the fix, on the surface where the problem
shows up (the `git status` of whoever is going to commit):

- in this repo, the file is not in the index and `.gitignore` ignores it;
- in a repo with this one's `.gitignore`, the real hook fires, writes the
  marker, and `git status` stays clean.

Run: python3 tests/test_feedback_nudge_outside_git.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "feedback-nudge.py"
MARKER = ".claude/feedback-nudge"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True)


def test_repo_does_not_version_the_marker():
    listed = git(REPO, "ls-files", "--", MARKER).stdout.strip()
    check("marcador fora do índice do repo", listed == "", listed)
    ignored = git(REPO, "check-ignore", "-q", "--no-index", MARKER)
    check("o .gitignore do repo ignora o marcador", ignored.returncode == 0,
          f"exit {ignored.returncode}")


def test_hook_writes_and_status_stays_clean():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        git(root, "init", "-q")
        git(root, "config", "user.email", "t@t")
        git(root, "config", "user.name", "t")
        (root / ".gitignore").write_text(
            (REPO / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8")
        git(root, "add", ".gitignore")
        git(root, "commit", "-qm", "base")

        payload = {"prompt": "esse hook é irritante, não gosto dele",
                   "session_id": "sessao-teste", "cwd": str(root)}
        r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                           capture_output=True, text=True, cwd=root)
        check("o hook disparou o aviso", "feedback-capture" in r.stdout,
              r.stdout[-300:] + r.stderr[-300:])
        file = root / MARKER
        check("o hook gravou o marcador",
              file.exists() and file.read_text().strip() == "sessao-teste")
        status = git(root, "status", "--porcelain").stdout.strip()
        check("git status limpo depois do hook", status == "", status)


def main():
    print("feedback-nudge — marcador fora do git\n")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"{name}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
