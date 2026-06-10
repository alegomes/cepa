#!/usr/bin/env python3
"""Shared library for the per-session worktree system.

One physical place for everything the launcher, the session hooks, and the
worktree commands need to agree on: the session registry format, PID-based
liveness, the git-worktree scan, classification (alive / dirty / unmerged /
mergeable), the safe auto-clean rule, and conflict prediction.

Registry: each session writes `.claude/sessions/<key>.json`. `<key>` is the
claude `session_id` once known; before that, the launcher writes a claim file
keyed by a generated `claim-id`, and the SessionStart hook renames it to the
session_id (handed over via the CLAUDE_WT_CLAIM env var, which survives the
launcher's `exec` and is inherited by the hook subprocess).

Entry schema (all optional except session_id/pid/cwd):
  {
    "session_id": "abc...",        # or the claim-id, pre-upgrade
    "pid": 12345,                  # the claude process (liveness probe)
    "hostname": "macbook",         # PID liveness only valid on the same host
    "cwd": "/abs/worktree",        # the working tree this session runs in
    "started_at": "2026-06-11T...",
    "last_seen": "2026-06-11T...", # bumped by session-activity on each edit
    "branch": "session/0611-1430",
    "is_session_worktree": true,   # launcher created this as an isolated wt
    "worktree_path": "/abs/repo-session-0611-1430",
    "base_branch": "main",         # fork point — where merge lands
    "base_commit": "deadbeef",
    "touched_dirs": {"billing": 12, "api": 3},  # top-level dir -> edit count
    "subject": {                   # session-subject (Tier-2) state
       "centroid": {"cache": 3, ...}, "prompts": N, "last_flag": K
    }
  }
"""

import json
import os
import re
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path

STALE_HOURS = 24

# Gitignored files copied into a fresh worktree by default (override via
# $CCW_SEED or a .claude/worktree-seed file). A fresh worktree starts without
# any gitignored files (checkout only carries tracked content), so essentials
# like .env would otherwise have to be recreated by hand and get lost on discard.
DEFAULT_SEED_GLOBS = [".env", ".env.local"]


# ── time / identity ──────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def host() -> str:
    try:
        return socket.gethostname()
    except OSError:
        return "unknown"


def pid_alive(pid) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def entry_is_live(entry: dict) -> bool:
    """Live = same host with a living PID, and not past the staleness horizon.

    Cross-host entries can't be PID-probed, so they fall back to staleness only.
    """
    same_host = entry.get("hostname") in (None, host())
    if same_host and "pid" in entry and not pid_alive(entry.get("pid")):
        return False
    stamp = entry.get("last_seen") or entry.get("started_at")
    if stamp:
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(stamp)
            if age.total_seconds() > STALE_HOURS * 3600:
                return False
        except ValueError:
            pass
    return True


# ── git plumbing ─────────────────────────────────────────────────────────

def git(args, cwd=None, timeout=15):
    """Run git; return (returncode, stdout, stderr). Never raises."""
    try:
        p = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except (OSError, subprocess.SubprocessError) as e:
        return 1, "", str(e)


def repo_root(cwd) -> str:
    rc, out, _ = git(["rev-parse", "--show-toplevel"], cwd=cwd)
    return out if rc == 0 else ""


def main_root(cwd) -> str:
    """The MAIN worktree's root, reachable from any linked worktree.

    The session registry must be shared across every worktree of a repo, but
    each worktree has its own `.claude/`. The main worktree is the one stable
    home. `--git-common-dir` resolves to the main repo's `.git` from anywhere,
    so its parent is the main worktree root. Falls back to show-toplevel.
    """
    rc, out, _ = git(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=cwd)
    if rc == 0 and out:
        common = os.path.abspath(out)
        if os.path.basename(common) == ".git":
            return os.path.dirname(common)
    return repo_root(cwd)


def current_branch(cwd) -> str:
    rc, out, _ = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
    return out if rc == 0 else ""


def current_commit(cwd) -> str:
    rc, out, _ = git(["rev-parse", "HEAD"], cwd=cwd)
    return out if rc == 0 else ""


def is_dirty(cwd) -> bool:
    rc, out, _ = git(["status", "--porcelain"], cwd=cwd)
    return rc == 0 and bool(out)


def commits_ahead(cwd, base: str, branch: str) -> int:
    """How many commits `branch` has that `base` doesn't (-1 if unknown)."""
    if not base:
        return -1
    rc, out, _ = git(["rev-list", "--count", f"{base}..{branch}"], cwd=cwd)
    try:
        return int(out) if rc == 0 else -1
    except ValueError:
        return -1


def is_merged(cwd, base: str, branch: str) -> bool:
    """True when branch has no commits base lacks (fully merged or empty)."""
    return commits_ahead(cwd, base, branch) == 0


