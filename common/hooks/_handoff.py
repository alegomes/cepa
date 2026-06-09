#!/usr/bin/env python3
"""Shared format + IO for session handoffs.

A handoff is a single Markdown file, keyed by BRANCH (not session_id), living at
`<main-root>/.claude/handoffs/<branch-slug>.md`. Branch-keying makes resume a
direct lookup (the new session knows its own branch) instead of a scan, and
keeps parallel worktrees — which run on distinct branches — naturally separate.
The only collision is two sessions on the same branch in the same working tree,
which the registry's overlap warning already covers.

The file has two independently-owned zones so the two writers never clobber
each other:

  - AUTO  zone — the mechanical skeleton (commits, touched dirs, last intents).
                 Rewritten every turn by session-checkpoint.py (the Stop hook).
                 Survives token-limit kills because it is always current.
  - NOTE  zone — the narrative (decisions, next step, caveats). Written by the
                 /common:handoff command (model synthesis). Optional.

`write()` only replaces the zone(s) you pass; the other is preserved from disk.

This module is pure stdlib and self-contained — imported by the checkpoint hook
and the registry's resume step. The /common:handoff command is model-driven and
just follows the same on-disk format.
"""

import os
import re
from datetime import datetime, timezone
from pathlib import Path

FRESH_WINDOW_SECONDS = 48 * 3600  # resume only offers handoffs newer than this

_AUTO_START = "<!-- HANDOFF:AUTO -->"
_AUTO_END = "<!-- /HANDOFF:AUTO -->"
_NOTE_START = "<!-- HANDOFF:NOTE -->"
_NOTE_END = "<!-- /HANDOFF:NOTE -->"

_AUTO_PLACEHOLDER = "_(sem checkpoint ainda)_"
_NOTE_PLACEHOLDER = "_(sem narrativa — rode `/common:handoff` para escrever a história e o próximo passo)_"


def handoffs_dir(root: str) -> Path:
    return Path(root) / ".claude" / "handoffs"


def branch_slug(branch: str) -> str:
    """Filesystem-safe slug for a branch name (`session/0611-1430` → `session-0611-1430`)."""
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", (branch or "").strip()).strip("-")
    return s or "detached"


def handoff_path(root: str, branch: str) -> Path:
    return handoffs_dir(root) / f"{branch_slug(branch)}.md"


def _between(text: str, start: str, end: str) -> str:
    i = text.find(start)
    if i == -1:
        return ""
    j = text.find(end, i + len(start))
    if j == -1:
        return ""
    return text[i + len(start):j].strip("\n")


def parse(path: Path):
    """Return (meta: dict, auto: str, note: str). Tolerant of a missing/garbled file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}, "", ""
    meta = {}
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            for line in text[4:end].splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip()] = v.strip()
            body = text[end + len("\n---\n"):]
    auto = _between(body, _AUTO_START, _AUTO_END)
    note = _between(body, _NOTE_START, _NOTE_END)
    return meta, auto, note


def render(meta: dict, auto: str, note: str) -> str:
    fm = "---\n" + "".join(f"{k}: {v}\n" for k, v in meta.items()) + "---\n"
    return (
        f"{fm}\n"
        f"{_AUTO_START}\n{auto or _AUTO_PLACEHOLDER}\n{_AUTO_END}\n\n"
        f"{_NOTE_START}\n{note or _NOTE_PLACEHOLDER}\n{_NOTE_END}\n"
    )


def write(path: Path, meta: dict, auto: str = None, note: str = None) -> None:
    """Write the handoff, replacing only the zone(s) provided. Merges meta over
    whatever is on disk so each writer can refresh updated_at/turns without
    knowing the other's fields."""
    old_meta, old_auto, old_note = parse(path) if path.exists() else ({}, "", "")
    merged = {**old_meta, **{k: v for k, v in meta.items() if v is not None}}
    new_auto = old_auto if auto is None else auto
    new_note = old_note if note is None else note
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(render(merged, new_auto, new_note), encoding="utf-8")
    os.replace(tmp, path)  # atomic — a half-written handoff is worse than none


def age_seconds(meta: dict) -> float:
    stamp = meta.get("updated_at", "")
    if not stamp:
        return float("inf")
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(stamp)).total_seconds()
    except ValueError:
        return float("inf")
