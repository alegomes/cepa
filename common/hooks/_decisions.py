"""Reader of the "Decided without asking" section of a spec or Epic.

One reader, two callers (item 6 of O2', base of item 3, in
docs/spec/tres-portas-spec-epic.md): the `spec-readiness-gate` hook counts the
lines without a verdict on the passage to ready, and `cepa-plan decisions`
lists them. Two copies of "what counts as a decision" and "what counts as a
verdict" would drift apart, and the count the owner sees at closing would stop
matching the list the command shows.

What it reads:
  * the `## Decided without asking` section, or the old name
    `## Decidido sem perguntar` (a title that STARTS with either, so
    "## Decidido sem perguntar (vete aqui)" counts too), up to the next `## `;
  * each top-level list item (`- `, `* `, `+ `) is one decision. Indented lines
    right below it continue the same item: the text comes back whole, with the
    file's words, lines joined by a space. A checkbox (`- [ ]`) is a question,
    not a decision; a template line (`<...>`) or a filler (`n/a`, `tbd`) is not
    a decision either;
  * the verdict is the marker `cepa-plan verdict` writes at the end of the
    item: `· mantida em`, `· vetada em` or `· refinada em`.

Stdlib only: it is imported from a hook, which runs on every Write.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

SECTION_NAMES = ("decided without asking", "decidido sem perguntar")

VERDICTS = ("mantida", "vetada", "refinada")

VERDICT_RE = re.compile(r"·\s*(mantida|vetada|refinada)\s+em\b", re.IGNORECASE)

_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
_ITEM_RE = re.compile(r"^[-*+]\s+(.+)$")
_CHECKBOX_RE = re.compile(r"^\[[ xX]\]")

_FILLERS = ("", "-", "n/a", "na", "tbd", "todo", "a definir", "?", "...")


@dataclass
class Decision:
    text: str               # the item, in the file's words
    line: int               # 1-based line where the item starts
    verdict: Optional[str]  # "mantida" | "vetada" | "refinada" | None


@dataclass
class Decisions:
    pending: List[Decision] = field(default_factory=list)  # without verdict
    decided: List[Decision] = field(default_factory=list)  # with verdict


def _clean(value: str) -> str:
    v = value.strip()
    v = re.sub(r"^(\*\*|__|`)+|(\*\*|__|`)+$", "", v).strip()
    v = v.strip("*_`").strip()
    return v.rstrip(".;,").strip()


def _is_filler(value: str) -> bool:
    v = _clean(value).lower()
    return v.startswith("<") or v in _FILLERS


def _is_section_title(title: str) -> bool:
    return title.strip().lower().startswith(SECTION_NAMES)


def read(content: str) -> Optional[Decisions]:
    """The decisions of `content`, split by verdict, or None when the document
    has no "Decided without asking" section. Only the first such section is
    read, as the gate does."""
    lines = content.splitlines()
    start = None
    for i, raw in enumerate(lines):
        m = _HEADING_RE.match(raw)
        if m and _is_section_title(m.group(1)):
            start = i + 1
            break
    if start is None:
        return None

    items = []      # (line_number, [parts])
    current = None  # the item indented lines still continue
    for i in range(start, len(lines)):
        raw = lines[i]
        if _HEADING_RE.match(raw):
            break
        m = _ITEM_RE.match(raw)
        if m:
            current = (i + 1, [m.group(1).strip()])
            items.append(current)
        elif current is not None and raw.strip() and raw[:1].isspace():
            current[1].append(raw.strip())
        else:
            # A blank line or loose prose ends the current item.
            current = None

    out = Decisions()
    for number, parts in items:
        text = " ".join(parts)
        if _CHECKBOX_RE.match(text) or _is_filler(text):
            continue
        found = VERDICT_RE.findall(text)
        verdict = found[-1].lower() if found else None
        d = Decision(text=text, line=number, verdict=verdict)
        (out.decided if verdict else out.pending).append(d)
    return out


def read_file(path) -> Optional[Decisions]:
    """`read` over a file on disk. None also when the file cannot be read."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return read(text)
