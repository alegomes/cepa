#!/usr/bin/env python3
"""Regression tests for the .claude/ artifact rescue on worktree removal.

No third-party deps — run with `python3 tests/test_worktree_artifact_rescue.py`.
Exits non-zero on first failure.

Guards the loss found on 2026-08-10: a WEGO execution plan (10 prioritized
follow-ups) vanished when its session worktree was reaped. Root cause is that
an IGNORED file is invisible to every guard on the removal path —
`git status --porcelain` doesn't list it (so is_dirty() reads clean and the
WIP-autosave never fires) and `git worktree remove` deletes it returning 0 even
WITHOUT --force. Test 1 pins that premise; the rest pin the net.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "common" / "hooks"))
import _wtlib as L  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def git(args, cwd):
    return subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True,
                          text=True)


def make_repo(root: Path, ignore_claude=True):
    """A repo + one session worktree, with the artifacts a real run leaves."""
    r, w = root / "r", root / "w"
    r.mkdir(parents=True)
    git(["init", "-q", "."], r)
    git(["config", "user.email", "t@t"], r)
    git(["config", "user.name", "t"], r)
    (r / ".gitignore").write_text(".claude\n" if ignore_claude else "*.log\n")
    git(["add", ".gitignore"], r)
    git(["commit", "-qm", "init"], r)
    git(["worktree", "add", "-q", str(w), "-b", "session/todo"], r)

    art = w / ".claude"
    (art / "programs" / "WEGO").mkdir(parents=True)
    (art / "programs" / "WEGO" / "plan.yaml").write_text("items: [WEGO-1992]\n")
    (art / "proof").mkdir()
    (art / "proof" / "WEGO-2001.yaml").write_text("verdict: PROVEN\n")
    (art / "sessions").mkdir()
    (art / "sessions" / "abc.json").write_text("{}\n")
    (art / "last-build.json").write_text("{}\n")
    return r, w


def test_ignored_file_dies_silently(tmp):
    """The premise: this is why the net has to exist at all."""
    r, w = make_repo(Path(tmp) / "premise")
    status = git(["status", "--porcelain"], w).stdout
    check("ignored artifact leaves the worktree looking clean", status == "",
          f"status={status!r}")
    check("is_dirty agrees it is clean", not L.is_dirty(str(w)))
    res = git(["worktree", "remove", str(w)], r)
    check("`worktree remove` WITHOUT --force succeeds anyway",
          res.returncode == 0, res.stderr)
    check("and the plan is gone",
          not (w / ".claude" / "programs" / "WEGO" / "plan.yaml").exists())


def test_doomed_lists_artifacts_and_skips_ephemeral(tmp):
    r, w = make_repo(Path(tmp) / "doomed")
    doomed = L.doomed_artifacts(str(w))
    check("plan is listed", ".claude/programs/WEGO/plan.yaml" in doomed, doomed)
    check("proof is listed", ".claude/proof/WEGO-2001.yaml" in doomed, doomed)
    check("sessions/ is skipped",
          not any("sessions/" in d for d in doomed), doomed)
    check("last-build.json is skipped",
          ".claude/last-build.json" not in doomed, doomed)


def test_tracked_artifacts_are_not_rescued(tmp):
    """A repo that tracks .claude (like cepa) needs no rescue — commits hold it."""
    r, w = make_repo(Path(tmp) / "tracked", ignore_claude=False)
    git(["add", "-A", ".claude"], w)
    git(["commit", "-qm", "track artifacts"], w)
    doomed = L.doomed_artifacts(str(w))
    check("tracked artifacts are left alone", doomed == [], doomed)


def test_rescue_survives_removal(tmp):
    r, w = make_repo(Path(tmp) / "rescue")
    saved = L.rescue_artifacts(str(w), str(r), "session/todo")
    check("rescue reports what it saved",
          ".claude/programs/WEGO/plan.yaml" in saved, saved)
    res = git(["worktree", "remove", str(w)], r)
    check("worktree removal still succeeds", res.returncode == 0, res.stderr)

    kept = r / ".claude" / "rescued" / "session-todo"
    plan = kept / "programs" / "WEGO" / "plan.yaml"
    check("plan survived the removal", plan.exists())
    check("plan content is intact",
          plan.exists() and plan.read_text() == "items: [WEGO-1992]\n")
    check("proof survived too", (kept / "proof" / "WEGO-2001.yaml").exists())
    check("ephemeral state was not dragged along",
          not (kept / "last-build.json").exists())


def test_rescue_never_clobbers_the_live_plan(tmp):
    """The main worktree usually has its OWN plan for the same program."""
    r, w = make_repo(Path(tmp) / "clobber")
    live = r / ".claude" / "programs" / "WEGO"
    live.mkdir(parents=True)
    (live / "plan.yaml").write_text("items: [WEGO-1437]\n")

    L.rescue_artifacts(str(w), str(r), "session/todo")
    check("the live plan is untouched",
          (live / "plan.yaml").read_text() == "items: [WEGO-1437]\n")
    rescued = (r / ".claude" / "rescued" / "session-todo" / "programs" /
               "WEGO" / "plan.yaml")
    check("the rescued one sits beside it, not on it",
          rescued.exists() and rescued.read_text() == "items: [WEGO-1992]\n")


def test_rescued_dirs_reports_for_session_start(tmp):
    r, w = make_repo(Path(tmp) / "report")
    check("nothing to announce before a rescue", L.rescued_dirs(str(r)) == [])
    L.rescue_artifacts(str(w), str(r), "session/todo")
    got = L.rescued_dirs(str(r))
    check("rescue is announceable at SessionStart",
          got == [("session-todo", 2)], got)


def test_cli_rescues_on_command_removal_path(tmp):
    """The gap of 2026-08-16: worktree-merge/discard run a raw `git worktree
    remove`, bypassing session-registry's in-process rescue. The commands now
    call `python3 _wtlib.py rescue <worktree>` first — pin that entry point."""
    r, w = make_repo(Path(tmp) / "cli")
    res = subprocess.run(
        [sys.executable, str(REPO / "common" / "hooks" / "_wtlib.py"),
         "rescue", str(w)], capture_output=True, text=True)
    check("CLI exits 0", res.returncode == 0, res.stderr)
    check("CLI names what it saved",
          "programs/WEGO/plan.yaml" in res.stdout, res.stdout)
    res2 = git(["worktree", "remove", str(w)], r)
    check("subsequent raw removal still succeeds",
          res2.returncode == 0, res2.stderr)
    plan = (r / ".claude" / "rescued" / "session-todo" / "programs" / "WEGO"
            / "plan.yaml")
    check("plan survived the command-path removal", plan.exists())


def test_cli_refuses_the_main_worktree(tmp):
    r, _ = make_repo(Path(tmp) / "cli-main")
    res = subprocess.run(
        [sys.executable, str(REPO / "common" / "hooks" / "_wtlib.py"),
         "rescue", str(r)], capture_output=True, text=True)
    check("CLI refuses to 'rescue' the main worktree onto itself",
          res.returncode == 2, f"rc={res.returncode} {res.stdout}")
    check("and explains why", "main worktree" in res.stderr, res.stderr)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        for fn in (test_ignored_file_dies_silently,
                   test_doomed_lists_artifacts_and_skips_ephemeral,
                   test_tracked_artifacts_are_not_rescued,
                   test_rescue_survives_removal,
                   test_rescue_never_clobbers_the_live_plan,
                   test_rescued_dirs_reports_for_session_start,
                   test_cli_rescues_on_command_removal_path,
                   test_cli_refuses_the_main_worktree):
            print(f"\n{fn.__name__}")
            fn(tmp)
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s): {', '.join(FAILURES)}")
        return 1
    print("\nall green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
