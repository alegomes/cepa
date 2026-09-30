#!/usr/bin/env python3
"""cepa-until — hook de plugin mudado na branch da noite só vale depois de
aterrissar e reinstalar.

No run 2026-09-28-1146 o item 2 consertou o `bash-path-lock` e o item 1 o
`no-background-build`, e as 4 rodadas seguintes continuaram barradas pelas
versões antigas: os hooks rodam do plugin instalado no cache (cópia do clone),
não da branch da noite. Nenhuma rodada se perdeu, mas nada no run dizia isso.

Os casos abaixo fixam o aviso:
  - o item que commita `<plugin>/hooks/...` ganha uma linha na tela, antes do
    item seguinte começar, e um evento `hook_so_apos_reinstalar` no registro;
  - o fim do run cobra o `bin/install.sh` em "Fica com você" e no estado;
  - `hooks/` fora de plugin (sem `.claude-plugin/plugin.json`) não avisa;
  - hook que saiu da branch com o build vermelho não é cobrado no fim.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    FAILURES, check, fake_claude, item, ledger_de, monta_repo, roda)


def com_plugin(raiz):
    """O repo de teste vira repo de plugin: `meuplug/` com plugin.json e um
    hook, e `solto/hooks/` sem plugin.json."""
    (raiz / "meuplug" / ".claude-plugin").mkdir(parents=True)
    (raiz / "meuplug" / ".claude-plugin" / "plugin.json").write_text("{}")
    (raiz / "meuplug" / "hooks").mkdir()
    (raiz / "meuplug" / "hooks" / "trava.py").write_text("v1\n")
    (raiz / "solto" / "hooks").mkdir(parents=True)
    (raiz / "solto" / "hooks" / "x.py").write_text("v1\n")
    subprocess.run(["git", "add", "-A"], cwd=raiz, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "plugin"], cwd=raiz, check=True)
    return raiz


# O `claude` falso commita o arquivo que FAKE_ARQUIVOS manda para o item
# (`a1=meuplug/hooks/trava.py;a2=...`), ou só `<id>.txt`.
TRABALHA = (
    "import subprocess\n"
    "ident = primeiro_pendente()\n"
    "mapa = dict(p.split('=') for p in "
    "os.environ.get('FAKE_ARQUIVOS', '').split(';') if p)\n"
    "alvo = mapa.get(ident, ident + '.txt')\n"
    "open(alvo, 'a').write(ident + '\\n')\n"
    "if ident in os.environ.get('FAKE_QUEBRA', '').split(','):\n"
    "    open('quebra.txt', 'w').write('x')\n"
    "subprocess.run(['git', 'add', '-A'], check=True)\n"
    "subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t',\n"
    "                'commit', '-qm', ident], check=True)\n"
    "marca(ident, status='done', evidence='ok')\n")

VERIFY = "test ! -f quebra.txt"


def plano_de(raiz):
    return raiz / ".claude" / "programs" / "fila" / "plan.yaml"


def estado_de(raiz):
    d = raiz / ".claude" / "programs" / "fila" / "until"
    arqs = sorted(d.glob("*.estado.json"))
    return json.loads(arqs[-1].read_text()) if arqs else {}


def avisos(raiz):
    return [e for e in ledger_de(raiz)
            if e["evento"] == "hook_so_apos_reinstalar"]


def test_item_que_muda_hook_de_plugin_e_avisado_na_hora_e_no_fim():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = com_plugin(monta_repo(tmp, [item("a1"), item("a2")]))
        binv = fake_claude(tmp, TRABALHA)
        p, _ = roda(raiz, binv, plano_de(raiz), ["--for", "2h"],
                    extra_env={"FAKE_ARQUIVOS": "a1=meuplug/hooks/trava.py"})
        ev = avisos(raiz)
        check("o registro ganha hook_so_apos_reinstalar do a1",
              len(ev) == 1 and ev[0]["id"] == "a1"
              and ev[0]["arquivos"] == ["meuplug/hooks/trava.py"], str(ev))
        out = p.stdout
        i_aviso = out.find("a1 mudou hook de plugin (meuplug/hooks/trava.py)")
        i_a2 = out.find("] a2 — ")
        check("a tela avisa o hook logo depois do a1, antes do a2 começar",
              0 <= i_aviso < i_a2, out[-1500:])
        check("...e o aviso diz o que fazer",
              "bin/install.sh" in out[i_aviso:i_a2], out[i_aviso:i_a2])
        fica = {f["id"]: f["texto"]
                for f in estado_de(raiz).get("fica_com_voce", [])}
        check("o estado do run cobra a reinstalação em fica_com_voce",
              "reinstalar-plugin" in fica
              and "meuplug/hooks/trava.py" in fica["reinstalar-plugin"],
              str(fica))
        check("o resumo do fim traz a reinstalação em Fica com você",
              "- reinstalar-plugin:" in out.split("── fim")[-1], out[-1200:])


def test_hooks_fora_de_plugin_nao_avisa():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = com_plugin(monta_repo(tmp, [item("a1")]))
        binv = fake_claude(tmp, TRABALHA)
        p, _ = roda(raiz, binv, plano_de(raiz), ["--for", "2h"],
                    extra_env={"FAKE_ARQUIVOS": "a1=solto/hooks/x.py"})
        check("pasta hooks/ sem plugin.json não gera aviso",
              not avisos(raiz) and "mudou hook" not in p.stdout,
              p.stdout[-800:])
        check("...nem cobrança no fim",
              "reinstalar-plugin" not in p.stdout
              and all(f["id"] != "reinstalar-plugin" for f in
                      estado_de(raiz).get("fica_com_voce", [])),
              p.stdout[-800:])


def test_hook_que_saiu_com_o_build_vermelho_nao_e_cobrado_no_fim():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = com_plugin(monta_repo(tmp, [item("a1"), item("a2")]))
        binv = fake_claude(tmp, TRABALHA)
        p, _ = roda(raiz, binv, plano_de(raiz), ["--for", "2h",
                                                 "--verify", VERIFY],
                    extra_env={"FAKE_ARQUIVOS": "a1=meuplug/hooks/trava.py",
                               "FAKE_QUEBRA": "a1"})
        ev = avisos(raiz)
        check("o hook do item vermelho não fica na branch, então não avisa",
              not ev, str(ev))
        check("...e o fim não cobra reinstalação",
              "reinstalar-plugin" not in p.stdout, p.stdout[-1200:])


# 1ª tentativa do a1: commita o hook e sai `pending` (commit é progresso, o
# supervisor avisa o hook). 2ª: commita `quebra.txt` e fecha `done`; o build
# vermelho leva os commits das DUAS tentativas para a lateral. Depois disso o
# a1 sai `blocked` para o run acabar.
AVISA_E_SAI = (
    "import subprocess\n"
    "ident = primeiro_pendente()\n"
    "cont = os.environ['FAKE_CHAMADAS'] + '.vez'\n"
    "vez = (int(open(cont).read()) if os.path.exists(cont) else 0) + 1\n"
    "open(cont, 'w').write(str(vez))\n"
    "def commita(alvo):\n"
    "    open(alvo, 'a').write(str(vez) + '\\n')\n"
    "    subprocess.run(['git', 'add', '-A'], check=True)\n"
    "    subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t',\n"
    "                    'commit', '-qm', f'{ident} {vez}'], check=True)\n"
    "if vez == 1:\n"
    "    commita('meuplug/hooks/trava.py')\n"
    "elif vez == 2:\n"
    "    commita('quebra.txt')\n"
    "    marca(ident, status='done', evidence='ok')\n"
    "else:\n"
    "    marca(ident, status='blocked', evidence='fim do teste')\n")


def test_hook_avisado_que_saiu_depois_nao_e_cobrado_no_fim():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = com_plugin(monta_repo(tmp, [item("a1")]))
        binv = fake_claude(tmp, AVISA_E_SAI)
        p, _ = roda(raiz, binv, plano_de(raiz), ["--for", "2h",
                                                 "--verify", VERIFY])
        check("a 1ª tentativa deixou o hook na branch e a tela avisou",
              len(avisos(raiz)) == 1, str(avisos(raiz)))
        check("o build vermelho da 2ª levou o hook para a lateral",
              "vermelho-a1" in p.stdout, p.stdout[-1500:])
        check("o fim recalcula e não cobra o hook que saiu",
              "reinstalar-plugin" not in p.stdout
              and all(f["id"] != "reinstalar-plugin" for f in
                      estado_de(raiz).get("fica_com_voce", [])),
              p.stdout[-1500:])


# Tentativas por item, como o TENTA de test_cepa_until_branch_da_noite: a
# tentativa n commita `<id>-t<n>.txt`; FAKE_HOOK1 põe o hook na 1ª tentativa,
# FAKE_HOOK2 na 2ª; FAKE_QUEBRA quebra o build da 2ª em diante; FAKE_DUAS
# deixa a 1ª `pending` (e FAKE_ADIA a joga para o fim da fila).
TENTA = (
    "import subprocess\n"
    "ident = primeiro_pendente()\n"
    "lista = lambda k: os.environ.get(k, '').split(',')\n"
    "cont = os.environ['FAKE_CHAMADAS'] + '.n.' + ident\n"
    "n = int(open(cont).read()) + 1 if os.path.exists(cont) else 1\n"
    "open(cont, 'w').write(str(n))\n"
    "open(f'{ident}-t{n}.txt', 'w').write('x')\n"
    "if ident in lista(f'FAKE_HOOK{n}'):\n"
    "    open('meuplug/hooks/trava.py', 'a').write(f'{ident}-t{n}\\n')\n"
    "if n >= 2 and ident in lista('FAKE_QUEBRA'):\n"
    "    open('quebra.txt', 'w').write('x')\n"
    "subprocess.run(['git', 'add', '-A'], check=True)\n"
    "subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t',\n"
    "                'commit', '-qm', f'{ident}-t{n}'], check=True)\n"
    "if ident not in lista('FAKE_DUAS') or n >= 2:\n"
    "    marca(ident, status='done', evidence='ok')\n"
    "elif ident in lista('FAKE_ADIA'):\n"
    "    p = carrega()\n"
    "    p['items'].sort(key=lambda it: it['id'] == ident)\n"
    "    grava(p)\n")


def test_hook_do_item_que_encerra_o_run_por_dentro_do_laco_e_avisado():
    """O aviso do topo do laço não vê o item que sai por um `break` no corpo.
    Aqui o a1 muda o hook na 2ª tentativa, o build fica vermelho e o reset
    apagaria o a2 do meio: o run para em `verify-vermelho` com o hook na
    branch da noite, e só o aviso antes do `run_end` o pega."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = com_plugin(monta_repo(tmp, [item("a1"), item("a2")]))
        binv = fake_claude(tmp, TENTA)
        p, _ = roda(raiz, binv, plano_de(raiz),
                    ["--for", "2h", "--verify", VERIFY],
                    extra_env={"FAKE_DUAS": "a1", "FAKE_ADIA": "a1",
                               "FAKE_QUEBRA": "a1", "FAKE_HOOK2": "a1"})
        fim = [e for e in ledger_de(raiz) if e["evento"] == "run_end"]
        check("o run para por dentro do laço (verify-vermelho)",
              fim and fim[0]["motivo"] == "verify-vermelho", str(fim))
        ev = avisos(raiz)
        check("o registro ganha hook_so_apos_reinstalar do a1",
              [e["id"] for e in ev] == ["a1"], str(ev))
        antes_do_fim = p.stdout.split("── fim")[0]
        check("a tela avisa antes do resumo do fim",
              "a1 mudou hook de plugin" in antes_do_fim, antes_do_fim[-1200:])


