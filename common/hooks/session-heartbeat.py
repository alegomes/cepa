#!/usr/bin/env python3
"""UserPromptSubmit hook: keep the session's registry entry alive, and tell a
resumed conversation when its worktree was removed under it.

WHY (incident fb-20261110-4): session 56e8cebe was opened on 07/11 and resumed on
10/11. Its worktree and branch had vanished. `auto_clean` (_wtlib.py, run at every
SessionStart of the repo) removes a session worktree with no changes and no
commits whose session `entry_is_live` calls dead. This one looked dead because
`last_seen` was only bumped at SessionStart and on edits (STALE_HOURS = 24), and
because the app restart killed the registered pid.

1. HEARTBEAT. On every prompt: `last_seen = now`. Decision on `pid`: it is
   refreshed (to this hook's parent, the same os.getppid() convention
   session-registry uses at SessionStart) ONLY when the registered pid is no
   longer alive. `entry_is_live` answers "dead" as soon as the pid is gone,
   whatever `last_seen` says, so a resumed conversation (new claude process,
   no new SessionStart registration) would otherwise stay dead forever. When the
   registered pid is still alive it is left alone: overwriting a good pid with
   a wrong one would be worse than the gap. STALE_HOURS is unchanged.
   Never creates an entry: a session nobody registered stays unregistered.

2. WARNING ON RESUME. If this conversation's worktree no longer exists (entry
   cwd missing, or a tombstone `.claude/sessions/<session_id>.gone` left by
   prune_dead / auto_clean), say once, in pt-BR, what disappeared (path, branch)
   and where the rescued artifacts are (`.claude/rescued/<slug>/` in the main
   root). "Once" = `warned_at` stamped in the tombstone (or `gone_warned` in the
   entry) before printing.

Never blocks, exit 0 always. One `git rev-parse` plus a small JSON read/write.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _wtlib as L  # noqa: E402


def find_root(cwd: str) -> str:
    """Main root for the payload cwd.

    Resumed-conversation case: cwd and $CLAUDE_PROJECT_DIR are BOTH the deleted
    worktree, a sibling of the main clone (`~/cepa-worktrees/<repo>-<slug>`),
    so walking up never reaches the clone. Order: an existing directory wins;
    then the home-dir index of worktree -> main root (_wtlib.index_register);
    last, the first existing ancestor, for worktrees nested inside the repo.
    """
    cands = [c for c in (cwd, os.environ.get("CLAUDE_PROJECT_DIR", "")) if c]
    for cand in cands:
        if os.path.isdir(cand):
            root = L.main_root(cand)
            if root:
                return root
    for cand in cands:
        root = L.index_lookup(cand)
        if root:
            return root
    for cand in cands:
        cur = os.path.abspath(cand)
        while cur != os.path.dirname(cur):
            cur = os.path.dirname(cur)
            if os.path.isdir(cur):
                root = L.main_root(cur)
                if root:
                    return root
                break
    return ""


def gone_message(root: str, sid: str, path: str, branch: str, tomb: dict) -> str:
    slug = L.rescue_slug(branch)
    rescued_dir = os.path.join(root, ".claude", "rescued", slug)
    if os.path.isdir(rescued_dir):
        n = sum(1 for _ in os.scandir(rescued_dir))
        saved = (f"O que havia de artefato em `.claude/` foi copiado para "
                 f"`{rescued_dir}/` ({n} item(ns) no primeiro nível).")
    else:
        saved = ("Não há cópia em `.claude/rescued/` para essa branch: o worktree "
                 "não tinha artefatos do harness para resgatar, ou a remoção não "
                 "passou pelo resgate.")
    by = (tomb or {}).get("removed_by_session")
    when = (tomb or {}).get("removed_at")
    lines = [
        "[session-heartbeat] ⚠ O worktree desta conversa não existe mais.",
        f"  Caminho: {path or '?'}",
        f"  Branch: {branch or '?'}",
    ]
    if by or when:
        lines.append("  Removido" + (f" pela sessão {str(by)[:8]}" if by else "")
                     + (f" em {when}" if when else "") + ".")
    lines += [
        f"  {saved}",
        "  A intenção da sessão (`.claude/session-intent`) e o histórico de prompts "
        "(`.claude/session-log.md`) não são resgatados e foram junto com o diretório.",
        "  Avise o dono em uma frase e continue a partir da raiz principal do repo "
        f"(`{root}`); se o trabalho precisar de isolamento, abra outro worktree de lá.",
    ]
    return "\n".join(lines)


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        sys.exit(0)
    if not isinstance(payload, dict):
        sys.exit(0)
    sid = payload.get("session_id") or ""
    if not sid or "/" in sid:
        sys.exit(0)

    try:
        root = find_root(payload.get("cwd") or os.getcwd())
        if not root:
            sys.exit(0)

        # 1. heartbeat
        entry = L.find_entry(root, sid)
        if entry:
            entry["last_seen"] = L.now_iso()
            if not L.pid_alive(entry.get("pid")):
                entry["pid"] = os.getppid()
                entry["hostname"] = L.host()

        # 2. worktree gone?
        notice = ""
        tomb = L.read_tombstone(root, sid)
        if tomb and not tomb.get("warned_at"):
            path = tomb.get("worktree_path") or tomb.get("cwd") or ""
            if path and not os.path.isdir(path):
                tomb["warned_at"] = L.now_iso()
                L.tombstone_path(root, sid).write_text(
                    json.dumps(tomb, indent=2), encoding="utf-8")
                notice = gone_message(root, sid, path, tomb.get("branch", ""), tomb)
        elif entry and not entry.get("gone_warned") and not tomb:
            path = entry.get("worktree_path") or entry.get("cwd") or ""
            if entry.get("is_session_worktree") and path and not os.path.isdir(path):
                entry["gone_warned"] = True
                notice = gone_message(root, sid, path, entry.get("branch", ""), {})

        if entry:
            L.write_entry(root, sid, entry)
        if notice:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": notice,
            }}, ensure_ascii=False))
    except Exception as e:  # noqa: BLE001 — bookkeeping never blocks a prompt
        print(f"[session-heartbeat] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
