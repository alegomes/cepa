#!/usr/bin/env python3
"""Regression tests of the session-routine-guard.

/common:session and /common:spec contradict each other. The session says, in these
words, "between the start and the report, you ask nothing", activates the
default-yes skill and anticipates in step 3, in a round of at most four questions, everything
the target command would ask later. /common:spec loads the
guided-interrogation skill, which SUSPENDS default-yes, and asks in rounds because
each answer decides which the next ones are.

Without this gate, `/common:session common:spec <idea>` resolves and runs: the session
squeezes four generic questions at the start and guesses the rest. A well-formatted
docs/spec/<slug>.md comes out, with Surface and Red test in every
criterion, passing the spec-readiness-gate — which checks that the fields exist,
not that the answers came from the owner. The session ends saying "done".

What these tests pin down:
  - /common:session with a routine marked `interaction: conversational`
    blocks, and the message orders running the command directly;
  - a normal routine (without the marker) passes;
  - the aliases of step 1 of session.md are resolved (prove-drain → board-flow);
  - the owner is matched by the manifest NAME, not by the directory: `capture` exists
    in board-flow and in discovery, and the `docs` plugin lives in `docs-topology/`;
  - calling /common:spec DIRECTLY never blocks (it is the right path);
  - a prompt that is not /common:session exits immediately;
  - the gate fails OPEN on everything it does not understand.

Run: python3 tests/test_session_routine_guard.py
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "session-routine-guard.py"
PLUGIN_ROOT = REPO / "common"

# Empty HOME: no installed_plugins.json, so the gate falls back to the scan.
_NO_REGISTRY = tempfile.TemporaryDirectory()
NO_REGISTRY = Path(_NO_REGISTRY.name)

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def run(prompt, plugin_root=PLUGIN_ROOT, home=None):
    """home isolates CC's installed_plugins.json.

    Without this the suite would read the REAL registry of the machine of whoever runs it, and the
    result would depend on the owner having common installed. A test that changes
    color depending on the machine teaches people to ignore the color.
    """
    env = {"PATH": "/usr/bin:/bin", "CLAUDE_PLUGIN_ROOT": str(plugin_root)}
    env["HOME"] = str(home) if home else str(NO_REGISTRY)
    if plugin_root is None:
        env.pop("CLAUDE_PLUGIN_ROOT")
    p = subprocess.run([sys.executable, str(HOOK)],
                       input=json.dumps({"prompt": prompt}),
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stderr


def test_spec_via_session_blocks():
    rc, err = run("/common:session common:spec preciso repensar o modelo de dados")
    check("session + spec bloqueia", rc == 2, f"rc={rc} err={err[:200]}")
    check("mensagem manda rodar direto", "/common:spec" in err, err[:300])
    check("mensagem explica a contradição", "default-yes" in err, err[:300])


def test_normal_routine_passes():
    for routine in ("board-flow:prove-drain", "common:doctor", "common:next"):
        rc, err = run(f"/common:session {routine}")
        check(f"{routine} passa", rc == 0, f"rc={rc} err={err[:150]}")


def test_aliases_of_step_1():
    # prove-drain resolves to board-flow:prove-drain, which is NOT conversational.
    rc, _ = run("/common:session prove-drain --max 5")
    check("apelido prove-drain passa", rc == 0, f"rc={rc}")
    # docs resolves to docs:survey, whose plugin lives in docs-topology/ —
    # if the gate matched by directory, it would not find the file.
    rc, _ = run("/common:session docs")
    check("apelido docs (plugin em docs-topology/) passa", rc == 0, f"rc={rc}")


def test_ambiguous_capture_does_not_confuse():
    # capture.md exists in board-flow AND in discovery. Neither is conversational,
    # so both pass; what this test pins down is that the gate neither blows up nor
    # blocks by matching the wrong file.
    for routine in ("board-flow:capture", "discovery:capture"):
        rc, err = run(f"/common:session {routine} uma ideia")
        check(f"{routine} passa sem confusão", rc == 0, f"rc={rc} err={err[:150]}")


def test_direct_spec_never_blocks():
    rc, _ = run("/common:spec preciso repensar o modelo de dados")
    check("chamar /common:spec direto passa", rc == 0, f"rc={rc}")


def test_foreign_prompt_exits_immediately():
    for prompt in ("boa tarde", "/common:doctor", "rode /common:session depois",
                   "/common:sessionista coisa", ""):
        rc, _ = run(prompt)
        check(f"prompt {prompt[:24]!r} passa", rc == 0, f"rc={rc}")


def test_fails_open():
    rc, _ = run("/common:session naoexiste:comando")
    check("comando inexistente libera", rc == 0, f"rc={rc}")

    rc, _ = run("/common:session apelidoQueNaoExiste")
    check("apelido desconhecido libera", rc == 0, f"rc={rc}")

    # A root that leads to no plugin. NB: a root that is merely nonexistent INSIDE the
    # repo does not work as a case — the gate goes up two levels and finds the real file,
    # and then blocking is right: it found the command, it is not in the dark.
    with tempfile.TemporaryDirectory() as empty:
        rc, _ = run("/common:session common:spec",
                    plugin_root=Path(empty) / "cepa" / "common")
        check("raiz sem plugin nenhum libera", rc == 0, f"rc={rc}")

    rc, _ = run("/common:session common:spec x", plugin_root=None)
    check("sem CLAUDE_PLUGIN_ROOT nem registro libera", rc == 0, f"rc={rc}")

    p = subprocess.run([sys.executable, str(HOOK)], input="{ not json",
                       capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "HOME": str(NO_REGISTRY),
                            "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT)})
    check("payload ilegível libera", p.returncode == 0, f"rc={p.returncode}")


def test_reads_the_live_version_not_the_alphabetically_first():
    """CC's cache keeps the versions side by side.

    The first version of this hook swept with sorted() and read
    cache/cepa/common/1.5.0/commands/spec.md — the copy BEFORE the marker —,
    quietly releasing the invocation that should be blocked. The tests against the repo
    could not see this: the repo has no version directory. What caught it was running
    the really installed hook.
    """
    with tempfile.TemporaryDirectory() as d:
        base = Path(d) / "cache" / "cepa" / "common"
        for version, marker in (("1.5.0", ""), ("1.6.0", "interaction: conversational\n")):
            cmds = base / version / "commands"
            cmds.mkdir(parents=True)
            (base / version / ".claude-plugin").mkdir()
            (base / version / ".claude-plugin" / "plugin.json").write_text(
                json.dumps({"name": "common", "version": version}), encoding="utf-8")
            (cmds / "spec.md").write_text(
                f"---\ndescription: x\n{marker}---\n\ncorpo\n", encoding="utf-8")

        rc, err = run("/common:session common:spec uma ideia",
                      plugin_root=base / "1.6.0")
        check("lê a versão viva, não a 1.5.0", rc == 2, f"rc={rc} err={err[:200]}")

        # And through the pure scan (without CLAUDE_PLUGIN_ROOT pointing to the right one):
        rc, _ = run("/common:session common:spec uma ideia", plugin_root=base)
        check("varredura pega a maior versão", rc == 2, f"rc={rc}")


def test_aliases_do_not_diverge_from_session_md():
    """The hook's APELIDOS table and the list in step 1 of session.md are two
    copies of the same thing. If one gains an alias and the other does not, the gate
    resolves to a different command than the one session will run — and fails
    open in silence, which is the failure mode this whole file fights.
    """
    hook = HOOK.read_text(encoding="utf-8")
    block = hook.split("APELIDOS = {", 1)[1].split("}", 1)[0]
    from_hook = dict(re.findall(r'"([^"]+)":\s*"([^"]+)"', block))

    md = (REPO / "common" / "commands" / "session.md").read_text(encoding="utf-8")
    step1 = md.split("### 1. Resolve the routine", 1)[1].split("###", 1)[0]
    from_md = dict(re.findall(r'`([a-z-]+)` →\s*`/([a-z-]+:[a-z-]+)`', step1))

    for alias_name, target in from_hook.items():
        check(f"apelido {alias_name} está no session.md apontando para {target}",
              from_md.get(alias_name) == target, f"session.md diz {from_md.get(alias_name)!r}")
    check("drain-plan é um apelido do hook",
          from_hook.get("drain-plan") == "common:drain-plan", f"{from_hook.get('drain-plan')!r}")


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            fn()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {', '.join(FAILURES)}")
        sys.exit(1)
    print("all green")


if __name__ == "__main__":
    main()