def test_hook_avisado_que_saiu_nao_e_cobrado_num_run_com_o_que_aterrissar():
    """Com `acoes` vazio a cobrança do fim já sai vazia, e o caso acima de
    hook que saiu não distingue recalcular do diff de reaproveitar a lista de
    avisos. Aqui o a0 fica na branch (há o que aterrissar) e o hook do a1,
    avisado na 1ª tentativa, sai com o build vermelho da 2ª."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = com_plugin(monta_repo(tmp, [item("a0"), item("a1")]))
        binv = fake_claude(tmp, TENTA)
        p, _ = roda(raiz, binv, plano_de(raiz),
                    ["--for", "2h", "--verify", VERIFY],
                    extra_env={"FAKE_DUAS": "a1", "FAKE_QUEBRA": "a1",
                               "FAKE_HOOK1": "a1"})
        check("o hook da 1ª tentativa do a1 foi avisado",
              [e["id"] for e in avisos(raiz)] == ["a1"], str(avisos(raiz)))
        check("há o que aterrissar (o a0 ficou na branch)",
              "aterrissar" in p.stdout.split("── fim")[-1], p.stdout[-1200:])
        check("o fim não cobra o hook que saiu",
              "reinstalar-plugin" not in p.stdout
              and all(f["id"] != "reinstalar-plugin" for f in
                      estado_de(raiz).get("fica_com_voce", [])),
              p.stdout[-1500:])


def main():
    print("cepa-until — hook que só vale depois de reinstalar\n")
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            print(f"{nome}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
