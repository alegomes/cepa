#!/usr/bin/env python3
"""PreToolUse hook: block "wrap-up" operations when build is STALE or FAILED.

Hard gate. Reads .claude/last-build.json (maintained by mark-build-stale
and capture-build-result hooks). When the orchestrator tries to commit,
push, open a PR, or do anything else that signals "I'm done" — and the
build state is STALE or FAILURE — refuses with a clear message.

Exit codes:
  0 — allowed
  2 — blocked (stderr reaches the agent so it can self-correct)

What gets gated, in two tiers:

  LOCAL operations — fail-OPEN when no baseline exists (with a loud
  warning). Recoverable with `git reset` if the commit was a mistake.
    - git commit

  SHARING operations — fail-CLOSED when no baseline exists. Broadcasts
  unverified code to others; the friction of forcing a baseline is
  worth it.
    - git push
    - gh pr create / merge / approve, gh release
    - kubectl apply, terraform apply
    - docker push
    - aws/gcloud/az deploy or push

  Both tiers fail-CLOSED when state is STALE or FAILURE (existing
  build context says "broken"; no exceptions).

What does NOT get gated:
  - Read-only Bash (status, log, diff, ls, etc.)
  - Test/build invocations themselves (./mvnw, gradle, pytest, npm test).
    These are how you fix STALE/FAILURE — gating them would be a deadlock.
  - ANY project that declares it has no build, via a `.claude/no-build`
    marker file. Explicit, human-placed opt-out for docs-only / build-less
    repos where a build baseline can never exist.
  - A project with NO recognizable build manifest at its root (no pom.xml,
    mvnw, gradlew, package.json, pyproject.toml, Cargo.toml, go.mod,
    Makefile...): sharing ops are allowed with a loud warning instead of
    blocked. There is nothing to baseline in such a repo, so fail-closed
    only produces a dead end (seen in practice: `git push` blocked on a
    browser-extension repo that has no build at all). The warning still
    asks for the `.claude/no-build` marker to make the opt-out explicit.
  - A LOCAL `git add <tests> && git commit -m ...` whose files are ALL test
    files while the baseline is FAILURE of TESTS (not of compilation/collection):
    allowed with a loud warning. It is the red regression test the test-first
    rule asks to commit BEFORE the fix (seen 2026-11-04, WEGO-2511/2513/2514/
    2515). Only that shape is inspected: -a / --include / --only / pathspec /
    --amend / command substitution / any other git command before the commit
    keep the block, as do a production file, an unknown file list, STALE/EMPTY,
    a compile failure and every SHARING operation (push / PR / deploy).

Which repo is judged: the one that RECEIVES the commit/push, not the one the
session runs in. `cd X && git commit` / `git -C X push` read `.claude/no-build`,
`last-build.json` and the build manifest at X's repo root. Seen 2026-10-10: a
session in kodez.cool (STALE baseline) ran `cd ~/coding/cepa && git commit` and
was blocked by kodez.cool's state. No cd / -C: the session's repo, as before.
Any failure resolving the target falls back to the session's repo (fail-open).

UNKNOWN status (state file present but unrecognized) is treated as
FAILURE (something's off; don't proceed).
"""

import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _wtlib as L  # noqa: E402
import _shellscan as S  # noqa: E402


