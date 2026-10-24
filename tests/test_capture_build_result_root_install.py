#!/usr/bin/env python3
"""Regression tests for the `.claude/last-root-install.json` marker written by
`common/hooks/capture-build-result.py` (release 2 of the maven-reactor-guard,
2026-09-27).

No third-party deps — run with `python3 tests/test_capture_build_result_root_install.py`.
Exits non-zero on failure.

Guards the contract:
  - Maven SUCCESS that runs `install` over the whole reactor (without `-pl`/`--projects`)
    writes `.claude/last-root-install.json` = {"at": <iso utc>, "command": <cmd[:200]>};
  - `-pl x install` (a single module) does NOT write — it did not install the whole reactor;
  - `cd domain && ./mvnw install` (without `-f`) does NOT write — the effective pom is that of
    `domain` (build_dir), not that of the session root;
  - FAILURE does not write, even with `install` over the whole reactor;
  - the file is SEPARATE from last-build.json: a later `-pl` SUCCESS does not
    erase the root-install marker that already existed.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

# This test runs a hook that emits telemetry; without this the events would land
# in ~/.claude/cepa-telemetry/ and enter the /common:metrics report
# as if they were real use. See tests/_telemetria_isolada.py.
from _telemetria_isolada import isola

isola()

REPO = Path(__file__).resolve().parent.parent
CAPTURE = REPO / "common" / "hooks" / "capture-build-result.py"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def run_hook(payload):
    return subprocess.run(
        [sys.executable, str(CAPTURE)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )


def bash_payload(cwd, command, output, exit_code=None):
    resp = {"stdout": output}
    if exit_code is not None:
        resp["exit_code"] = exit_code
    return {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": resp,
        "cwd": str(cwd),
    }


def read_marker(root):
    p = Path(root) / ".claude" / "last-root-install.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


BUILD_SUCCESS = "[INFO] BUILD SUCCESS"
BUILD_FAILURE = "[INFO] BUILD FAILURE"


def main():
    with tempfile.TemporaryDirectory() as td:
        # ── root install, SUCCESS → writes the marker ───────────────────────
        r = Path(td) / "root-install"
        r.mkdir()
        res = run_hook(bash_payload(r, "./mvnw install -DskipTests", BUILD_SUCCESS))
        check("hook exits 0", res.returncode == 0, res.stderr)
        m = read_marker(r)
        check("install da raiz SUCCESS grava last-root-install.json",
              m is not None, str(m))
        check("marcador grava `at` e `command`",
              m is not None and "at" in m and "command" in m, str(m))
        check("marcador grava o comando (truncado em 200)",
              m is not None and m["command"] == "./mvnw install -DskipTests", str(m))

        # ── -pl x install (a single module) → does NOT write ────────────────
        r2 = Path(td) / "pl-install"
        r2.mkdir()
        run_hook(bash_payload(r2, "./mvnw -pl domain install -DskipTests", BUILD_SUCCESS))
        check("-pl <modulo> install NÃO grava o marcador (não é a raiz inteira)",
              read_marker(r2) is None)

        # ── -f/--file pointing to a submodule or to the root ────────────────
        # Bypass reproduced by the pair-reviewer on 2026-09-27: `-f` alone
        # (without `-pl`) resolved to "installed the whole reactor" even when
        # the pom.xml pointed to was a submodule's.
        r5 = Path(td) / "f-submodule"
        r5.mkdir()
        run_hook(bash_payload(r5, "./mvnw -f domain/pom.xml install", BUILD_SUCCESS))
        check("-f domain/pom.xml install NÃO grava o marcador (pom de submódulo)",
              read_marker(r5) is None)

        r6 = Path(td) / "f-root"
        r6.mkdir()
        run_hook(bash_payload(r6, "./mvnw -f pom.xml install", BUILD_SUCCESS))
        check("-f pom.xml install grava o marcador (pom da raiz)",
              read_marker(r6) is not None)

        # ── cd into a submodule without -f (bypass reproduced by the pair-reviewer
        # on 2026-09-27): build_dir becomes <root>/domain, but the marker still
        # goes to <root>/.claude — the effective pom (domain's, by default,
        # since there is no -f) has to be compared against the SESSION root's,
        # not against the build_dir's own. ───────────────────────────────
        r8 = Path(td) / "cd-submodule"
        r8.mkdir()
        (r8 / "domain").mkdir()
        run_hook(bash_payload(r8, "cd domain && ./mvnw install", BUILD_SUCCESS))
        check("cd domain && ./mvnw install NÃO grava o marcador na raiz da sessão",
              read_marker(r8) is None)
        check("cd domain && ./mvnw install também não grava sob domain/.claude",
              read_marker(r8 / "domain") is None)

        r9 = Path(td) / "cd-submodule-f-root"
        r9.mkdir()
        (r9 / "domain").mkdir()
        run_hook(bash_payload(r9, "cd domain && ./mvnw -f ../pom.xml install", BUILD_SUCCESS))
        check("cd domain && ./mvnw -f ../pom.xml install grava o marcador (pom da raiz da sessão)",
              read_marker(r9) is not None)

        # ── -rf/--resume-from (partial reactor even without -pl) ────────────
        r7 = Path(td) / "resume-from"
        r7.mkdir()
        run_hook(bash_payload(r7, "./mvnw -rf :bootstrap install", BUILD_SUCCESS))
        check("-rf :bootstrap install NÃO grava o marcador (retomada parcial)",
              read_marker(r7) is None)

        # ── FAILURE does not write, even with install of the whole root ─────
        r3 = Path(td) / "root-install-red"
        r3.mkdir()
        run_hook(bash_payload(r3, "./mvnw install -DskipTests", BUILD_FAILURE))
        check("install da raiz com BUILD FAILURE NÃO grava o marcador",
              read_marker(r3) is None)

        # ── the marker is SEPARATE from last-build.json ─────────────────────
        r4 = Path(td) / "separate-file"
        r4.mkdir()
        run_hook(bash_payload(r4, "./mvnw install -DskipTests", BUILD_SUCCESS))
        first = read_marker(r4)
        check("pré-condição: marcador da raiz gravado", first is not None, str(first))
        # a later -pl SUCCESS should not erase the marker (it does not write to it)
        run_hook(bash_payload(r4, "./mvnw -pl domain -am test", BUILD_SUCCESS))
        second = read_marker(r4)
        check("um -pl SUCCESS depois não apaga o marcador da raiz",
              second is not None and second == first, f"{first} -> {second}")
        last_build = json.loads((r4 / ".claude" / "last-build.json").read_text())
        check("last-build.json, por outro lado, foi sobrescrito pelo -pl",
              "domain" in last_build.get("command", ""), str(last_build))

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {', '.join(FAILURES)}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
