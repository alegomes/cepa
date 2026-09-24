#!/usr/bin/env python3
"""cepa-until — a branch da noite e o build completo do supervisor.

O run de 2026-09-23 no WEGO entregou 5 cards em 25 rodadas: cada subprocesso
abriu a própria worktree a partir de `origin/main`, nada mesclou, e os cards
seguintes travaram porque o antecessor só existia numa branch solta. A 2308
ainda fechou `done` com o build completo rodado antes do último refactor.

Os casos abaixo fixam o conserto:
  - o supervisor cria `until/<run>` numa worktree e roda cada subprocesso nela;
  - o clone principal não sai da branch em que estava;
  - o 2º card enxerga o commit do 1º;
  - depois de cada `done` o supervisor roda o build completo; vermelho tira os
    commits do item da branch da noite (sem perdê-los) e marca o item
    `blocked`;
  - `done` sem commit na branch da noite é apontado no registro;
  - repo sem build conhecido não começa sem `--verify` ou `--sem-verify`;
  - o resumo separa entregues de travados;
  - a análise do fim chama `/common:until-review` e grava `<run>.review.md`.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    FAILURES, check, fake_claude, item, ledger_de, monta_repo, roda)


# Um `claude` falso que trabalha como o drain-plan com `--na-branch`: commita
# no diretório em que acordou. Grava o conteúdo que viu de `a1.txt` para o
# teste saber se o 2º card enxergou o 1º.
TRABALHA = (
    "import subprocess\n"
    "ident = primeiro_pendente()\n"
    "viu = os.path.exists('a1.txt')\n"
    "open(ident + '.txt', 'w').write('feito')\n"
    "if ident in os.environ.get('FAKE_QUEBRA', '').split(','):\n"
    "    open('quebra.txt', 'w').write('x')\n"
    "subprocess.run(['git', 'add', '-A'], check=True)\n"
    "subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t',\n"
    "                'commit', '-qm', ident], check=True)\n"
    "with open(os.environ['FAKE_CHAMADAS'] + '.cwd', 'a') as f:\n"
    "    f.write(json.dumps({'id': ident, 'cwd': os.getcwd(), 'viu_a1': viu})"
    " + '\\n')\n"
    "marca(ident, status='done', evidence='ok')\n")

# Build completo de mentira: vermelho quando o item deixou `quebra.txt`.
VERIFY = "test ! -f quebra.txt"


def cwds(raiz):
    f = Path(raiz).parent / "chamadas.jsonl.cwd"
    return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


def plano_de(raiz):
    return raiz / ".claude" / "programs" / "fila" / "plan.yaml"


def status(raiz, ident):
    for it in yaml.safe_load(plano_de(raiz).read_text())["items"]:
        if it["id"] == ident:
            return it
    return None


def git(raiz, *args):
    return subprocess.run(["git", *args], cwd=raiz, capture_output=True,
                          text=True).stdout.strip()


def test_subprocesso_roda_na_branch_da_noite_e_o_clone_fica_parado():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        branch_antes = git(raiz, "rev-parse", "--abbrev-ref", "HEAD")
        binv = fake_claude(tmp, TRABALHA)
        p, chamadas = roda(raiz, binv, plano_de(raiz),
                           ["--for", "2h", "--verify", VERIFY])
        inicio = [e for e in ledger_de(raiz) if e["evento"] == "run_start"][0]
        branch = inicio.get("branch") or ""
        check("a largada cria uma branch until/<run>",
              branch.startswith("until/"), str(inicio))
        vistos = cwds(raiz)
        check("cada subprocesso acorda na worktree da noite",
              len(vistos) == 2 and all(Path(v["cwd"]).resolve()
                                       == Path(inicio["arvore"]).resolve()
                                       for v in vistos), str(vistos))
        check("...que fica fora do clone",
              not Path(inicio["arvore"]).resolve().is_relative_to(raiz.resolve()),
              inicio["arvore"])
        check("o pedido ao claude leva --na-branch",
              chamadas and all(f"--na-branch {branch}" in c[1] for c in chamadas),
              str(chamadas))
        check("o 2º card enxerga o commit do 1º",
              len(vistos) == 2 and vistos[1]["viu_a1"], str(vistos))
        check("o clone principal não sai da branch em que estava",
              git(raiz, "rev-parse", "--abbrev-ref", "HEAD") == branch_antes)
        check("a branch da noite tem os 2 commits",
              git(raiz, "rev-list", "--count", f"{inicio['base']}..{branch}")
              == "2", p.stdout[-600:])
        check("o resumo diz como aterrissar",
              f"git merge {branch}" in p.stdout, p.stdout[-600:])


def test_build_vermelho_tira_o_item_da_branch_sem_perder_os_commits():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2"), item("a3")])
        binv = fake_claude(tmp, TRABALHA)
        p, _ = roda(raiz, binv, plano_de(raiz),
                    ["--for", "2h", "--verify", VERIFY],
                    extra_env={"FAKE_QUEBRA": "a2"})
        ev = ledger_de(raiz)
        inicio = [e for e in ev if e["evento"] == "run_start"][0]
        branch = inicio["branch"]
        check("o item com build vermelho vira blocked",
              status(raiz, "a2")["status"] == "blocked", str(status(raiz, "a2")))
        check("...e a evidência diz onde estão os commits",
              "vermelho-a2" in (status(raiz, "a2").get("evidence") or ""),
              str(status(raiz, "a2")))
        lateral = f"{branch}-vermelho-a2"
        check("os commits do item ficam na branch lateral",
              git(raiz, "log", "-1", "--format=%s", lateral) == "a2")
        log_noite = git(raiz, "log", "--format=%s", branch).splitlines()
        check("a branch da noite não tem o commit vermelho",
              "a2" not in log_noite and "a1" in log_noite and "a3" in log_noite,
              str(log_noite))
        vistos = {v["id"]: v for v in cwds(raiz)}
        check("o card seguinte começa sem o código vermelho",
              "a3" in vistos, str(vistos))
        fim = [e for e in ev if e["evento"] == "run_end"][0]
        check("o registro conta entregues, travados e vermelhos",
              (fim.get("entregues"), fim.get("travados"),
               fim.get("verify_vermelho")) == (2, 1, 1), str(fim))
        check("o resumo separa entregues de travados",
              "2 entregue(s) · 1 travado(s)" in p.stdout, p.stdout[-800:])


def test_done_sem_commit_na_branch_da_noite_e_apontado():
    """O caso de 23/09 visto por dentro: o card fecha `done`, mas o trabalho
    foi para outra branch. O supervisor não tem como buscá-lo; tem como dizer."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        p, _ = roda(raiz, binv, plano_de(raiz),
                    ["--for", "2h", "--verify", VERIFY])
        ev = ledger_de(raiz)
        check("o registro marca done_sem_commit",
              any(e["evento"] == "done_sem_commit" and e["id"] == "a1"
                  for e in ev), str(ev))
        check("...e o resumo aponta", "sem commit na branch da noite" in p.stdout,
              p.stdout[-600:])
        check("sem nenhum commit, a branch da noite some",
              "removi" in p.stdout
              and not git(raiz, "branch", "--list", "until/*"), p.stdout[-400:])


