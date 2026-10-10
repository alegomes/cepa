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

Root-install marker (2026-09-27): when a Maven command classifies SUCCESS and
one of its segments ran `install` over the WHOLE reactor (no `-pl`/`--projects`,
no `-rf`/`--resume-from` — a partial reactor even without `-pl` — and its
effective pom — `-f`/`--file`'s target resolved relative to the effective
build dir, or that build dir's own `pom.xml` when there's no `-f` — is the
`pom.xml` of `marker_root`, the directory whose `.claude/` receives the
marker: the session root when the build ran inside the session tree, the
build dir itself when it ran outside it — `_mvnscan.goals`/`has_pl`/
`has_resume_from`/`file_flag_target`), this hook also writes
`.claude/last-root-install.json`
= {"at": <iso utc>, "command": <cmd[:200]>} next to last-build.json. It is a
SEPARATE file, not folded into last-build.json: that one gets overwritten by
every build (including a later `-pl` one), so it can't answer "when did the
reactor last see a full install?" a few commands later. `maven-reactor-guard.py`
reads this file to liberate `-pl` without `-am` when no reactor source is newer
than `at` — see that hook's docstring for the full rationale
(docs/investigations/2026-09-25-stale-e-reactor-no-wego.md, seção 5).

Background builds (2026-10-02): a build that goes to the background — by
`run_in_background: true`, or because it outlived the Bash timeout and CC
moved it — returns a tool_response with `backgroundTaskId` and no output, so
there is nothing to classify at that moment. The wego `./mvnw verify` takes
~25 min and never fits in the foreground, so its baseline was never written.
Measured on claude 2.1.287: CC keeps writing the command's output to
`<tmp>/claude-<uid>/<project>/<session_id>/tasks/<id>.output` and appends
`[exited with code N]` when it ends. So at launch this hook leaves
`<id>.cepa-build.json` next to that file (outside the repo: no `git status`
noise), and every later Bash call — here and in gate-advance, BEFORE it reads
the baseline — harvests the finished ones with the same markers, plus the
real exit code. A result is discarded when the baseline changed after the
launch (a source edit marked STALE, or a newer build ran): it describes code
that is no longer the code on disk. See harvest_background().
"""

import glob
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _wtlib as L  # noqa: E402
import _shellscan as S  # noqa: E402
import _mvnscan as M  # noqa: E402


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
    # pytest: a linha de resumo é "== 10 passed in 0.01s ==" ou "== 1 failed,
    # 9 passed ==" / "!!! Interrupted: 3 errors during collection !!!". Sem
    # marcador, um pytest verde nunca era registrado (o CC omite o exit code
    # no sucesso) e o gate-advance ficava STALE para sempre em projeto Python
    # (medido no pastinha-pipeline, 2026-10-10). Falha vence: "1 failed, 9
    # passed" é FAILURE.
    (re.compile(r"(?:^|\s)pytest\b"),
     "pytest", [" passed"], [" failed", " error", "errors during collection", "no tests ran"]),
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


# ─── root-install marker ───────────────────────────────────────────────

def runs_root_install(command: str, build_dir: Path, marker_root: Path) -> bool:
    """True se algum segmento Maven do comando roda `install` sobre o reator
    INTEIRO a partir de `build_dir`, E o pom efetivo desse install é o
    `pom.xml` de `marker_root` — o diretório cujo `.claude/` recebe o
    marcador (a raiz da sessão quando o build rodou dentro da árvore da
    sessão; `build_dir` quando rodou fora — ver a ramificação em `main()`).

    Quatro jeitos de NÃO ser um install completo da raiz, mesmo com `install`
    no goal:
      - `-pl x install` (um módulo só) — quem chamou instalou uma fração do
        reator, não o reator inteiro;
      - `-rf`/`--resume-from` (retomada) — o reator não roda de novo desde o
        começo, é um reator PARCIAL mesmo sem `-pl`;
      - `-f`/`--file X` (ou `-f=X`/`--file=X`) apontando para outra coisa que
        não o pom.xml de `marker_root`. `X` pode ser um diretório
        (`X/pom.xml` é o que conta) ou um arquivo; resolvido relativo a
        `build_dir`. Bug reproduzido pelo pair-reviewer em 2026-09-27:
        `./mvnw -f domain/pom.xml install` marcava a raiz como fresca quando
        só `domain` tinha sido instalado — `-pl` nem precisa aparecer para o
        install ser parcial, `-f` sozinho já resolve para outro pom;
      - SEM `-f`: o pom efetivo é o de `build_dir` (o pom que o Maven usa por
        default é o do diretório corrente). Se `build_dir` não é
        `marker_root` — por exemplo `cd domain && ./mvnw install`, um `cd`
        para dentro de um submódulo sem `-f` nenhum — o install rodou sobre o
        reator do SUBMÓDULO, não sobre o da sessão, mesmo sem `-pl`/`-rf`.
        Bug reproduzido pelo pair-reviewer em 2026-09-27: essa combinação
        (sem `-f`, `build_dir` != `marker_root`) escapava do check porque só
        o ramo com `-f` comparava contra a raiz."""
    root_pom = (marker_root / "pom.xml").resolve()
    for seg in S._split_segments(command):
        seg = seg.strip()
        if not seg:
            continue
        args = M.maven_args(seg)
        if args is None:
            continue
        if "install" not in M.goals(args):
            continue
        if M.has_pl(args) or M.has_resume_from(args):
            continue
        target = M.file_flag_target(args)
        if target is not None:
            resolved = Path(target)
            resolved = resolved if resolved.is_absolute() else (build_dir / resolved)
            resolved = resolved.resolve()
            if resolved.is_dir():
                resolved = resolved / "pom.xml"
        else:
            resolved = (build_dir / "pom.xml").resolve()
        if resolved != root_pom:
            continue
        return True
    return False


# ─── recording ────────────────────────────────────────────────────────

def record(command, kind, status, text, tests_run, empty_reason,
           state_path: Path, build_dir: Path, marker_root: Path, cwd: Path,
           extra=None):
    """Write last-build.json (+ the root-install marker) and emit telemetry."""
    new_state = {
        "status": status,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "command": command[:200],
        "kind": kind,
        "tail": tail(text),
    }
    if tests_run is not None:
        new_state["tests_run"] = tests_run
    if empty_reason:
        new_state["reason"] = empty_reason
        print(f"[capture-build-result] EMPTY, not green: {empty_reason}", file=sys.stderr)
    new_state.update(extra or {})

    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(new_state, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        print(f"[capture-build-result] could not write {state_path}: {e}", file=sys.stderr)

    if status == "SUCCESS" and kind == "maven" and runs_root_install(command, build_dir, marker_root):
        # Marcador SEPARADO do last-build.json (mesmo diretório): o de cima é
        # sobrescrito a cada build, inclusive por um `-pl` posterior que não
        # instalou nada — perderia exatamente o dado que o
        # maven-reactor-guard precisa para liberar depois. Ver docstring.
        root_install_path = state_path.parent / "last-root-install.json"
        try:
            root_install_path.write_text(json.dumps({
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "command": command[:200],
            }, indent=2) + "\n", encoding="utf-8")
        except OSError as e:
            print(f"[capture-build-result] could not write {root_install_path}: {e}",
                  file=sys.stderr)

    try:
        import _telemetry as T
        T.emit("build_result", cwd=str(cwd), status=status, kind=kind)
    except Exception:
        pass  # telemetry never breaks the capture


# ─── background builds ────────────────────────────────────────────────

PENDING_SUFFIX = ".cepa-build.json"
# CC appends this line to the task's .output file when the command ends.
_EXIT_LINE = re.compile(r"\[exited with code (-?\d+)\]\s*$")
# A task CC never finished (session killed, task stopped) leaves no exit
# line; its pending file is dropped after this long instead of piling up.
PENDING_MAX_AGE_S = 6 * 3600


def background_task_id(tool_response):
    if isinstance(tool_response, dict):
        task_id = tool_response.get("backgroundTaskId")
        if isinstance(task_id, str) and task_id:
            return task_id
    return None


def task_dirs(session_id):
    """CC's `tasks/` directories for this session. The project segment of the
    path is a slug of the launch dir that we don't rebuild — glob for it."""
    if not session_id:
        return []
    found = []
    roots = [os.environ.get("TMPDIR"), tempfile.gettempdir(), "/tmp", "/private/tmp"]
    for root in dict.fromkeys(r for r in roots if r):
        pattern = os.path.join(glob.escape(root), "claude-*", "*",
                               glob.escape(session_id), "tasks")
        for d in glob.glob(pattern):
            real = os.path.realpath(d)
            if real not in found:
                found.append(real)
    return found


