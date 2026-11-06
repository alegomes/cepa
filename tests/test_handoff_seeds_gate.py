#!/usr/bin/env python3
"""Regression tests for common/hooks/handoff-seeds-gate.py (A1).

No third-party deps — run with `python3 tests/test_handoff_seeds_gate.py`.

Guards the contracts of the discovery-handoff gate:
  - a brief carrying both fields passes; each missing one blocks and is named;
  - an explicit `none` is a valid answer (nulls are explicit, not absent);
  - pt-BR labels are accepted as equivalents;
  - only docs/discovery/<key>/handoff.md is gated — other paths pass;
  - present-but-unlabeled is reported as a FORMAT problem, not an omission
    (the 2026-07-21 summary-nulls-gate lesson: a gate that misdiagnoses a
    formatting slip teaches agents that gates are noise);
  - other tools, unseeable content, and unparseable payloads fail open.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "handoff-seeds-gate.py"

FAILURES = []

PATH = "docs/discovery/DISC-12/handoff.md"

COMPLETE = """\
# Delivery brief: faster invoice search

## What user-visible change is being committed to?
Search returns in under a second.

## Validation seeds
- Signal: median search latency on the invoices endpoint.
- Expected direction: down, from ~3s to under 1s.
- Falsifier: if p50 improves but p95 worsens, the change traded tail latency.

## Carry-forward notes
- The legacy `emissao` column is text, not date — sorting needs a cast.
- Partner API rate-limits at 10 rps; batch imports must respect it.
"""

MISSING_SEEDS = """\
# Delivery brief: faster invoice search

## Carry-forward notes
- The legacy `emissao` column is text, not date.
"""

MISSING_NOTES = """\
# Delivery brief: faster invoice search

## Validation seeds
- Signal: median search latency.
"""

EXPLICIT_NONE = """\
# Delivery brief: internal index rebuild

**Validation seeds:** none — internal substrate, no user-visible signal.
**Carry-forward notes:** none.
"""

PT_BR = """\
# Brief de entrega: busca de faturas

## Sementes de validação
- Sinal: latência mediana da busca.

## Achados a carregar
- A coluna `emissao` é texto, não data.
"""

UNLABELED = """\
# Delivery brief: faster invoice search

The validation seeds we thought of: median latency should drop below 1s.
Carry-forward notes we gathered: the emissao column is text.
"""


SESSION_PATH = ".claude/handoffs/session-1104-2335.md"

SESSION_OK = """\
## Onde estamos
Gate novo.

## Próximo passo
Implementar o gate.
porque: o dono abriu a spec e não reconheceu o assunto; a pergunta original era "como o handoff grava o porquê?"
**Próximo:** repo=/x mode=build comando=/common:spec foo

