#!/usr/bin/env python3
"""Regression test: auto_clean removed the worktree and branch of two LIVE
sessions on 2026-11-24 (queue item `auto-clean-nao-apaga-sessao-viva`,
feedback fb-20261124-6 / -7).

Chain of the bug:
  1. session-heartbeat.py and session-subject.py run in parallel on
     UserPromptSubmit; each does find_entry + mutate + write_entry on the same
     `.claude/sessions/<id>.json`. write_entry used `write_text` (truncate +
     write, no temp file), so two writers of different lengths left trailing
     garbage: invalid JSON.
  2. read_entries skips invalid JSON silently, find_entry returns None for it.
  3. classify sets alive=False when it finds no entry for a worktree.
  4. auto_clean removes any clean, zero-ahead session worktree that is not alive.

Contract guarded here:
  A. write_entry is atomic: concurrent writers of different sizes never expose
     invalid JSON to a reader; temp files never match read_entries' `*.json`
     glob and none are left behind; a write that dies midway leaves the
     previous content intact.
  B. A registry file that exists but cannot be parsed counts as a live session:
     classify does not say alive=False, auto_clean keeps worktree and branch,
     prune_dead does not delete the file.
  C. A worktree with no readable registry and no tombstone is not removed.
     Counter-case (must stay as today): a readable dead entry, pruned by
     prune_dead (which leaves a tombstone) and then auto_clean, in the same
     order session-registry.py runs them, IS removed.

Run with `python3 tests/test_auto_clean_keeps_live_session.py`.
"""

import builtins
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "common" / "hooks"
sys.path.insert(0, str(HOOKS))

from _isolated_telemetry import isolate

isolate()

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def git(*args, cwd):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   cwd=cwd, check=True, capture_output=True)


def branch_exists(repo, branch):
    return subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
                          cwd=repo, capture_output=True).returncode == 0


def dead_pid():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def iso(delta=timedelta(0)):
    return (datetime.now(timezone.utc) - delta).isoformat(timespec="seconds")


def make_repo(base: Path, name: str):
    repo = base / name
    repo.mkdir()
    git("init", "-q", "-b", "main", cwd=repo)
    git("commit", "-q", "--allow-empty", "-m", "init", cwd=repo)
    # Real projects gitignore .claude/, otherwise the registry would make the
    # worktree "dirty" and auto_clean would (rightly) leave it alone.
    (repo / ".git" / "info" / "exclude").write_text(".claude/\n")
    return repo


def add_wt(repo: Path, base: Path, name: str):
    """A clean, zero-commits-ahead session worktree."""
    wt = base / f"wt-{name}"
    git("worktree", "add", "-q", "-b", f"session/{name}", str(wt), cwd=repo)
    sdir = repo / ".claude" / "sessions"
    sdir.mkdir(parents=True, exist_ok=True)
    return wt, sdir


def entry_for(name: str, sid: str, wt: Path, **over):
    e = {"session_id": sid, "pid": os.getpid(), "hostname": socket.gethostname(),
         "cwd": str(wt), "worktree_path": str(wt), "branch": f"session/{name}",
         "is_session_worktree": True, "base_branch": "main",
         "started_at": iso(), "last_seen": iso()}
    e.update(over)
    return e


# Child process: find_entry + mutate + write_entry in a loop, payload of a
# given size (the two children use very different sizes, like heartbeat vs
# subject writing different-length JSON to the same file).
CHILD = r"""
import sys
sys.path.insert(0, sys.argv[1])
import _wtlib as L
root, key, size, rounds = sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
for i in range(rounds):
    e = L.find_entry(root, key) or {}
    e["session_id"] = key
    e["pad"] = "x" * size
    e["n"] = i
    L.write_entry(root, key, e)
"""