def predict_conflict(root: str, base: str, branch: str):
    """Predict whether merging `branch` into `base` conflicts, WITHOUT touching
    the working tree. Uses `git merge-tree --write-tree` (git >= 2.38).

    Returns True (conflicts), False (clean), or None (couldn't tell)."""
    if not base:
        return None
    rc, _, err = git(["merge-tree", "--write-tree", base, branch], cwd=root)
    if rc == 0:
        return False
    if rc == 1:
        return True
    return None  # old git / unknown ref / error


# ── worktree label (free-text purpose) ─────────────────────────────────────
#
# A session worktree's purpose is stored as the branch's git *description*
# (`branch.<name>.description`), NOT in the per-session registry entry. The
# entry is deleted at SessionEnd, but a worktree outlives its session — so a
# label kept in the entry would vanish exactly when the next session needs it.
# The branch description is durable, branch-keyed, never touches the ref name,
# and git drops it automatically when the branch is deleted (merge/discard).

def branch_description(root: str, branch: str) -> str:
    """The free-text label attached to a session branch, or '' if none."""
    if not branch:
        return ""
    rc, out, _ = git(["config", f"branch.{branch}.description"], cwd=root)
    return out if rc == 0 else ""


def set_branch_description(root: str, branch: str, text: str) -> bool:
    """Set (or, with empty text, clear) a branch's label. Idempotent clear."""
    if not branch:
        return False
    if text:
        rc, _, _ = git(["config", f"branch.{branch}.description", text], cwd=root)
        return rc == 0
    rc, _, _ = git(["config", "--unset", f"branch.{branch}.description"], cwd=root)
    return rc in (0, 5)  # 5 = key absent → already clear


def subject_hint(entry: dict, n: int = 3) -> str:
    """Top-n subject terms from a live session's running vocabulary — a weak,
    auto-derived stand-in shown only while no human label exists. Empty once the
    session (and its centroid) is gone, which is fine: by then a label was due.
    """
    cent = (entry.get("subject") or {}).get("centroid") or {}
    if not cent:
        return ""
    return ", ".join(sorted(cent, key=lambda k: -cent[k])[:n])


def caption(label: str, hint: str) -> str:
    """Display suffix for a worktree's purpose: the human label if set (quoted),
    else a clearly-marked auto-guess from the subject vocabulary, else nothing.
    """
    if label:
        return f"“{label}”"
    if hint:
        return f"(assunto≈ {hint})"
    return ""


# ── registry ─────────────────────────────────────────────────────────────

def sessions_dir(root: str) -> Path:
    return Path(root) / ".claude" / "sessions"


