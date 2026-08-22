#!/usr/bin/env python3
"""Regression tests do default-yes-inject.

A skill `default-yes` existe desde 18/08/2026 e diz o que fazer com uma
recomendação: ação reversível, ou que só registra algo, com recomendação clara
→ execute e preste contas no relatório; pergunte só o irreversível, e em lote
nas pontas. Só que skill não se ativa sozinha — ela vale quando o comando que
está rodando manda ativá-la, e em 22/08/2026 só 6 dos 56 comandos do repo a
citavam.

O buraco não era cosmético. `/board-flow:drain` cita a skill, mas chama
`/board-flow:execute` por card, que despacha para `plan-build-validate` /
`reproduce-fix-verify`, que chamam `prove` e `advance` — e nenhum desses citava.
A política valia na largada (onde a pergunta é barata) e evaporava no meio do
run (onde ela é cara).

O que estes testes fixam:
  - comando marcado `interaction: routine` injeta a política, e o texto diz que
    ela vale para os comandos e subagentes invocados — que é o ponto todo;
  - comando `conversational` (/common:spec) NÃO injeta: ali a skill
    guided-interrogation suspende a default-yes de propósito, e reinjetá-la
    reabriria a contradição que o session-routine-guard fecha;
  - /common:session <rotina> segue o ALVO, não o invólucro;
  - prompt que não é comando de plugin sai na hora, sem custo;
  - tudo que o hook não entende → não injeta. Ele CONCEDE autonomia; na dúvida
    não concede. E nunca bloqueia: exit 0 sempre.

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

# HOME vazio: sem installed_plugins.json o hook cai na varredura do repo, em vez
# de ler o registro REAL da máquina de quem roda a suíte.
_SEM_REGISTRO = tempfile.TemporaryDirectory()
SEM_REGISTRO = Path(_SEM_REGISTRO.name)

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def run(prompt, plugin_root=PLUGIN_ROOT):
    env = {"PATH": "/usr/bin:/bin", "HOME": str(SEM_REGISTRO)}
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


def test_rotina_injeta():
    for rotina in ("board-flow:prove-drain", "board-flow:drain", "common:doctor",
                   "build-hex:plan-build-validate", "board-flow:advance"):
        rc, ctx = run(f"/{rotina} --max 5")
        check(f"{rotina} injeta", rc == 0 and "default-yes" in ctx,
              f"rc={rc} ctx={ctx[:120]!r}")


def test_texto_alcanca_o_meio_do_run():
    """O que faltava não era a política, era o ALCANCE dela."""
    _, ctx = run("/board-flow:drain --max 3")
    check("diz que vale para o run inteiro", "run inteiro" in ctx, ctx[:200])
    check("nomeia subagentes/comandos invocados",
          "subagentes" in ctx and "invocar" in ctx, ctx[:200])
    check("mantém a fronteira do irreversível", "irreversível" in ctx, ctx[:200])
    check("exige prestar contas no relatório", "relatório final" in ctx, ctx[:200])


def test_conversacional_nao_injeta():
    rc, ctx = run("/common:spec preciso repensar o modelo de dados")
    check("spec não injeta", rc == 0 and ctx == "", f"rc={rc} ctx={ctx[:120]!r}")
    rc, ctx = run("/common:debrief")
    check("debrief não injeta", rc == 0 and ctx == "", f"rc={rc} ctx={ctx[:120]!r}")


def test_session_segue_o_alvo():
    # O invólucro é routine, mas quem manda na política é a rotina-alvo.
    rc, ctx = run("/common:session prove-drain --max 5")
    check("session + rotina injeta", rc == 0 and "board-flow:prove-drain" in ctx,
          f"rc={rc} ctx={ctx[:150]!r}")
    rc, ctx = run("/common:session common:spec uma ideia")
    check("session + conversacional não injeta", rc == 0 and ctx == "",
          f"rc={rc} ctx={ctx[:150]!r}")


def test_prompt_alheio_sai_na_hora():
    for prompt in ("boa tarde", "rode /common:doctor depois", "/help", "",
                   "/clear", "e o /board-flow:drain?"):
        rc, ctx = run(prompt)
        check(f"prompt {prompt[:22]!r} não injeta", rc == 0 and ctx == "",
              f"rc={rc} ctx={ctx[:120]!r}")


def test_na_duvida_nao_concede():
    rc, ctx = run("/naoexiste:comando")
    check("comando inexistente não injeta", rc == 0 and ctx == "", f"rc={rc}")
    rc, ctx = run("/common:doctor", plugin_root=None)
    check("sem CLAUDE_PLUGIN_ROOT não injeta", rc == 0 and ctx == "", f"rc={rc}")
    # Raiz FORA do repo: a varredura de `bases()` não tem onde achar o comando.
    # (Uma raiz inexistente DENTRO do repo, ao contrário, resolve — os irmãos
    # do CLAUDE_PLUGIN_ROOT são justamente onde os plugins moram, e é assim que
    # o session-routine-guard também acha. Isso é acerto, não vazamento.)
    with tempfile.TemporaryDirectory() as fora:
        rc, ctx = run("/common:doctor", plugin_root=Path(fora) / "common")
        check("raiz fora do repo não injeta", rc == 0 and ctx == "",
              f"rc={rc} ctx={ctx[:120]!r}")


def test_todo_comando_declara_interaction():
    """O hook só funciona sobre comandos marcados — um comando novo sem o campo
    volta a interromper em silêncio, que é o defeito original."""
    import re
    FM = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    faltando = []
    for f in sorted(REPO.glob("*/commands/*.md")):
        m = FM.match(f.read_text(encoding="utf-8"))
        val = re.search(r"^interaction\s*:\s*(\S+)", m.group(1), re.M) if m else None
        if not val or val.group(1) not in ("routine", "conversational"):
            faltando.append(str(f.relative_to(REPO)))
    check("todo comando declara interaction válido", not faltando, str(faltando))


for fn in list(globals().values()):
    if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
        print(f"\n{fn.__name__}")
        fn()

print("\nall green" if not FAILURES else f"\n{len(FAILURES)} FAILURES: {FAILURES}")
sys.exit(1 if FAILURES else 0)
