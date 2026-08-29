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
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "session-routine-guard.py"
PLUGIN_ROOT = REPO / "common"

# HOME vazio: nenhum installed_plugins.json, entao o gate cai na varredura.
_SEM_REGISTRO = tempfile.TemporaryDirectory()
SEM_REGISTRO = Path(_SEM_REGISTRO.name)

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def run(prompt, plugin_root=PLUGIN_ROOT, home=None):
    """home isola o installed_plugins.json do CC.

    Sem isso a suite leria o registro REAL da maquina de quem roda, e o
    resultado dependeria de o dono ter o common instalado. Teste que muda de
    cor conforme a maquina ensina a ignorar a cor.
    """
    env = {"PATH": "/usr/bin:/bin", "CLAUDE_PLUGIN_ROOT": str(plugin_root)}
    env["HOME"] = str(home) if home else str(SEM_REGISTRO)
    if plugin_root is None:
        env.pop("CLAUDE_PLUGIN_ROOT")
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
    with tempfile.TemporaryDirectory() as vazio:
        rc, _ = run("/common:session common:spec",
                    plugin_root=Path(vazio) / "cepa" / "common")
        check("raiz sem plugin nenhum libera", rc == 0, f"rc={rc}")

    rc, _ = run("/common:session common:spec x", plugin_root=None)
    check("sem CLAUDE_PLUGIN_ROOT nem registro libera", rc == 0, f"rc={rc}")

    p = subprocess.run([sys.executable, str(HOOK)], input="{ not json",
                       capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "HOME": str(SEM_REGISTRO),
                            "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT)})
    check("payload ilegível libera", p.returncode == 0, f"rc={p.returncode}")


def test_le_a_versao_viva_e_nao_a_alfabeticamente_primeira():
    """O cache do CC guarda as versões lado a lado.

    A primeira versão deste hook varria com sorted() e lia
    cache/cepa/common/1.5.0/commands/spec.md — a cópia ANTERIOR ao marcador —,
    liberando calada a invocação que devia barrar. Os testes contra o repo não
    podiam ver isso: o repo não tem diretório de versão. Quem pegou foi rodar
    o hook instalado de verdade.
    """
    with tempfile.TemporaryDirectory() as d:
        base = Path(d) / "cache" / "cepa" / "common"
        for versao, marcador in (("1.5.0", ""), ("1.6.0", "interaction: conversational\n")):
            cmds = base / versao / "commands"
            cmds.mkdir(parents=True)
            (base / versao / ".claude-plugin").mkdir()
            (base / versao / ".claude-plugin" / "plugin.json").write_text(
                json.dumps({"name": "common", "version": versao}), encoding="utf-8")
            (cmds / "spec.md").write_text(
                f"---\ndescription: x\n{marcador}---\n\ncorpo\n", encoding="utf-8")

        rc, err = run("/common:session common:spec uma ideia",
                      plugin_root=base / "1.6.0")
        check("lê a versão viva, não a 1.5.0", rc == 2, f"rc={rc} err={err[:200]}")

        # E pela varredura pura (sem CLAUDE_PLUGIN_ROOT apontando para a certa):
        rc, _ = run("/common:session common:spec uma ideia", plugin_root=base)
        check("varredura pega a maior versão", rc == 2, f"rc={rc}")


def test_apelidos_nao_divergem_do_session_md():
    """A tabela APELIDOS do hook e a lista do passo 1 do session.md são duas
    cópias da mesma coisa. Se uma ganhar um apelido e a outra não, o gate
    resolve para um comando diferente do que o session vai rodar — e falha
    aberto calado, que é o modo de falha que este arquivo inteiro combate."""
    hook = HOOK.read_text(encoding="utf-8")
    bloco = hook.split("APELIDOS = {", 1)[1].split("}", 1)[0]
    do_hook = dict(re.findall(r'"([^"]+)":\s*"([^"]+)"', bloco))

    md = (REPO / "common" / "commands" / "session.md").read_text(encoding="utf-8")
    passo1 = md.split("### 1. Resolver a rotina", 1)[1].split("###", 1)[0]
    do_md = dict(re.findall(r'`([a-z-]+)` →\s*`/([a-z-]+:[a-z-]+)`', passo1))

    for apelido, alvo in do_hook.items():
        check(f"apelido {apelido} está no session.md apontando para {alvo}",
              do_md.get(apelido) == alvo, f"session.md diz {do_md.get(apelido)!r}")
    check("drain-plan é um apelido do hook",
          do_hook.get("drain-plan") == "common:drain-plan", f"{do_hook.get('drain-plan')!r}")


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