def read_entries(root: str):
    """Return list of (path, entry-dict) for every registry json (claims too)."""
    out = []
    d = sessions_dir(root)
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.json")):
        try:
            out.append((f, json.loads(f.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def write_entry(root: str, key: str, entry: dict) -> None:
    d = sessions_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(json.dumps(entry, indent=2), encoding="utf-8")


def find_entry(root: str, key: str):
    f = sessions_dir(root) / f"{key}.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    return None


def prune_dead(root: str, keep_key: str = "") -> None:
    for f, entry in read_entries(root):
        if f.stem == keep_key:
            continue
        if not entry_is_live(entry):
            try:
                f.unlink()
            except OSError:
                pass


def same_path(a: str, b: str) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return a == b


def live_sessions_in(root: str, tree_cwd: str, exclude_key: str = ""):
    """Live entries whose cwd is `tree_cwd` (after symlink resolution)."""
    return [
        e for f, e in read_entries(root)
        if f.stem != exclude_key
        and same_path(e.get("cwd", ""), tree_cwd)
        and entry_is_live(e)
    ]


def branch_owners(root: str, branch: str, exclude_cwd: str = ""):
    """Live registry entries currently sitting on `branch`.

    A branch with a live owner is being actively worked (and possibly rewritten):
    merging it, or merging *into* it, from another session is how parallel
    sessions clobber each other. `exclude_cwd` drops the caller's own entry so a
    session never reports itself as a competing owner.
    """
    out = []
    for _, e in read_entries(root):
        if exclude_cwd and same_path(e.get("cwd", ""), exclude_cwd):
            continue
        if e.get("branch") == branch and entry_is_live(e):
            out.append(e)
    return out


# ── worktree scan / classify ─────────────────────────────────────────────

def list_worktrees(root: str):
    """Parse `git worktree list --porcelain` → [{path, branch, head}]."""
    rc, out, _ = git(["worktree", "list", "--porcelain"], cwd=root)
    if rc != 0:
        return []
    trees, cur = [], {}
    for line in out.splitlines():
        if line.startswith("worktree "):
            if cur:
                trees.append(cur)
            cur = {"path": line[len("worktree "):]}
        elif line.startswith("branch "):
            ref = line[len("branch "):]
            cur["branch"] = ref.replace("refs/heads/", "")
        elif line.startswith("HEAD "):
            cur["head"] = line[len("HEAD "):]
    if cur:
        trees.append(cur)
    return trees


def session_worktrees(root: str):
    """Worktrees on a `session/*` branch."""
    return [w for w in list_worktrees(root) if w.get("branch", "").startswith("session/")]


def age_str(stamp: str) -> str:
    if not stamp:
        return "?"
    try:
        secs = (datetime.now(timezone.utc) - datetime.fromisoformat(stamp)).total_seconds()
    except ValueError:
        return "?"
    if secs < 3600:
        return f"{int(secs // 60)}m"
    if secs < 86400:
        return f"{int(secs // 3600)}h"
    return f"{int(secs // 86400)}d"


def classify(root: str, predict=False):
    """Classify every session worktree. predict=True adds conflict prediction
    (slower — runs merge-tree per worktree)."""
    entries = read_entries(root)

    def entry_for(wt):
        for _, e in entries:
            if same_path(e.get("worktree_path", "") or e.get("cwd", ""), wt["path"]):
                return e
        return {}

    result = []
    for wt in session_worktrees(root):
        e = entry_for(wt)
        branch = wt.get("branch", "")
        base = e.get("base_branch") or default_base(root)
        ahead = commits_ahead(root, base, branch)
        dirty = is_dirty(wt["path"])
        touched = e.get("touched_dirs") or {}
        info = {
            "path": wt["path"],
            "branch": branch,
            "base": base,
            "alive": entry_is_live(e) if e else False,
            "dirty": dirty,
            "ahead": ahead,
            "merged": ahead == 0,
            "age": age_str(e.get("started_at", "")),
            "areas": sorted(touched, key=lambda k: -touched[k]),
            "multi_area": len(touched) > 1,
            "label": branch_description(root, branch),
            "hint": subject_hint(e),
        }
        if predict and ahead > 0:
            info["conflict"] = predict_conflict(root, base, branch)
        result.append(info)
    return result


def default_base(root: str) -> str:
    """Best guess at the integration branch when an entry didn't record one."""
    rc, out, _ = git(["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"], cwd=root)
    if rc == 0 and out:
        return out.replace("refs/remotes/origin/", "")
    for cand in ("main", "master"):
        rc, _, _ = git(["rev-parse", "--verify", "--quiet", cand], cwd=root)
        if rc == 0:
            return cand
    return "main"


def auto_clean(root: str):
    """Remove session worktrees that are provably safe to drop:
    not alive AND clean AND (fully merged or zero commits). Returns names removed.
    """
    removed = []
    for info in classify(root):
        if info["alive"] or info["dirty"]:
            continue
        if info["ahead"] != 0:   # has unmerged commits (or unknown) → keep
            continue
        rc, _, _ = git(["worktree", "remove", info["path"]], cwd=root)
        if rc != 0:
            git(["worktree", "remove", "--force", info["path"]], cwd=root)
        git(["branch", "-D", info["branch"]], cwd=root)
        removed.append(info["branch"])
    return removed


# ── worktree seeding ──────────────────────────────────────────────────────

def seed_globs(main_root: str):
    """Globs of gitignored files to copy into a fresh worktree.

    Precedence: $CCW_SEED (space/colon-separated) > .claude/worktree-seed
    (one glob per line, '#' comments) > DEFAULT_SEED_GLOBS.
    """
    env = os.environ.get("CCW_SEED", "").strip()
    if env:
        return [g for g in re.split(r"[:\s]+", env) if g]
    cfg = Path(main_root) / ".claude" / "worktree-seed"
    if cfg.is_file():
        try:
            lines = cfg.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        out = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
        if out:
            return out
    return list(DEFAULT_SEED_GLOBS)


def seed_worktree(main_root: str, wt_path: str):
    """Copy gitignored seed files from the main tree into a fresh worktree so it
    is usable immediately (e.g. .env).

    Copies (never symlinks) — a symlink would re-couple the worktree to the
    synced main tree, which is the very thing the relocated worktree home avoids.
    Only fills files ABSENT in the worktree, so it never clobbers tracked content
    the checkout already placed. Returns the list of copied relative paths.
    """
    copied = []
    main = Path(main_root)
    dest = Path(wt_path)
    for pattern in seed_globs(main_root):
        if pattern.startswith("/") or ".." in pattern.split("/"):
            continue  # refuse absolute or traversal patterns
        try:
            matches = sorted(main.glob(pattern))
        except (ValueError, OSError):
            continue
        for src in matches:
            if not src.is_file():
                continue
            try:
                rel = src.relative_to(main)
            except ValueError:
                continue
            tgt = dest / rel
            if tgt.exists():
                continue  # checkout already placed it — don't clobber
            try:
                tgt.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, tgt)
                copied.append(str(rel))
            except OSError:
                pass
    return copied