def test_sobra_nao_commitada_nao_passa_para_o_proximo_item():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        corpo = ("ident = primeiro_pendente()\n"
                 "suja = os.path.exists('sobra.txt')\n"
                 "with open(os.environ['FAKE_CHAMADAS'] + '.cwd', 'a') as f:\n"
                 "    f.write(json.dumps({'id': ident, 'cwd': os.getcwd(),"
                 " 'viu_a1': suja}) + '\\n')\n"
                 "open('sobra.txt', 'w').write('x')\n"
                 "marca(ident, status='blocked', evidence='travou')\n")
        binv = fake_claude(tmp, corpo)
        roda(raiz, binv, plano_de(raiz), ["--for", "2h"])
        vistos = cwds(raiz)
        check("o 2º item não acorda com a sobra do 1º",
              len(vistos) == 2 and not vistos[1]["viu_a1"], str(vistos))
        ev = ledger_de(raiz)
        guardadas = [e for e in ev if e["evento"] == "sobra_guardada"]
        check("a sobra fica num stash registrado",
              len(guardadas) == 2 and all(e.get("stash") for e in guardadas),
              str(guardadas))
        for e in guardadas:
            subprocess.run(["git", "stash", "drop", e["stash"]], cwd=raiz,
                           capture_output=True)