def register_background(task_id, session_id, command, kind,
                        state_path: Path, build_dir: Path, marker_root: Path, cwd: Path):
    for d in task_dirs(session_id):
        output = Path(d) / f"{task_id}.output"
        if not output.exists():
            continue
        entry = {
            "task_id": task_id,
            "output": str(output),
            "command": command,
            "kind": kind,
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "state_path": str(state_path),
            "build_dir": str(build_dir),
            "marker_root": str(marker_root),
            "cwd": str(cwd),
        }
        try:
            (Path(d) / f"{task_id}{PENDING_SUFFIX}").write_text(
                json.dumps(entry, indent=2) + "\n", encoding="utf-8")
        except OSError as e:
            print(f"[capture-build-result] could not register background build: {e}",
                  file=sys.stderr)
            return False
        print(f"[capture-build-result] build in background ({task_id}); its result "
              f"will be recorded when it ends.", file=sys.stderr)
        return True
    print(f"[capture-build-result] build went to the background ({task_id}) but its "
          f"output file was not found; its result will NOT be recorded.", file=sys.stderr)
    return False


def _parse_ts(raw):
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _baseline_moved_since(state_path: Path, started_at) -> bool:
    """True when last-build.json was rewritten after the launch: an edit
    marked it STALE (`since`) or another build recorded (`at`)."""
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    for key in ("since", "at"):
        ts = _parse_ts(state.get(key)) if state.get(key) else None
        if ts and started_at and ts > started_at:
            return True
    return False


