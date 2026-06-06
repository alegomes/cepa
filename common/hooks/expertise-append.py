#!/usr/bin/env python3
"""Append a feedback entry to an agent's expertise file — atomically, under a lock.

Why this exists: the `common/expertise/<agent>-mental-model.yaml` files are
symlinked from the plugin source and shared across EVERY project and EVERY
concurrent `claude` session. Worktree-per-session isolates the repo's `.claude/`
state, but it does NOT isolate these files — they're one physical copy behind
all worktrees. Two `/common:debrief` runs (or two agents writing learnings at
task end) that hit the same agent file concurrently race on a read-modify-write
and lose one side's entry.

This helper serializes that write with an advisory file lock (`flock`) and does
the whole read → append → prune → write cycle while holding it, so concurrent
callers queue instead of clobbering.

Formatting is preserved deliberately. These files are hand-edited and use YAML
block scalars (`|`) and intentional blank-line spacing; round-tripping through
`yaml.dump` would rewrite the entire file into a noisy diff. So we parse with
PyYAML ONLY to count and classify existing entries (for the 20-cap prune), and
we mutate at the TEXT level — appending the caller's verbatim item block and
deleting whole line-ranges of pruned items. Kept items keep their exact original
text.

Usage:
  printf '<item block>' | python3 expertise-append.py --file <path> [--cap 20]

The item block on stdin is the new `feedback:` list item, already indented as it
should appear in the file, e.g.:

  - run_id: 2026-06-06-foo
    date: 2026-06-06
    topic: ...
    user_verdict: keep
    user_reason: "..."
    tag: example

Exit codes: 0 on success (prints a one-line summary), 1 on usage/IO error.
Prune rule: when appending would exceed --cap entries, drop the oldest entries
whose `tag` is not `principle`, oldest first, until at cap. principle-tagged
entries are never auto-pruned.
"""

import argparse
import fcntl
import os
import re
import sys

try:
    import yaml
    _HAVE_YAML = True
except ImportError:  # degrade gracefully — append still works, prune is skipped
    _HAVE_YAML = False


ITEM_RE = re.compile(r"^( *)- ")          # a sequence item line
TOPKEY_RE = re.compile(r"^[^\s#-][^:]*:")  # a column-0 mapping key


def split_region(lines: list[str], section: str) -> tuple[int, int]:
    """Return (start, end) line indices of the `<section>:` block body.

    start = index of the first line AFTER the `<section>:` key line.
    end   = index of the next column-0 key (exclusive), or len(lines).
    Returns (-1, -1) if there's no column-0 `<section>:` key.
    """
    key_line = -1
    for i, ln in enumerate(lines):
        if not ln.startswith(" ") and ln.lstrip().startswith(f"{section}:"):
            key_line = i
            break
    if key_line == -1:
        return -1, -1
    end = len(lines)
    for j in range(key_line + 1, len(lines)):
        if TOPKEY_RE.match(lines[j]):
            end = j
            break
    return key_line + 1, end


def item_blocks(region: list[str]) -> list[tuple[int, int]]:
    """Split a feedback region into (start, end) line-index ranges, one per item."""
    starts = [i for i, ln in enumerate(region) if ITEM_RE.match(ln)]
    blocks = []
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else len(region)
        blocks.append((s, e))
    return blocks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--section", default="feedback",
                    help="top-level sequence to append into (feedback, "
                         "heuristics, ecosystem_gotchas, ...). Default: feedback")
    ap.add_argument("--cap", type=int, default=20,
                    help="max entries in the section; 0 disables auto-prune. "
                         "When over cap, oldest non-principle entries drop first")
    args = ap.parse_args()
    section = args.section

    new_item = sys.stdin.read().rstrip("\n")
    if not new_item.strip():
        print("[expertise-append] empty entry on stdin; nothing to do", file=sys.stderr)
        return 1

    path = args.file
    if not os.path.exists(path):
        print(f"[expertise-append] file not found: {path}", file=sys.stderr)
        return 1

    # Lock the file for the whole read-modify-write. flock is advisory but every
    # writer goes through this helper, so the lock is honoured by construction.
    with open(path, "r+", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            text = f.read()
            lines = text.splitlines()

            # Classify existing entries (tag == principle => protected).
            protected = []
            count = 0
            if _HAVE_YAML:
                try:
                    data = yaml.safe_load(text) or {}
                    existing = data.get(section) or []
                    count = len(existing)
                    protected = [
                        isinstance(e, dict) and e.get("tag") == "principle"
                        for e in existing
                    ]
                except yaml.YAMLError:
                    count, protected = 0, []  # can't classify → append only

            start, end = split_region(lines, section)
            new_block = new_item.split("\n")

            if start == -1:
                # No such section yet — create it at EOF.
                tail = [] if (not lines or lines[-1].strip() == "") else [""]
                lines = lines + tail + [f"{section}:"] + new_block
                dropped = 0
            else:
                region = lines[start:end]
                blocks = item_blocks(region)
                # Decide drops: appending one => count+1; trim to cap (cap 0 = off).
                overflow = (count + 1) - args.cap if args.cap > 0 else 0
                drop_idx = set()
                if overflow > 0 and len(blocks) == count and protected:
                    for i in range(len(blocks)):  # oldest first
                        if overflow <= 0:
                            break
                        if not protected[i]:
                            drop_idx.add(i)
                            overflow -= 1
                dropped = len(drop_idx)

                kept_region = []
                for i, (bs, be) in enumerate(blocks):
                    if i in drop_idx:
                        continue
                    block = region[bs:be]
                    # normalise: strip trailing blank lines inside the block
                    while block and block[-1].strip() == "":
                        block.pop()
                    kept_region.extend(block)
                    kept_region.append("")  # one blank line between items
                kept_region.extend(new_block)

                lines = lines[:start] + kept_region + lines[end:]

            out = "\n".join(lines).rstrip("\n") + "\n"

            # Atomic-ish replace within the locked handle.
            f.seek(0)
            f.write(out)
            f.truncate()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    print(f"[expertise-append] appended to {os.path.basename(path)} "
          f"[{section}] (was {count}, dropped {dropped}, now {count + 1 - dropped})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