def harvest_background(session_id, cwd=None):
    """capture-build-result's harvest, loaded by path (hyphenated file name).
    Never raises: a harvest failure must not decide the gate."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "capture_build_result", Path(__file__).resolve().parent / "capture-build-result.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.harvest_background(session_id, cwd)
    except Exception as e:
        print(f"[gate-advance] background build harvest failed: {e}", file=sys.stderr)

try:
    import _telemetry as T
except Exception:  # telemetry must never break the gate
    class T:  # noqa: N801
        @staticmethod
        def emit(*a, **k):
            pass


# Optional `-C <dir>` (or attached `-C<dir>`) between `git` and the subcommand:
# `git -C other-repo push` is the same operation as `cd other-repo && git push`
# and must not slip past the gate. Nothing else is widened (no --git-dir, -c k=v).
GIT_C = r"(?:\s+-C\s*\S+)*"

# Local operations: commit. Recoverable with git reset; missing baseline
# falls open with a loud warning (H1).
LOCAL_PATTERNS = [
    re.compile(r"(?:^|\s|&&\s|;\s)git" + GIT_C + r"\s+commit\b"),
]

# Sharing operations: push code to others / deploy. Missing baseline
# fails CLOSED (H2). Once your work crosses the boundary out of your
# machine, it's unrecoverable — the gate forces a baseline first.
SHARING_PATTERNS = [
    re.compile(r"(?:^|\s|&&\s|;\s)git" + GIT_C + r"\s+push\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)gh\s+pr\s+(?:create|merge|review\s+--approve)\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)gh\s+release\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)kubectl\s+apply\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)terraform\s+apply\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)docker\s+push\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)(?:aws|gcloud|az)\s+(?:.*\b)?(?:deploy|push)\b"),
]

# Test/build invocations should NEVER be gated — they're how you clear
# STALE/FAILURE. Allowlist explicitly.
EXEMPT_PATTERNS = [
    re.compile(r"(?:^|\s|&&\s|;\s)(?:\./)?mvnw?\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)(?:\./)?gradlew?\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)gradle\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)npm\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)(?:yarn|pnpm)\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)pytest\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)cargo\s+(?:test|build|check)\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)go\s+test\b"),
    # Allow git operations that don't push state out
    re.compile(r"(?:^|\s|&&\s|;\s)git" + GIT_C + r"\s+(?:status|log|diff|show|stash|checkout|restore|reset|add|rm|mv|fetch|pull|merge|rebase|branch|tag|worktree|config|remote)\b"),
]


# Root-level files that indicate the project HAS a build/test toolchain.
# Absence of all of them means there is nothing to baseline.
BUILD_MANIFESTS = [
    "pom.xml", "mvnw", "build.gradle", "build.gradle.kts", "gradlew",
    "package.json", "pyproject.toml", "setup.py", "Cargo.toml", "go.mod",
    "Makefile", "CMakeLists.txt", "mix.exs", "Gemfile",
]


def has_build_manifest(cwd: Path) -> bool:
    return any((cwd / m).exists() for m in BUILD_MANIFESTS)


def baseline_age_days(state: dict) -> float | None:
    """Best-effort age of the baseline in days, from its timestamp fields."""
    for key in ("at", "since"):
        raw = state.get(key)
        if not raw:
            continue
        try:
            ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds() / 86400
    return None


def classify(command: str) -> str:
    """Return one of: 'local', 'sharing', 'exempt-only', 'unrelated'."""
    matches_local = any(p.search(command) for p in LOCAL_PATTERNS)
    matches_sharing = any(p.search(command) for p in SHARING_PATTERNS)
    matches_exempt = any(p.search(command) for p in EXEMPT_PATTERNS)

    # When the command mixes exempt + gated portions, the gated portion
    # still matters. The strictest tier wins: sharing > local > exempt.
    if matches_sharing:
        return "sharing"
    if matches_local:
        return "local"
    if matches_exempt:
        return "exempt-only"
    return "unrelated"


def target_dir(command: str, cwd: str):
    """Directory the gated segment of `command` acts in, or None if not explicit.

    Never raises: any parse problem means "no explicit target" (today's anchor).
    """
    try:
        for seg, d, explicit in S.segment_dirs(command, cwd):
            if classify(seg) in ("local", "sharing"):
                # A target that does not resolve (`cd $VAR`, `cd -`, nonexistent
                # path) is a resolution failure, not a build-less repo: falls
                # back to the session's repo.
                return d if explicit and os.path.isdir(d) else None
    except Exception:
        pass
    return None


# ─── Red-test-only commit (test-first) ───────────────────────────────────
# capture-build-result's `kind` is the build TOOL, not the failure type, so the
# test-vs-compile distinction is read from the state's `tail` (last 12 lines).
COMPILE_MARKERS = [re.compile(p, re.M) for p in (
    # maven
    r"COMPILATION ERROR", r"Compilation failure", r"maven-compiler-plugin",
    r"cannot find symbol",
    # pytest collection
    r"errors? during collection", r"ImportError", r"ModuleNotFoundError",
    r"SyntaxError", r"IndentationError",
    # js
    r"Failed to compile", r"Cannot find module", r"\bTS\d{4}\b",
    # go
    r"\[build failed\]", r"undefined:", r"cannot use", r"syntax error",
    # cargo
    r"error\[E\d+\]", r"could not compile",
)]
TEST_MARKERS = [re.compile(p, re.M) for p in (
    # maven
    r"Tests run: \d+, Failures: [1-9]", r"Tests run: \d+, Failures: \d+, Errors: [1-9]",
    r"There (?:are|were) test failures", r"<<< FAILURE!", r"<<< ERROR!",
    r"maven-surefire-plugin", r"maven-failsafe-plugin",
    # pytest
    r"\b\d+ failed\b",
    # jest / vitest
    r"Tests:?\s+.*\b\d+ failed", r"✕", r"^FAIL ",
    # go (also covers the repo's script-style `FAIL  name`)
    r"--- FAIL:", r"^FAIL\s",
    # cargo
    r"test result: FAILED", r"panicked at",
)]

TEST_DIR_SEGMENTS = {"test", "tests", "__tests__", "spec", "specs", "testing"}
TEST_BASENAME = re.compile(
    r"^(?:test_.*\.py|.*_test\.py|conftest\.py|.*Tests?\.java|.*IT\.java|"
    r".*TestCase\.java|.*Test\.kt|.*Spec\.kt|.*Spec\.scala|"
    r".*\.(?:test|spec)\.(?:jsx?|tsx?|mjs|cjs)|.*_test\.go|.*_spec\.rb|.*_test\.rb)$"
)


def failure_is_test_failure(state: dict) -> bool:
    """True only when the FAILURE baseline is positively a failing TEST.

    Fail-closed: no tail, no marker, or any compile/collection marker -> False.
    A build stopped by Claude Code did not fail at all -> False.
    """
    try:
        if state.get("stopped_by") == "claude-code":
            return False
        text = "\n".join(str(state.get(k) or "") for k in ("tail", "reason"))
        if not text.strip():
            return False
        if any(m.search(text) for m in COMPILE_MARKERS):
            return False
        return any(m.search(text) for m in TEST_MARKERS)
    except Exception:
        return False


def is_test_path(path: str) -> bool:
    """True for test sources and fixtures/resources under a test directory."""
    parts = [x for x in path.replace("\\", "/").split("/") if x]
    if not parts:
        return False
    if any(seg in TEST_DIR_SEGMENTS for seg in parts[:-1]):
        return True
    return bool(TEST_BASENAME.match(parts[-1]))


_FLAGS_WITH_ARG = {
    "-m", "-F", "-C", "-c", "--author", "--date", "--message", "--file",
    "--fixup", "--squash", "--reuse-message", "--reedit-message", "--trailer",
    "-t", "--template", "--cleanup",
}


def _git_lines(repo_dir: str, args: list):
    r = subprocess.run(["git", "-C", repo_dir] + args, capture_output=True,
                       text=True, timeout=15)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return [ln for ln in r.stdout.splitlines() if ln]


def _status_paths(repo_dir: str, pathspec=None) -> list:
    """Paths `git status` reports (tracked changes + untracked files), repo-relative."""
    args = ["status", "--porcelain", "-z", "--untracked-files=all"]
    if pathspec:
        args += ["--", pathspec]
    r = subprocess.run(["git", "-C", repo_dir] + args, capture_output=True,
                       text=True, timeout=15)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    out, entries, i = [], r.stdout.split("\0"), 0
    while i < len(entries):
        e = entries[i]
        i += 1
        if len(e) < 4:
            continue
        out.append(e[3:])
        if e[0] in "RC" or e[1] in "RC":
            # rename/copy: the origin path follows as its own entry; a rename
            # deletes it, so it counts as touched too
            if i < len(entries) and entries[i]:
                out.append(entries[i])
            i += 1
    return out


_ADD_ALL_FLAGS = {"--all", "--update", "--patch", "--interactive"}

# Subcommands that change the index/tree in ways the hook cannot simulate: when
# one runs before the commit in the same command, the file list is unknowable.
_UNSIMULABLE_GIT = {"mv", "rm", "apply", "checkout", "restore", "reset", "stash",
                    "cherry-pick", "revert", "merge", "rebase"}


def _git_subcommand(toks: list):
    """Subcommand of a tokenized `git ...` segment (skips -C <dir> / -c k=v), or None."""
    if not toks or toks[0] != "git":
        return None
    i = 1
    while i < len(toks):
        if toks[i] in ("-C", "-c"):
            i += 2
        elif toks[i].startswith("-"):
            i += 1
        else:
            return toks[i]
    return None


_WRAPPERS = {"env", "command", "sudo", "nice", "time"}
_READONLY_GIT = {"status", "log", "diff", "show", "ls-files", "rev-parse", "branch"}


def _prior_segment_kind(seg: str) -> str:
    """Classify a segment that runs BEFORE the commit: 'add', 'safe' or 'unknown'.

    'add' = a plain `git add`; 'safe' = read-only git; anything that mentions git
    in any other way (VAR=x git ..., env/sudo git ..., sh -c "git ...") is 'unknown';
    everything else is 'other'. No non-git command is trusted as a no-op (echo, :,
    export can hide writes via redirection, $(...) or backticks).
    """
    toks = _tokens(seg)
    if toks and toks[0] == "git":
        sub = _git_subcommand(toks)
        if sub == "add":
            return "add"
        if sub in _READONLY_GIT:
            return "safe"
        return "unknown"
    if re.search(r"\bgit\b", seg):
        return "unknown"  # git behind VAR=value / env / sudo / sh -c ...
    return "other"  # not git: irrelevant to a plain commit (only the index counts)


def _tokens(seg: str) -> list:
    try:
        return shlex.split(seg)
    except ValueError:
        return seg.split()


def _add_files(seg: str, seg_dir: str, repo_dir: str, earlier_other: bool = False) -> list:
    """Paths a `git add` segment would stage (over-inclusive; may raise).

    A status-based add (-A/-u/-p/-i/./:/, a directory or a glob) reads the tree
    NOW, before an earlier non-git segment (`rm x;`) has run: it raises then.
    """
    def status_based(pathspec=None):
        if earlier_other:
            raise ValueError("status-based git add after a non-git segment")
        return _status_paths(repo_dir, pathspec)

    try:
        toks = shlex.split(seg)
    except ValueError:
        toks = seg.split()
    args = toks[toks.index("add") + 1:]
    out, after_dd = [], False
    for t in args:
        if any(c in t for c in "$`("):
            raise ValueError("shell expansion in git add")  # cannot evaluate: fail-closed
        if t.startswith(("--pathspec-from-file", "--pathspec-file-nul")):
            raise ValueError("pathspec from file")  # cannot read it: fail-closed
        if not after_dd and t == "--":
            after_dd = True
            continue
        if not after_dd and t.startswith("-") and len(t) > 1:
            if t in _ADD_ALL_FLAGS or (not t.startswith("--") and set(t[1:]) & set("Auip")):
                return status_based()
            continue
        if t in (".", ":/", ":/."):
            return status_based()
        rel = os.path.relpath(
            os.path.normpath(os.path.join(os.path.realpath(seg_dir), t)),
            os.path.realpath(repo_dir))
        expands = os.path.isdir(os.path.join(os.path.realpath(seg_dir), t)) or any(
            c in t for c in "*?[")
        found = status_based(rel) if expands else _status_paths(repo_dir, rel)
        out += found or [rel]
    return out


# Why the last commit_files() call answered None ("widen" = -a/--include/--only/
# pathspec form); read by main() to pick the BLOCKED hint.
_WHY = {"reason": None}


def commit_files(command: str, repo_dir: str, session_cwd=None):
    """Files the gated `git commit` would include, or None when unknown.

    Only the shape `git add <paths> && git commit -m ...` is inspected: staged
    files (`diff --cached`) plus the paths of any plain `git add` that comes
    BEFORE the commit in the same command (the hook runs before it, so the index
    does not have them yet). Forms whose file list depends on the working tree or
    on something the hook cannot evaluate answer None (fail-closed): -a/--all,
    --include/-i, --only/-o, pathspecs, --amend, command substitution, any git
    command before the commit other than a plain `git add` / read-only git.
    """
    _WHY["reason"] = None
    try:
        if "$(" in command or "`" in command:
            return None  # command substitution the hook cannot evaluate
        base = session_cwd or repo_dir
        seg, files, earlier_other = None, set(), False
        add_re = re.compile(r"^git" + GIT_C + r"\s+add\b")
        for s_, d_, _e in S.segment_dirs(command, base):
            if classify(s_) == "local":
                seg = s_
                break
            kind = _prior_segment_kind(s_)
            if kind == "unknown" or _git_subcommand(_tokens(s_)) in _UNSIMULABLE_GIT:
                return None
            if kind == "add" and add_re.search(s_.strip()):
                files |= set(_add_files(s_, d_, repo_dir, earlier_other))
            elif kind == "other":
                earlier_other = True
        if seg is None:
            return None
        toks = _tokens(seg)
        if "commit" not in toks:
            return None
        args = toks[toks.index("commit") + 1:]
        i = 0
        while i < len(args):
            t = args[i]
            if t == "--amend":
                return None  # the amended commit also carries the previous commit's files
            widen = False
            if t == "--":
                widen = i + 1 < len(args)
            elif t in _FLAGS_WITH_ARG:
                i += 2
                continue
            elif (not t.startswith("--") and len(t) > 2 and t.startswith("-")
                  and t[-1] in "mFCct" and not set(t[1:-1]) & set("aio")):
                i += 2  # cluster ending in an option that takes the next token: -qm "msg"
                continue
            elif t.startswith("--"):
                widen = t in ("--all", "--include", "--only")
            elif t.startswith("-") and len(t) > 1:
                widen = bool(set(t[1:]) & set("aio"))
            else:
                widen = True  # positional pathspec
            if widen:
                _WHY["reason"] = "widen"
                return None
            i += 1
        files |= set(_git_lines(repo_dir, ["diff", "--cached", "--no-renames", "--name-only"]))
        return sorted(files) or None
    except Exception:
        return None


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[gate-advance] could not parse hook payload; allowing", file=sys.stderr)
        sys.exit(0)

    if payload.get("tool_name") != "Bash":
        sys.exit(0)

    command = (payload.get("tool_input") or {}).get("command", "")
    if not command:
        sys.exit(0)

    tier = classify(command)
    if tier in ("unrelated", "exempt-only"):
        sys.exit(0)

    # A build that ran in the background may have ended since the last Bash
    # call; record it before judging the baseline (capture-build-result's
    # docstring, "Background builds").
    harvest_background(payload.get("session_id"),
                       L.session_root(payload.get("cwd") or os.getcwd()))

    # The worktree ROOT, not the current directory: Bash's cwd persists
    # between calls, and a `cd subdir` would divert this session's state
    # to `subdir/.claude/` for the rest of it (see _wtlib.session_root).
    # But if the command acts on ANOTHER repo (`cd X && git commit`,
    # `git -C X ...`), the baseline of the repo that receives the commit is
    # the one that counts (2026-10-10).
    session_cwd = payload.get("cwd") or os.getcwd()
    target = target_dir(command, session_cwd) or session_cwd
    cwd = Path(L.session_root(target)).resolve()

    # Explicit opt-out. A project with no build to verify declares it by
    # creating `.claude/no-build`. The gate has nothing to baseline here,
    # so it does not apply — to EITHER tier. This is a deliberate,
    # human-placed marker, never auto-detection: the gate does not open
    # a door by guessing a repo is build-less. (Commit the marker if the
    # opt-out should hold for teammates / CI too.)
    if (cwd / ".claude" / "no-build").exists():
        print(
            "[gate-advance] .claude/no-build present — this project opts out of "
            "build-baseline gating (no build to verify); allowing.",
            file=sys.stderr,
        )
        sys.exit(0)

    state_path = cwd / ".claude" / "last-build.json"

    # ─── Missing baseline ─────────────────────────────────────────────
    if not state_path.exists():
        if tier == "local":
            # H1: fail-OPEN for local commits, but make the warning
            # impossible to ignore. The user can `git reset` if they
            # later realize this commit slipped a broken build through.
            warning = (
                "\n"
                "╔══════════════════════════════════════════════════════════════════════╗\n"
                "║              ⚠  COMMIT WITHOUT BUILD VERIFICATION  ⚠               ║\n"
                "╠══════════════════════════════════════════════════════════════════════╣\n"
                "║  No .claude/last-build.json found at this project.                  ║\n"
                "║  No build has been verified yet — this commit is UNVERIFIED.        ║\n"
                "║                                                                      ║\n"
                "║  RECOMMENDED: run your project's verify command FIRST to establish  ║\n"
                "║    a baseline (e.g., `./mvnw verify`, `npm test`, `pytest`).        ║\n"
                "║                                                                      ║\n"
                "║  ALLOWED because this is a LOCAL commit (recoverable via            ║\n"
                "║    `git reset`). Pushes / PRs / deploys will be BLOCKED until       ║\n"
                "║    a SUCCESS baseline is recorded.                                  ║\n"
                "╚══════════════════════════════════════════════════════════════════════╝\n"
            )
            print(warning, file=sys.stderr)
            T.emit("gate_warn", cwd=str(cwd), tier=tier, reason="no-baseline")
            sys.exit(0)
        elif not has_build_manifest(cwd):
            # Build-less repo (no recognizable build manifest at root):
            # there is nothing to baseline, so blocking is a dead end.
            # Allow with a loud warning and ask for the explicit marker.
            print(
                "[gate-advance] ⚠ ALLOWED WITH WARNING: sharing operation in a repo "
                "with no recognizable build manifest (no pom.xml/package.json/etc.) "
                "and no build baseline. Nothing to verify here.\n"
                "  If this repo genuinely has no build, make the opt-out explicit:\n"
                "    mkdir -p .claude && touch .claude/no-build   (commit it)\n"
                "  If it DOES have a build under a non-root path, run its verify "
                "command from that path first to record a baseline.",
                file=sys.stderr,
            )
            T.emit("gate_warn", cwd=str(cwd), tier=tier, reason="no-build-manifest")
            sys.exit(0)
        else:
            # H2: fail-CLOSED for sharing operations.
            print(
                f"[gate-advance] BLOCKED: sharing operation requires a build baseline.\n"
                f"  Command: {command[:200]}\n"
                f"  No .claude/last-build.json found — no build has been verified at\n"
                f"  this project yet. Sharing unverified code is the failure mode this\n"
                f"  gate exists to prevent.\n"
                f"  Suggestion: run your project's verify command (e.g. `./mvnw verify`,\n"
                f"  `npm test`, `pytest`) to establish a SUCCESS baseline, then retry.\n"
                f"  If your project uses a build tool not recognized by capture-build-\n"
                f"  result.py, extend its PATTERNS list rather than faking the state file.\n"
                f"  If this project genuinely has NO build (e.g. docs-only), opt out\n"
                f"  honestly: create `.claude/no-build` (commit it to apply for the team).",
                file=sys.stderr,
            )
            T.emit("gate_block", cwd=str(cwd), tier=tier, reason="no-baseline")
            sys.exit(2)

    # ─── Baseline exists — read and gate on status ─────────────────────
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[gate-advance] could not read {state_path}: {e}; allowing", file=sys.stderr)
        sys.exit(0)

    status = state.get("status", "UNKNOWN")
    extra_note = ""
    if status == "SUCCESS":
        sys.exit(0)

    age = baseline_age_days(state)
    age_note = ""
    if age is not None:
        age_note = f" ({age:.0f} day(s) ago)"
        if age > 7:
            age_note += (
                " — this baseline is OLD and may describe a state that no longer "
                "exists (e.g. recorded by another session/worktree); re-running "
                "the verify command is the fastest way to find out"
            )

    # STALE, FAILURE or EMPTY (filtered green, zero tests) → block (regardless of tier).
    if status == "STALE":
        reason = f"build is STALE since edit to {state.get('after_edit_to', '<unknown path>')} at {state.get('since', '<unknown time>')}{age_note}"
        suggestion = "Run your project's verify command (e.g. `./mvnw <scope> verify`) before this operation. The hook will clear STALE on a green run."
    elif status == "EMPTY":
        reason = (
            f"build is EMPTY since {state.get('at', '<unknown time>')}{age_note}: the test "
            f"filter in `{state.get('command', '<unknown>')}` matched zero tests — it exited "
            f"green, but no test ran, so it proves nothing"
        )
        suggestion = (
            "Fix the test name in the filter (-Dtest= / -k / -run / -t) so it matches the "
            "tests you mean and re-run it, or make the build fail on an empty filter "
            "(Maven: -Dsurefire.failIfNoSpecifiedTests=true). A green with zero tests "
            "never counts as green."
        )
    elif status == "FAILURE":
        reason = f"build is FAILURE since {state.get('at', '<unknown time>')}{age_note} (command: `{state.get('command', '<unknown>')}`)"
        if state.get("reason"):
            # capture-build-result explains a FAILURE it did not read from the
            # build's own output (e.g. CC stopped the background task).
            reason += f": {state['reason']}"
        suggestion = "Fix the failing tests / build errors, re-run the verify command, and try again. Don't proceed with broken state."
        if tier == "local":
            if not failure_is_test_failure(state):
                if state.get("stopped_by") != "claude-code":
                    extra_note = (
                        "\n  the failure is a compilation/collection error, not a red test "
                        "— the tests-only exemption does not apply"
                    )
            else:
                files = commit_files(command, str(cwd), session_cwd)
                if files and all(is_test_path(f) for f in files):
                    shown = ", ".join(files[:5]) + (" ..." if len(files) > 5 else "")
                    print(
                        "\n[gate-advance] ⚠ ALLOWED WITH WARNING: local commit touching only "
                        f"test files ({shown}) while the baseline is a TEST failure.\n"
                        "  This is the red regression test the test-first rule asks to commit "
                        "BEFORE the fix.\n"
                        "  Push / PR / deploy still require a SUCCESS baseline. Disabling or "
                        "deleting the red test is not a fix.",
                        file=sys.stderr,
                    )
                    T.emit("gate_warn", cwd=str(cwd), tier=tier,
                           reason="red-test-only-commit", files=len(files))
                    sys.exit(0)
                if not files and _WHY["reason"] == "widen":
                    extra_note = (
                        "\n  the tests-only exemption applies to `git add <tests> && git "
                        "commit -m ...` only: -a / --include / pathspec forms are not inspected"
                    )
                elif not files:
                    extra_note = (
                        "\n  no files found for this commit: stage the test files (git add) "
                        "in a previous command or in this same command, before git commit"
                    )
                if files:
                    prod = next(f for f in files if not is_test_path(f))
                    extra_note = f"\n  not a tests-only commit: {prod}"
        if state.get("stopped_by") == "claude-code":
            suggestion = (
                "The build did not fail — it was stopped before it ended. Re-run it with a "
                "`timeout` that fits it (run_in_background takes up to 2 h; BASH_MAX_TIMEOUT_MS "
                "raises that ceiling, BASH_DEFAULT_TIMEOUT_MS the 30 min of an auto-backgrounded "
                "command), or narrow it so it fits."
            )
    else:
        reason = f"build status is {status!r} — unrecognized"
        suggestion = "Run your project's verify command to establish a known-good baseline."

    print(
        f"[gate-advance] BLOCKED: cannot run advancement command — {reason}.\n"
        f"  Command: {command[:200]}\n"
        f"  Suggestion: {suggestion}\n"
        f"  State file: {state_path}\n"
        f"  Override by re-establishing green build, not by editing the state file."
        f"{extra_note}",
        file=sys.stderr,
    )
    T.emit(
        "gate_block", cwd=str(cwd), tier=tier, reason=status.lower(),
        age_days=round(age, 1) if age is not None else None,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
