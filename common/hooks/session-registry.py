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
import _handoff as H  # noqa: E402


def emit_context(text: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}
    }))


def resume_notice(session_id: str, cwd: str, root: str):
    """Direct lookup of this branch's handoff, left by a previous session.

    Branch-keyed, so no scan: the new session knows its own branch. We offer the
    handoff only when it's safe and unambiguous — not our own, no LIVE peer in
    this same tree (that's the overlap case, handled separately), and fresh.
    Returns the context block (with its own "don't announce" rule) or None.
    """
    branch = L.current_branch(cwd)
    path = H.handoff_path(root, branch)
    if not path.exists():
        return None
    meta, auto, note = H.parse(path)
    if meta.get("session_id") == session_id:
        return None  # already ours
    if L.live_sessions_in(root, str(cwd), exclude_key=session_id):
        return None  # a live peer shares this tree → ambiguous; overlap warning covers it
    if H.age_seconds(meta) > H.FRESH_WINDOW_SECONDS:
        return None  # too old to be "where we left off"

    parts = [p for p in (auto, note) if p and "sem narrativa" not in p and "sem checkpoint" not in p]
    body = "\n\n".join(parts).strip()
    if not body:
        return None
    return (
        "[resume] Há um handoff de uma sessão anterior neste branch "
        f"(`{meta.get('branch', '?')}`, atualizado {meta.get('updated_at', '?')}). "
        "Conteúdo abaixo.\n"
        "REGRA: se a primeira mensagem do usuário continua este trabalho, apenas "
        "siga de onde parou — NÃO anuncie nem resuma o handoff de volta pro usuário. "
        "Se for outro assunto, ignore em silêncio.\n"
        "REGRA: o handoff é HIPÓTESE, não fato — ele descreve o mundo de quando foi "
        "escrito. Antes de AFIRMAR qualquer fato vindo daqui (remotes, existência de "
        "diretórios/repos vizinhos, nomes pós-rename, estado de build, o que está ou "
        "não implementado), re-verifique no disco/git com um comando barato. Repetir "
        "um fato stale de handoff como verdade é o erro nº 1 apontado pelo usuário.\n\n" + body
    )


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
    entry.setdefault("start_commit", L.current_commit(cwd))  # baseline for "commits this session"
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
                cap = L.caption(c.get("label", ""), c.get("hint", ""))
                head = f"{c['branch']} {cap}".rstrip()
                lines.append(f"  • {head} — {', '.join(bits) or 'no commits'}, "
                             f"{c['age']} old{live}")
            lines.append("  Land with `/common:worktree-merge <name>`, inspect with "
                         "`/common:worktree-list`, drop with `/common:worktree-discard <name>`, "
                         "or label one with `/common:worktree-label <purpose>` so you "
                         "remember what it's for.")
            notices.append("\n".join(lines))
    except Exception as e:  # noqa: BLE001
        print(f"[session-registry] worktree scan failed: {e}", file=sys.stderr)

    # Two context blocks with DIFFERENT instructions, kept apart so they don't
    # contradict: notices are meant to be surfaced; the resume block is meant to
    # be acted on silently.
    parts = []
    if notices:
        parts.append("\n\n".join(notices) + "\n\nMention the relevant points to "
                     "the user at the start of your reply.")
    resume = resume_notice(session_id, str(cwd), root)
    if resume:
        parts.append(resume)
    if parts:
        emit_context("\n\n———\n\n".join(parts))


def prune_marker_path(root: str, session_id: str):
    return L.sessions_dir(root) / f"{session_id}.prune-on-exit"


def read_prune_marker(root: str, session_id: str):
    """The deferred-prune intent left by /common:wrap-up, or None.

    wrap-up runs from INSIDE the session worktree, so it can't remove that
    worktree itself: deleting the live session's cwd makes the very next Stop
    hook fail to launch (`posix_spawn '/bin/sh' ENOENT`, cwd gone). Instead it
    drops this marker and we reap the worktree here, after the session's last
    turn — no hook ever fires from a dead cwd.
    """
    marker = prune_marker_path(root, session_id)
    if not marker.exists():
        return None
    try:
        return json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}  # present but unreadable → still consume it below


def do_prune_on_exit(root: str, session_id: str, cwd: str, spec: dict) -> None:
    """Reap the session worktree wrap-up flagged for deferred pruning.

    Land path (discard=false): only delete the branch if it's truly merged into
    base — if wrap-up's merge didn't land (or later work made the branch ahead
    again), leave everything for the user / auto_clean rather than drop commits.
    Discard path (discard=true): the user explicitly threw it away → force.
    """
    marker = prune_marker_path(root, session_id)
    base_wt = spec.get("base_worktree") or ""
    base_branch = spec.get("base_branch") or ""
    branch = spec.get("branch") or L.current_branch(cwd)
    session_wt = spec.get("session_worktree") or cwd
    discard = bool(spec.get("discard"))

    # Step out of the dir we're about to remove so git never hits EBUSY on cwd.
    try:
        if base_wt and os.path.isdir(base_wt):
            os.chdir(base_wt)
    except OSError:
        pass

    if not (base_wt and branch and session_wt):
        print(f"[session-registry] prune-on-exit marker incomplete; skipping "
              f"({session_id[:8]})", file=sys.stderr)
    elif discard:
        L.git(["worktree", "remove", "--force", session_wt], cwd=base_wt)
        L.git(["branch", "-D", branch], cwd=base_wt)
        print(f"[session-registry] discarded worktree {branch} on exit", file=sys.stderr)
    elif base_branch and L.is_merged(base_wt, base_branch, branch):
        rc, _, _ = L.git(["worktree", "remove", session_wt], cwd=base_wt)
        if rc != 0:
            L.git(["worktree", "remove", "--force", session_wt], cwd=base_wt)
        L.git(["branch", "-d", branch], cwd=base_wt)
        print(f"[session-registry] pruned landed worktree {branch} on exit",
              file=sys.stderr)
    else:
        print(f"[session-registry] prune-on-exit skipped: {branch} not merged into "
              f"{base_branch or '?'}; leaving worktree intact", file=sys.stderr)

    try:
        marker.unlink()
    except OSError:
        pass


def on_end(session_id: str, cwd: str) -> None:
    root = L.main_root(cwd)
    branch = L.current_branch(cwd)
    spec = read_prune_marker(root, session_id) if root else None

    # 5. WIP-autosave — ONLY in a session worktree, ONLY if dirty, and NEVER when
    #    this worktree is being discarded (committing work we're about to throw
    #    away is pointless and would mark a clean branch as ahead of base).
    if branch.startswith("session/") and not (spec and spec.get("discard")) \
            and L.is_dirty(cwd):
        L.git(["add", "-A"], cwd=cwd)
        rc, _, err = L.git(
            ["commit", "-m", f"WIP: session autosave ({session_id[:8]})",
             "--no-verify"], cwd=cwd)
        if rc == 0:
            print(f"[session-registry] WIP-autosaved uncommitted work on {branch}",
                  file=sys.stderr)
        else:
            print(f"[session-registry] WIP-autosave failed: {err}", file=sys.stderr)

    # 5b. Deferred prune (wrap-up's marker) — reap the worktree now that the
    #     session's last turn is over, so no Stop hook fires from a dead cwd.
    if root and spec is not None:
        do_prune_on_exit(root, session_id, cwd, spec)

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
