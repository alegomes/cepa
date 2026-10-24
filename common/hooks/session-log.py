#!/usr/bin/env python3
"""UserPromptSubmit hook: append every user prompt to .claude/session-log.md.

Captures intent in real-time so /common:recap can render an "asked vs.
delivered" view of the session, even if auto-compaction has dropped the
earlier prompts from context.

Failure modes:
- Hook never blocks. Any error → stderr warning, exit 0.
- Empty / whitespace prompts skipped (CC sometimes fires this hook on
  internal events that we don't want logged).
- File grows unbounded; rotation is intentionally not built in. Manual
  rotation: rename or delete .claude/session-log.md when you want a
  fresh log.

Format: markdown with date headers and timestamped prompt blocks.

  # Session log
  ## 2026-05-07
  ### 19:45:32 UTC
  <user prompt verbatim>

  ### 19:46:10 UTC
  <next prompt>
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _wtlib as L  # noqa: E402

try:
    import _telemetry as T
except Exception:  # noqa: BLE001 — telemetry never breaks the hook
    T = None

# The routines: the commands a session exists for. Everything the user types
# BEFORE the first of them is preparation; everything after the last is
# closing. Measuring those two numbers is what allows saying, with evidence,
# whether the friction at the ends dropped, instead of memory against memory.
ROUTINES = {
    "board-flow:drain", "board-flow:prove-drain", "board-flow:triage",
    "board-flow:execute", "board-flow:fix", "board-flow:prove",
    "board-flow:decide", "board-flow:plan-track-build-validate",
    "common:autonomous-start", "common:autonomous-resume", "common:session",
    "docs:survey", "docs:author", "maestro:run", "review-gate:review",
}
CLOSING = {"common:wrap-up", "common:handoff"}


def classify(prompt: str):
    """(kind, cmd) of the prompt. Only the command NAME goes to telemetry,
    never the prompt text, which would carry user content."""
    m = re.match(r"\s*/([a-z0-9:_-]+)", prompt, re.I)
    if not m:
        return "prosa", None
    cmd = m.group(1).lower()
    if cmd in ROUTINES:
        return "rotina", cmd
    if cmd in CLOSING:
        return "fechamento", cmd
    return "comando", cmd


# "Where are we / what are we doing / what is the next step": the questions the
# owner uses to re-orient the session. Each occurrence is a sign that the
# recorded intent was not in view (telemetry `intent.asked`). Strict on
# purpose: matches the short, typical question, not any prose that contains
# "próximo passo" in the middle of another subject.
_WHERE_ARE_WE_QUESTION = re.compile(
    r"""^\s*(?:
        /common:whereami
      | (?:e\s+)?(?:ent[aã]o[,\s]+)?
        (?: o\s+que\s+(?:a\s+gente\s+)?(?:estamos|estou|vamos|v[ao]mos)\s+(?:fazendo|fazer)
          | (?:onde|em\s+que\s+passo|em\s+qual\s+passo)\s+(?:a\s+gente\s+)?(?:estamos|paramos|estou|est[aá])
          | (?:qual|quais)\s+(?:[eé]\s+)?(?:o\s+|a\s+)?(?:pr[oó]ximo\s+passo|pr[oó]xima\s+etapa)
          | e\s+(?:o\s+)?pr[oó]ximo\s+passo
          | pr[oó]ximo\s+passo
          | where\s+are\s+we
          | what\s+are\s+we\s+(?:doing|working\s+on)
          | what(?:'?s|\s+is)\s+(?:the\s+)?next(?:\s+step)?
          | what\s+(?:was|were)\s+we\s+doing
        )
    )[\s?!.]*$""",
    re.I | re.X)


def asks_where_we_are(prompt: str) -> bool:
    """Is the prompt a short "where are we / next step" question?
    The whole sentence (up to 80 characters), not an excerpt: "o próximo passo
    do deploy exige X" is something else."""
    p = (prompt or "").strip()
    return 0 < len(p) <= 80 and bool(_WHERE_ARE_WE_QUESTION.match(p))


def now() -> tuple[str, str]:
    """Return (date_header, time_header) in UTC."""
    n = datetime.now(timezone.utc)
    return n.strftime("%Y-%m-%d"), n.strftime("%H:%M:%S UTC")


def append_entry(log_path: Path, prompt: str) -> None:
    """Append a prompt entry, creating the file with a header if needed.

    Adds a date header only when the date has rolled over (or file is new),
    so the log groups entries by day without repeating the date for every
    prompt.
    """
    date_header, time_header = now()

    log_path.parent.mkdir(parents=True, exist_ok=True)

    needs_top_header = not log_path.exists()
    needs_date_header = True
    if not needs_top_header:
        try:
            existing = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            existing = ""
        if f"## {date_header}\n" in existing:
            needs_date_header = False

    chunks: list[str] = []
    if needs_top_header:
        chunks.append("# Session log\n\n")
    if needs_date_header:
        chunks.append(f"## {date_header}\n\n")
    chunks.append(f"### {time_header}\n\n{prompt.rstrip()}\n\n")

    with log_path.open("a", encoding="utf-8") as f:
        f.write("".join(chunks))


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[session-log] could not parse hook payload; skipping", file=sys.stderr)
        sys.exit(0)

    prompt = payload.get("prompt") or payload.get("message") or ""
    if isinstance(prompt, dict):
        prompt = prompt.get("content", "") or ""
    if not isinstance(prompt, str):
        prompt = str(prompt)

    if not prompt.strip():
        sys.exit(0)

    # The worktree ROOT, not the current directory: Bash's cwd persists
    # between calls, and a `cd subdir` would divert this session's state to
    # `subdir/.claude/` for the rest of it (see _wtlib.session_root).
    cwd = Path(L.session_root(payload.get("cwd") or os.getcwd())).resolve()
    log_path = cwd / ".claude" / "session-log.md"

    try:
        append_entry(log_path, prompt)
    except OSError as e:
        print(f"[session-log] could not append to {log_path}: {e}", file=sys.stderr)

    if T is not None:
        try:
            kind, cmd = classify(prompt)
            T.emit("prompt", cwd=str(cwd), kind=kind, cmd=cmd or "",
                   session=str(payload.get("session_id") or "")[:8])
            if asks_where_we_are(prompt):
                T.emit("intent.asked", cwd=str(cwd),
                       session=str(payload.get("session_id") or "")[:8])
        except Exception:  # noqa: BLE001 — telemetry never breaks the hook
            pass

    sys.exit(0)


if __name__ == "__main__":
    main()
