#!/usr/bin/env python3
"""CS-1 of docs/spec/tres-portas-spec-epic.md (item 6 of O2'): when the
spec-readiness-gate lets a spec through to `ready-to-build` (or an Epic to
`ready`/`closed`), it shows the owner "N decisões sem veredito neste arquivo",
counting the list lines of the "Decided without asking" section that carry
neither `· mantida em`, `· vetada em` nor `· refinada em`.

Driven the way Claude Code drives the hook: the PreToolUse payload on stdin.
What reaches the owner is the `systemMessage` field of the JSON on stdout
(exit 0); the same text goes in `additionalContext`, so the agent can repeat it
in the final report (CS-3).

The count only prints on the PASSAGE to ready: a second Write over a file that
is already ready on disk stays quiet, otherwise every later edit would repeat it.

Run: python3 tests/test_spec_readiness_decision_count.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "spec-readiness-gate.py"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def run(payload):
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def shown(stdout):
    """The text shown to the owner (`systemMessage`), or '' when silent."""
    if not stdout.strip():
        return ""
    try:
        return json.loads(stdout).get("systemMessage", "") or ""
    except json.JSONDecodeError:
        return ""


def agent_sees(stdout):
    try:
        return (json.loads(stdout).get("hookSpecificOutput") or {}).get(
            "additionalContext", "") or ""
    except (json.JSONDecodeError, AttributeError):
        return ""


DECISIONS_3 = """## Decided without asking
- A primeira decisão, que ninguém vetou ainda. Vete aqui se discordar.
- A segunda decisão, já conferida. Vete aqui se discordar. · mantida em 2026-11-06
- A terceira decisão, também pendente. Vete aqui se discordar.
"""

DECISIONS_NONE_PENDING = """## Decided without asking
- Uma decisão vetada. · vetada em 2026-11-06: fora do ciclo
- Uma decisão refinada. · refinada em 2026-11-06: só no hook
"""


def spec(status="ready-to-build", decisions=DECISIONS_3):
    return f"""# Especificação: x

**Status:** {status}

## Como chegamos aqui
O dono perguntou em 2026-11-06: "quantas decisões ficaram sem veredito?"

## Critérios de sucesso

### CS-1: o hook conta as decisões

**Surface:** event
**Red test:** o hook imprime a contagem — hoje não imprime.

## Perguntas em aberto
- [x] Conta só o arquivo? — sim (dono, 2026-11-06).

