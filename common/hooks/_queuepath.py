"""_queuepath: where a repo's single-track queue lives, in both layouts.

The queue moved from `.claude/programs/<name>/plan.yaml` (key `program:`,
written by /common:plan) to `.claude/queues/<name>/queue.yaml` (key `queue:`,
written by /common:queue), to match the vocabulary of docs/how-it-fits.md.
During the transition every consumer READS BOTH layouts; `cepa-queue migrate`
moves the existing queues. The maestro wave plan (`parallel-waves`) stays in
`.claude/programs/<name>/plan.yaml`: it is a program, not a queue.

This module is the only copy of the resolution rule; the binaries import it.
"""
import re
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


# The side branches `cepa-until` creates: `until/<run>-vermelho-<id>[-v<n>]` on a
# red build, `until/<run>-parado-<id>` on the item that spent its attempts and
# `until/<run>-travado-<id>` on the item the agent closed `blocked` with commits.
# A `--all` run puts the queue in front of the id: `<run>-vermelho-<queue>-<id>`.
SIDE_BRANCH = re.compile(
    r"^until/(\d{4}-\d{2}-\d{2}-\d{4})-(?:vermelho|parado|travado)-(.+?)"
    r"(?:-v\d+)?$")
ALL_DIR = "_all"


def _run_ledger(root, queue, run):
    return queue_dir(root, queue) / "until" / f"{run}.jsonl"


def side_branch_item(root, queue, branch):
    """The id of the `queue` item a side branch belongs to, or None when the
    branch is not a side branch or belongs to another queue.

    Queues reuse ids (`CS-1`, `CS-6`), so the id in the name says nothing about
    the queue. The run in the name does: each run writes its `.jsonl` in the
    folder of its own queue (or of `_all`, for `--all`). The branch is this
    queue's when that run's ledger is in this queue's folder; a `--all` run's
    branch is, when its ledger is in `_all` and the name carries the queue.
    When the same run name has a ledger in another queue too (two runs started
    in the same minute), the ledger has to name the branch (fb-20261120-2)."""
    m = SIDE_BRANCH.match(str(branch).strip())
    if not m:
        return None
    run, tail = m.groups()
    own = _run_ledger(root, queue, run)
    if own.is_file():
        others = [p for base in (NEW_DIR, LEGACY_DIR)
                  for p in (Path(root) / base).glob(f"*/until/{run}.jsonl")
                  if p.parent.parent.name not in (queue, ALL_DIR)]
        if not others:
            return tail
        try:
            return tail if branch in own.read_text(encoding="utf-8") else None
        except OSError:
            return None
    prefix = f"{queue}-"
    if (_run_ledger(root, ALL_DIR, run).is_file() and tail.startswith(prefix)
            and len(tail) > len(prefix)):
        return tail[len(prefix):]
    return None