def _read_tail(path: Path, size=4096) -> str:
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - size))
        return f.read().decode("utf-8", errors="replace")


def harvest_background(session_id, now=None):
    """Record every finished background build of this session. Never raises."""
    now = now or datetime.now(timezone.utc)
    try:
        pendings = [p for d in task_dirs(session_id)
                    for p in glob.glob(os.path.join(glob.escape(d), "*" + PENDING_SUFFIX))]
    except Exception as e:  # a harvest bug never breaks the tool call
        print(f"[capture-build-result] background harvest failed: {e}", file=sys.stderr)
        return
    for pending in pendings:
        try:
            _harvest_one(Path(pending), now)
        except Exception as e:
            print(f"[capture-build-result] harvest of {pending} failed: {e}",
                  file=sys.stderr)


def _harvest_one(pending: Path, now):
    entry = json.loads(pending.read_text(encoding="utf-8"))
    output = Path(entry["output"])
    started_at = _parse_ts(entry.get("started_at"))
    m = _EXIT_LINE.search(_read_tail(output)) if output.exists() else None
    if not m:
        if started_at is None or (now - started_at).total_seconds() > PENDING_MAX_AGE_S:
            pending.unlink(missing_ok=True)
        return

    pending.unlink(missing_ok=True)
    command, kind = entry["command"], entry.get("kind")
    state_path = Path(entry["state_path"])
    if _baseline_moved_since(state_path, started_at):
        print(f"[capture-build-result] background build {entry['task_id']} ended, but the "
              f"baseline changed after it started (edit or newer build); result discarded.",
              file=sys.stderr)
        return

    text = output.read_text(encoding="utf-8", errors="replace")
    exit_code = int(m.group(1))
    if exit_code != 0:
        # The real exit code is the strongest signal there is: fail-closed
        # even when a success marker printed before something later failed.
        status, kind, _ = "FAILURE", kind, f"background exit code {exit_code}"
    else:
        status, kind, _ = classify(command, text, exit_code)
    status, tests_run, empty_reason = refine_empty(command, kind, status, text)
    if status is None:
        return
    record(command, kind, status, text, tests_run, empty_reason, state_path,
           Path(entry["build_dir"]), Path(entry["marker_root"]), Path(entry["cwd"]),
           extra={"started_at": entry.get("started_at"),
                  "background_task": entry["task_id"]})
    print(f"[capture-build-result] background build {entry['task_id']} recorded: {status}.",
          file=sys.stderr)


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

    # Any Bash call is a chance to record a background build that ended.
    harvest_background(payload.get("session_id"))

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

    task_id = background_task_id(tool_response)
    if status is None and not (kind and task_id):
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
        marker_root = build_dir
        state_path = build_dir / ".claude" / "last-build.json"
        print(
            f"[capture-build-result] build ran outside the session tree "
            f"({build_dir}); recording its result there — main baseline untouched.",
            file=sys.stderr,
        )
    else:
        # Inside the tree (including `cd subdir && build` in a monorepo):
        # the session's baseline is the right home, as before. The root-
        # install marker (below) must also be checked against THIS
        # directory's pom, not build_dir's — `cd domain && ./mvnw install`
        # has build_dir == cwd/domain but the marker still lands in cwd/.claude.
        marker_root = cwd
        state_path = cwd / ".claude" / "last-build.json"

    if status is None:
        register_background(task_id, payload.get("session_id"), command, kind,
                            state_path, build_dir, marker_root, cwd)
        sys.exit(0)

    record(command, kind, status, response_text, tests_run, empty_reason,
           state_path, build_dir, marker_root, cwd)
    sys.exit(0)


if __name__ == "__main__":
    main()
