#!/usr/bin/env python3
"""CS-3 of docs/spec/reforma-de-nomes-dos-comandos.md: the renamed slash commands
exist under the new name and the old ones do not exist (Q5: no file stays behind
under the old name to announce the new one; that line lives only in the CLI).

    /common:drain-plan    -> /common:queue-run
    /common:until-review  -> /common:run-review
    /common:worktree-name -> /common:worktree-rename
    /common:fila          -> /common:queue-status   (queue-status.md already exists)
    /common:modos         -> /common:modes          (modes.md already exists)
    /common:plan          -> /common:queue          (queue.md already exists)

Reads files only, no third-party dependency. Run with
`python3 tests/test_slash_command_rename.py` (prints ok/FAIL per case, exits
non-zero on failure) or with pytest.

What it does NOT prove: that the runner prompt behaves well (that is prompt), nor
the later prefix change (`common:` -> `cepa:`, items CS-12/CS-13). History files
(docs/acceptance, docs/proof, docs/archive, docs/spec, .claude/**) keep the old
names on purpose and are not scanned.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COMMANDS = REPO / "common" / "commands"

NEW = ["queue-run.md", "run-review.md", "worktree-rename.md"]
OLD = ["drain-plan.md", "until-review.md", "worktree-name.md",
       "fila.md", "modos.md", "plan.md"]
OLD_SLASH = ["drain-plan", "until-review", "worktree-name", "fila", "modos", "plan"]

# Declared compatibility: records on disk keep the name they were written with
# (spec Q4), so the digest reader must still recognise the old analysis command.
# One exact line in one file, nothing broader.
ALLOWED_LINES = {
    "common/bin/_run_digest.py":
        'REVIEW_COMMANDS = ("/common:run-review", "/common:until-review")',
}

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def live_files():
    """Files that must not point at a slash command that no longer exists."""
    out = []
    patterns = ["*/commands/*.md", "*/skills/**/SKILL.md", "*/agents/*.md",
                "common/hooks/*.py", "common/bin/*", "board-flow/bin/*",
                "compass/hooks/*", "*/.claude-plugin/plugin.json",
                ".claude-plugin/marketplace.json", "common/plan-schema.yaml",
                "README.md", "docs/commands.md", "docs/cepa-cli.md",
                "docs/cepa-until.md", "docs/workflow.md", "docs/how-it-fits.md",
                "docs/harness-ops.md", "docs/internals/hooks.md",
                "docs/modos-de-trabalho.md", "docs/execution-plan.md"]
    for pat in patterns:
        for f in sorted(REPO.glob(pat)):
            if f.is_file() and "__pycache__" not in f.parts:
                out.append(f)
    return out


def main():
    names = {p.name for p in COMMANDS.glob("*.md")}
    for n in NEW:
        check(f"{n} exists", n in names)
    for n in OLD:
        check(f"{n} does not exist", n not in names)

    # queue-run.md is the real runner, not a forwarder.
    qr = (COMMANDS / "queue-run.md").read_text() if "queue-run.md" in names else ""
    check("queue-run.md is not a forwarder",
          "/common:drain-plan" not in qr and "Transitional" not in qr)
    check("queue-run.md has the workflow (>= 60 lines)", len(qr.splitlines()) >= 60,
          f"{len(qr.splitlines())} lines")
    check("queue-run.md title is /common:queue-run",
          re.search(r"^# /common:queue-run\b", qr, re.M) is not None)

    for fname, title in (("run-review.md", "/common:run-review"),
                         ("worktree-rename.md", "/common:worktree-rename")):
        p = COMMANDS / fname
        text = p.read_text() if p.exists() else ""
        check(f"{fname} title is {title}",
              re.search(rf"^# {re.escape(title)}\b", text, re.M) is not None)

    # No live file points at a command that no longer exists.
    slash = re.compile(r"/common:(" + "|".join(OLD_SLASH) + r")(?![\w-])")
    bare = re.compile(r"""["'](drain-plan|until-review|worktree-name)["']\s*:\s*["']common:""")
    for f in live_files():
        text = f.read_text(errors="replace")
        rel = f.relative_to(REPO)
        allowed = ALLOWED_LINES.get(str(rel))
        if allowed:
            text = "\n".join(ln for ln in text.splitlines() if ln.strip() != allowed)
        hits = [m.group(0) for m in slash.finditer(text)] + \
               [m.group(0) for m in bare.finditer(text)]
        check(f"{rel} has no stale slash-command reference", not hits, str(hits[:3]))

    if FAILURES:
        print(f"\n{len(FAILURES)} failed")
        sys.exit(1)
    print("\nall ok")


def test_slash_command_rename():
    global FAILURES
    FAILURES = []
    try:
        main()
    except SystemExit as e:
        assert e.code in (0, None), FAILURES


if __name__ == "__main__":
    main()