## Threads abertas
- nada
"""

SESSION_NO_PORQUE = SESSION_OK.replace(
    'porque: o dono abriu a spec e não reconheceu o assunto; a pergunta original era "como o handoff grava o porquê?"\n',
    "")


def run_hook(tool_name, tool_input):
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    return subprocess.run(
        [sys.executable, str(HOOK)], input=payload, capture_output=True, text=True
    )


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def write(path, content):
    return run_hook("Write", {"file_path": path, "content": content})


def main():
    # ── happy paths ────────────────────────────────────────────────────────
    r = write(PATH, COMPLETE)
    check("brief completo passa", r.returncode == 0, r.stderr)

    r = write(PATH, EXPLICIT_NONE)
    check("nulo explícito ('none') passa", r.returncode == 0, r.stderr)

    r = write(PATH, PT_BR)
    check("rótulos pt-BR são aceitos", r.returncode == 0, r.stderr)

    r = write("/Users/x/proj/docs/discovery/DISC-9/handoff.md", COMPLETE)
    check("caminho absoluto é reconhecido", r.returncode == 0, r.stderr)

    # ── blocks ─────────────────────────────────────────────────────────────
    r = write(PATH, MISSING_SEEDS)
    check("sem Validation seeds bloqueia", r.returncode == 2, r.stdout)
    check("bloqueio nomeia o campo ausente",
          "Validation seeds" in r.stderr and "missing required field" in r.stderr,
          r.stderr)
    check("não acusa o campo que está presente",
          "- **Carry-forward notes:**" not in r.stderr.split("A handoff carries")[0],
          r.stderr)

    r = write(PATH, MISSING_NOTES)
    check("sem Carry-forward notes bloqueia", r.returncode == 2, r.stdout)
    check("bloqueio nomeia Carry-forward notes",
          "Carry-forward notes" in r.stderr, r.stderr)

    r = write(PATH, "# Delivery brief\n\nNothing else.\n")
    check("brief sem nenhum dos dois bloqueia", r.returncode == 2, r.stdout)

    # ── absent vs. malformatted (the lesson of the 07/21 false positive) ───
    r = write(PATH, UNLABELED)
    check("presente-mas-sem-marcação bloqueia", r.returncode == 2, r.stdout)
    check("diagnostica FORMATO, não omissão",
          "NOT in a recognized format" in r.stderr
          and "missing required field" not in r.stderr, r.stderr)
    check("manda re-formatar, não re-escrever",
          "only the label's markup is wrong" in r.stderr, r.stderr)

    # ── scope: only the discovery handoff is watched ───────────────────────
    for other in ("docs/discovery/DISC-12/framing.md",
                  "docs/discovery/DISC-12/research.md",
                  "docs/handoff.md",
                  "README.md",
                  ".claude/handoffs/main.md"):
        r = write(other, "sem campo nenhum")
        check(f"fora de escopo passa: {other}", r.returncode == 0, r.stderr)

    # ── fail-open ──────────────────────────────────────────────────────────
    r = run_hook("Read", {"file_path": PATH})
    check("outra ferramenta passa", r.returncode == 0, r.stderr)

    r = run_hook("Write", {"file_path": PATH})
    check("sem conteúdo visível → fail-open", r.returncode == 0, r.stderr)

    r = subprocess.run([sys.executable, str(HOOK)], input="{ not json",
                       capture_output=True, text=True)
    check("payload inválido → fail-open", r.returncode == 0, r.stderr)

    r = subprocess.run([sys.executable, str(HOOK)], input="",
                       capture_output=True, text=True)
    check("payload vazio → fail-open", r.returncode == 0, r.stderr)

    # ── Edit/MultiEdit carregam fragmento ──────────────────────────────────
    r = run_hook("Edit", {"file_path": PATH, "new_string": COMPLETE})
    check("Edit com os dois campos passa", r.returncode == 0, r.stderr)

    r = run_hook("Edit", {"file_path": PATH, "new_string": "só um parágrafo"})
    check("Edit sem os campos bloqueia", r.returncode == 2, r.stdout)

    r = run_hook("MultiEdit", {"file_path": PATH, "edits": [
        {"new_string": "## Validation seeds\n- sinal"},
        {"new_string": "## Carry-forward notes\n- quirk"},
    ]})
    check("MultiEdit soma os fragmentos", r.returncode == 0, r.stderr)

    # ── session handoff: the `porque:` line of `## Próximo passo` ──────────
    r = write(SESSION_PATH, SESSION_OK)
    check("session handoff com porque passa", r.returncode == 0, r.stderr)

    r = write(SESSION_PATH, SESSION_NO_PORQUE)
    check("session handoff sem porque bloqueia", r.returncode == 2, r.stdout)
    check("bloqueio do session handoff nomeia porque",
          "porque" in r.stderr and "Próximo passo" in r.stderr, r.stderr)

    r = write(SESSION_PATH, SESSION_OK.replace(
        "porque:", "**Porque:**"))
    check("forma **Porque:** em negrito passa", r.returncode == 0, r.stderr)

    r = write(SESSION_PATH, SESSION_OK.replace("porque:", "- Porque:"))
    check("forma de lista '- Porque:' passa", r.returncode == 0, r.stderr)

    r = write(SESSION_PATH, "## Onde estamos\nNota curta, sem próximo passo.\n")
    check("session handoff sem '## Próximo passo' passa", r.returncode == 0, r.stderr)

    r = write(SESSION_PATH, SESSION_OK)
    check("session handoff não exige Validation seeds/Carry-forward",
          r.returncode == 0 and "Validation seeds" not in r.stderr, r.stderr)

    # porque in ANOTHER section does not satisfy the Próximo passo section
    r = write(SESSION_PATH, SESSION_NO_PORQUE + "\n## Cuidados\nporque: algo\n")
    check("porque fora de '## Próximo passo' não vale", r.returncode == 2, r.stderr)

    for label, val in (("vazio", ""), ("só espaços", "   "),
                       ("placeholder <...>", " <a pergunta do dono que começou o assunto>"),
                       ("negrito vazio", "**")):
        line = "**Porque:**" + val if label == "negrito vazio" else "porque:" + val
        r = write(SESSION_PATH, SESSION_NO_PORQUE.replace(
            "Implementar o gate.\n", "Implementar o gate.\n" + line + "\n"))
        check(f"porque {label} bloqueia", r.returncode == 2, r.stderr)
        check(f"porque {label}: mensagem diz presente-mas-vazio, não ausente",
              "EMPTY" in r.stderr and "has no `porque:` line" not in r.stderr,
              r.stderr)
    r = write(SESSION_PATH, SESSION_NO_PORQUE)
    check("porque ausente: mensagem diz ausente",
          "has no `porque:` line" in r.stderr and "EMPTY" not in r.stderr,
          r.stderr)
    r = write(SESSION_PATH, SESSION_NO_PORQUE.replace(
        "Implementar o gate.\n", "Implementar o gate.\nporque: texto real\n"))
    check("porque: texto real passa", r.returncode == 0, r.stderr)
    r = write(SESSION_PATH, SESSION_NO_PORQUE.replace(
        "Implementar o gate.\n", "Implementar o gate.\n**Porque:** texto real\n"))
    check("**Porque:** texto real passa", r.returncode == 0, r.stderr)

    r = write(PATH, COMPLETE)
    check("handoff de discovery não pede porque", r.returncode == 0, r.stderr)

    r = run_hook("Edit", {"file_path": SESSION_PATH,
                          "new_string": SESSION_NO_PORQUE})
    check("Edit com '## Próximo passo' sem porque bloqueia",
          r.returncode == 2, r.stdout)

    r = run_hook("Edit", {"file_path": SESSION_PATH,
                          "new_string": "## Threads abertas\n- algo novo\n"})
    check("Edit em outra seção passa", r.returncode == 0, r.stderr)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
