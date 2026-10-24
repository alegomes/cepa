#!/usr/bin/env python3
"""Regression tests for the default-yes-inject.

The `default-yes` skill has existed since 2026-08-18 and says what to do with a
recommendation: a reversible action, or one that only records something, with a
clear recommendation → execute and account for it in the report; ask only the
irreversible, and in batches at the edges. But a skill does not activate itself —
it applies when the running command orders it activated, and on 2026-08-22 only
6 of the repo's 56 commands cited it.

The hole was not cosmetic. `/board-flow:drain` cites the skill, but calls
`/board-flow:execute` per card, which dispatches to `plan-build-validate` /
`reproduce-fix-verify`, which call `prove` and `advance` — and none of those cited it.
The policy held at the start (where asking is cheap) and evaporated in the middle
of the run (where it is expensive).

What these tests pin down:
  - a command marked `interaction: routine` injects the policy, and the text says
    it applies to the commands and subagents invoked — which is the whole point;
  - a `conversational` command (/common:spec) does NOT inject: there the
    guided-interrogation skill suspends default-yes on purpose, and re-injecting it
    would reopen the contradiction that the session-routine-guard closes;
  - /common:session <routine> follows the TARGET, not the wrapper;
  - a prompt that is not a plugin command exits immediately, at no cost;
  - anything the hook does not understand → does not inject. It GRANTS autonomy; when
    in doubt it does not grant. And it never blocks: always exit 0.

Run: python3 tests/test_default_yes_inject.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "default-yes-inject.py"
PLUGIN_ROOT = REPO / "common"

# Empty HOME: without installed_plugins.json the hook falls back to scanning the repo, instead
# of reading the REAL registry of the machine of whoever runs the suite.
_NO_REGISTRY = tempfile.TemporaryDirectory()
NO_REGISTRY = Path(_NO_REGISTRY.name)

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def run(prompt, plugin_root=PLUGIN_ROOT):
    env = {"PATH": "/usr/bin:/bin", "HOME": str(NO_REGISTRY)}
    if plugin_root is not None:
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
    p = subprocess.run([sys.executable, str(HOOK)],
                       input=json.dumps({"prompt": prompt}),
                       capture_output=True, text=True, env=env)
    ctx = ""
    if p.stdout.strip():
        try:
            ctx = json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
        except Exception:  # noqa: BLE001
            ctx = f"<stdout ilegível: {p.stdout[:120]}>"
    return p.returncode, ctx


def test_routine_injects():
    for routine_name in ("board-flow:prove-drain", "board-flow:drain", "common:doctor",
                   "build-hex:plan-build-validate", "board-flow:advance"):
        rc, ctx = run(f"/{routine_name} --max 5")
        check(f"{routine_name} injeta", rc == 0 and "default-yes" in ctx,
              f"rc={rc} ctx={ctx[:120]!r}")


def test_text_reaches_the_middle_of_the_run():
    """What was missing was not the policy, it was its REACH."""
    _, ctx = run("/board-flow:drain --max 3")
    check("diz que vale para o run inteiro", "run inteiro" in ctx, ctx[:200])
    check("nomeia subagentes/comandos invocados",
          "subagentes" in ctx and "invocar" in ctx, ctx[:200])
    check("mantém a fronteira do irreversível", "irreversível" in ctx, ctx[:200])
    check("exige prestar contas no relatório", "relatório final" in ctx, ctx[:200])


def test_conversational_does_not_inject():
    rc, ctx = run("/common:spec preciso repensar o modelo de dados")
    check("spec não injeta", rc == 0 and ctx == "", f"rc={rc} ctx={ctx[:120]!r}")
    rc, ctx = run("/common:debrief")
    check("debrief não injeta", rc == 0 and ctx == "", f"rc={rc} ctx={ctx[:120]!r}")


def test_session_follows_the_target():
    # The wrapper is routine, but whoever rules the policy is the target routine.
    rc, ctx = run("/common:session prove-drain --max 5")
    check("session + rotina injeta", rc == 0 and "board-flow:prove-drain" in ctx,
          f"rc={rc} ctx={ctx[:150]!r}")
    rc, ctx = run("/common:session drain-plan wego --max 2")
    check("session + apelido drain-plan injeta",
          rc == 0 and "common:drain-plan" in ctx, f"rc={rc} ctx={ctx[:150]!r}")
    rc, ctx = run("/common:session common:spec uma ideia")
    check("session + conversacional não injeta", rc == 0 and ctx == "",
          f"rc={rc} ctx={ctx[:150]!r}")


def test_foreign_prompt_exits_immediately():
    for prompt in ("boa tarde", "rode /common:doctor depois", "/help", "",
                   "/clear", "e o /board-flow:drain?"):
        rc, ctx = run(prompt)
        check(f"prompt {prompt[:22]!r} não injeta", rc == 0 and ctx == "",
              f"rc={rc} ctx={ctx[:120]!r}")


def test_when_in_doubt_does_not_grant():
    rc, ctx = run("/naoexiste:comando")
    check("comando inexistente não injeta", rc == 0 and ctx == "", f"rc={rc}")
    rc, ctx = run("/common:doctor", plugin_root=None)
    check("sem CLAUDE_PLUGIN_ROOT não injeta", rc == 0 and ctx == "", f"rc={rc}")
    # Root OUTSIDE the repo: the `bases()` scan has nowhere to find the command.
    # (A nonexistent root INSIDE the repo, on the contrary, resolves — the siblings
    # of CLAUDE_PLUGIN_ROOT are exactly where the plugins live, and that is how
    # the session-routine-guard finds it too. That is correct, not a leak.)
    with tempfile.TemporaryDirectory() as outside:
        rc, ctx = run("/common:doctor", plugin_root=Path(outside) / "common")
        check("raiz fora do repo não injeta", rc == 0 and ctx == "",
              f"rc={rc} ctx={ctx[:120]!r}")


def test_every_command_declares_interaction():
    """The hook only works on marked commands — a new command without the field
    goes back to interrupting in silence, which is the original defect.
    """
    import re
    FM = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    missing = []
    for f in sorted(REPO.glob("*/commands/*.md")):
        m = FM.match(f.read_text(encoding="utf-8"))
        val = re.search(r"^interaction\s*:\s*(\S+)", m.group(1), re.M) if m else None
        if not val or val.group(1) not in ("routine", "conversational"):
            missing.append(str(f.relative_to(REPO)))
    check("todo comando declara interaction válido", not missing, str(missing))


for fn in list(globals().values()):
    if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
        print(f"\n{fn.__name__}")
        fn()

print("\nall green" if not FAILURES else f"\n{len(FAILURES)} FAILURES: {FAILURES}")
sys.exit(1 if FAILURES else 0)
