#!/usr/bin/env python3
"""Regression tests do session-routine-guard.

/common:session e /common:spec se contradizem. O session diz, com essas
palavras, "entre a largada e o relatório, você não pergunta nada", ativa a skill
default-yes e antecipa no passo 3 numa rodada de no máximo quatro perguntas tudo
que o comando-alvo perguntaria depois. O /common:spec carrega a skill
guided-interrogation, que SUSPENDE a default-yes, e pergunta em rodadas porque
cada resposta decide quais são as próximas.

Sem este gate, `/common:session common:spec <ideia>` resolve e roda: o session
espreme quatro perguntas genéricas na largada e adivinha o resto. Sai um
docs/spec/<slug>.md bem formatado, com Superfície e Teste vermelho em todo
critério, passando no spec-readiness-gate — que confere se os campos existem,
não se as respostas vieram do dono. A sessão termina dizendo "concluído".

O que estes testes fixam:
  - /common:session com uma rotina marcada `interaction: conversational`
    bloqueia, e a mensagem manda rodar o comando direto;
  - rotina normal (sem o marcador) passa;
  - os apelidos do passo 1 do session.md são resolvidos (prove-drain → board-flow);
  - o dono é casado pelo NOME do manifest, não pelo diretório: `capture` existe
    em board-flow e em discovery, e o plugin `docs` mora em `docs-topology/`;
  - chamar /common:spec DIRETO nunca bloqueia (é o caminho certo);
  - prompt que não é /common:session sai na hora;
  - o gate falha ABERTO em tudo que não entende.

Run: python3 tests/test_session_routine_guard.py
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "session-routine-guard.py"
PLUGIN_ROOT = REPO / "common"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def run(prompt, plugin_root=PLUGIN_ROOT):
    env = {"PATH": "/usr/bin:/bin", "CLAUDE_PLUGIN_ROOT": str(plugin_root)}
    p = subprocess.run([sys.executable, str(HOOK)],
                       input=json.dumps({"prompt": prompt}),
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stderr


def test_spec_via_session_bloqueia():
    rc, err = run("/common:session common:spec preciso repensar o modelo de dados")
    check("session + spec bloqueia", rc == 2, f"rc={rc} err={err[:200]}")
    check("mensagem manda rodar direto", "/common:spec" in err, err[:300])
    check("mensagem explica a contradição", "default-yes" in err, err[:300])


def test_rotina_normal_passa():
    for rotina in ("board-flow:prove-drain", "common:doctor", "common:next"):
        rc, err = run(f"/common:session {rotina}")
        check(f"{rotina} passa", rc == 0, f"rc={rc} err={err[:150]}")


def test_apelidos_do_passo_1():
    # prove-drain resolve para board-flow:prove-drain, que NÃO é conversacional.
    rc, _ = run("/common:session prove-drain --max 5")
    check("apelido prove-drain passa", rc == 0, f"rc={rc}")
    # docs resolve para docs:survey, cujo plugin mora em docs-topology/ —
    # se o gate casasse pelo diretório, não acharia o arquivo.
    rc, _ = run("/common:session docs")
    check("apelido docs (plugin em docs-topology/) passa", rc == 0, f"rc={rc}")


def test_capture_ambiguo_nao_confunde():
    # capture.md existe em board-flow E em discovery. Nenhum é conversacional,
    # então ambos passam; o que este teste fixa é que o gate não explode nem
    # bloqueia por casar o arquivo errado.
    for rotina in ("board-flow:capture", "discovery:capture"):
        rc, err = run(f"/common:session {rotina} uma ideia")
        check(f"{rotina} passa sem confusão", rc == 0, f"rc={rc} err={err[:150]}")


def test_spec_direto_nunca_bloqueia():
    rc, _ = run("/common:spec preciso repensar o modelo de dados")
    check("chamar /common:spec direto passa", rc == 0, f"rc={rc}")


def test_prompt_alheio_sai_na_hora():
    for prompt in ("boa tarde", "/common:doctor", "rode /common:session depois",
                   "/common:sessionista coisa", ""):
        rc, _ = run(prompt)
        check(f"prompt {prompt[:24]!r} passa", rc == 0, f"rc={rc}")


def test_falha_aberto():
    rc, _ = run("/common:session naoexiste:comando")
    check("comando inexistente libera", rc == 0, f"rc={rc}")

    rc, _ = run("/common:session apelidoQueNaoExiste")
    check("apelido desconhecido libera", rc == 0, f"rc={rc}")

    # Raiz que não leva a plugin nenhum. NB: uma raiz apenas inexistente DENTRO
    # do repo não serve de caso — o gate sobe dois níveis e acha o arquivo real,
    # e aí bloquear é o certo: ele encontrou o comando, não está no escuro.
    import tempfile
    with tempfile.TemporaryDirectory() as vazio:
        rc, _ = run("/common:session common:spec",
                    plugin_root=Path(vazio) / "cepa" / "common")
        check("raiz sem plugin nenhum libera", rc == 0, f"rc={rc}")

    env = {"PATH": "/usr/bin:/bin"}   # sem CLAUDE_PLUGIN_ROOT
    p = subprocess.run([sys.executable, str(HOOK)],
                       input=json.dumps({"prompt": "/common:session common:spec x"}),
                       capture_output=True, text=True, env=env)
    check("sem CLAUDE_PLUGIN_ROOT libera", p.returncode == 0, f"rc={p.returncode}")

    p = subprocess.run([sys.executable, str(HOOK)], input="{ not json",
                       capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin",
                            "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT)})
    check("payload ilegível libera", p.returncode == 0, f"rc={p.returncode}")


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
