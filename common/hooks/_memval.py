#!/usr/bin/env python3
"""Declared expiry of Claude Code memories.

A STATE memory ("not installed yet", "still to run on a real repo") is true on
the day it was written and rots silently; the `MEMORY.md` index enters the
context of every session, and an expired line arrives looking just like a fresh
one. The `validade: AAAA-MM-DD` field in the memory's frontmatter says until
when the fact can be repeated without rechecking. After that date, `sweep()`
marks its line in the index and `notice()` warns the session that is opening.

A memory without the field does not expire: a permanent lesson has no deadline,
and an alarm invented from missing data is worse than silence. The mark is
reversible: extend the expiry and the next sweep removes it.

Pure stdlib. Imported by session-registry (SessionStart); also runs by hand:

    python3 _memval.py sweep [<memory-dir>]
"""

import os
import re
import sys
from datetime import date
from pathlib import Path

MARK_PREFIX = "[VENCIDA desde "
_MARK_RE = re.compile(r"\[VENCIDA desde \d{4}-\d{2}-\d{2}, reconfira antes de afirmar\] ")
_EXPIRY_RE = re.compile(r"^\s*validade:\s*['\"]?(\d{4}-\d{2}-\d{2})['\"]?\s*$", re.M)
_LINK_RE = re.compile(r"^(\s*-\s*\[[^\]]*\]\(([^)]+\.md)\)\s*(?:—|-)\s*)(.*)$")


def memory_dir(main_root: str, home: str = None) -> Path:
    """Where Claude Code keeps this repo's memories: the main clone's path with
    every non-alphanumeric character replaced by `-`."""
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(main_root))
    return Path(home or Path.home()) / ".claude" / "projects" / slug / "memory"


def expiry_of(path: Path):
    """The expiry date declared in the frontmatter, or None (absent/unreadable)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    m = _EXPIRY_RE.search(text[4:end if end != -1 else len(text)])
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def sweep(mdir: Path, today: date = None):
    """Marks the expired memories in the index, unmarks those valid again.
    Returns the expired ones: [{"file", "validade"}]."""
    today = today or date.today()
    mdir = Path(mdir)
    if not mdir.is_dir():
        return []
    expired = {}
    for f in sorted(mdir.glob("*.md")):
        if f.name == "MEMORY.md":
            continue
        v = expiry_of(f)
        if v and v < today:
            expired[f.name] = v

    index = mdir / "MEMORY.md"
    try:
        old = index.read_text(encoding="utf-8")
    except OSError:
        old = None
    if old is not None:
        out = []
        for line in old.splitlines(keepends=True):
            body = line.rstrip("\n")
            m = _LINK_RE.match(body)
            if m:
                head, fname, rest = m.group(1), m.group(2), _MARK_RE.sub("", m.group(3))
                if fname in expired:
                    rest = (f"{MARK_PREFIX}{expired[fname].isoformat()}, "
                            f"reconfira antes de afirmar] {rest}")
                body = head + rest
            out.append(body + ("\n" if line.endswith("\n") else ""))
        new = "".join(out)
        if new != old:
            tmp = index.with_suffix(".md.tmp")
            tmp.write_text(new, encoding="utf-8")
            os.replace(tmp, index)
    return [{"file": k, "validade": v.isoformat()} for k, v in expired.items()]


def notice(expired):
    if not expired:
        return None
    items = ", ".join(f"`{v['file'][:-3]}` (venceu em {v['validade']})" for v in expired)
    return (
        f"[memória] {len(expired)} memória(s) com validade vencida: {items}. "
        "O que elas afirmam sobre estado (instalado ou não, rodado ou não, pendente) "
        "pode ter mudado: reconfira no disco/git antes de repetir. Ao reconferir, "
        "atualize o texto e a `validade:` da memória; a marca no MEMORY.md sai sozinha."
    )


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "sweep":
        if len(sys.argv) >= 3:
            target = Path(sys.argv[2])
        else:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import _wtlib as L
            target = memory_dir(L.main_root(os.getcwd()) or os.getcwd())
        found = sweep(target)
        print(f"{target}: {len(found)} vencida(s)")
        for v in found:
            print(f"  {v['file']}  validade {v['validade']}")
        sys.exit(0)
    print("usage: _memval.py sweep [<memory-dir>]", file=sys.stderr)
    sys.exit(2)
