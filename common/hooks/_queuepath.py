"""_queuepath: where a repo's single-track queue lives, in both layouts.

The queue moved from `.claude/programs/<name>/plan.yaml` (key `program:`,
written by /common:plan) to `.claude/queues/<name>/queue.yaml` (key `queue:`,
written by /common:queue), to match the vocabulary of docs/how-it-fits.md.
During the transition every consumer READS BOTH layouts; `cepa-plan migrate`
moves the existing queues. The maestro wave plan (`parallel-waves`) stays in
`.claude/programs/<name>/plan.yaml`: it is a program, not a queue.

This module is the only copy of the resolution rule; the binaries import it.
"""
from pathlib import Path

NEW_DIR = ".claude/queues"
NEW_FILE = "queue.yaml"
LEGACY_DIR = ".claude/programs"
LEGACY_FILE = "plan.yaml"


def _new(root, name):
    return Path(root) / NEW_DIR / name / NEW_FILE


def _legacy(root, name):
    return Path(root) / LEGACY_DIR / name / LEGACY_FILE


def queue_file(root, name):
    """The queue file: the new one if it exists; else the legacy one if it
    exists; else the NEW path (a new queue is born in the new layout)."""
    new = _new(root, name)
    if new.exists():
        return new
    legacy = _legacy(root, name)
    if legacy.exists():
        return legacy
    return new


def queue_dir(root, name):
    """The queue directory (where `until/` and the `.bak` live)."""
    return queue_file(root, name).parent


def queue_files(root):
    """[(name, path)] of every candidate in both layouts, by name.

    When the same name exists in both, the new one wins. The caller still
    filters by `mode: single-track` (the legacy layout also holds wave plans)."""
    found = {}
    for base, fname in ((LEGACY_DIR, LEGACY_FILE), (NEW_DIR, NEW_FILE)):
        for p in (Path(root) / base).glob(f"*/{fname}"):
            found[p.parent.name] = p  # the new one comes later and overwrites
    return sorted(found.items())


def queue_name_of(plan, fallback=None):
    """The name recorded in the header: `queue:` (new) or `program:` (legacy)."""
    if not isinstance(plan, dict):
        return fallback
    return plan.get("queue") or plan.get("program") or fallback


def both_layouts(root, name):
    """True if the same name exists in both layouts (the new one hides the legacy)."""
    return _new(root, name).exists() and _legacy(root, name).exists()