def test_repo_sem_build_conhecido_nao_comeca_sem_dizer_qual():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, TRABALHA)
        env = dict(os.environ, PATH=f"{binv}:{os.environ['PATH']}")
        p = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[1] / "common"
                                 / "bin" / "cepa-until"),
             "fila", "--repo", str(raiz), "--for", "2h", "--sem-analise"],
            capture_output=True, text=True, timeout=60,
            env={**env, "FAKE_PLANO": str(plano_de(raiz)),
                 "FAKE_CHAMADAS": str(Path(tmp) / "chamadas.jsonl"),
                 "CEPA_WORKTREE_HOME": str(Path(tmp) / "worktrees")})
        check("sem mvnw/gradlew e sem flag, recusa", p.returncode == 2,
              f"saiu {p.returncode}: {p.stderr[-300:]}")
        check("...e diz as duas saídas",
              "--verify" in p.stderr and "--sem-verify" in p.stderr, p.stderr)
        check("...sem ter criado branch", not git(raiz, "branch", "--list",
                                                  "until/*"))


def test_mvnw_na_raiz_vira_o_build_padrao():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        (raiz / "mvnw").write_text("#!/bin/sh\nexit 0\n")
        subprocess.run(["git", "add", "-A"], cwd=raiz)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "mvnw"], cwd=raiz)
        binv = fake_claude(tmp, TRABALHA)
        p, _ = roda(raiz, binv, plano_de(raiz), ["--for", "2h", "--dry-run",
                                                  "--verify", "x"])
        # --verify explícito ganha; sem ele, o banner mostra o mvnw.
        check("--verify explícito ganha do mvnw", "x depois de cada item" in
              p.stdout, p.stdout)
        env_args = ["--for", "2h", "--dry-run"]
        p = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[1] / "common"
                                 / "bin" / "cepa-until"),
             "fila", "--repo", str(raiz), *env_args],
            capture_output=True, text=True, timeout=60,
            env=dict(os.environ, PATH=f"{binv}:{os.environ['PATH']}",
                     FAKE_PLANO="x", FAKE_CHAMADAS=str(Path(tmp) / "c.jsonl")))
        check("sem --verify, o banner mostra ./mvnw -B clean verify",
              "./mvnw -B clean verify" in p.stdout, p.stdout + p.stderr)


def test_analise_do_fim_grava_o_review_ao_lado_do_registro():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        corpo = ("if ARGS and ARGS[1].startswith('/common:until-review'):\n"
                 "    print('RELATORIO DA NOITE')\n"
                 "    sys.exit(0)\n"
                 "marca(primeiro_pendente(), status='blocked', evidence='x')\n")
        binv = fake_claude(tmp, corpo)
        p, chamadas = roda(raiz, binv, plano_de(raiz),
                           ["--for", "2h", "--com-analise"])
        pedidos = [c[1] for c in chamadas]
        check("a última chamada é o /common:until-review do registro",
              pedidos and pedidos[-1].startswith("/common:until-review ")
              and pedidos[-1].endswith(".jsonl"), str(pedidos))
        revs = list((raiz / ".claude" / "programs" / "fila" / "until")
                    .glob("*.review.md"))
        check("o review.md fica ao lado do registro",
              len(revs) == 1 and "RELATORIO DA NOITE" in revs[0].read_text(),
              str(revs))
        ev = ledger_de(raiz)
        check("o registro diz que a análise foi feita",
              any(e["evento"] == "analise" and e["feita"] for e in ev), str(ev))


def test_run_parado_pela_cota_nao_roda_a_analise():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        corpo = ("if ARGS and ARGS[1].startswith('/common:until-review'):\n"
                 "    sys.exit(0)\n"
                 "print(json.dumps({'type': 'result', 'result': "
                 "\"You've hit your session limit\"}))\n")
        binv = fake_claude(tmp, corpo)
        p, chamadas = roda(raiz, binv, plano_de(raiz),
                           ["--for", "2h", "--com-analise"])
        fim = [e for e in ledger_de(raiz) if e["evento"] == "run_end"][0]
        check("o run parou pela cota", fim["motivo"] == "limite-de-uso", str(fim))
        check("...e a análise não foi chamada",
              not any(c[1].startswith("/common:until-review") for c in chamadas),
              str(chamadas))
        check("...mas o resumo diz como rodá-la depois",
              "/common:until-review" in p.stdout, p.stdout[-400:])


def main():
    print("cepa-until — branch da noite\n")
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
