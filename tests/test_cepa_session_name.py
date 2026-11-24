#!/usr/bin/env python3
"""`cepa` names each session after its slice, so herdr's Agents list can tell them apart.

The bug: several sessions in one herdr Space all showed the same name, because the
name comes from the first prompt (the same mode menu for everyone) and the launcher
never passed `--name` to claude. Now a session on `session/<slice>` is launched with
`claude --name <slice>`, unless the owner already passed -n/--name.

Run: python3 tests/test_cepa_session_name.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

# CEPA_UNTIL_RUN and CEPA_MENU decide whether the launcher appends the mode menu as
# the opening prompt. Inside a cepa-until round the first is set and the menu is off;
# the supervisor's full build runs without it. Dropping both makes this file run the
# same in the two places (menu on, as in the owner's terminal).
for _k in ("CEPA_PROMPT", "CEPA_PROMPT_MODO", "CEPA_LAUNCH_ID", "CLAUDE_WT_CLAIM",
           "CEPA_MODO", "CEPA_MODO_DEFAULT", "CEPA_UNTIL_RUN", "CEPA_MENU"):
    os.environ.pop(_k, None)

REPO = Path(__file__).resolve().parent.parent
CEPA = REPO / "common" / "bin" / "cepa"

# One line per call: the branch, then every argv entry, tab-separated. An entry with
# line breaks (the mode menu) is flattened, or it would read as several calls.
STUB = """#!/bin/sh
printf '%s' "$(git rev-parse --abbrev-ref HEAD)" >> "$STUB_LOG"
for a in "$@"; do printf '\\t%s' "$(printf '%s' "$a" | tr '\\n' ' ')" >> "$STUB_LOG"; done
printf '\\n' >> "$STUB_LOG"
"""
GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
failures = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + ("" if cond else f" {detail}"))
    if not cond:
        failures.append(name)


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, check=True,
                          capture_output=True, text=True).stdout.strip()


class World:
    def __init__(self, main_branch="main"):
        self.main_branch = main_branch

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name).resolve()
        self.repo = t / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", ".")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "init")
        git(self.repo, "checkout", "-q", "-B", self.main_branch)
        self.stub = t / "fakeclaude"
        self.stub.write_text(STUB)
        self.stub.chmod(0o755)
        self.log = t / "stub.log"
        self.home = t / "worktrees"
        self.telemetry = t / "telemetry"
        self.tmp_home = t / "home"
        return self

    def __exit__(self, *a):
        self.tmp.cleanup()

    def cepa(self, *args, cwd=None):
        env = {**os.environ, "CLAUDE_WT_CLAUDE_BIN": str(self.stub), "CEPA_PREFLIGHT": "off",
               "CEPA_ENCADEAR": "off", "CEPA_WORKTREE_HOME": str(self.home),
               "CEPA_TELEMETRY_DIR": str(self.telemetry), "STUB_LOG": str(self.log),
               "HOME": str(self.tmp_home)}
        return subprocess.run([str(CEPA), "--mode", "construction", *args],
                              cwd=cwd or self.repo, env=env, capture_output=True, text=True,
                              timeout=60, stdin=subprocess.DEVNULL)

    def calls(self):
        """[(branch, [argv...])] for each fake-claude call."""
        if not self.log.exists():
            return []
        out = []
        for line in self.log.read_text().splitlines():
            branch, *argv = line.split("\t")
            # the launcher's own permission flag is not what this file is about
            out.append((branch, [a for a in argv if a != "--dangerously-skip-permissions"]))
        return out


def names(argv):
    return [argv[i + 1] for i, a in enumerate(argv[:-1]) if a in ("-n", "--name")]


def t_two_sessions_get_their_own_name():
    with World() as w:
        r1 = w.cepa("-s", "alpha", "do it")
        r2 = w.cepa("-s", "beta", "do it")
        c = w.calls()
        got = [names(a) for _, a in c]
        check("each session gets --name <its own slice>",
              got == [["alpha"], ["beta"]], f"{c} {r1.stderr} {r2.stderr}")
        check("the two names differ", len(got) == 2 and got[0] != got[1], str(got))


def t_session_opened_with_no_prompt_gets_name_and_menu():
    """The owner's own case: `cepa -s alpha` and nothing else, so the launcher appends
    the mode menu, which is the same text for every session."""
    with World() as w:
        r = w.cepa("-s", "alpha")
        c = w.calls()
        argv = c[0][1] if c else []
        check("with the mode menu as opening prompt, the session is still named after its slice",
              len(c) == 1 and argv[:2] == ["--name", "alpha"] and len(argv) == 3
              and argv[2].startswith("[menu do modo]"), f"{c} {r.stderr}")


def t_rest_of_owner_args_still_reach_claude():
    with World() as w:
        r = w.cepa("-s", "alpha", "--model", "opus", "do it")
        c = w.calls()
        argv = c[0][1] if c else []
        check("injected --name is followed by the owner's flag and prompt, intact and in order",
              len(c) == 1 and argv == ["--name", "alpha", "--model", "opus", "do it"],
              f"{c} {r.stderr}")


def t_owner_name_is_kept():
    for flag in (["-n", "foo"], ["--name", "foo"], ["--name=foo"]):
        with World() as w:
            r = w.cepa("-s", "alpha", *flag)
            c = w.calls()
            argv = c[0][1] if c else []
            check(f"owner {' '.join(flag)} forwarded, no second --name",
                  len(c) == 1 and argv[:len(flag)] == flag
                  and sum(a in ("-n", "--name") or a.startswith("--name=") for a in argv) == 1,
                  f"{c} {r.stderr}")


def t_no_session_branch_no_name():
    with World("main") as w:
        r = w.cepa("do it")
        c = w.calls()
        check("outside session/* no --name is injected",
              len(c) == 1 and c[0][0] == "main" and c[0][1] == ["do it"], f"{c} {r.stderr}")


for fn in (t_two_sessions_get_their_own_name,
           t_session_opened_with_no_prompt_gets_name_and_menu,
           t_rest_of_owner_args_still_reach_claude,
           t_owner_name_is_kept,
           t_no_session_branch_no_name):
    fn()

print(f"\n{len(failures)} failure(s)" if failures else "\nall ok")
sys.exit(1 if failures else 0)
