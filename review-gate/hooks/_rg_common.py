#!/usr/bin/env python3
"""Shared helpers for the review-gate hooks (no-direct-main, push-nudge).

Single source of truth for the two things both hooks need: the git subprocess
wrapper and the review-gate.yaml "protected branch" read. Keeping these in one
place stops the fence and the nudge from drifting on what 'protected' means —
a divergence between a security fence and its companion nudge is exactly the
class of bug that hides until someone notices they disagree.
"""

import re
import subprocess
from pathlib import Path


def git(args, cwd):
    """Run `git -C <cwd> <args>`; return (returncode, stdout-stripped).
    Never raises — on any OS/subprocess error returns (1, "") so callers
    fail-open."""
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True, text=True, timeout=5,
        )
        return out.returncode, out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def current_branch(cwd):
    rc, out = git(["branch", "--show-current"], cwd)
    return out if rc == 0 and out else None


# Top-level `default_dest` ONLY — anchored at column 0 so a nested/indented key
# (e.g. `default_dest` under some other block) can't masquerade as the protected
# branch and silently misdirect the fence.
_DEST_RE = re.compile(r"^default_dest\s*:\s*(\S+)")


def protected_branch(cwd):
    """The protected branch = top-level default_dest in review-gate.yaml,
    'main' if absent/unparseable. Hand-parsed to avoid a PyYAML dependency in a
    hook."""
    try:
        for line in (Path(cwd) / "review-gate.yaml").read_text(encoding="utf-8").splitlines():
            m = _DEST_RE.match(line)
            if m:
                return m.group(1).strip().strip("\"'")
    except OSError:
        pass
    return "main"
