#!/usr/bin/env python3
"""Stop hook: maintain a mechanical handoff skeleton every turn.

Fires when the main agent finishes a response. Writes the AUTO zone of this
branch's handoff (`<main-root>/.claude/handoffs/<branch-slug>.md`) with facts —
commits made this session, dirs touched, the last few user intents. Because it
runs every turn, the skeleton is always current, so a token-limit kill or crash
never loses the thread: a fresh-enough "where we are" note already exists.

This is the deterministic half. The narrative half (decisions, next step) is the
NOTE zone, written by /common:handoff — this hook never touches it.

Pure bookkeeping — never blocks, exit 0 always.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _wtlib as L  # noqa: E402
import _handoff as H  # noqa: E402

MAX_COMMITS = 15
MAX_INTENTS = 6


def recent_commits(cwd: str, start_commit: str) -> list:
    """Commits made since the session started (start_commit..HEAD). If we never
    captured a start point (session predates the feature), fall back to the last
    few commits with a marker so the skeleton still says something useful."""
    if start_commit:
        rc, out, _ = L.git(
            ["log", "--oneline", "--no-decorate", f"{start_commit}..HEAD"], cwd=cwd)
        if rc == 0:
            lines = [ln for ln in out.splitlines() if ln.strip()]
            return lines[:MAX_COMMITS]
        return []
    rc, out, _ = L.git(["log", "--oneline", "--no-decorate", "-3"], cwd=cwd)
    return [f"{ln}  (sessão sem ponto de partida — últimos 3)" for ln in out.splitlines()][:3] if rc == 0 else []


def recent_intents(cwd: str) -> list:
    """The last few user prompts from the session-log (intent trail)."""
    log = Path(cwd) / ".claude" / "session-log.md"
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    # Entries are blocks after `### HH:MM:SS UTC` headers.
    blocks = []
    cur = []
    for line in text.splitlines():
        if line.startswith("### "):
            if cur:
                blocks.append("\n".join(cur).strip())
            cur = []
        elif line.startswith(("# ", "## ")):
            continue
        else:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur).strip())
    intents = [b for b in blocks if b]
    out = []
    for b in intents[-MAX_INTENTS:]:
        one = " ".join(b.split())
        out.append(one[:140] + ("…" if len(one) > 140 else ""))
    return out


def build_auto(cwd: str, entry: dict) -> str:
    start_commit = (entry or {}).get("start_commit", "")
    commits = recent_commits(cwd, start_commit)
    touched = (entry or {}).get("touched_dirs", {}) or {}
    dirty = L.is_dirty(cwd)
    intents = recent_intents(cwd)

    lines = ["## Onde paramos (checkpoint automático)", ""]
    lines.append(f"- **Branch:** `{L.current_branch(cwd) or '?'}`"
                 + (" · ⚠ árvore suja (mudanças não commitadas)" if dirty else ""))
    if commits:
        lines.append(f"- **Commits desta sessão ({len(commits)}):**")
        lines += [f"  - {c}" for c in commits]
    else:
        lines.append("- **Commits desta sessão:** nenhum ainda")
    if touched:
        areas = ", ".join(f"{d} ({n})" for d, n in
                          sorted(touched.items(), key=lambda kv: -kv[1]))
        lines.append(f"- **Áreas tocadas:** {areas}")
    if intents:
        lines.append("- **Últimos pedidos:**")
        lines += [f"  - “{i}”" for i in intents]
    return "\n".join(lines)


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        sys.exit(0)

    session_id = payload.get("session_id") or ""
    cwd = os.path.abspath(payload.get("cwd") or os.getcwd())
    if not session_id:
        sys.exit(0)

    try:
        root = L.main_root(cwd)
        if not root:
            sys.exit(0)
        branch = L.current_branch(cwd)
        entry = L.find_entry(root, session_id) or {}
        turns = (entry.get("subject") or {}).get("prompts")

        meta = {
            "session_id": session_id,
            "branch": branch,
            "branch_slug": H.branch_slug(branch),
            "cwd": cwd,
            "updated_at": L.now_iso(),
            "turns": turns if turns is not None else "?",
        }
        H.write(H.handoff_path(root, branch), meta, auto=build_auto(cwd, entry))
    except Exception as e:  # noqa: BLE001 — a checkpoint error must never break the turn
        print(f"[session-checkpoint] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
