#!/usr/bin/env python3
"""PostToolUse hook: capture build/test results to .claude/last-build.json.

Fires after Bash invocations of common build/test commands. Parses the
tool result for SUCCESS / FAILURE markers and writes the canonical state
file the /common:green-or-revert skill and gate-advance hook consult.

Out-of-band: orchestrator can claim "build is green" only by reading this
file; it cannot fabricate the entry. Hook owns the write.

Patterns detected:
  - Maven: ./mvnw or mvn  → BUILD SUCCESS / BUILD FAILURE
  - Gradle: ./gradlew or gradle  → BUILD SUCCESSFUL / BUILD FAILED
  - npm/yarn/pnpm test → exit code is the signal
  - pytest → exit code is the signal
  - cargo → exit code
  - go test → exit code
  - docker build → output markers (writing image / naming to /
    Successfully built), NOT exit code — CC's Bash tool_response omits
    the exit code on success, so marker-less patterns can't classify.

If the command isn't one we know how to parse, we skip — better to leave
stale than mis-classify.

Third state, EMPTY: a command with a TEST FILTER (`-Dtest=`, `pytest -k`,
`go test -run`, jest `-t`/`--testNamePattern`) that exits green but executed
zero tests is recorded as EMPTY, never SUCCESS — see refine_empty().

Never blocks. Failures are stderr-only.

Debugging: set CAPTURE_BUILD_DEBUG=1 to dump every invocation's
payload + classification details to /tmp/capture-build-debug.log
(or to $CAPTURE_BUILD_DEBUG_LOG if set). Same pattern as
HEX_PATHLOCK_DEBUG.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _wtlib as L  # noqa: E402



# Shared markers for the JS/Node toolchain (npm/yarn/pnpm). CC's Bash
# tool_response omits the exit code on SUCCESS, so a green npm/Next build can
# only be recognized by text. FAILURES still carry a non-zero exit code (→
# is_error → exit-code fallback), so they classify even without a marker; the
# success markers below are what close the green-detection gap.
#
# Success markers cover the dominant build tools: Next.js / CRA / webpack
# ("Compiled successfully"), Vite ("built in"), and the yarn success footer
# ("Done in "). Failure markers are a safety net (checked first) so a build that
# prints a success marker mid-run but fails later — e.g. Next compiles, then a
# page throws during prerender — is still classified FAILURE.
_JS_SUCCESS = ["Compiled successfully", "built in", "build completed", "Done in "]
_JS_FAILURE = [
    "npm error",                  # npm v9/10 wraps any failed run-script
    "npm ERR!",                   # npm v8 and earlier
    "ELIFECYCLE",                 # npm/pnpm lifecycle failure
    "error Command failed",       # yarn
    "Failed to compile",          # Next.js / CRA compile error
    "Build error occurred",       # Next.js build failure
    "Export encountered errors",  # Next.js export/prerender failure
    "error TS",                   # tsc type error
]

# (regex on command, kind, success-markers, failure-markers)
# Markers may be None, a single string, or a list of substrings. Failure
# markers are checked first (fail-closed). When no marker is defined OR
# matched, we fall back to exit_code — but note CC's Bash tool_response
# omits the exit code on success in current versions, so marker-less
# patterns (pytest/cargo/go-test below) effectively can't classify a green
# build yet. Prefer text markers. See classify().
PATTERNS = [
    (re.compile(r"(?:^|\s)(?:\./)?mvnw?\b.*\b(?:verify|test|package|install)\b"),
     "maven", ["BUILD SUCCESS"], ["BUILD FAILURE"]),
    (re.compile(r"(?:^|\s)(?:\./)?gradlew?\b.*\b(?:build|test|check|verify)\b"),
     "gradle", ["BUILD SUCCESSFUL"], ["BUILD FAILED"]),
    (re.compile(r"(?:^|\s)npm\b.*\b(?:test|run\s+test|run\s+build)\b"),
     "npm", _JS_SUCCESS, _JS_FAILURE),
    (re.compile(r"(?:^|\s)(?:yarn|pnpm)\b.*\b(?:test|build)\b"),
     "yarn", _JS_SUCCESS, _JS_FAILURE),
    (re.compile(r"(?:^|\s)pytest\b"),
     "pytest", None, None),
    (re.compile(r"(?:^|\s)cargo\b.*\b(?:test|build|check)\b"),
     "cargo", None, None),
    (re.compile(r"(?:^|\s)go\s+test\b"),
     "go-test", None, None),
    # docker build emits no exit code the hook can read, so classify on
    # output text. BuildKit (plain progress) prints "writing image" +
    # "naming to"; the classic builder prints "Successfully built". Failures:
    # BuildKit "failed to solve" / "executor failed"; classic "returned a
    # non-zero code".
    (re.compile(r"(?:^|\s)docker\s+(?:buildx\s+)?build\b"),
     "docker-build",
     ["writing image", "naming to", "Successfully built"],
     ["failed to solve", "executor failed", "returned a non-zero code"]),
]


# ─── shape extraction ─────────────────────────────────────────────────

def _flatten_content_blocks(value):
    """Common pattern: list of {type: text|tool_result, text|content: ...}."""
    parts = []
    for item in value:
        if isinstance(item, dict):
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif item.get("type") == "tool_result" and "content" in item:
                # Recursive: tool_result block may contain text or another list.
                nested = item["content"]
                if isinstance(nested, str):
                    parts.append(nested)
                elif isinstance(nested, list):
                    parts.append(_flatten_content_blocks(nested))
                else:
                    parts.append(str(nested))
            elif isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif isinstance(item.get("content"), str):
                parts.append(item["content"])
            else:
                parts.append(str(item))
        elif isinstance(item, str):
            parts.append(item)
        else:
            parts.append(str(item))
    return "\n".join(parts)


def extract_text(tool_response) -> str:
    """tool_response shape varies across CC versions and plugin wrappers;
    flatten defensively to a single string. Returns empty string if no
    text-like field is found.

    Shapes covered:
      - str (raw)
      - list (top-level content blocks)
      - dict.stdout / output / result / content / text / data / message (str OR list-of-blocks)
      - dict.output.stdout (nested envelope used by some wrappers)
      - dict.tool_use_result.content (Anthropic SDK envelope)
      - dict.stderr (last-resort fallback)
    """
    if isinstance(tool_response, str):
        return tool_response

    if isinstance(tool_response, list):
        return _flatten_content_blocks(tool_response)

    if not isinstance(tool_response, dict):
        return str(tool_response) if tool_response is not None else ""

    # Direct string-or-list keys at top level.
    for key in ("stdout", "output", "result", "content", "text", "data", "message"):
        value = tool_response.get(key)
        if isinstance(value, str):
            if value:
                return value
        elif isinstance(value, list):
            text = _flatten_content_blocks(value)
            if text:
                return text

    # Nested envelope: dict.output may itself be a dict with stdout inside.
    output = tool_response.get("output")
    if isinstance(output, dict):
        for nested_key in ("stdout", "content", "text", "result"):
            value = output.get(nested_key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, list):
                text = _flatten_content_blocks(value)
                if text:
                    return text

    # Anthropic SDK envelope.
    tur = tool_response.get("tool_use_result")
    if isinstance(tur, dict):
        for nested_key in ("content", "text", "output", "result"):
            value = tur.get(nested_key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, list):
                text = _flatten_content_blocks(value)
                if text:
                    return text

    # Last resort: stderr alone.
    stderr = tool_response.get("stderr", "")
    if isinstance(stderr, str) and stderr:
        return stderr

    return ""


def extract_exit_code(tool_response):
    """Find an integer exit code in tool_response, regardless of nesting."""
    if not isinstance(tool_response, dict):
        return None

    for key in ("exit_code", "exitCode", "returncode", "returnCode", "status_code"):
        if key in tool_response and isinstance(tool_response[key], int):
            return tool_response[key]

    # Nested envelope
    output = tool_response.get("output")
    if isinstance(output, dict):
        for key in ("exit_code", "exitCode", "returncode", "returnCode"):
            if key in output and isinstance(output[key], int):
                return output[key]

    if tool_response.get("is_error"):
        return 1

    return None


# ─── classification ───────────────────────────────────────────────────

def tail(text: str, lines: int = 12) -> str:
    parts = text.splitlines()
    return "\n".join(parts[-lines:])


def _as_list(markers):
    """Normalize a marker spec (None | str | list) to a list of substrings."""
    if markers is None:
        return []
    if isinstance(markers, str):
        return [markers]
    return list(markers)


def classify(command: str, response_text: str, exit_code):
    """Return (status, kind, reason).

    status: "SUCCESS" | "FAILURE" | None
    kind:   pattern kind that matched (or None if no pattern matched)
    reason: one-line diagnostic string for debug log

    Markers (success/failure) may be None, a single string, or a list of
    substrings. Failure markers win over success markers (fail-closed: a
    build gate should bias to FAILURE on ambiguous output). When no marker
    is defined or matched, fall back to exit_code — but CC's Bash
    tool_response omits the exit code on success in current versions, so a
    marker-less pattern may stay unclassified (returns None) rather than
    falsely going green.
    """
    for pattern, kind, success_markers, failure_markers in PATTERNS:
        if not pattern.search(command):
            continue

        for m in _as_list(failure_markers):
            if m in response_text:
                return "FAILURE", kind, f"matched failure marker {m!r}"
        for m in _as_list(success_markers):
            if m in response_text:
                return "SUCCESS", kind, f"matched success marker {m!r}"

        # Marker-less or marker-missing — fall back to exit code if available.
        if exit_code == 0:
            return "SUCCESS", kind, "fallback: exit_code 0"
        if isinstance(exit_code, int) and exit_code != 0:
            return "FAILURE", kind, f"fallback: exit_code {exit_code}"

        return None, kind, (
            f"matched pattern {kind!r} but could not classify: "
            f"no marker in response_text (len={len(response_text)}), "
            f"no exit_code (exit_code={exit_code!r}). "
            f"CC's Bash tool_response often omits exit_code on success — "
            f"give this pattern text markers. Set CAPTURE_BUILD_DEBUG=1 to inspect."
        )

    return None, None, "no command pattern matched (not a build command)"


# ─── filtered green with zero tests (EMPTY) ───────────────────────────
#
# Found on the wego (2026-08-24): with `surefire.failIfNoSpecifiedTests=false`
# in the pom, `./mvnw -pl domain -am test -Dtest=NaoExisteEmLugarNenhumTest`
# prints BUILD SUCCESS with ZERO "Tests run:" lines. A mistyped test name
# became green, gate-advance let the commit through, and a card was declared
# done with no test run. `pytest -k`, `go test -run` and jest's `-t` /
# `--testNamePattern` fail the same way (exit 0, nothing executed).
#
# So: when the command carries a TEST FILTER and would classify SUCCESS, the
# output must show N > 0 tests executed. Zero — or no count at all — records a
# third state, "EMPTY", which every consumer treats as not-green.
#
# Scope: only FILTERED commands. An unfiltered `./mvnw verify` in a module
# with no tests is legitimate (build-only modules exist) and keeps today's
# behavior; demanding a count there would turn every such build red.

_TEST_FILTERS = {
    # -Dtest= (surefire) and -Dit.test= (failsafe)
    "maven": re.compile(r"(?:^|\s)-D(?:it\.)?test="),
    "pytest": re.compile(r"(?:^|\s)-k(?:\s|=|$)"),
    "go-test": re.compile(r"(?:^|\s)-(?:test\.)?run(?:\s|=)"),
    "npm": re.compile(r"(?:^|\s)(?:-t|--testNamePattern)(?:\s|=)"),
    "yarn": re.compile(r"(?:^|\s)(?:-t|--testNamePattern)(?:\s|=)"),
}

EMPTY_FIX_HINT = (
    "fix the test name in the filter, or make the build fail on it "
    "(Maven: -Dsurefire.failIfNoSpecifiedTests=true)"
)


def has_test_filter(command: str, kind: str) -> bool:
    rx = _TEST_FILTERS.get(kind)
    return bool(rx and rx.search(command))


def count_tests_run(kind: str, text: str):
    """How many tests the output says were EXECUTED (passed + failed), or
    None when the output carries no count this function recognizes.
    Skipped / deselected tests do not count — they did not run."""
    if kind == "maven":
        runs = [(int(a), int(s)) for a, s in re.findall(
            r"Tests run:\s*(\d+),.*?Skipped:\s*(\d+)", text)]
        if not runs:
            return None
        # Per-class lines + the Results summary repeat the same tests; only
        # zero-vs-nonzero matters, so take the largest executed count.
        return max(a - s for a, s in runs)
    if kind == "pytest":
        passed = sum(int(n) for n in re.findall(r"(\d+) passed", text))
        failed = sum(int(n) for n in re.findall(r"(\d+) failed", text))
        if passed or failed:
            return passed + failed
        if re.search(r"no tests ran|collected 0 items|\d+ deselected|0 selected", text):
            return 0
        return None
    if kind == "go-test":
        ran = len(re.findall(r"^--- (?:PASS|FAIL)", text, re.M))
        ran += sum(1 for line in text.splitlines()
                   if re.match(r"^ok\s", line) and "[no tests to run]" not in line)
        if ran:
            return ran
        if "[no tests to run]" in text or "[no test files]" in text:
            return 0
        return None
    if kind in ("npm", "yarn"):
        # jest: "Tests:       2 passed, 12 skipped, 14 total"
        # vitest: "Tests  2 passed (2)"
        m = re.search(r"^\s*Tests:?\s+(.*)$", text, re.M)
        if m:
            line = m.group(1)
            p = re.search(r"(\d+) passed", line)
            f = re.search(r"(\d+) failed", line)
            return (int(p.group(1)) if p else 0) + (int(f.group(1)) if f else 0)
        if re.search(r"No tests found|No test files found", text):
            return 0
        return None
    return None


def refine_empty(command: str, kind: str, status, text: str):
    """(status, tests_run, reason) after the zero-tests check. Only turns a
    SUCCESS from a FILTERED command into EMPTY; everything else passes through."""
    if status != "SUCCESS" or not has_test_filter(command, kind):
        return status, None, None
    n = count_tests_run(kind, text)
    if n is None:
        return "EMPTY", 0, (
            "test filter present but the output shows no count of executed "
            f"tests — treated as zero tests run; {EMPTY_FIX_HINT}"
        )
    if n <= 0:
        return "EMPTY", 0, (
            f"test filter matched zero tests (green with nothing executed); {EMPTY_FIX_HINT}"
        )
    return status, n, None


# ─── debug logging ────────────────────────────────────────────────────

def debug_log(payload, response_text, exit_code, status, kind, reason):
    """When CAPTURE_BUILD_DEBUG=1, append a JSON line to the debug log
    capturing what the hook saw + how it classified. Default log path
    is /tmp/capture-build-debug.log; override with
    CAPTURE_BUILD_DEBUG_LOG."""
    if os.environ.get("CAPTURE_BUILD_DEBUG") != "1":
        return

    log_path = os.environ.get("CAPTURE_BUILD_DEBUG_LOG", "/tmp/capture-build-debug.log")

    tool_response = payload.get("tool_response")
    response_top_keys = (
        sorted(tool_response.keys())
        if isinstance(tool_response, dict)
        else None
    )
    response_type = type(tool_response).__name__

    # Truncate the raw payload defensively so the log file doesn't explode.
    try:
        payload_preview = json.dumps(payload, default=str)[:4000]
    except (TypeError, ValueError):
        payload_preview = str(payload)[:4000]

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool_name": payload.get("tool_name"),
        "command_preview": (payload.get("tool_input") or {}).get("command", "")[:200],
        "tool_response_type": response_type,
        "tool_response_top_keys": response_top_keys,
        "extracted_text_len": len(response_text),
        "extracted_text_tail": tail(response_text, 4) if response_text else "",
        "exit_code": exit_code,
        "classified_status": status,
        "classified_kind": kind,
        "classification_reason": reason,
        "payload_preview": payload_preview,
    }

    try:
        with open(log_path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass


# ─── effective build dir ──────────────────────────────────────────────

# Leading `cd <target> &&` / `;` prefix — the idiom throwaway proof worktrees
# use to run a build outside the session tree ("cd /tmp/wt && ./mvnw verify").
# Quoted and unquoted targets; repeated leading cds compose.
_CD_PREFIX_RE = re.compile(
    r"""^\s*cd\s+(?:"(?P<dq>[^"]+)"|'(?P<sq>[^']+)'|(?P<bare>[^\s;&|]+))\s*(?:&&|;)\s*"""
)


