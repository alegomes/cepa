#!/usr/bin/env python3
"""Contract tests: per-session state anchors at the worktree ROOT, not at the raw cwd.

No third-party dependency — run with
`python3 tests/test_session_anchor_root.py`.

The defect, measured twice in this repo (2026-08-04 and 2026-08-18): the hooks
receive `cwd` as the shell's CURRENT directory, and Bash's directory PERSISTS
between calls. A single `cd common/hooks` inside a command diverts the rest
of the whole session: `session-log.md` started being written to
`common/hooks/.claude/session-log.md` and the diverted turns VANISHED from the real
log — it was not a copy, it was a loss, invisible to git because `.gitignore` covers
`.claude/`. It only showed up because the orphan directory jumped out in `git status`.

It is not one file, it is a CLASS. The hooks that anchor state at the raw cwd fail
all the same way, and three of them fail OPENING a gate in silence:

  session-log.py        the session log goes to the subdirectory  → /common:recap
                        assembles "you asked / I delivered" with half a session
  capture-build-result  build baseline written in the subdirectory
  mark-build-stale      an edit at the root becomes an invalid `relative_to` → the hook exits
                        in silence and the baseline NEVER becomes STALE
  gate-advance          does not find the baseline in the subdirectory → push released
  acceptance-gate       does not find the acceptance artifact → transition released
  loop-budget           the repetition count resets → the ceiling of 3 never fires
  session-checkpoint    reads the log in the wrong place → the checkpoint comes back empty

The right anchor is `_wtlib.session_root` (worktree root), NOT `main_root`:
state that belongs to this worktree must follow the worktree — reading the build of
one worktree as the baseline of another is the same lie in reverse.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# This test executes a hook that emits telemetry; without this the events would fall
# in ~/.claude/cepa-telemetry/ and enter the /common:metrics report
# as if they were real use. See tests/_telemetria_isolada.py.
from _telemetria_isolada import isola

isola()


REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "common" / "hooks"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def run_hook(script, payload):
    return subprocess.run(
        [sys.executable, str(HOOKS / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )


def git(args, cwd):
    return subprocess.run(["git"] + args, cwd=str(cwd),
                          capture_output=True, text=True)


def make_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    git(["init", "-q", "-b", "main"], path)
    git(["config", "user.email", "t@t"], path)
    git(["config", "user.name", "t"], path)
    (path / "pom.xml").write_text("<project/>", encoding="utf-8")
    (path / "README.md").write_text("x", encoding="utf-8")
    git(["add", "-A"], path)
    git(["commit", "-qm", "seed"], path)
    return path


def stray_dirs(root, sub):
    """Every `.claude/` that showed up outside the root — the signature of the defect."""
    return [str(p) for p in Path(root).rglob(".claude")
            if p.parent.resolve() != Path(root).resolve()]


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    # ─────────────────────────────────────────────────────────────────────
    print("\n# session-log.py — o defeito original")
    # ─────────────────────────────────────────────────────────────────────
    r1 = make_repo(tmp / "r1")
    sub = r1 / "common" / "hooks"
    sub.mkdir(parents=True)

    r = run_hook("session-log.py", {"prompt": "pedido do usuário", "cwd": str(sub)})
    check("hook sai 0", r.returncode == 0, r.stderr)
    log = r1 / ".claude" / "session-log.md"
    check("log gravado na RAIZ", log.exists(), f"não existe: {log}")
    check("prompt está no log",
          log.exists() and "pedido do usuário" in log.read_text(encoding="utf-8"))
    check("nenhum .claude órfão no subdiretório",
          not stray_dirs(r1, sub), stray_dirs(r1, sub))

    # Two turns, one from the root and one from the subdirectory, in the SAME file: that is what
    # "it was not a copy, it was a loss" means — the log cannot split in two.
    run_hook("session-log.py", {"prompt": "turno da raiz", "cwd": str(r1)})
    text = log.read_text(encoding="utf-8")
    check("os dois turnos moram no mesmo log",
          "pedido do usuário" in text and "turno da raiz" in text)

    # ─────────────────────────────────────────────────────────────────────
    print("\n# worktree ligada — o estado segue a WORKTREE, não o clone principal")
    # ─────────────────────────────────────────────────────────────────────
    wt = tmp / "wt1"
    git(["worktree", "add", "-q", "-b", "session/x", str(wt)], r1)
    wtsub = wt / "common" / "hooks"
    wtsub.mkdir(parents=True, exist_ok=True)
    run_hook("session-log.py", {"prompt": "turno da worktree", "cwd": str(wtsub)})
    wtlog = wt / ".claude" / "session-log.md"
    check("log da worktree fica na raiz DELA", wtlog.exists(), f"não existe: {wtlog}")
    check("não vazou para o clone principal",
          "turno da worktree" not in log.read_text(encoding="utf-8"))

    # ─────────────────────────────────────────────────────────────────────
    print("\n# capture-build-result.py — baseline de build")
    # ─────────────────────────────────────────────────────────────────────
    r2 = make_repo(tmp / "r2")
    sub2 = r2 / "src" / "main"
    sub2.mkdir(parents=True)
    r = run_hook("capture-build-result.py", {
        "tool_name": "Bash",
        "tool_input": {"command": "./mvnw verify"},
        "tool_response": {"stdout": "BUILD SUCCESS\nTests run: 12, Failures: 0"},
        "cwd": str(sub2),
    })
    state = r2 / ".claude" / "last-build.json"
    check("baseline gravada na RAIZ", state.exists(), f"não existe: {state}")
    check("nenhum .claude órfão", not stray_dirs(r2, sub2), stray_dirs(r2, sub2))

    # ─────────────────────────────────────────────────────────────────────
    print("\n# mark-build-stale.py — invalidar a baseline (falha ABRINDO portão)")
    # ─────────────────────────────────────────────────────────────────────
    # cwd in the subdirectory, edit on a file of the ROOT: with the raw cwd
    # `relative_to` blew up with ValueError and the hook exited in silence, leaving the
    # baseline green forever.
    r = run_hook("mark-build-stale.py", {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(r2 / "src" / "App.java")},
        "cwd": str(sub2),
    })
    check("hook sai 0", r.returncode == 0, r.stderr)
    st = json.loads(state.read_text(encoding="utf-8")) if state.exists() else {}
    check("baseline virou STALE", st.get("status") == "STALE", st.get("status"))

    # ─────────────────────────────────────────────────────────────────────
    print("\n# gate-advance.py — barrar push com baseline vermelha")
    # ─────────────────────────────────────────────────────────────────────
    r3 = make_repo(tmp / "r3")
    sub3 = r3 / "api" / "src"
    sub3.mkdir(parents=True)
    (r3 / ".claude").mkdir(exist_ok=True)
    (r3 / ".claude" / "last-build.json").write_text(json.dumps({
        "status": "FAILURE", "at": "2026-08-25T10:00:00+00:00",
        "command": "./mvnw verify", "kind": "maven",
    }), encoding="utf-8")
    r = run_hook("gate-advance.py", {
        "tool_name": "Bash",
        "tool_input": {"command": "git push origin main"},
        "cwd": str(sub3),
    })
    check("push BARRADO mesmo com o cwd no subdiretório",
          r.returncode == 2, f"exit={r.returncode} stderr={r.stderr[:200]}")

    # And the honest opt-out is still read from the root.
    r4 = make_repo(tmp / "r4")
    sub4 = r4 / "docs"
    sub4.mkdir(parents=True)
    (r4 / ".claude").mkdir(exist_ok=True)
    (r4 / ".claude" / "no-build").write_text("", encoding="utf-8")
    r = run_hook("gate-advance.py", {
        "tool_name": "Bash",
        "tool_input": {"command": "git push origin main"},
        "cwd": str(sub4),
    })
    check("`.claude/no-build` da raiz vale no subdiretório", r.returncode == 0, r.stderr[:200])

    # ─────────────────────────────────────────────────────────────────────
    print("\n# loop-budget.py — o teto de repetição de falha")
    # ─────────────────────────────────────────────────────────────────────
    r5 = make_repo(tmp / "r5")
    sub5 = r5 / "pkg"
    sub5.mkdir(parents=True)
    run_hook("loop-budget.py", {
        "tool_name": "Task",
        "tool_input": {"subagent_type": "x", "prompt": "y"},
        "tool_response": {"content": "erro: NullPointerException em Foo.java:42"},
        "cwd": str(sub5),
    })
    # Without the `or`: with it, a hook that wrote NOTHING anywhere
    # would pass through the second side of the disjunction (pointed out by the completeness
    # auditor, 2026-08-25).
    check("estado do loop gravado na RAIZ",
          (r5 / ".claude" / "loop-state.json").exists(),
          f"não existe: {r5 / '.claude' / 'loop-state.json'}")
    check("nenhum .claude órfão", not stray_dirs(r5, sub5), stray_dirs(r5, sub5))

    # ─────────────────────────────────────────────────────────────────────
    print("\n# acceptance-gate.py — barrar transição com aceite INCOMPLETE")
    # ─────────────────────────────────────────────────────────────────────
    # The acceptance artifact lives at the root; with the raw cwd the gate did not find it and
    # exited in silence (`sys.exit(0)`) — a gate open without a line of warning.
    r6 = make_repo(tmp / "r6")
    sub6 = r6 / "api"
    sub6.mkdir(parents=True)
    acc = r6 / ".claude" / "acceptance"
    acc.mkdir(parents=True)
    (acc / "WEGO-1234.yaml").write_text(
        "key: WEGO-1234\nstatus: INCOMPLETE\ncriteria:\n"
        "  - id: AC1\n    gap: nenhum teste exercita o endpoint\n",
        encoding="utf-8")
    r = run_hook("acceptance-gate.py", {
        "tool_name": "mcp__mcp-atlassian__jira_transition_issue",
        "tool_input": {"issue_key": "WEGO-1234", "transition_id": "351"},
        "cwd": str(sub6),
    })
    check("transição BARRADA com o cwd no subdiretório",
          r.returncode == 2, f"exit={r.returncode} stderr={r.stderr[:200]}")
    check("a lacuna aparece na mensagem",
          "nenhum teste exercita o endpoint" in r.stderr, r.stderr[:200])

    # ─────────────────────────────────────────────────────────────────────
    print("\n# session-checkpoint.py — o rastro de intenção não pode voltar vazio")
    # ─────────────────────────────────────────────────────────────────────
    # The checkpoint READS the same file that session-log WRITES. If writer and
    # reader use different anchors, the handoff comes back empty in silence.
    #
    # Exercised as a PROCESS, and not by importing `recent_intents` and calling the
    # function: the hook runs at Stop with a payload on stdin and its product is the
    # handoff file on disk. Calling the function from inside would skip precisely
    # `main()`, which is where the anchor is resolved.
    r7 = make_repo(tmp / "r7")
    sub7 = r7 / "deep" / "nested"
    sub7.mkdir(parents=True)
    run_hook("session-log.py", {"prompt": "intenção do turno", "cwd": str(sub7)})
    r = run_hook("session-checkpoint.py",
                 {"session_id": "sessao-de-teste", "cwd": str(sub7)})
    check("checkpoint sai 0", r.returncode == 0, r.stderr)
    handoffs = list((r7 / ".claude" / "handoffs").glob("*.md"))
    check("handoff gravado", len(handoffs) == 1, [str(h) for h in handoffs])
    hand = handoffs[0].read_text(encoding="utf-8") if handoffs else ""
    check("a intenção do subdiretório chegou ao handoff",
          "intenção do turno" in hand, hand[:300])

    # ─────────────────────────────────────────────────────────────────────
    print("\n# fora de um repo git — o hook não pode morrer por isto")
    # ─────────────────────────────────────────────────────────────────────
    # The criterion speaks in the plural — "NO hook dies from this" — so all SEVEN
    # are exercised, not only session-log. There was no bug in any of them; what
    # was missing was the lock: a regression in any of the other six
    # would go unnoticed (pointed out by the completeness auditor, 2026-08-25).
    bare = tmp / "sem-git"
    bare.mkdir()

    r = run_hook("session-log.py", {"prompt": "sem repo", "cwd": str(bare)})
    check("session-log.py sai 0 fora de repo", r.returncode == 0, r.stderr)
    check("session-log.py cai no próprio cwd",
          (bare / ".claude" / "session-log.md").exists())

    outside = [
        ("capture-build-result.py", {
            "tool_name": "Bash",
            "tool_input": {"command": "./mvnw verify"},
            "tool_response": {"stdout": "BUILD SUCCESS"},
            "cwd": str(bare)}),
        ("mark-build-stale.py", {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(bare / "App.java")},
            "cwd": str(bare)}),
        ("gate-advance.py", {
            "tool_name": "Bash",
            "tool_input": {"command": "git push origin main"},
            "cwd": str(bare)}),
        ("acceptance-gate.py", {
            "tool_name": "mcp__mcp-atlassian__jira_transition_issue",
            "tool_input": {"issue_key": "WEGO-9999", "transition_id": "351"},
            "cwd": str(bare)}),
        ("loop-budget.py", {
            "tool_name": "Task",
            "tool_input": {"subagent_type": "x", "prompt": "y"},
            "tool_response": {"content": "erro qualquer"},
            "cwd": str(bare)}),
        ("session-checkpoint.py", {
            "session_id": "sessao-de-teste", "cwd": str(bare)}),
    ]
    # One directory PER hook: with only one, capture-build-result writes a
    # baseline there, mark-build-stale dirties it, and gate-advance blocks the push —
    # the gate working, but measuring the wrong thing. What this case asserts is
    # only that no hook DIES outside a git repo.
    for i, (name, payload) in enumerate(outside):
        target = tmp / f"sem-git-{i}"
        target.mkdir()
        payload = dict(payload, cwd=str(target))
        ti = payload.get("tool_input")
        if ti and "file_path" in ti:
            payload["tool_input"] = dict(ti, file_path=str(target / "App.java"))
        r = run_hook(name, payload)
        check(f"{name} sai 0 fora de repo", r.returncode == 0, r.stderr[:200])


# ─────────────────────────────────────────────────────────────────────────
print("\n# guarda de deriva — nenhum hook novo pode voltar a ancorar no cwd cru")
# ─────────────────────────────────────────────────────────────────────────
# The list of hooks that anchor state under `.claude/`. A new hook that writes
# state and is not here is an omission; a hook from here that goes back to the raw cwd
# is a regression. Both things turn red.
ANCHORED = [
    "session-log.py", "session-checkpoint.py", "capture-build-result.py",
    "gate-advance.py", "mark-build-stale.py", "loop-budget.py",
    "acceptance-gate.py",
    # Reads `.claude/session-mode` instead of writing, and for that very reason it enters: a
    # `cd` that diverts the read makes the hook not find the mode and release EVERYTHING in
    # silence, which is the failure OPENING a gate — the same as the other four.
    "write-mode-gate.py",
]

for name in ANCHORED:
    src = (HOOKS / name).read_text(encoding="utf-8")
    check(f"{name}: usa session_root", "session_root(" in src)

# The raw pattern: `Path(payload.get("cwd") ...)` without going through the helper.
RAW = re.compile(r'Path\(\s*payload\.get\(\s*["\']cwd["\']')
for name in ANCHORED:
    src = (HOOKS / name).read_text(encoding="utf-8")
    hits = [ln for ln in src.splitlines() if RAW.search(ln)]
    check(f"{name}: nenhum Path(payload['cwd']) cru", not hits, hits)

check("_wtlib expõe session_root",
      "def session_root(" in (HOOKS / "_wtlib.py").read_text(encoding="utf-8"))


print()
if FAILURES:
    print(f"{len(FAILURES)} FALHA(S): {', '.join(FAILURES)}")
    sys.exit(1)
print("todos os casos verdes")
