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
try:
    import _telemetry as T
except Exception:  # noqa: BLE001 — telemetria nunca quebra o hook
    T = None

# As rotinas: os comandos pelos quais uma sessão existe. Tudo que o usuário
# digita ANTES da primeira delas é preparação; tudo depois da última é
# fechamento. Medir esses dois números é o que permite dizer, com evidência,
# se o atrito das pontas caiu — em vez de memória contra memória.
ROTINAS = {
    "board-flow:drain", "board-flow:prove-drain", "board-flow:triage",
    "board-flow:execute", "board-flow:fix", "board-flow:prove",
    "board-flow:decide", "board-flow:plan-track-build-validate",
    "common:autonomous-start", "common:autonomous-resume", "common:session",
    "docs:survey", "docs:author", "maestro:run", "review-gate:review",
}
FECHAMENTO = {"common:wrap-up", "common:handoff"}


def classify(prompt: str):
    """(kind, cmd) do prompt. Só o NOME do comando vai para a telemetria —
    nunca o texto do prompt, que carregaria conteúdo do usuário."""
    m = re.match(r"\s*/([a-z0-9:_-]+)", prompt, re.I)
    if not m:
        return "prosa", None
    cmd = m.group(1).lower()
    if cmd in ROTINAS:
        return "rotina", cmd
    if cmd in FECHAMENTO:
        return "fechamento", cmd
    return "comando", cmd


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

    cwd = Path(payload.get("cwd") or os.getcwd()).resolve()
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
        except Exception:  # noqa: BLE001 — telemetria nunca quebra o hook
            pass

    sys.exit(0)


if __name__ == "__main__":
    main()
