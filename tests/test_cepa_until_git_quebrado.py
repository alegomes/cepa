#!/usr/bin/env python3
"""cepa-until — git que não responde não é troca de branch.

O run WEGO de 25/09/2026 parou às 00:25 com `branch-mudou` ("agora estamos em
`?`") e 5h40 de prazo sobrando. Ninguém trocou de branch: a pasta
`.git/worktrees/`, que liga a worktree da noite ao clone, sumiu, e o
`branch_atual` devolvia `"?"` para qualquer erro do git.

Os casos abaixo fixam o conserto:
  - ligação apagada com a worktree no disco: o supervisor refaz a ligação e a
    noite segue, com o próximo commit na branch da noite;
  - ligação apagada e reparo impossível (a branch sumiu do clone): o run para
    com `git-quebrado`, nomeando o erro do git, e não com `branch-mudou`.

Rode com `python3 tests/test_cepa_until_git_quebrado.py`.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    FAILURES, check, fake_claude, item, ledger_de, monta_repo, roda)


# Commita o item na worktree em que acordou e, no `a1`, apaga a pasta
# `<clone>/.git/worktrees` inteira, como aconteceu em 25/09. Com
# FAKE_APAGA_BRANCH, apaga também a branch da noite no clone, o que deixa o
# reparo sem ter para onde apontar.
APAGA_LIGACAO = (
    "import subprocess, shutil\n"
    "ident = primeiro_pendente()\n"
    "if ident == 'a2':\n"
    "    open(os.environ['FAKE_CHAMADAS'] + '.status', 'w').write(\n"
    "        subprocess.run(['git', 'status', '--porcelain'],\n"
    "                       capture_output=True, text=True).stdout)\n"
    "open(ident + '.txt', 'w').write('feito')\n"
    "subprocess.run(['git', 'add', '-A'], check=True)\n"
    "subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t',\n"
    "                'commit', '-qm', ident], check=True)\n"
    "marca(ident, status='done', evidence='ok')\n"
    "if ident == 'a1':\n"
    "    comum = subprocess.run(['git', 'rev-parse', '--path-format=absolute',\n"
    "                            '--git-common-dir'], capture_output=True,\n"
    "                           text=True, check=True).stdout.strip()\n"
    "    branch = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'],\n"
    "                            capture_output=True, text=True,\n"
    "                            check=True).stdout.strip()\n"
    "    shutil.rmtree(os.path.join(comum, 'worktrees'))\n"
    "    if os.environ.get('FAKE_APAGA_BRANCH'):\n"
    "        subprocess.run(['git', '--git-dir', comum, 'branch', '-D', branch],\n"
    "                       check=True, capture_output=True)\n")


def plano_de(raiz):
    return raiz / ".claude" / "programs" / "fila" / "plan.yaml"


def status(raiz, ident):
    for it in yaml.safe_load(plano_de(raiz).read_text())["items"]:
        if it["id"] == ident:
            return it["status"]
    return None


def git(raiz, *args):
    return subprocess.run(["git", *args], cwd=raiz, capture_output=True,
                          text=True).stdout.strip()


def test_ligacao_apagada_e_refeita_e_a_noite_segue():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, APAGA_LIGACAO)
        p, chamadas = roda(raiz, binv, plano_de(raiz), ["--for", "2h"])
        ev = ledger_de(raiz)
        fim = [e for e in ev if e.get("evento") == "run_end"][0]
        check("o run não para por `branch-mudou` nem por `git-quebrado`",
              fim["motivo"] not in ("branch-mudou", "git-quebrado"), str(fim))
        check("o 2º item roda depois da ligação apagada", len(chamadas) == 2,
              f"disparou {len(chamadas)}x · {p.stdout[-600:]}")
        check("e fecha `done`", status(raiz, "a2") == "done")
        reparos = [e for e in ev if e.get("evento") == "git_reparo"]
        check("o registro diz que reparou e qual erro o git deu",
              len(reparos) == 1 and reparos[0]["reparou"]
              and "not a git repository" in reparos[0]["erro"], str(reparos))
        branch = [e for e in ev if e.get("evento") == "run_start"][0]["branch"]
        log = git(raiz, "log", "--format=%s", branch)
        check("o commit do 2º item está na branch da noite, em cima do 1º",
              log.splitlines()[:2] == ["a2", "a1"], log)
        check("o clone voltou a listar a worktree da noite",
              branch in git(raiz, "worktree", "list"),
              git(raiz, "worktree", "list"))
        # O índice morava na pasta apagada. Sem refazê-lo, o 2º item acordaria
        # com todos os arquivos como apagados no índice e soltos na árvore.
        visto = Path(tmp) / "chamadas.jsonl.status"
        check("o 2º item acorda com a worktree limpa, índice refeito",
              visto.exists() and visto.read_text() == "",
              visto.read_text() if visto.exists() else "não gravou")


def test_reparo_impossivel_para_como_git_quebrado_e_nao_branch_mudou():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, APAGA_LIGACAO)
        p, chamadas = roda(raiz, binv, plano_de(raiz), ["--for", "2h"],
                           extra_env={"FAKE_APAGA_BRANCH": "1"})
        fim = [e for e in ledger_de(raiz) if e.get("evento") == "run_end"][0]
        check("o motivo é `git-quebrado`", fim["motivo"] == "git-quebrado",
              str(fim))
        detalhe = fim.get("detalhe") or ""
        check("o detalhe traz o erro do git e o que impediu o reparo",
              "not a git repository" in detalhe and "não existe mais" in detalhe,
              detalhe)
        check("o detalhe não acusa troca de branch",
              "`?`" not in detalhe and "trocou de branch no meio" not in detalhe,
              detalhe)
        check("o 2º item não é disparado", len(chamadas) == 1,
              f"disparou {len(chamadas)}x")
        check("e segue `pending`", status(raiz, "a2") == "pending")
        arvore = [e for e in ledger_de(raiz)
                  if e.get("evento") == "run_start"][0]["arvore"]
        check("a worktree da noite continua no disco com o trabalho",
              (Path(arvore) / "a1.txt").exists())


def _cepa_until():
    from importlib.machinery import SourceFileLoader
    from importlib.util import module_from_spec, spec_from_loader
    from test_cepa_until import CEPA_UNTIL
    loader = SourceFileLoader("cepa_until", str(CEPA_UNTIL))
    mod = module_from_spec(spec_from_loader("cepa_until", loader))
    loader.exec_module(mod)
    return mod


def test_reparo_nao_escreve_fora_da_pasta_de_worktrees_do_clone():
    """O `.git` da worktree diz onde a ligação mora. Se ele aponta para fora de
    `<clone>/.git/worktrees/`, o reparo recusa em vez de criar pasta onde o
    arquivo mandar."""
    cu = _cepa_until()
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        arvore = Path(tmp) / "wt"
        subprocess.run(["git", "worktree", "add", "-q", "-b", "until/x",
                        str(arvore), "HEAD"], cwd=raiz, check=True)
        fora = Path(tmp) / "fora" / "wt"
        (arvore / ".git").write_text(f"gitdir: {fora}\n")
        falha = cu.repara_ligacao(raiz, arvore, "until/x")
        check("recusa ligação fora de .git/worktrees",
              falha is not None and "fora de" in falha, str(falha))
        check("e não cria nada lá", not fora.parent.exists())


def main():
    print("cepa-until — git quebrado na worktree da noite\n")
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
