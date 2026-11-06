"""Single definition of "what counts as dirt" in a clone.

Reason (fb-20261105-3, 2026-11-05): `/common:wrap-up` said "Safe to exit" with
the main clone dirty, and right after `cepa-until` refused to start on that
same clone. The rule lived in two places (cepa-until and cepa-doctor) and had
already drifted (the doctor did not ignore `queue.yaml.bak`). Everything that
asks "is this clone clean?" imports it from here: cepa-until, cepa-doctor and
the safe-exit-gate Stop hook.
"""

import fnmatch
import re
import subprocess

# The run's own record (`.jsonl`, `.log`, `.review.md`) lives inside the
# repo, in `.claude/queues/<queue>/until/` (or `.claude/programs/<queue>/until/`, the old
# layout). It is not dirt: without this filter, the
# first run leaves the folder untracked and the next one refuses to start
# because of what the previous one wrote.
RUN_RECORD = re.compile(r"^.. \.claude/(programs|queues)/[^/]+/until/")
# For the same reason, the copy that `cepa-plan write` makes of the previous queue before
# rewriting it: it is born untracked, and without this filter every rewrite of the
# queue blocked the next run until someone deleted the `.bak` by hand. Only the
# untracked (`??`): a `.bak` that was committed and then changed is a real change.
QUEUE_BAK = re.compile(r"^\?\? \.claude/(programs/[^/]+/plan|queues/[^/]+/queue)\.yaml\.bak$")

# Machine-local runtime state that hooks/commands write and that must never be
# tracked (mirrors this repo's own .gitignore). Gitignore-style: a trailing
# slash means "anything under this directory".
HOOK_RUNTIME_PATTERNS = (
    ".claude/session-log.md",
    ".claude/doctor-last-run",
    ".claude/last-build.json",
    ".claude/loop-state.json",
    ".claude/session-mode",
    ".claude/session-intent",
    ".claude/feedback-nudge",
    ".claude/sessions/",
    ".claude/handoffs/",
    ".claude/rescued/",
    ".claude/expertise",
    ".claude/queues/*/until/*.log",
    ".claude/queues/*/until/*.estado.json",
    ".claude/programs/*/until/*.log",
    ".claude/programs/*/until/*.estado.json",
)

# `.claude/expertise` is the install symlink here, but a project may track
# `.claude/expertise/*.yaml` on purpose: a hook appending to a tracked expertise
# file is a change the wrap-up commits, not a file to untrack. So the doctor's
# "tracked file hooks write" warning leaves it out.
TRACKED_IS_WRONG = tuple(p for p in HOOK_RUNTIME_PATTERNS if p != ".claude/expertise")

EXCLUDE_HEADER = "# cepa: estado de runtime dos hooks (safe-exit-gate)"


def counts_as_dirt(line):
    """A `git status --porcelain` line that makes the clone dirty."""
    return bool(line.strip()) and not RUN_RECORD.match(line) \
        and not QUEUE_BAK.match(line)


def _git(repo, args, timeout=30):
    try:
        p = subprocess.run(["git", "-c", "core.quotepath=false"] + args,
                           cwd=str(repo), capture_output=True,
                           text=True, timeout=timeout)
    except Exception:
        return None
    return p.stdout if p.returncode == 0 else None


def dirt(repo, untracked_all=True):
    """Porcelain lines that count as dirt; None when git fails.

    Untracked files are listed one by one (`--untracked-files=all`), never as a
    collapsed directory: a collapsed `?? .claude/` hides the run record and the
    runtime files the filters below are meant to tell apart. `cepa-until` and the
    doctor list the same way, so the three agree on what is dirt."""
    args = ["status", "--porcelain"]
    if untracked_all:
        args.append("--untracked-files=all")
    out = _git(repo, args)
    if out is None:
        return None
    return [l for l in out.splitlines() if counts_as_dirt(l)]


def _path_of(line):
    """Repo-relative path of a porcelain line (the new name for renames)."""
    p = line[3:]
    if " -> " in p:
        p = p.split(" -> ", 1)[1]
    if len(p) >= 2 and p[0] == '"' and p[-1] == '"':
        p = p[1:-1]
    return p


def is_runtime(path, patterns=HOOK_RUNTIME_PATTERNS):
    """Does the repo-relative path match a hook-runtime pattern?"""
    for pat in patterns:
        if pat.endswith("/"):
            if path.startswith(pat) or path + "/" == pat:
                return True
        elif fnmatch.fnmatch(path, pat) or path.startswith(pat + "/"):
            return True
    return False


def classify(repo):
    """Split the dirt into tracked changes / untracked runtime / other untracked.
    Returns None when git fails."""
    lines = dirt(repo)
    if lines is None:
        return None
    res = {"tracked": [], "runtime": [], "untracked": []}
    for l in lines:
        path = _path_of(l)
        if l.startswith("??"):
            res["runtime" if is_runtime(path) else "untracked"].append(path)
        else:
            res["tracked"].append(path)
    return res


def tracked_runtime(repo):
    """Tracked files that match a hook-runtime pattern (excluding does not
    help these; they need `git rm --cached`)."""
    out = _git(repo, ["ls-files"])
    if out is None:
        return []
    return [p for p in out.splitlines() if is_runtime(p, TRACKED_IS_WRONG)]


def exclude_runtime(repo, paths):
    """Append to `<git-common-dir>/info/exclude` the runtime patterns matching
    `paths` (skipping any already present). Returns the patterns added."""
    import os
    out = _git(repo, ["rev-parse", "--path-format=absolute", "--git-common-dir"])
    if not out or not out.strip():
        return []
    ex = os.path.join(out.strip(), "info", "exclude")
    try:
        existing = open(ex, encoding="utf-8").read()
    except OSError:
        existing = ""
    have = {l.strip() for l in existing.splitlines()}
    add = []
    for pat in HOOK_RUNTIME_PATTERNS:
        if pat in have or pat in add:
            continue
        if any(is_runtime(p) and (fnmatch.fnmatch(p, pat) or
                                  (pat.endswith("/") and p.startswith(pat)) or
                                  p.startswith(pat + "/") or p + "/" == pat)
               for p in paths):
            add.append(pat)
    if add:
        os.makedirs(os.path.dirname(ex), exist_ok=True)
        text = existing
        if text and not text.endswith("\n"):
            text += "\n"
        if EXCLUDE_HEADER not in have:
            text += EXCLUDE_HEADER + "\n"
        text += "\n".join(add) + "\n"
        with open(ex, "w", encoding="utf-8") as f:
            f.write(text)
    return add
