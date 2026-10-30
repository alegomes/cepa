#!/usr/bin/env python3
"""Resolves the FILE of a plugin command and reads its frontmatter.

Two hooks need the same answer to the same question: "which .md file is this
command, and what does its `interaction:` field say?":

  - session-routine-guard.py  refuses /common:session on a `conversational`
    command;
  - default-yes-inject.py     injects the default-yes policy when the command
    is `routine`.

Duplicating the resolution would be worse than it looks. It has a trap that
already bit once (June/2026, in session-routine-guard): the Claude Code cache
keeps the versions side by side (cache/cepa/common/1.4.0, 1.5.0, 1.6.0) and an
alphabetical scan reads the OLD version, from before the field existed, and
confidently answers the wrong thing. Two copies of the resolution are two
chances for the fix to exist in only one of them.

Search order, from most to least authoritative:

  1. CC's installed_plugins.json, which knows which copy is alive;
  2. CLAUDE_PLUGIN_ROOT itself, when the requested plugin owns the hook;
  3. a scan, from the HIGHEST version to the lowest (never alphabetical).

The owning plugin is matched by the NAME declared in the manifest, not by
directory: `capture.md` exists in board-flow AND in discovery, and the `docs`
plugin lives in the `docs-topology/` directory.

Every function fails by returning None. The caller decides what to do with the
"don't know", and in both hooks today "don't know" means do not interfere.
"""

import json
import os
import re
from pathlib import Path

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
INTERACTION_RE = re.compile(
    r"^interaction\s*:\s*[\"']?([A-Za-z-]+)[\"']?\s*$", re.MULTILINE
)

# The field's closed vocabulary. Any other value is treated as unknown, and
# unknown never activates any policy.
ROUTINE = "routine"
CONVERSATIONAL = "conversational"
VALUES = (ROUTINE, CONVERSATIONAL)


def bases():
    """Directories where to look for plugins, in the repo and in the installed cache.

    In the repo,  CLAUDE_PLUGIN_ROOT = <repo>/common               → siblings in <repo>/
    In the cache, CLAUDE_PLUGIN_ROOT = <cache>/cepa/common/2.2.0   → siblings two
    levels up, each with its own version directory.
    """
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not root:
        return []
    p = Path(root)
    return [d for d in (p.parent, p.parent.parent) if d and d.is_dir()]


def plugin_name(cmd_file: Path):
    """The name declared in the manifest of the plugin that owns this command file."""
    for parent in cmd_file.parents:
        mf = parent / ".claude-plugin" / "plugin.json"
        if mf.is_file():
            try:
                return json.loads(mf.read_text(encoding="utf-8")).get("name")
            except Exception:  # noqa: BLE001
                return None
    return None


def installed_root(plugin: str):
    """The copy CC says is alive, according to installed_plugins.json.

    The marketplace name is not assumed: `<plugin>@` is matched whatever the
    suffix.
    """
    reg = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
    try:
        d = json.loads(reg.read_text(encoding="utf-8")).get("plugins", {})
    except Exception:  # noqa: BLE001
        return None
    for key, entries in d.items():
        if not key.startswith(f"{plugin}@") or not entries:
            continue
        path = entries[0].get("installPath")
        if path and (Path(path) / "commands").is_dir():
            return Path(path)
    return None


def version_of(cand: Path):
    """Sort key: the highest version first, the rest after."""
    for parent in cand.parents:
        parts = parent.name.split(".")
        if len(parts) == 3 and all(x.isdigit() for x in parts):
            return tuple(int(x) for x in parts)
    return (0, 0, 0)


def find_command(plugin: str, cmd: str):
    """The .md file of `<plugin>:<cmd>`, or None if it cannot be determined."""
    # 1. The copy CC declares alive.
    root = installed_root(plugin)
    if root:
        f = root / "commands" / f"{cmd}.md"
        if f.is_file() and plugin_name(f) == plugin:
            return f

    # 2. The root the hook is running from, when the target is this plugin.
    here = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if here:
        f = Path(here) / "commands" / f"{cmd}.md"
        if f.is_file() and plugin_name(f) == plugin:
            return f

    # 3. Scan, from the highest version to the lowest, never alphabetical.
    for base in bases():
        for pattern in (f"{plugin}*/commands/{cmd}.md",
                       f"{plugin}*/*/commands/{cmd}.md",
                       f"*/commands/{cmd}.md",
                       f"*/*/commands/{cmd}.md"):
            found = [c for c in base.glob(pattern) if plugin_name(c) == plugin]
            if found:
                return max(found, key=version_of)
    return None


def interaction(cmd_file: Path):
    """The value of the frontmatter `interaction:` field, lowercased.

    None when the file does not open, has no frontmatter, or does not declare the field.
    """
    try:
        text = cmd_file.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return None
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    found = INTERACTION_RE.search(m.group(1))
    return found.group(1).lower() if found else None
