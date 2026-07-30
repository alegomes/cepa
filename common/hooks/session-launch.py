#!/usr/bin/env python3
"""Launch-time decision core for the `cepa` launcher.

Run by `cepa` BEFORE `claude` starts, inside an fcntl lock (macOS has no `flock`
CLI, so the critical section lives here in Python). Decides — atomically — whether
this new session should run in the main tree or be auto-isolated into its own
git worktree, then writes a claim file the SessionStart hook will adopt.

Decision:
  - explicit slice name given            → isolate (named worktree, reuse if it exists)
  - another LIVE session already in tree  → isolate (auto-named worktree)
  - otherwise                             → run in place (main tree)

The claim file is keyed by a generated claim-id. `cepa` passes that id to claude
via CLAUDE_WT_CLAIM (survives `exec`, inherited by the hook), and the SessionStart
hook renames the claim to the real session_id.

Env in:  CLAUDE_WT_ROOT (repo root, required), CLAUDE_WT_SLICE (optional name)
Stdout:  one line  "<launch-dir>\t<claim-id>"   (launch-dir = where cepa should cd)
Exit:    0 on success; non-zero → cepa falls back to launching in place.
"""

import fcntl
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _wtlib as L  # noqa: E402


def neutral_name(root: str) -> str:
    base = datetime.now(timezone.utc).strftime("%m%d-%H%M")
    name = base
    n = 2
    while True:
        rc, _, _ = L.git(["rev-parse", "--verify", "--quiet", f"refs/heads/session/{name}"], cwd=root)
        if rc != 0:
            return name
        name = f"{base}-{n}"
        n += 1


def main() -> int:
    root_in = os.environ.get("CLAUDE_WT_ROOT", "").strip()
    slice_name = os.environ.get("CLAUDE_WT_SLICE", "").strip()
    if not root_in:
        return 1
    root = L.main_root(root_in) or root_in  # registry always lives in the main tree

    sdir = L.sessions_dir(root)
    sdir.mkdir(parents=True, exist_ok=True)
    lock_path = sdir / ".launch.lock"

    with open(lock_path, "w") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            L.prune_dead(root)
            occupied = bool(L.live_sessions_in(root, root))
            claim_id = uuid.uuid4().hex

            entry = {
                "session_id": claim_id,
                "claim": True,
                "pid": os.getppid(),  # cepa's pid → becomes claude's pid after exec
                "hostname": L.host(),
                "started_at": L.now_iso(),
                "last_seen": L.now_iso(),
            }

            if not slice_name and not occupied:
                # Run in place — but still claim the main tree so a simultaneous
                # second launcher sees an occupant and isolates itself.
                entry.update({"cwd": root, "is_session_worktree": False,
                              "branch": L.current_branch(root)})
                L.write_entry(root, claim_id, entry)
                print(f"{root}\t{claim_id}")
                return 0

            # Isolate into a worktree. Place it OUTSIDE the repo tree — a repo
            # under a cloud-sync folder (Insync/Dropbox/iCloud) would otherwise
            # have its sibling worktrees synced too, and the sync daemon's own
            # move/replace/conflict-copy races delete live worktrees mid-step.
            # Default home is ~/cepa-worktrees; override with CEPA_WORKTREE_HOME
            # (the pre-rename CCW_WORKTREE_HOME is still honoured, so a shell
            # that still exports it keeps working instead of silently relocating
            # every worktree to the new default).
            name = slice_name or neutral_name(root)
            branch = f"session/{name}"
            repo_name = os.path.basename(os.path.abspath(root))
            wt_home = os.environ.get("CEPA_WORKTREE_HOME", "").strip() \
                or os.environ.get("CCW_WORKTREE_HOME", "").strip() \
                or os.path.expanduser("~/cepa-worktrees")
            wt_home = os.path.abspath(wt_home)
            os.makedirs(wt_home, exist_ok=True)
            wt_path = os.path.join(wt_home, f"{repo_name}-{name}")
            base_branch = L.current_branch(root)
            base_commit = L.current_commit(root)

            branch_exists = L.git(
                ["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=root
            )[0] == 0
            already_wt = any(L.same_path(w.get("path", ""), wt_path)
                             for w in L.list_worktrees(root))

            if already_wt:
                pass  # resume an existing worktree as-is
            elif branch_exists:
                rc, _, err = L.git(["worktree", "add", wt_path, branch], cwd=root)
                if rc != 0:
                    print(f"[session-launch] worktree add failed: {err}", file=sys.stderr)
                    return 1
            else:
                rc, _, err = L.git(["worktree", "add", wt_path, "-b", branch], cwd=root)
                if rc != 0:
                    print(f"[session-launch] worktree add failed: {err}", file=sys.stderr)
                    return 1

            if not already_wt:
                # Fill the fresh worktree with gitignored essentials (.env, …)
                # so it's usable immediately and nothing is lost on discard.
                L.seed_worktree(root, wt_path)

            entry.update({
                "cwd": wt_path,
                "is_session_worktree": True,
                "worktree_path": wt_path,
                "branch": branch,
                "base_branch": base_branch,
                "base_commit": base_commit,
            })
            L.write_entry(root, claim_id, entry)
            print(f"{wt_path}\t{claim_id}")
            return 0
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


if __name__ == "__main__":
    sys.exit(main())
