#!/usr/bin/env python3
"""Gate of the refactor mode (`refactor`): blocks editing an EXTERNAL test while the refactor runs.

The exit condition of Refactor has three parts (docs/modos-de-trabalho.md):
the declared budget exhausted, green build, and no external test edited. The
first two nobody can measure alone — the budget is free text and green build
already has green-or-revert. The third is mechanical, and it is the one that
matters:

    refactor reorganizes the code WITHOUT changing observable behavior.
    If the test that already passed had to change, the behavior changed.
    So it was not a refactor — it was construction, and construction demands an
    acceptance criterion and a red test BEFORE (the boundary the mode exists
    to enforce).

It blocks instead of warning on purpose: a warning arrives after the leak,
which is exactly what the modes exist to prevent. The way out is not to force
the block — it is to end the refactor and open construction with a criterion.

An INTERNAL test stays free: renaming a class forces touching its unit test,
and that is a legitimate refactor. The distinction lives in the patterns
below, overridable per repo in `.claude/external-tests` (one glob per line).

Silent outside the refactor mode. Turned off with CEPA_MODO=off.
"""

import fnmatch
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _modes  # noqa: E402

# Tests that assert observable behavior from the outside. A repo with another
# layout overrides the list in .claude/external-tests.
DEFAULT_EXTERNAL = [
    "*IT.java", "*ITCase.java", "*IntegrationTest*", "*E2E*", "*e2e*",
    "*/e2e/*", "*/integration/*", "*/integration-tests/*",
    "*/cypress/*", "*/playwright/*",
    "*_e2e_test.*", "test_e2e_*", "*/acceptance/*", "*AcceptanceTest*",
]

# `>` and `>>` that are not `>&` nor `>=`; `>=` already cost a false block in
# this repo (bash-path-lock), so the exclusion is explicit.
_REDIR = re.compile(r"""(?<![0-9&])>>?\s*(?![&=])("[^"]+"|'[^']+'|[^\s;&|<>()]+)""")
# Editors that write without redirecting — the path a Write block leaks through
# if nobody looks at Bash.
_INPLACE = re.compile(
    r"\b(?:sed\s+(?:-[^\s]*\s+)*-i|perl\s+-[^\s]*i|tee|cp|mv|install)\b\s+(.+)"
)


def repo_root(cwd):
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd,
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else cwd
    except Exception:  # noqa: BLE001
        return cwd


def active_mode(root):
    path = os.path.join(root, ".claude", "session-mode")
    if not os.path.isfile(path):
        return None, None
    try:
        with open(path, encoding="utf-8") as fh:
            data = _modes.parse_session_mode(fh.read())
    except Exception:  # noqa: BLE001
        return None, None
    # keys `mode`/`budget` (or the old `modo`/`orcamento`); the mode value
    # already comes with the new name (`reforma` -> `refactor`)
    return data.get("mode"), data.get("budget")


def patterns(root):
    override = os.path.join(root, ".claude", "external-tests")
    if os.path.isfile(override):
        try:
            with open(override, encoding="utf-8") as fh:
                pats = [ln.strip() for ln in fh
                        if ln.strip() and not ln.lstrip().startswith("#")]
            if pats:
                return pats
        except Exception:  # noqa: BLE001
            pass
    return DEFAULT_EXTERNAL


def is_external_test(path, pats):
    p = path.replace("\\", "/")
    # "/" in front so a directory pattern (*/cypress/*) also matches when the
    # directory is at the repo ROOT — without it, `cypress/x.cy.js` escapes and
    # `a/cypress/x.cy.js` does not, which is the worst kind of gate: one that
    # catches some cases and gives the impression of covering all of them.
    forms = {p, "/" + p.lstrip("/"), os.path.basename(p)}
    return next((pat for pat in pats
                 if any(fnmatch.fnmatch(f, pat) for f in forms)), None)


def targets(tool, inp):
    """Paths this call is going to write."""
    if tool in ("Edit", "Write", "NotebookEdit"):
        t = inp.get("file_path") or inp.get("notebook_path")
        return [t] if t else []
    if tool == "MultiEdit":
        t = inp.get("file_path")
        return [t] if t else []
    if tool == "Bash":
        cmd = inp.get("command") or ""
        found = [m.group(1).strip("\"'") for m in _REDIR.finditer(cmd)]
        for m in _INPLACE.finditer(cmd):
            found += [tok.strip("\"'") for tok in m.group(1).split()
                      if not tok.startswith("-")]
        return found
    return []


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        sys.exit(0)

    try:
        if os.environ.get("CEPA_MODO", "on") == "off":
            sys.exit(0)

        cwd = payload.get("cwd") or os.getcwd()
        root = repo_root(cwd)
        mode, budget = active_mode(root)
        if mode != "refactor":
            sys.exit(0)

        pats = patterns(root)
        for target in targets(payload.get("tool_name", ""),
                              payload.get("tool_input", {}) or {}):
            pat = is_external_test(target, pats)
            if not pat:
                continue
            print(
                f"[refactor-gate] BLOCKED: this session is in refactor mode and "
                f"you were about to edit an external test.\n"
                f"  Target: {target}   (matched pattern {pat!r})\n"
                + (f"  Refactor budget: {budget}\n" if budget else "")
                + f"  Refactor reorganizes the code WITHOUT changing observable "
                f"behavior. If the test that already passed needs to change, "
                f"the behavior changed — that is construction, not refactor, "
                f"and construction demands an acceptance criterion and a red "
                f"test BEFORE.\n"
                f"  What to do: record this through the off-mode-capture skill "
                f"and carry on with the refactor; or end the refactor and open "
                f"a construction session with the criterion written.\n"
                f"  If this file is not an external test, fix the list in "
                f".claude/external-tests (one glob per line).",
                file=sys.stderr,
            )
            sys.exit(2)
    except Exception as e:  # noqa: BLE001
        print(f"[refactor-gate] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
