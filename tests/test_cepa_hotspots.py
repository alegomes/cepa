#!/usr/bin/env python3
"""Regression tests for common/bin/cepa-hotspots.

No third-party deps — run with `python3 tests/test_cepa_hotspots.py`.
Exits non-zero on first failure.

Guards the two acceptance criteria from docs/spec/planejador-de-lotes-
paralelos.md that name this script (CS-2, CS-3):
  - a fixture repo with a planted conflict points at the right file, ranked
    by how many conflicting merge pairs it explains;
  - a repo with fewer real merge pairs than --min-pairs comes back with an
    EMPTY list and the exact "histórico insuficiente: N pares, mínimo M"
    message — never a heuristic dressed up as a measurement.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOTSPOTS = REPO / "common" / "bin" / "cepa-hotspots"

FAILURES = []


def run_hotspots(repo, extra=None):
    cmd = [sys.executable, str(HOTSPOTS), str(repo)] + (extra or [])
    return subprocess.run(cmd, capture_output=True, text=True)


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def git(repo, *args, check_rc=True):
    r = subprocess.run(["git", "-C", str(repo)] + list(args),
                        capture_output=True, text=True)
    if check_rc and r.returncode != 0:
        raise RuntimeError(f"git {args} failed: {r.stderr}")
    return r


def write(repo, path, content):
    p = repo / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def make_conflict_repo(tmp, n_merges=6):
    """A repo whose history has N real merge commits that all conflict on the
    same file (cartorio.txt) — the planted "arquivo-cartório"."""
    repo = Path(tmp) / "r"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@t.com")
    git(repo, "config", "user.name", "t")

    write(repo, "cartorio.txt", "base\n")
    write(repo, "other.txt", "base\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")

    for i in range(n_merges):
        cur = git(repo, "rev-parse", "HEAD").stdout.strip()

        git(repo, "checkout", "-qb", f"l{i}", cur)
        write(repo, "cartorio.txt", f"base\nleft-{i}\n")
        git(repo, "add", "cartorio.txt")
        git(repo, "commit", "-qm", f"left {i}")

        git(repo, "checkout", "-qb", f"r{i}", cur)
        write(repo, "cartorio.txt", f"base\nright-{i}\n")
        git(repo, "add", "cartorio.txt")
        git(repo, "commit", "-qm", f"right {i}")

        git(repo, "checkout", "-q", f"l{i}")
        merged = subprocess.run(["git", "-C", str(repo), "merge", "--no-edit",
                                  f"r{i}"], capture_output=True, text=True)
        assert merged.returncode != 0, "expected a real conflict on cartorio.txt"
        write(repo, "cartorio.txt", f"resolved-{i}\n")
        git(repo, "add", "cartorio.txt")
        git(repo, "commit", "-qm", f"merge {i}")

    return repo


def make_sparse_repo(tmp):
    """A repo with a couple of commits and no merges at all."""
    repo = Path(tmp) / "r"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@t.com")
    git(repo, "config", "user.name", "t")
    write(repo, "a.txt", "1\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "one")
    write(repo, "a.txt", "2\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "two")
    return repo


def main():
    with tempfile.TemporaryDirectory() as tmp:
        # CS-2: planted conflict is found and ranked
        repo = make_conflict_repo(tmp, n_merges=6)
        r = run_hotspots(repo, ["--min-pairs", "5"])
        check("planted conflict repo exits 0", r.returncode == 0, r.stdout + r.stderr)
        check("cartorio.txt named as the top hotspot",
              "cartorio.txt" in r.stdout.splitlines()[
                  next(i for i, l in enumerate(r.stdout.splitlines()) if "×" in l)
              ] if "×" in r.stdout else False, r.stdout)

        r_json = run_hotspots(repo, ["--min-pairs", "5", "--json"])
        import json
        data = json.loads(r_json.stdout)
        check("json: sufficient_history true", data["sufficient_history"] is True, data)
        check("json: pairs == 6", data["pairs"] == 6, data)
        check("json: top hotspot is cartorio.txt",
              bool(data["hotspots"]) and data["hotspots"][0]["path"] == "cartorio.txt",
              data)
        check("json: cartorio.txt explains all 6 conflicting pairs",
              bool(data["hotspots"]) and data["hotspots"][0]["conflicting_pairs"] == 6,
              data)

        # a repo with unrelated single-file conflicts should never crash and
        # should still terminate with a valid exit code
        r_limit = run_hotspots(repo, ["--min-pairs", "5", "--limit", "1", "--json"])
        data_limit = json.loads(r_limit.stdout)
        check("--limit 1 caps the list", len(data_limit["hotspots"]) <= 1, data_limit)

        # CS-3: insufficient history never fabricates a list
        sparse_tmp = tempfile.mkdtemp(dir=tmp)
        sparse = make_sparse_repo(sparse_tmp)
        r_sparse = run_hotspots(sparse, ["--min-pairs", "3"])
        check("sparse repo exits 1 (insufficient)", r_sparse.returncode == 1,
              r_sparse.stdout + r_sparse.stderr)
        check("sparse repo names the exact shortfall message",
              "histórico insuficiente: 0 pares, mínimo 3" in r_sparse.stdout,
              r_sparse.stdout)

        r_sparse_json = run_hotspots(sparse, ["--min-pairs", "3", "--json"])
        data_sparse = json.loads(r_sparse_json.stdout)
        check("sparse repo json: sufficient_history false",
              data_sparse["sufficient_history"] is False, data_sparse)
        check("sparse repo json: hotspots empty", data_sparse["hotspots"] == [],
              data_sparse)

        # non-repo path is a hard error, not a silent empty list
        not_a_repo = Path(tempfile.mkdtemp(dir=tmp)) / "not-a-repo"
        not_a_repo.mkdir()
        r_bad = run_hotspots(not_a_repo)
        check("non-git dir exits 2", r_bad.returncode == 2, r_bad.stdout + r_bad.stderr)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
