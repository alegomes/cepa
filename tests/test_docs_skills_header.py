#!/usr/bin/env python3
"""Every skill of the `docs-topology` plugin has a valid header block, and every
skill its agents are told to apply resolves to one.

No dependencies — run with `python3 tests/test_docs_skills_header.py`.
Exits non-zero if any check fails.

Without the `---` header block Claude Code does not list a skill, while the
agents still say "Apply `<skill>`" — a silent dead reference.

Covers, for `docs-topology/skills/*/SKILL.md`:

  - the file starts with a `---` block that closes;
  - `name` equals the directory name;
  - `description` is non-empty;

and, for `docs-topology/agents/*.md`:

  - every skill named by the phrase "Apply `<skill>`" is a skill directory of
    THIS plugin with a valid header (skills of other plugins, such as
    `humanizer`, are out of scope here and are skipped by name).

Scoped to one plugin on purpose; a repo-wide validator is a separate item.
Mirrors the style of `tests/test_marketing_topology.py`.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN_DIR = REPO / "docs-topology"
SKILLS_DIR = PLUGIN_DIR / "skills"
AGENTS_DIR = PLUGIN_DIR / "agents"

FAILURES = []

HEADER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)
# Agents also say "Apply `X` and `Y`" (docs-lead); catch the follow-on names.
APPLY_LINE_RE = re.compile(r"Apply\s+`[^`]+`(?:\s*(?:,|and)\s*`[^`]+`)*")
NAME_RE = re.compile(r"`([^`]+)`")


def check(label, cond, detail=""):
    if cond:
        print(f"  ok  {label}")
    else:
        FAILURES.append(label)
        print(f"FAIL  {label}  {detail}")


def header_of(path: Path):
    """Return the header as a dict, or None when there is no closed block."""
    m = HEADER_RE.match(path.read_text(encoding="utf-8"))
    if not m:
        return None
    out = {}
    for line in m.group(1).splitlines():
        if ":" not in line or line[:1].isspace():
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


def valid_header_problem(skill_dir: Path):
    """Return None when the skill header is valid, else a short reason."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return "SKILL.md missing"
    fm = header_of(skill_md)
    if fm is None:
        return "no closed --- header block"
    if fm.get("name") != skill_dir.name:
        return f"name={fm.get('name')!r}, expected {skill_dir.name!r}"
    if not fm.get("description"):
        return "empty description"
    return None


def test_skill_headers():
    dirs = sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())
    check("docs-topology has skill directories", bool(dirs))
    for d in dirs:
        problem = valid_header_problem(d)
        check(f"{d.name}: SKILL.md has a valid header (name + description)",
              problem is None, problem or "")


def applied_skills():
    """Map skill name -> sorted agent files that say 'Apply `<skill>`'."""
    found = {}
    for agent in sorted(AGENTS_DIR.glob("*.md")):
        text = agent.read_text(encoding="utf-8")
        for m in APPLY_LINE_RE.finditer(text):
            for name in NAME_RE.findall(m.group(0)):
                found.setdefault(name, set()).add(agent.name)
    return found


def test_applied_skills_resolve():
    found = applied_skills()
    # The two that motivated this test must be covered by the scan itself.
    for required in ("diataxis-discipline", "how-why-boundary"):
        check(f"agents apply `{required}` (scan sees it)", required in found)
    local = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()}
    for name, agents in sorted(found.items()):
        if name not in local:
            # Lives in another plugin (e.g. `humanizer` in common); not ours.
            print(f"  skip {name}: not a docs-topology skill "
                  f"({', '.join(sorted(agents))})")
            continue
        problem = valid_header_problem(SKILLS_DIR / name)
        check(f"`{name}` applied by {', '.join(sorted(agents))} resolves to a "
              f"valid skill", problem is None, problem or "")


def main():
    test_skill_headers()
    test_applied_skills_resolve()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} falha(s):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("all green")


if __name__ == "__main__":
    main()