def effective_build_dir(command: str, cwd: Path) -> Path:
    """Where the build actually ran: follow leading `cd X &&` prefixes."""
    where = cwd
    rest = command
    while True:
        m = _CD_PREFIX_RE.match(rest)
        if not m:
            return where
        target = os.path.expanduser(m.group("dq") or m.group("sq") or m.group("bare"))
        where = Path(target).resolve() if os.path.isabs(target) else (where / target).resolve()
        rest = rest[m.end():]


# ─── main ─────────────────────────────────────────────────────────────

def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[capture-build-result] could not parse hook payload; skipping", file=sys.stderr)
        sys.exit(0)

    if payload.get("tool_name") != "Bash":
        sys.exit(0)

    command = (payload.get("tool_input") or {}).get("command", "")
    if not command:
        sys.exit(0)

    tool_response = payload.get("tool_response") or {}
    response_text = extract_text(tool_response)
    exit_code = extract_exit_code(tool_response)

    status, kind, reason = classify(command, response_text, exit_code)
    status, tests_run, empty_reason = refine_empty(command, kind, status, response_text)
    if empty_reason:
        reason = f"{reason}; {empty_reason}"

    debug_log(payload, response_text, exit_code, status, kind, reason)

    if status is None:
        sys.exit(0)  # Not a build command we recognize, or result was ambiguous.

    # RAIZ da worktree, não o diretório corrente: o cwd do Bash persiste
    # entre chamadas, e um `cd subdir` desviaria o estado desta sessão
    # para `subdir/.claude/` pelo resto dela (ver _wtlib.session_root).
    cwd = Path(L.session_root(payload.get("cwd") or os.getcwd())).resolve()
    build_dir = effective_build_dir(command, cwd)
    if build_dir != cwd and not build_dir.is_relative_to(cwd):
        # The build ran OUTSIDE the session tree — e.g. a proof worktree
        # producing a deliberate RED for a perturbation proof. Its result
        # describes THAT tree, not this one: recording it here poisons the
        # main baseline and gate-advance blocks the next push on another
        # directory's failure (the proof gate and the advance gate working
        # against each other). Record it where the build ran instead.
        state_path = build_dir / ".claude" / "last-build.json"
        print(
            f"[capture-build-result] build ran outside the session tree "
            f"({build_dir}); recording its result there — main baseline untouched.",
            file=sys.stderr,
        )
    else:
        # Inside the tree (including `cd subdir && build` in a monorepo):
        # the session's baseline is the right home, as before.
        state_path = cwd / ".claude" / "last-build.json"

    new_state = {
        "status": status,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "command": command[:200],
        "kind": kind,
        "tail": tail(response_text),
    }
    if tests_run is not None:
        new_state["tests_run"] = tests_run
    if empty_reason:
        new_state["reason"] = empty_reason
        print(f"[capture-build-result] EMPTY, not green: {empty_reason}", file=sys.stderr)

    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(new_state, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        print(f"[capture-build-result] could not write {state_path}: {e}", file=sys.stderr)

    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import _telemetry as T
        T.emit("build_result", cwd=str(cwd), status=status, kind=kind)
    except Exception:
        pass  # telemetry never breaks the capture

    sys.exit(0)


if __name__ == "__main__":
    main()