{decisions}"""


def tmp_spec_path():
    d = Path(tempfile.mkdtemp())
    (d / "docs" / "spec").mkdir(parents=True)
    return d / "docs" / "spec" / "x.md"


def write_payload(path, content):
    return {"tool_name": "Write",
            "tool_input": {"file_path": str(path), "content": content}}


def test_passage_to_ready_shows_pending_count():
    path = tmp_spec_path()          # nothing on disk yet: it is a passage
    rc, out, err = run(write_payload(path, spec()))
    msg = shown(out)
    check("ready-to-build completo sai com 0", rc == 0, f"rc={rc} err={err[:200]}")
    check("mostra '2 decisões sem veredito' (3 linhas, 1 mantida)",
          "2 decisões sem veredito" in msg, f"stdout={out[:300]!r}")
    check("a frase diz que a conta é deste arquivo",
          "neste arquivo" in msg, msg)
    check("o agente recebe o mesmo número para repetir no relatório",
          "2 decisões sem veredito" in agent_sees(out), out[:300])


def test_zero_pending_prints_zero():
    path = tmp_spec_path()
    rc, out, err = run(write_payload(path, spec(decisions=DECISIONS_NONE_PENDING)))
    check("zero pendente sai com 0", rc == 0, f"rc={rc} err={err[:200]}")
    check("imprime '0 decisões sem veredito' em vez de calar",
          "0 decisões sem veredito" in shown(out), f"stdout={out[:300]!r}")


def test_one_pending_is_singular():
    path = tmp_spec_path()
    one = DECISIONS_NONE_PENDING + "- Uma pendente.\n"
    rc, out, _ = run(write_payload(path, spec(decisions=one)))
    check("uma pendente vira '1 decisão sem veredito'",
          "1 decisão sem veredito" in shown(out), f"stdout={out[:300]!r}")


def test_without_section_says_so():
    path = tmp_spec_path()
    rc, out, err = run(write_payload(path, spec(decisions="")))
    check("spec sem a seção sai com 0 (seção não é obrigatória em spec)",
          rc == 0, f"rc={rc} err={err[:200]}")
    check("mostra 'sem seção Decided without asking'",
          "sem seção Decided without asking" in shown(out), f"stdout={out[:300]!r}")


def test_old_section_name_counts():
    path = tmp_spec_path()
    old = DECISIONS_3.replace("## Decided without asking", "## Decidido sem perguntar")
    rc, out, _ = run(write_payload(path, spec(decisions=old)))
    check("o nome antigo da seção também conta",
          "2 decisões sem veredito" in shown(out), f"stdout={out[:300]!r}")


def test_second_write_on_ready_file_is_quiet():
    path = tmp_spec_path()
    path.write_text(spec(), encoding="utf-8")       # already ready on disk
    rc, out, err = run(write_payload(path, spec() + "\nmais uma linha\n"))
    check("segundo Write sobre arquivo já pronto sai com 0", rc == 0,
          f"rc={rc} err={err[:200]}")
    check("...e não imprime a contagem", "sem veredito" not in out,
          f"stdout={out[:300]!r}")


def test_passage_from_draft_on_disk_prints():
    path = tmp_spec_path()
    path.write_text(spec(status="draft"), encoding="utf-8")
    rc, out, _ = run(write_payload(path, spec()))
    check("draft no disco -> Write ready imprime",
          "2 decisões sem veredito" in shown(out), f"stdout={out[:300]!r}")


def test_edit_that_flips_status_prints():
    path = tmp_spec_path()
    path.write_text(spec(status="draft"), encoding="utf-8")
    payload = {"tool_name": "Edit", "tool_input": {
        "file_path": str(path),
        "old_string": "**Status:** draft",
        "new_string": "**Status:** ready-to-build"}}
    rc, out, err = run(payload)
    check("Edit que troca draft -> ready sai com 0", rc == 0, f"rc={rc} err={err[:200]}")
    check("...e imprime a contagem do arquivo resultante",
          "2 decisões sem veredito" in shown(out), f"stdout={out[:300]!r}")


def test_draft_and_blocked_are_quiet():
    path = tmp_spec_path()
    rc, out, _ = run(write_payload(path, spec(status="draft")))
    check("draft não imprime contagem", rc == 0 and "sem veredito" not in out,
          f"rc={rc} stdout={out[:200]!r}")
    broken = spec().replace("**Surface:** event\n", "")
    rc, out, err = run(write_payload(path, broken))
    check("ready bloqueado sai com 2 e não imprime contagem no stdout",
          rc == 2 and "sem veredito" not in out, f"rc={rc} stdout={out[:200]!r}")


EPIC = """# Epic: x

**Status:** {status}

## Who it is for
O dono do Cepa, que fecha specs sozinho.

## Out of scope
- Mudar o debrief.

## Outcome metric
**Baseline:** 7 · **Target:** 0 · **Source:** cepa-doctor

## Value ladder
| Cycle | Script | Effect on screen | Effect in backend |
|---|---|---|---|
| c1 | o dono fecha | a contagem aparece | o hook sai com 0 |

## Invariants
- Draft nunca bloqueia.

{decisions}"""


def test_epic_ready_shows_count():
    d = Path(tempfile.mkdtemp())
    (d / "docs" / "epics").mkdir(parents=True)
    path = d / "docs" / "epics" / "x.md"
    rc, out, err = run(write_payload(path, EPIC.format(status="ready",
                                                      decisions=DECISIONS_3)))
    check("Epic ready sai com 0", rc == 0, f"rc={rc} err={err[:300]}")
    check("Epic ready mostra '2 decisões sem veredito'",
          "2 decisões sem veredito" in shown(out), f"stdout={out[:300]!r}")
    path.write_text(EPIC.format(status="ready", decisions=DECISIONS_3), encoding="utf-8")
    rc, out, _ = run(write_payload(path, EPIC.format(status="ready",
                                                    decisions=DECISIONS_3) + "\n"))
    check("Epic já ready no disco: segundo Write quieto",
          rc == 0 and "sem veredito" not in out, f"stdout={out[:200]!r}")


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