class _HalfWriter:
    """Wraps a file opened for writing: the first write lands half of the data
    and then raises, simulating a process that dies midway through a write."""

    def __init__(self, f):
        self._f = f

    def write(self, data):
        self._f.write(data[: max(1, len(data) // 2)])
        self._f.flush()
        raise OSError("simulated crash midway through the write")

    def __getattr__(self, name):
        return getattr(self._f, name)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self._f.close()
        return False


def part_a(base: Path):
    print("A. write_entry is atomic")
    import _wtlib as L
    root = base / "a-root"
    sdir = root / ".claude" / "sessions"
    sdir.mkdir(parents=True)
    key = "aaaaaaaa-race"
    target = sdir / f"{key}.json"
    L.write_entry(str(root), key, {"session_id": key, "pad": "y" * 10})

    rounds = 400
    procs = [subprocess.Popen([sys.executable, "-c", CHILD, str(HOOKS), str(root), key, str(size), str(rounds)])
             for size in (6000, 20)]
    bad = 0
    reads = 0
    while any(p.poll() is None for p in procs):
        try:
            txt = target.read_text(encoding="utf-8")
        except OSError:
            continue
        reads += 1
        try:
            json.loads(txt)
        except ValueError:
            bad += 1
    for p in procs:
        p.wait()
    check("concurrent writers: reader never saw invalid JSON", bad == 0,
          f"({bad} invalid reads out of {reads})")
    try:
        json.loads(target.read_text(encoding="utf-8"))
        final_ok = True
    except ValueError as exc:
        final_ok = False
        final_err = str(exc)
    check("concurrent writers: final file is valid JSON", final_ok,
          "" if final_ok else f"({final_err})")
    check("no temp leftovers in the sessions dir after the writes",
          sorted(p.name for p in sdir.iterdir()) == [target.name],
          str(sorted(p.name for p in sdir.iterdir())))

    # A temp file dropped mid-write must never be read as a session.
    sdir2 = base / "a-root2" / ".claude" / "sessions"
    sdir2.mkdir(parents=True)
    L.write_entry(str(base / "a-root2"), "bbbbbbbb-one", {"session_id": "bbbbbbbb-one"})
    names = {p.name for p in sdir2.iterdir()}
    read_names = {f.name for f, _ in L.read_entries(str(base / "a-root2"))}
    check("read_entries only sees the real entry (temp names do not match *.json)",
          read_names == {"bbbbbbbb-one.json"} and names == {"bbbbbbbb-one.json"},
          f"dir={sorted(names)} read={sorted(read_names)}")

    # Deterministic: a write that dies midway leaves the previous content intact.
    root3 = base / "a-root3"
    L.write_entry(str(root3), "cccccccc-crash", {"session_id": "cccccccc-crash", "v": "old"})
    f3 = root3 / ".claude" / "sessions" / "cccccccc-crash.json"
    before = f3.read_text(encoding="utf-8")

    real_open, real_io_open, real_wt, real_popen, real_fdopen = (
        builtins.open, io.open, Path.write_text, Path.open, os.fdopen)

    def wrap_open(opener):
        def inner(*a, **kw):
            f = opener(*a, **kw)
            mode = kw.get("mode") or (a[1] if len(a) > 1 else "r")
            return _HalfWriter(f) if any(c in str(mode) for c in "wax+") else f
        return inner

    def half_write_text(self, data, *a, **kw):
        kw.pop("newline", None)
        with real_open(self, "w", encoding=kw.get("encoding") or "utf-8") as f:
            f.write(data[: max(1, len(data) // 2)])
        raise OSError("simulated crash midway through the write")

    def path_open(self, mode="r", *a, **kw):
        f = real_popen(self, mode, *a, **kw)
        return _HalfWriter(f) if any(c in mode for c in "wax+") else f

    builtins.open = wrap_open(real_open)
    io.open = wrap_open(real_io_open)
    os.fdopen = wrap_open(real_fdopen)
    Path.write_text = half_write_text
    Path.open = path_open
    try:
        try:
            L.write_entry(str(root3), "cccccccc-crash", {"session_id": "cccccccc-crash", "v": "new" * 50})
        except Exception:  # noqa: BLE001 — the crash may surface or be swallowed
            pass
    finally:
        builtins.open, io.open, os.fdopen = real_open, real_io_open, real_fdopen
        Path.write_text, Path.open = real_wt, real_popen
    after = f3.read_text(encoding="utf-8")
    check("a write that dies midway leaves the previous content intact",
          after == before, f"(file now: {after[:80]!r})")
    left = sorted(p.name for p in f3.parent.iterdir())
    check("...and leaves no temp file behind (only <key>.json in the dir)",
          left == [f3.name], str(left))


def part_b(base: Path):
    print("B. an unreadable registry file counts as a live session")
    import _wtlib as L
    repo = make_repo(base, "b-main")
    wt, sdir = add_wt(repo, base, "x")
    f = sdir / "bbbbbbbb-garbage.json"
    # Dead pid and old last_seen on purpose: only the unreadability should
    # decide here. Trailing garbage after the final `}` is the observed damage.
    e = entry_for("x", "bbbbbbbb-garbage", wt, pid=dead_pid(),
                  started_at=iso(timedelta(hours=72)), last_seen=iso(timedelta(hours=72)))
    f.write_text(json.dumps(e, indent=2) + '\n  "tail": 1\n}', encoding="utf-8")
    try:
        json.loads(f.read_text())
        check("fixture: the registry file really is invalid JSON", False)
    except ValueError:
        check("fixture: the registry file really is invalid JSON", True)
    raw_before = f.read_text()

    info = [i for i in L.classify(str(repo)) if i["branch"] == "session/x"]
    check("classify does not say alive=False for the unreadable-registry worktree",
          len(info) == 1 and info[0]["alive"] is True, str(info))
    L.prune_dead(str(repo))
    check("prune_dead does not delete the unreadable file",
          f.exists() and f.read_text() == raw_before)
    removed = L.auto_clean(str(repo), by_session="newcomer")
    check("auto_clean keeps the worktree directory", wt.is_dir(), f"(removed={removed})")
    check("auto_clean keeps the branch", branch_exists(repo, "session/x"), f"(removed={removed})")


def part_b_horizon(base: Path):
    print("B. horizon: an unreadable file older than STALE_HOURS no longer protects")
    import _wtlib as L
    repo = make_repo(base, "bh-main")
    wt, sdir = add_wt(repo, base, "h")
    f = sdir / "hhhhhhhh-old.json"
    f.write_text('{"session_id": "hhhhhhhh-old"} trailing garbage', encoding="utf-8")
    old = time.time() - (L.STALE_HOURS + 1) * 3600
    os.utime(f, (old, old))
    check("unreadable_recent ignores the stale file", L.unreadable_recent(str(repo)) == [])
    info = [i for i in L.classify(str(repo)) if i["branch"] == "session/h"]
    check("classify: stale unreadable file does not make the worktree alive",
          len(info) == 1 and info[0]["alive"] is False
          and info[0]["alive_reason"] == "no-entry", str(info))
    removed = L.auto_clean(str(repo), by_session="newcomer")
    check("...but with no tombstone either, rule C still keeps the worktree",
          wt.is_dir() and branch_exists(repo, "session/h"), f"(removed={removed})")


def part_c(base: Path):
    print("C. no readable registry and no tombstone: not removed")
    import _wtlib as L
    repo = make_repo(base, "c-main")
    wt, sdir = add_wt(repo, base, "y")
    check("fixture: no registry file and no tombstone",
          not list(sdir.glob("*.json")) and not list(sdir.glob("*.gone")))
    removed = L.auto_clean(str(repo), by_session="newcomer")
    check("auto_clean keeps a worktree with no registry and no tombstone",
          wt.is_dir() and branch_exists(repo, "session/y"), f"(removed={removed})")

    print("C. counter-case: readable dead entry (prune_dead then auto_clean) is still removed")
    repo2 = make_repo(base, "c2-main")
    wt2, sdir2 = add_wt(repo2, base, "z")
    f2 = sdir2 / "dddddddd-dead.json"
    f2.write_text(json.dumps(entry_for("z", "dddddddd-dead", wt2, pid=dead_pid(),
                                       started_at=iso(timedelta(hours=72)),
                                       last_seen=iso(timedelta(hours=72)))))
    # Same order as session-registry.py: prune_dead(root, keep_key=<new session>)
    # first (deletes the entry, leaves a .gone tombstone), then auto_clean.
    L.prune_dead(str(repo2), keep_key="newcomer")
    check("fixture: prune_dead deleted the entry and left a tombstone",
          not f2.exists() and (sdir2 / "dddddddd-dead.gone").exists())
    removed = L.auto_clean(str(repo2), by_session="newcomer")
    check("auto_clean still removes the worktree of a readable dead session",
          not wt2.exists() and "session/z" in removed, f"(removed={removed})")
    check("...and its branch", not branch_exists(repo2, "session/z"))


def part_next_json(base: Path):
    print("B. an invalid *.next.json is not a session: it does not protect")
    import _wtlib as L
    repo = make_repo(base, "nj-main")
    wt, sdir = add_wt(repo, base, "nj")
    f = sdir / "something.next.json"
    f.write_text('{"next": broken', encoding="utf-8")   # invalid, mtime = now
    check("unreadable_recent does not list the invalid .next.json",
          L.unreadable_recent(str(repo)) == [], str(L.unreadable_recent(str(repo))))
    info = [i for i in L.classify(str(repo)) if i["branch"] == "session/nj"]
    check("classify: no alive_reason=unreadable-registry because of a .next.json",
          len(info) == 1 and info[0]["alive_reason"] != "unreadable-registry"
          and info[0]["alive"] is False, str(info))


def part_dead_unpruned(base: Path):
    print("C. counter-case: readable dead entry NOT pruned (no tombstone) is removed")
    import _wtlib as L
    repo = make_repo(base, "du-main")
    wt, sdir = add_wt(repo, base, "du")
    f = sdir / "uuuuuuuu-dead.json"
    f.write_text(json.dumps(entry_for("du", "uuuuuuuu-dead", wt, pid=dead_pid(),
                                      started_at=iso(timedelta(hours=72)),
                                      last_seen=iso(timedelta(hours=72)))))
    check("fixture: entry present, no tombstone", f.exists() and not list(sdir.glob("*.gone")))
    removed = L.auto_clean(str(repo), by_session="newcomer")
    check("auto_clean removes the worktree of a readable dead entry",
          not wt.exists() and "session/du" in removed, f"(removed={removed})")
    check("...and its branch", not branch_exists(repo, "session/du"))


def part_hostile(base: Path):
    print("B. hostile registry content: no crash, counts as an unreadable (live) registry")
    import _wtlib as L
    cases = [("binary garbage", b"\xff\xfe\x80\x00\xc3\x28garbage"),
             ("list", b"[]"), ("string", b'"x"'), ("number", b"3"),
             ("null", b"null"), ("empty file", b""), ("directory", None)]
    for i, (label, content) in enumerate(cases):
        repo = make_repo(base, f"hs{i}-main")
        wt, sdir = add_wt(repo, base, f"hs{i}")
        f = sdir / "x.json"
        if content is None:
            f.mkdir()
        else:
            f.write_bytes(content)
        branch = f"session/hs{i}"
        try:
            info = [x for x in L.classify(str(repo)) if x["branch"] == branch]
            classify_ok = True
        except Exception as exc:  # noqa: BLE001
            info, classify_ok = [], False
            check(f"{label}: classify does not raise", False, repr(exc))
        if classify_ok:
            check(f"{label}: classify reports alive via unreadable-registry",
                  len(info) == 1 and info[0]["alive"] is True
                  and info[0]["alive_reason"] == "unreadable-registry", str(info))
        try:
            L.auto_clean(str(repo), by_session="newcomer")
            check(f"{label}: auto_clean does not raise", True)
        except Exception as exc:  # noqa: BLE001
            check(f"{label}: auto_clean does not raise", False, repr(exc))
        check(f"{label}: worktree and branch kept",
              wt.is_dir() and branch_exists(repo, branch))


def part_find_entry(base: Path):
    print("B. find_entry: hostile registry content returns None, valid object returns the dict")
    import _wtlib as L
    root = base / "fe-root"
    sdir = root / ".claude" / "sessions"
    sdir.mkdir(parents=True)
    cases = [("invalid utf-8", b"\xff\xfe\x00garbage"),
             ("trailing garbage", b'{"a": 1}garbage'),
             ("list", b"[]"), ("string", b'"x"'), ("number", b"3"),
             ("null", b"null"), ("empty file", b"")]
    for label, content in cases:
        (sdir / "k.json").write_bytes(content)
        try:
            got = L.find_entry(str(root), "k")
            check(f"find_entry {label}: returns None", got is None, repr(got))
        except Exception as exc:  # noqa: BLE001
            check(f"find_entry {label}: returns None", False, repr(exc))
    (sdir / "k.json").write_bytes(b'{"a": 1}')
    check("find_entry valid object: returns the dict",
          L.find_entry(str(root), "k") == {"a": 1})
    check("find_entry missing file: returns None", L.find_entry(str(root), "nope") is None)


def main():
    with tempfile.TemporaryDirectory() as t:
        base = Path(t).resolve()
        (base / "home").mkdir()
        os.environ["HOME"] = str(base / "home")   # _wtlib.index_* use Path.home()
        part_a(base)
        part_b(base)
        part_b_horizon(base)
        part_c(base)
        part_next_json(base)
        part_dead_unpruned(base)
        part_hostile(base)
        part_find_entry(base)

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S): {', '.join(failures)}")
        return 1
    print("all green")
    return 0


def test_auto_clean_keeps_live_session():
    failures.clear()
    assert main() == 0, failures


if __name__ == "__main__":
    sys.exit(main())
