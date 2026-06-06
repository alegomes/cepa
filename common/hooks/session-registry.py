#!/usr/bin/env python3
"""SessionStart / SessionEnd hook: the live-session registry + worktree hygiene.

SessionStart:
  1. Adopt the launcher's claim (CLAUDE_WT_CLAIM) → rekey it to this session_id,
     or register a fresh entry if claude was started without `ccw`.
  2. Reclaim dead entries (PID-checked).
  3. Warn if another LIVE session shares this exact working tree.
  4. Auto-clean session worktrees that are provably safe to drop, and remind the
     user of any that carry unmerged work (so a forgotten merge can't strand it).

SessionEnd:
  5. WIP-autosave — if this is a `session/*` worktree with uncommitted changes,
     commit them to the session branch (NEVER the main tree) so nothing is lost.
  6. Deregister this session.

Never blocks; any error → stderr note, exit 0.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _wtlib as L  # noqa: E402


def emit_context(text: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}
    }))


def on_start(session_id: str, cwd: str) -> None:
    root = L.main_root(cwd)
    if not root:
        return
    sdir = L.sessions_dir(root)
    sdir.mkdir(parents=True, exist_ok=True)

    # 1. Adopt the launcher's claim, if any.
    claim_id = os.environ.get("CLAUDE_WT_CLAIM", "").strip()
    entry = {}
    if claim_id:
        claimed = L.find_entry(root, claim_id)
        if claimed:
            entry = claimed
            try:
                (sdir / f"{claim_id}.json").unlink()
            except OSError:
                pass
    if not entry:
        branch = L.current_branch(cwd)
        entry = {
            "pid": os.getppid(),
            "hostname": L.host(),
            "cwd": str(cwd),
            "started_at": L.now_iso(),
            "branch": branch,
            "is_session_worktree": branch.startswith("session/"),
        }
    entry["session_id"] = session_id
    entry["last_seen"] = L.now_iso()
    entry.pop("claim", None)
    L.write_entry(root, session_id, entry)

    # 2. Reclaim dead entries.
    L.prune_dead(root, keep_key=session_id)

    notices = []

    # 3. Overlap warning — another live session in THIS working tree.
    others = L.live_sessions_in(root, str(cwd), exclude_key=session_id)
    if others:
        n = len(others)
        notices.append(
            f"⚠ {n} other live session{'s' if n > 1 else ''} "
            f"{'are' if n > 1 else 'is'} running in this same working tree "
            f"(`{cwd}`). You share one copy of the source and one `.claude/` "
            f"state dir — same-file edits will silently clobber each other. "
            f"For parallel work, launch with `ccw` (it auto-isolates) or run "
            f"`/common:worktree-start <slice>`."
        )

    # 4. Auto-clean safe worktrees, remind about the rest.
    try:
        cleaned = L.auto_clean(root)
        if cleaned:
            notices.append(f"🧹 Auto-removed {len(cleaned)} finished session "
                           f"worktree(s): {', '.join(cleaned)}.")
        pending = [c for c in L.classify(root) if c["ahead"] != 0 or c["dirty"]]
        if pending:
            lines = ["📋 Unmerged session worktrees (don't forget to land them):"]
            for c in pending:
                bits = []
                if c["ahead"] > 0:
                    bits.append(f"{c['ahead']} commit{'s' if c['ahead'] != 1 else ''}")
                if c["dirty"]:
                    bits.append("uncommitted changes")
                if c["multi_area"]:
                    bits.append(f"spans {', '.join(c['areas'][:4])}")
                live = " (live)" if c["alive"] else ""
                lines.append(f"  • {c['branch']} — {', '.join(bits) or 'no commits'}, "
                             f"{c['age']} old{live}")
            lines.append("  Land with `/common:worktree-merge <name>`, inspect with "
                         "`/common:worktree-list`, or drop with `/common:worktree-discard <name>`.")
            notices.append("\n".join(lines))
    except Exception as e:  # noqa: BLE001
        print(f"[session-registry] worktree scan failed: {e}", file=sys.stderr)

    if notices:
        emit_context("\n\n".join(notices) + "\n\nMention the relevant points to "
                     "the user at the start of your reply.")


def on_end(session_id: str, cwd: str) -> None:
    root = L.main_root(cwd)
    branch = L.current_branch(cwd)

    # 5. WIP-autosave — ONLY in a session worktree, ONLY if dirty.
    if branch.startswith("session/") and L.is_dirty(cwd):
        L.git(["add", "-A"], cwd=cwd)
        rc, _, err = L.git(
            ["commit", "-m", f"WIP: session autosave ({session_id[:8]})",
             "--no-verify"], cwd=cwd)
        if rc == 0:
            print(f"[session-registry] WIP-autosaved uncommitted work on {branch}",
                  file=sys.stderr)
        else:
            print(f"[session-registry] WIP-autosave failed: {err}", file=sys.stderr)

    # 6. Deregister.
    if root:
        f = L.sessions_dir(root) / f"{session_id}.json"
        try:
            f.unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            print(f"[session-registry] deregister failed: {e}", file=sys.stderr)


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        sys.exit(0)

    session_id = payload.get("session_id") or ""
    if not session_id:
        sys.exit(0)
    cwd = os.path.abspath(payload.get("cwd") or os.getcwd())
    event = payload.get("hook_event_name") or ""

    try:
        if event == "SessionEnd":
            on_end(session_id, cwd)
        else:
            on_start(session_id, cwd)
    except Exception as e:  # noqa: BLE001 — a registry error must never break the session
        print(f"[session-registry] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
