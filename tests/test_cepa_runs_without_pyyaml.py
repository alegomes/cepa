#!/usr/bin/env python3
"""The Cepa commands run in a repo whose `python3` has no PyYAML
(docs/spec/cepa-roda-sem-pyyaml-instalado.md).

"A python3 without PyYAML" is simulated, on any machine and in CI, by a
`python3` shim at the front of PATH that execs the real interpreter with `-S`
(no site-packages). The command under test is run DIRECTLY through its
shebang (`#!/usr/bin/env python3`), the way a user's shell runs it, never via
`sys.executable`.

This file does not import yaml: fixtures are written as YAML text, so it runs
in the same environment it simulates. Later success criteria add their cases
here, reusing `make_shim`, `make_repo` and `run_direct`.

Cases:
  CS-1  `cepa-plan ready` lists the ready item, exit 0, no "PyYAML" on stderr
  CS-2  the other 11 (cepa-dor, cepa-until, cepa-until-digest, five maestro-*,
        waivers.py, classify_needs_human.py, board-flow-fleet-validate.sh) each
        reach a real YAML read: no "PyYAML" / yaml ImportError on stderr and the
        output carries a marker that only exists in the example YAML
  CS-3  the 9 hooks read YAML for real under the shim. Event level (the hook
        script is fed a harness event on stdin): acceptance-gate,
        merge-truth-gate, build-hex proof-verdict-guard. Function level (the
        hook is loaded by path and its reading function called): _jiramut,
        _autonomy, ui-proof-verdict-guard, expertise-append, reflection-gate,
        jira-create-fields-gate.

Run with `python3 tests/test_cepa_runs_without_pyyaml.py`.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CEPA_PLAN = REPO / "common" / "bin" / "cepa-plan"
BIN = REPO / "common" / "bin"
MAESTRO = REPO / "maestro" / "bin"
BOARD_FLOW = REPO / "board-flow"
HOOKS = REPO / "common" / "hooks"
FAILURES = []


def check(name, cond, detail=""):
    print(f"  ok  {name}" if cond else f"FAIL  {name}  {detail}")
    if not cond:
        FAILURES.append(name)


def make_shim(tmp):
    """Dir with an executable `python3` that runs the real one with -S."""
    d = Path(tmp) / "shim"
    d.mkdir()
    shim = d / "python3"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" -S "$@"\n',
                    encoding="utf-8")
    shim.chmod(0o755)
    return d


def make_repo(tmp, queue="q", item_id="X-1"):
    """Temp git repo with one single-track queue holding one pending item."""
    root = Path(tmp) / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    d = root / ".claude" / "queues" / queue
    d.mkdir(parents=True)
    (d / "queue.yaml").write_text(
        "schema_version: 2\n"
        "mode: single-track\n"
        f"queue: {queue}\n"
        "source: teste\n"
        "items:\n"
        f"- id: {item_id}\n"
        f"  title: item {item_id}\n"
        "  why: porque\n"
        "  status: pending\n"
        "  blocked_by: []\n"
        "  human_pending: null\n"
        "  evidence: null\n",
        encoding="utf-8")
    return root


def run_direct(script, args, cwd, shim_dir, extra_env=None):
    """Run `script` through its shebang with the shim first on PATH."""
    env = dict(os.environ)
    env["PATH"] = f"{shim_dir}{os.pathsep}{env.get('PATH', '')}"
    env.pop("PYTHONPATH", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run([str(script)] + list(args), capture_output=True,
                          text=True, cwd=str(cwd), env=env)


def write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def no_yaml_complaint(name, r):
    """The shared negative checks of CS-2: the missing-yaml symptoms are gone."""
    check(f"{name}: no 'PyYAML' on stderr", "PyYAML" not in r.stderr, r.stderr)
    bad = ("ModuleNotFoundError" in r.stderr or "ImportError" in r.stderr
           or "No module named" in r.stderr)
    check(f"{name}: no yaml import error on stderr", not bad, r.stderr)


def cs2(tmp, shim):
    tmp = Path(tmp) / "cs2"
    (tmp / "m").mkdir(parents=True)
    root = make_repo(tmp)                     # git repo, queue q, item X-1
    plan_dir = Path(tmp) / "plans"

    # cepa-dor: a v2 single-track plan is refused with a message that names the
    # mode, which only exists inside the YAML.
    plan = write(plan_dir / "dor.yaml",
                 "schema_version: 2\nmode: single-track\nprogram: uniq-dor\n")
    r = run_direct(BIN / "cepa-dor", [str(plan)], root, shim)
    no_yaml_complaint("CS-2 cepa-dor", r)
    check("CS-2 cepa-dor read the plan (names its single-track mode)",
          "single-track" in r.stdout and "ilegível" not in r.stdout,
          r.stdout + r.stderr)

    # cepa-until: --dry-run prints the run plan from the queue, no claude.
    r = run_direct(BIN / "cepa-until", ["q", "--for", "1h", "--dry-run", "--dirty-ok",
                                  "--no-verify"],
                   root, shim)
    no_yaml_complaint("CS-2 cepa-until", r)
    check("CS-2 cepa-until dry-run read the queue (names item X-1)",
          "X-1" in r.stdout + r.stderr, r.stdout + r.stderr)

    # cepa-until-digest: the touched item's CURRENT status comes from the queue.
    prog = Path(tmp) / "digest" / ".claude" / "programs" / "F"
    write(prog / "plan.yaml",
          "items:\n- id: A1\n  status: uniq-status-digest\n  blocked_by: []\n")
    ledger = write(prog / "until" / "r.jsonl",
                   '{"evento": "run_start", "fila": "F", "branch": "until/r"}\n'
                   '{"evento": "item_start", "id": "A1", "title": "um"}\n'
                   '{"evento": "run_end", "motivo": "end-of-queue"}\n')
    write(prog / "until" / "r.log", "")
    r = run_direct(BIN / "cepa-until-digest", [str(ledger)], root, shim)
    no_yaml_complaint("CS-2 cepa-until-digest", r)
    check("CS-2 cepa-until-digest shows the item status read from the YAML",
          "uniq-status-digest" in r.stdout, r.stdout + r.stderr)

    # maestro-* : one program dir with a wave-state and a plan.
    wave_state = ("program: uniq-prog\nwave: 1\ntimeout_min_default: 45\n"
                  "slices:\n  uniq-slice:\n    status: running\n"
                  "    started_epoch: 1000\n")
    mroot = make_repo(Path(tmp) / "m", queue="mq")
    pdir = mroot / ".claude" / "programs" / "uniq-prog"
    write(pdir / "wave-state.yaml", wave_state)
    write(pdir / "slices" / "uniq-slice" / "resultado.txt", "MAESTRO-EXIT:0\n")
    r = run_direct(MAESTRO / "maestro-poll", [str(pdir), "--now", "2000"],
                   mroot, shim)
    no_yaml_complaint("CS-2 maestro-poll", r)
    check("CS-2 maestro-poll reports the slice from wave-state.yaml",
          "uniq-slice" in r.stdout and '"DONE"' in r.stdout, r.stdout + r.stderr)

    mplan = write(plan_dir / "maestro.yaml",
                  "schema_version: 2\nmode: parallel-waves\nprogram: uniq-prog\n"
                  "slices:\n  s1:\n    surface: [uniq-surface/**]\n"
                  "waves:\n- id: 1\n  slices: [s1]\n")
    r = run_direct(MAESTRO / "maestro-fork-settings", [str(mplan), "s1"],
                   mroot, shim)
    no_yaml_complaint("CS-2 maestro-fork-settings", r)
    check("CS-2 maestro-fork-settings emits the slice surface from the plan",
          "uniq-surface" in r.stdout, r.stdout + r.stderr)

    write(pdir / "plan.yaml",
          "schema_version: 2\nmode: parallel-waves\nprogram: uniq-prog\n"
          "slices:\n  uniq-slice:\n    surface: [x/**]\n"
          "waves:\n- id: 1\n  slices: [uniq-slice]\n")
    r = run_direct(MAESTRO / "maestro-programs", [str(mroot), "--json"],
                   mroot, shim)
    no_yaml_complaint("CS-2 maestro-programs", r)
    check("CS-2 maestro-programs lists the program and its wave-state slice",
          "uniq-prog" in r.stdout and "uniq-slice" in r.stdout,
          r.stdout + r.stderr)

    r = run_direct(MAESTRO / "maestro-wave-state",
                   ["get", str(pdir), "--json"], mroot, shim)
    no_yaml_complaint("CS-2 maestro-wave-state", r)
    check("CS-2 maestro-wave-state get returns the file content",
          "uniq-slice" in r.stdout, r.stdout + r.stderr)

    write(pdir / "wave-state.yaml",
          "program: uniq-prog\nwave: 1\nslices:\n  uniq-slice:\n"
          "    status: FAIL\n")
    r = run_direct(MAESTRO / "maestro-prune",
                   [str(pdir), "--repo", str(mroot), "--dry-run"], mroot, shim)
    no_yaml_complaint("CS-2 maestro-prune", r)
    check("CS-2 maestro-prune read the wave-state (keeps the FAIL slice)",
          "uniq-slice" in r.stdout, r.stdout + r.stderr)

    # board-flow python modules, run through the python3 shim.
    wroot = Path(tmp) / "w"
    write(wroot / ".claude" / "waivers" / "teste-cego--uniq.yaml",
          "motivo: teste-cego\nescopo: uniq-escopo\nrazao: porque\n"
          "autor: alguem\ncriado_em: 2026-01-01\nrevisit_trigger: 2099-01-01\n")
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import waivers; "
            "print([w['escopo'] for w in waivers.load(sys.argv[2])])")
    r = run_direct(shim / "python3",
                   ["-c", code, str(BOARD_FLOW / "bin"), str(wroot)], root, shim)
    no_yaml_complaint("CS-2 waivers.py", r)
    check("CS-2 waivers.py load() returns the waiver from the YAML",
          "uniq-escopo" in r.stdout, r.stdout + r.stderr)

    croot = Path(tmp) / "c"
    write(croot / "docs" / "proof" / "UNIQ-9.yaml",
          "card: UNIQ-9\nverdict: needs-human\n")
    r = run_direct(shim / "python3",
                   [str(BOARD_FLOW / "bin" / "classify_needs_human.py"),
                    str(croot)], root, shim)
    no_yaml_complaint("CS-2 classify_needs_human.py", r)
    check("CS-2 classify_needs_human.py lists the card from the proof YAML",
          "UNIQ-9" in r.stdout, r.stdout + r.stderr)

    # board-flow-fleet-validate.sh: a fake `twg` passes the preflight and logs
    # the project key; the script has resolved it from board-flow.yaml by then.
    # The real Jira calls are NOT exercised, only the YAML read that precedes.
    frepo = Path(tmp) / "f"
    write(frepo / "board-flow.yaml",
          "defaults:\n  project_key: UNIQKEY\n  status_map:\n    to_do: A fazer\n")
    twg = write(Path(tmp) / "fake" / "twg",
                "#!/bin/sh\n"
                'case "$*" in\n'
                '  *doctor*) echo \'{"data":{"connectivity":{"ok":true}}}\' ;;\n'
                '  *) echo "fake twg: $*"; exit 1 ;;\n'
                "esac\n")
    twg.chmod(0o755)
    env = {"TWG_BIN": str(twg)}
    r = run_direct(BOARD_FLOW / "board-flow-fleet-validate.sh", [str(frepo)],
                   root, shim, extra_env=env)
    no_yaml_complaint("CS-2 board-flow-fleet-validate.sh", r)
    check("CS-2 board-flow-fleet-validate.sh resolved project_key from the YAML",
          "UNIQKEY" in r.stdout + r.stderr, r.stdout + r.stderr)


BOARD_FLOW_YAML = (
    "defaults:\n  project_key: UNIQ\n"
    "  status_map:\n    in_review: Em Revisao Uniq\n    in_progress: In Progress\n"
    "    done: Done\n"
    "  transition_ids:\n    '31': in_progress\n    '51': done\n"
    "  required_fields:\n  - id: customfield_uniq\n    name: UniqField\n")


def run_event(script, payload, cwd, shim):
    """Run a hook the way the harness does: `python3 <script>` (hooks are not
    executable files), JSON on stdin, the shim python3 first on PATH."""
    import json
    env = dict(os.environ)
    env["PATH"] = f"{shim}{os.pathsep}{env.get('PATH', '')}"
    env.pop("PYTHONPATH", None)
    return subprocess.run([str(shim / "python3"), str(script)],
                          input=json.dumps(payload),
                          capture_output=True, text=True, cwd=str(cwd), env=env)


def call_fn(shim, hook, expr, cwd, *args):
    """Load `hook` by path under the shim python3 and print repr(expr).
    `expr` sees `m` (the module) and `a` (the extra args)."""
    code = ("import importlib.util, sys\n"
            "spec = importlib.util.spec_from_file_location('hookmod', sys.argv[1])\n"
            "m = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(m)\n"
            "a = sys.argv[2:]\n"
            f"print(repr({expr}))\n")
    return run_direct(shim / "python3", ["-c", code, str(hook)] + list(args),
                      cwd, shim)


VENDOR_LINE = ('sys.path.insert(0, os.path.join(os.path.dirname('
               'os.path.dirname(os.path.abspath(__file__))), "_vendor"))\n')


def isolated_common(tmp, name):
    """Copy of common/hooks + common/_vendor where `_jiramut.py` no longer
    inserts `_vendor` into sys.path. acceptance-gate and merge-truth-gate import
    `_jiramut`, which would otherwise hand them the path: with it stripped, the
    path can only come from the hook's OWN line. Fails loudly if the line to
    strip is gone, so the case cannot silently stop isolating."""
    import shutil
    dest = Path(tmp) / name
    ign = shutil.ignore_patterns("__pycache__")
    shutil.copytree(HOOKS, dest / "hooks", ignore=ign)
    shutil.copytree(REPO / "common" / "_vendor", dest / "_vendor", ignore=ign)
    jm = dest / "hooks" / "_jiramut.py"
    text = jm.read_text(encoding="utf-8")
    check(f"CS-3 isolation: _jiramut.py has the _vendor line to strip ({name})",
          text.count(VENDOR_LINE) == 1, f"found {text.count(VENDOR_LINE)}x")
    jm.write_text(text.replace(VENDOR_LINE, ""), encoding="utf-8")
    return dest / "hooks"


def cs3(tmp, shim):
    tmp = Path(tmp) / "cs3"
    tmp.mkdir()

    # ---- event level -------------------------------------------------------
    # acceptance-gate: transition 31 maps to in_progress ONLY if board-flow.yaml
    # was read; that is a backward move and passes (exit 0) even with an
    # incomplete audit. Unread, the target is unresolvable and the gate blocks.
    acc = tmp / "acc"
    write(acc / "board-flow.yaml", BOARD_FLOW_YAML)
    write(acc / ".claude" / "acceptance" / "UNIQ-1.yaml",
          "key: UNIQ-1\nstatus: incomplete\ncriteria:\n  - id: AC1\n    gap: x\n")
    ev = {"tool_name": "mcp__mcp-atlassian__jira_transition_issue",
          "tool_input": {"issue_key": "UNIQ-1", "transition_id": "31"},
          "cwd": str(acc)}
    iso = isolated_common(tmp, "iso-acc")
    r = run_event(iso / "acceptance-gate.py", ev, acc, shim)
    check("CS-3 acceptance-gate read board-flow.yaml (31 -> in_progress passes)",
          r.returncode == 0, f"exit {r.returncode}: {r.stderr.strip()[:300]}")

    # merge-truth-gate: 51 maps to done ONLY if the YAML was read; the key's
    # code lives on a side branch, so a closing transition is blocked (exit 2).
    mt = tmp / "mt"
    mt.mkdir()
    def sh(*a):
        subprocess.run(list(a), cwd=mt, capture_output=True, check=True)
    sh("git", "init", "-q", "-b", "main")
    sh("git", "config", "user.email", "t@t")
    sh("git", "config", "user.name", "t")
    write(mt / "seed.txt", "seed\n")
    sh("git", "add", "-A")
    sh("git", "commit", "-qm", "seed")
    write(mt / "board-flow.yaml", BOARD_FLOW_YAML)
    sh("git", "add", "-A")
    sh("git", "commit", "-qm", "config")
    sh("git", "checkout", "-q", "-b", "feature/x")
    write(mt / "f.txt", "x\n")
    sh("git", "add", "-A")
    sh("git", "commit", "-qm", "UNIQ-7 work only on a side branch")
    sh("git", "checkout", "-q", "main")
    ev = {"tool_name": "mcp__mcp-atlassian__jira_transition_issue",
          "tool_input": {"issue_key": "UNIQ-7", "transition_id": "51"},
          "cwd": str(mt)}
    iso = isolated_common(tmp, "iso-mt")
    r = run_event(iso / "merge-truth-gate.py", ev, mt, shim)
    check("CS-3 merge-truth-gate read board-flow.yaml (51 -> done is blocked)",
          r.returncode == 2, f"exit {r.returncode}: {r.stderr.strip()[:300]}")

    # build-hex proof-verdict-guard: a `proven` artifact with a level name
    # outside the closed set is blocked ONLY by the real YAML parse; the line
    # fallback cannot see level names and lets it through.
    pv = tmp / "pv"
    pv.mkdir()
    ev = {"tool_name": "Write",
          "tool_input": {"file_path": str(pv / "docs" / "proof" / "UNIQ-3.yaml"),
                         "content": "card: UNIQ-3\nverdict: proven\nlevels:\n"
                                    "  uniq_bogus_level:\n    status: pass\n"},
          "cwd": str(pv)}
    r = run_event(REPO / "build-hex" / "hooks" / "proof-verdict-guard.py", ev, pv, shim)
    check("CS-3 build-hex proof-verdict-guard parsed the proof with yaml (blocks)",
          r.returncode == 2 and "uniq_bogus_level" in r.stderr,
          f"exit {r.returncode}: {r.stderr.strip()[:300]}")

    # ---- function level ----------------------------------------------------
    fn = tmp / "fn"
    write(fn / "board-flow.yaml", BOARD_FLOW_YAML)
    r = call_fn(shim, HOOKS / "_jiramut.py",
                "m.logical_status('Em Revisao Uniq', a[0])", fn, str(fn))
    check("CS-3 _jiramut.logical_status reads status_map from board-flow.yaml",
          r.stdout.strip() == "'in_review'", r.stdout + r.stderr[-300:])

    write(fn / "aut.yaml", "uniq_key: 1\n")
    r = call_fn(shim, HOOKS / "_autonomy.py",
                "m._read_yaml(__import__('pathlib').Path(a[0]))", fn,
                str(fn / "aut.yaml"))
    check("CS-3 _autonomy._read_yaml returns the file content",
          r.stdout.strip() == "{'uniq_key': 1}", r.stdout + r.stderr[-300:])

    r = call_fn(shim, HOOKS / "ui-proof-verdict-guard.py",
                "m.parse_with_yaml(a[0])[0]", fn, "verdict: uniq-verdict\n")
    check("CS-3 ui-proof-verdict-guard.parse_with_yaml reads the verdict",
          r.stdout.strip() == "'uniq-verdict'", r.stdout + r.stderr[-300:])

    r = call_fn(shim, HOOKS / "expertise-append.py", "m._HAVE_YAML", fn)
    check("CS-3 expertise-append sees yaml (_HAVE_YAML)",
          r.stdout.strip() == "True", r.stdout + r.stderr[-300:])

    r = call_fn(shim, HOOKS / "reflection-gate.py", "m.load(a[0])", fn,
                "uniq: 1\n")
    check("CS-3 reflection-gate.load parses YAML",
          r.stdout.strip() == "{'uniq': 1}", r.stdout + r.stderr[-300:])

    r = call_fn(shim, HOOKS / "jira-create-fields-gate.py",
                "m._load_rules(a[0])[0]", fn, str(fn))
    check("CS-3 jira-create-fields-gate._load_rules reads required_fields",
          r.stdout.strip() == "'UNIQ'", r.stdout + r.stderr[-300:])


def main():
    with tempfile.TemporaryDirectory() as tmp:
        shim = make_shim(tmp)
        probe = subprocess.run(
            [str(shim / "python3"), "-c", "import yaml"],
            capture_output=True, text=True,
            env={**os.environ, "PATH": f"{shim}{os.pathsep}{os.environ['PATH']}"})
        check("shim: this python3 really has no PyYAML",
              probe.returncode != 0, probe.stdout + probe.stderr)

        root = make_repo(tmp)

        # CS-1
        r = run_direct(CEPA_PLAN, ["ready"], root, shim)
        check("CS-1 cepa-plan ready exit 0 without PyYAML",
              r.returncode == 0, f"exit {r.returncode}: {r.stderr.strip()}")
        check("CS-1 cepa-plan ready lists the ready item",
              "X-1" in r.stdout, r.stdout)
        check("CS-1 no 'PyYAML' on stderr", "PyYAML" not in r.stderr, r.stderr)

        cs2(tmp, shim)
        cs3(tmp, shim)

    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ cepa runs without PyYAML")
    return 0


if __name__ == "__main__":
    sys.exit(main())
