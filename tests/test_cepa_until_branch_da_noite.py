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
              f"cepa-until aterrissar fila/{branch.split('/', 1)[1]}"
              in p.stdout, p.stdout[-600:])


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
        # Revisão 3: o a2 volta a `pending` na 1ª volta vermelha e só vira
        # `blocked` na 2ª, então são dois vermelhos para um travado.
        check("o registro conta entregues, travados e vermelhos",
              (fim.get("entregues"), fim.get("travados"),
               fim.get("verify_vermelho")) == (2, 1, 2), str(fim))
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
        check("...e nomeia a suíte que teria bastado",
              "tests/run-all.sh" in p.stderr, p.stderr)
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


def _roda_sem_flag_de_verify(tmp, raiz, binv):
    """Sem `--verify` nem `--sem-verify`: quem escolhe é o `cepa-until`."""
    return subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "common"
                             / "bin" / "cepa-until"),
         "fila", "--repo", str(raiz), "--for", "2h", "--sem-analise"],
        capture_output=True, text=True, timeout=120,
        env=dict(os.environ, PATH=f"{binv}:{os.environ['PATH']}",
                 FAKE_PLANO=str(plano_de(raiz)),
                 FAKE_CHAMADAS=str(Path(tmp) / "chamadas.jsonl"),
                 CEPA_WORKTREE_HOME=str(Path(tmp) / "worktrees"),
                 # longe do ledger real do /common:metrics
                 CEPA_TELEMETRY_DIR=str(Path(tmp) / "telemetria")))


def _commita(raiz, msg):
    subprocess.run(["git", "add", "-A"], cwd=raiz)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", msg], cwd=raiz)


def test_no_build_com_suite_roda_a_suite():
    # O cepa tem `.claude/no-build` (sem build para o gate-advance) e
    # `tests/run-all.sh`. O run 2026-09-26-2203 leu o primeiro como "sem
    # verify" e 18 itens fecharam sem a suíte inteira rodar.
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        marca_suite = Path(tmp) / "suite-rodou"
        (raiz / ".claude" / "no-build").write_text("# sem build\n")
        (raiz / "tests").mkdir(exist_ok=True)
        suite = raiz / "tests" / "run-all.sh"
        suite.write_text(f"#!/bin/sh\necho x >> {marca_suite}\nexit 0\n")
        suite.chmod(0o755)
        _commita(raiz, "no-build + suite")
        binv = fake_claude(tmp, TRABALHA)
        p = _roda_sem_flag_de_verify(tmp, raiz, binv)
        inicio = [e for e in ledger_de(raiz) if e["evento"] == "run_start"]
        check("com no-build e tests/run-all.sh, o run começa",
              p.returncode == 0 and inicio, f"saiu {p.returncode}: {p.stderr[-300:]}")
        check("...e o run_start grava a suíte como verify, não null",
              inicio and inicio[0].get("verify") == "tests/run-all.sh",
              str(inicio))
        check("...e a suíte rodou depois do item done", marca_suite.exists(),
              p.stdout[-400:])


def test_suite_sem_no_build_vira_o_verify():
    # Repo sem mvnw/gradlew e sem `.claude/no-build`, só com a suíte: ela é o
    # build completo, em vez da recusa "não sei o build deste repo".
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        marca_suite = Path(tmp) / "suite-rodou"
        (raiz / "tests").mkdir(exist_ok=True)
        suite = raiz / "tests" / "run-all.sh"
        suite.write_text(f"#!/bin/sh\necho x >> {marca_suite}\nexit 0\n")
        suite.chmod(0o755)
        _commita(raiz, "suite")
        binv = fake_claude(tmp, TRABALHA)
        p = _roda_sem_flag_de_verify(tmp, raiz, binv)
        inicio = [e for e in ledger_de(raiz) if e["evento"] == "run_start"]
        check("só com tests/run-all.sh, o run começa com a suíte como verify",
              p.returncode == 0 and inicio
              and inicio[0].get("verify") == "tests/run-all.sh",
              f"saiu {p.returncode}: {inicio} {p.stderr[-300:]}")
        check("...e a suíte rodou", marca_suite.exists(), p.stdout[-400:])


def test_no_build_sem_suite_continua_dispensando():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        (raiz / ".claude" / "no-build").write_text("# sem build\n")
        _commita(raiz, "no-build")
        binv = fake_claude(tmp, TRABALHA)
        p = _roda_sem_flag_de_verify(tmp, raiz, binv)
        inicio = [e for e in ledger_de(raiz) if e["evento"] == "run_start"]
        check("só com no-build, o run começa sem verify",
              p.returncode == 0 and inicio and inicio[0].get("verify") is None,
              f"saiu {p.returncode}: {inicio} {p.stderr[-300:]}")


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


# ── todas as tentativas vão para a lateral (Revisão 3, passo 1; C4) ─────────

# Um `claude` falso que precisa de mais de uma tentativa. Cada chamada commita
# `<id>-t<n>`. Os itens em FAKE_DUAS só fecham na 2ª; os em FAKE_QUEBRA deixam
# o build vermelho na 2ª; os em FAKE_ADIA vão para o fim da fila depois da 1ª
# (para outro item fechar no meio); os em FAKE_PARA não fazem nada da 2ª em
# diante (tentativa sem progresso).
TENTA = (
    "import subprocess\n"
    "ident = primeiro_pendente()\n"
    "lista = lambda k: os.environ.get(k, '').split(',')\n"
    "cont = os.environ['FAKE_CHAMADAS'] + '.n.' + ident\n"
    "n = int(open(cont).read()) + 1 if os.path.exists(cont) else 1\n"
    "open(cont, 'w').write(str(n))\n"
    "if n >= 2 and ident in lista('FAKE_PARA'):\n"
    "    sys.exit(0)\n"
    "open(f'{ident}-t{n}.txt', 'w').write('x')\n"
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


def test_build_vermelho_leva_os_commits_de_todas_as_tentativas():
    """O WEGO-2320 levou duas tentativas: a lateral ficou com os 2 commits da
    segunda e os 9 da primeira ficaram na branch da noite, sem nunca passar
    pelo build do supervisor."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a0"), item("a1"), item("a2")])
        binv = fake_claude(tmp, TENTA)
        p, _ = roda(raiz, binv, plano_de(raiz),
                    ["--for", "2h", "--verify", VERIFY],
                    extra_env={"FAKE_DUAS": "a1", "FAKE_QUEBRA": "a1"})
        branch = [e for e in ledger_de(raiz)
                  if e["evento"] == "run_start"][0]["branch"]
        lateral = git(raiz, "log", "--format=%s",
                      f"{branch}-vermelho-a1").splitlines()
        check("a lateral tem os commits das duas tentativas",
              "a1-t1" in lateral and "a1-t2" in lateral, str(lateral))
        noite = git(raiz, "log", "--format=%s", branch).splitlines()
        check("a branch da noite não tem nenhum commit do item vermelho",
              "a1-t1" not in noite and "a1-t2" not in noite, str(noite))
        check("...e guarda os itens verdes de antes e de depois",
              "a0-t1" in noite and "a2-t1" in noite, str(noite))


def test_outro_done_no_meio_das_tentativas_para_em_vez_de_resetar():
    """O reset até o começo da 1ª tentativa apagaria o item que fechou verde no
    meio. A C4 manda parar e avisar."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, TENTA)
        p, _ = roda(raiz, binv, plano_de(raiz),
                    ["--for", "2h", "--verify", VERIFY],
                    extra_env={"FAKE_DUAS": "a1", "FAKE_QUEBRA": "a1",
                               "FAKE_ADIA": "a1"})
        ev = ledger_de(raiz)
        branch = [e for e in ev if e["evento"] == "run_start"][0]["branch"]
        noite = git(raiz, "log", "--format=%s", branch).splitlines()
        check("o item verde do meio continua na branch da noite",
              "a2-t1" in noite, str(noite))
        fim = [e for e in ev if e["evento"] == "run_end"][0]
        check("o run para no vermelho", fim["motivo"] == "verify-vermelho",
              str(fim))
        check("...e o aviso nomeia o item do meio",
              "a2" in (fim.get("detalhe") or ""), str(fim))


def test_item_esgotado_leva_os_commits_das_tentativas_para_a_lateral():
    """A 1ª tentativa commitou sem fechar e a 2ª não andou: o teto marca
    `blocked`, e os commits da 1ª ficavam na branch da noite sem build."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, TENTA)
        p, _ = roda(raiz, binv, plano_de(raiz),
                    ["--for", "2h", "--verify", VERIFY],
                    extra_env={"FAKE_DUAS": "a1", "FAKE_PARA": "a1"})
        branch = [e for e in ledger_de(raiz)
                  if e["evento"] == "run_start"][0]["branch"]
        check("o item vira blocked", status(raiz, "a1")["status"] == "blocked",
              str(status(raiz, "a1")))
        noite = git(raiz, "log", "--format=%s", branch).splitlines()
        check("a branch da noite não tem o commit do item parado",
              "a1-t1" not in noite and "a2-t1" in noite, str(noite))
        laterais = git(raiz, "branch", "--list", f"{branch}-*-a1").split()
        check("o commit fica numa lateral",
              laterais and "a1-t1" in git(raiz, "log", "--format=%s",
                                          laterais[-1]), str(laterais))
        check("...que a evidência nomeia",
              laterais and laterais[-1] in (status(raiz, "a1").get("evidence")
                                            or ""), str(status(raiz, "a1")))


# ── o vermelho se resolve sem o dono (Revisão 3, passos 4a, 4b, 4d, 4e) ─────

# Um `claude` falso que, a cada chamada, anota a `evidence` que o item tinha ao
# ser pego: é o recado que o agente veria no `cepa-plan start`.
TRABALHA_E_LE = TRABALHA.replace(
    "ident = primeiro_pendente()\n",
    "ident = primeiro_pendente()\n"
    "_ev = [it.get('evidence') for it in carrega()['items'] if it['id'] == ident][0]\n"
    "with open(os.environ['FAKE_CHAMADAS'] + '.recado', 'a') as f:\n"
    "    f.write(json.dumps({'id': ident, 'evidence': _ev}) + '\\n')\n", 1)

SEMPRE_VERMELHO = "false"


def recados(raiz):
    f = Path(raiz).parent / "chamadas.jsonl.recado"
    return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


def telemetria(dirt):
    ev = []
    for f in Path(dirt).glob("*.jsonl"):
        ev += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return ev


def test_4a_segundo_build_verde_fecha_done_e_grava_a_instabilidade():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, TRABALHA)
        cont = Path(tmp) / "n-verify"
        # vermelho na 1ª chamada, verde da 2ª em diante
        verify = (f"n=$(cat {cont} 2>/dev/null || echo 0); "
                  f"echo $((n+1)) > {cont}; [ $n -ge 1 ]")
        tele = Path(tmp) / "tele"
        p, _ = roda(raiz, binv, plano_de(raiz),
                    ["--for", "2h", "--verify", verify],
                    extra_env={"CEPA_TELEMETRY_DIR": str(tele)})
        check("o item fecha done", status(raiz, "a1")["status"] == "done",
              str(status(raiz, "a1")) + p.stdout[-600:])
        ev = ledger_de(raiz)
        check("o registro grava verify_repetido_verde",
              any(e["evento"] == "verify_repetido_verde" and e["id"] == "a1"
                  for e in ev), str(ev))
        t = [e for e in telemetria(tele) if e.get("event") == "build_instavel"]
        check("a telemetria grava build_instavel com card e run",
              len(t) == 1 and t[0].get("card") == "a1" and t[0].get("run"),
              str(telemetria(tele)))
        branch = [e for e in ev if e["evento"] == "run_start"][0]["branch"]
        check("o commit fica na branch da noite",
              "a1" in git(raiz, "log", "--format=%s", branch).splitlines())


def test_4b_volta_vermelha_devolve_o_item_a_pending_com_recado():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, TRABALHA_E_LE)
        p, _ = roda(raiz, binv, plano_de(raiz),
                    ["--for", "2h", "--verify", SEMPRE_VERMELHO,
                     "--max-falhas", "5"])
        ev = ledger_de(raiz)
        branch = [e for e in ev if e["evento"] == "run_start"][0]["branch"]
        vistos = recados(raiz)
        check("o item volta a ser executado depois da 1ª volta",
              len(vistos) >= 2, str(vistos) + p.stdout[-800:])
        recado = (vistos[1]["evidence"] or "") if len(vistos) >= 2 else ""
        check("...como pending, com a lateral no recado",
              f"{branch}-vermelho-a1" in recado, recado)
        check("...o motivo e o número da volta",
              "saiu 1" in recado and "volta 1" in recado, recado)
        check("...e que desligar teste não conserta",
              "desabilitar" in recado.lower(), recado)
        check("o registro grava volta_vermelha",
              any(e["evento"] == "volta_vermelha" and e["id"] == "a1"
                  for e in ev), str(ev))
        check("o 2º build rodou antes da volta",
              len([e for e in ev if e["evento"] == "verify"
                   and e["id"] == "a1"]) >= 2, str(ev))


def test_4d_segunda_volta_vermelha_vira_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, TRABALHA)
        p, _ = roda(raiz, binv, plano_de(raiz),
                    ["--for", "2h", "--verify", SEMPRE_VERMELHO])
        check("o run termina com o item blocked",
              status(raiz, "a1")["status"] == "blocked",
              str(status(raiz, "a1")) + p.stdout[-600:])
        voltas = [e for e in ledger_de(raiz)
                  if e["evento"] == "volta_vermelha" and e["id"] == "a1"]
        check("...e exatamente duas voltas vermelhas", len(voltas) == 2,
              str(voltas))
        branch = [e for e in ledger_de(raiz)
                  if e["evento"] == "run_start"][0]["branch"]
        check("a 2ª volta não sobrescreve a lateral da 1ª",
              git(raiz, "branch", "--list", f"{branch}-vermelho-a1")
              and git(raiz, "branch", "--list", f"{branch}-vermelho-a1-v2"),
              git(raiz, "branch", "--list", "until/*"))


def test_4d_voltas_contam_entre_runs():
    """O teto conta nos `.jsonl` da fila, e não só na janela corrente."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, TRABALHA)
        d = raiz / ".claude" / "programs" / "fila" / "until"
        d.mkdir(parents=True)
        (d / "2026-01-01-0000.jsonl").write_text(json.dumps(
            {"evento": "volta_vermelha", "id": "a1", "volta": 1}) + "\n")
        subprocess.run(["git", "add", "-A"], cwd=raiz, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "run anterior"], cwd=raiz, check=True)
        roda(raiz, binv, plano_de(raiz),
             ["--for", "2h", "--verify", SEMPRE_VERMELHO])
        check("com uma volta de um run anterior, a 1ª deste já vira blocked",
              status(raiz, "a1")["status"] == "blocked"
              and len(recados(raiz)) == 0 and len(cwds(raiz)) == 1,
              str(status(raiz, "a1")) + str(cwds(raiz)))


def test_4e_cada_volta_conta_no_disjuntor():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2"), item("a3")])
        binv = fake_claude(tmp, TRABALHA)
        roda(raiz, binv, plano_de(raiz),
             ["--for", "2h", "--verify", SEMPRE_VERMELHO, "--max-falhas", "2"])
        fim = [e for e in ledger_de(raiz) if e["evento"] == "run_end"][0]
        check("o run para pelo disjuntor", fim["motivo"] == "disjuntor", str(fim))
        check("...sem nenhum item done",
              not any(status(raiz, i)["status"] == "done"
                      for i in ("a1", "a2", "a3")), str(fim))


# ── a lateral só some com cópia (Revisão 3, passo 4f) ───────────────────────

def lateral_antiga(raiz, nome, arquivo):
    """Uma lateral de um run anterior com um commit que a main não tem."""
    git(raiz, "checkout", "-q", "-b", nome)
    (raiz / arquivo).write_text("x")
    git(raiz, "add", "-A")
    git(raiz, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm",
        f"commit de {arquivo}")
    git(raiz, "checkout", "-q", "-")


def test_4f_lateral_de_item_fechado_vira_patch_antes_de_sumir():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1", status="dropped"), item("a2"),
                                item("a3", status="blocked")])
        lateral_antiga(raiz, "until/2026-01-01-0000-vermelho-a1", "l1.txt")
        lateral_antiga(raiz, "until/2026-01-01-0000-vermelho-a1-v2", "l1b.txt")
        lateral_antiga(raiz, "until/2026-01-01-0000-parado-a3", "l3.txt")
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        roda(raiz, binv, plano_de(raiz), ["--for", "2h"])
        d = raiz / ".claude" / "programs" / "fila" / "until"
        patches = sorted(d.glob("*.laterais/*.patch"))
        nomes = [p.name for p in patches]
        check("as duas laterais do item dropped viram patch",
              len(patches) == 2 and all("vermelho-a1" in n for n in nomes),
              str(nomes))
        check("...com o commit dentro",
              any("commit de l1.txt" in p.read_text() for p in patches),
              str(nomes))
        check("...e só então somem",
              not git(raiz, "branch", "--list", "until/*-vermelho-a1*"),
              git(raiz, "branch", "--list", "until/*"))
        check("a lateral de item ainda aberto (blocked) fica",
              git(raiz, "branch", "--list", "until/2026-01-01-0000-parado-a3"),
              git(raiz, "branch", "--list", "until/*"))
        check("o registro grava a lateral apagada com o patch",
              any(e["evento"] == "lateral_apagada" and e.get("patch")
                  for e in ledger_de(raiz)), str(ledger_de(raiz)))


def test_4f_sem_patch_a_lateral_fica():
    import shutil
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1", status="done"), item("a2")])
        lateral_antiga(raiz, "until/2026-01-01-0000-vermelho-a1", "l1.txt")
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        falso = binv / "git"
        falso.write_text(
            "#!/bin/sh\n"
            "for a in \"$@\"; do [ \"$a\" = format-patch ] && exit 1; done\n"
            f"exec {shutil.which('git')} \"$@\"\n")
        falso.chmod(0o755)
        roda(raiz, binv, plano_de(raiz), ["--for", "2h"])
        check("com o format-patch falhando, a branch continua",
              git(raiz, "branch", "--list", "until/2026-01-01-0000-vermelho-a1"),
              git(raiz, "branch", "--list", "until/*"))
        check("...e o registro diz por quê",
              any(e["evento"] == "lateral_mantida" for e in ledger_de(raiz)),
              str(ledger_de(raiz)))


# ── estado do run e lista de ações (passo 2; C6, C7 e A4) ───────────────────

def estado_de(raiz):
    d = raiz / ".claude" / "programs" / "fila" / "until"
    arqs = sorted(d.glob("*.estado.json"))
    return json.loads(arqs[-1].read_text()) if arqs else None


# O `claude` falso anota o estado do run que vê: durante o item, e na análise
# do fim (chamada `/common:until-review`).
OLHA_ESTADO = (
    "import glob\n"
    "def _estado():\n"
    "    d = os.path.join(os.path.dirname(PLANO), 'until')\n"
    "    a = sorted(glob.glob(os.path.join(d, '*.estado.json')))\n"
    "    return json.load(open(a[-1])) if a else None\n"
    "with open(os.environ['FAKE_CHAMADAS'] + '.estado', 'a') as f:\n"
    "    f.write(json.dumps({'args0': ARGS[1][:30] if len(ARGS) > 1 else '',\n"
    "                        'estado': _estado()}) + '\\n')\n"
    "if ARGS and ARGS[1].startswith('/common:until-review'):\n"
    "    print(json.dumps({'type': 'result', 'result': 'analise'}))\n"
    "    sys.exit(0)\n")


def vistos_estado(raiz):
    f = Path(raiz).parent / "chamadas.jsonl.estado"
    return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


def test_2_estado_do_run_rodando_e_depois_esperando_dono_antes_da_analise():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        corpo = OLHA_ESTADO + TRABALHA.replace(
            "marca(ident, status='done', evidence='ok')\n",
            "if ident == 'a2':\n"
            "    marca(ident, status='blocked', evidence='travou no Keycloak')\n"
            "else:\n"
            "    marca(ident, status='done', evidence='ok')\n")
        binv = fake_claude(tmp, corpo)
        p, _ = roda(raiz, binv, plano_de(raiz),
                    ["--for", "2h", "--verify", VERIFY, "--com-analise"])
        vistos = vistos_estado(raiz)
        durante = [v for v in vistos if not v["args0"].startswith("/common:until")]
        check("durante o item, o estado é rodando",
              durante and all((v["estado"] or {}).get("estado") == "rodando"
                              for v in durante), str(durante)[:400])
        analise = [v for v in vistos if v["args0"].startswith("/common:until")]
        est = (analise[0]["estado"] or {}) if analise else {}
        check("a análise já encontra o estado final gravado",
              est.get("estado") == "esperando-dono", str(analise)[:400])
        acoes = est.get("acoes") or []
        branch = [e for e in ledger_de(raiz)
                  if e["evento"] == "run_start"][0]["branch"]
        check("a única ação é aterrissar, com a branch da noite",
              [a.get("id") for a in acoes] == ["aterrissar"]
              and f"fila/{branch.split('/', 1)[1]}"
              in (acoes[0].get("comando") or ""), str(acoes))
        check("...com a frase leiga do efeito",
              acoes and acoes[0].get("frase"), str(acoes))
        itens = est.get("itens") or []
        check("uma linha por item",
              [i.get("id") for i in itens] == ["a1", "a2"], str(itens))
        fica = est.get("fica_com_voce") or []
        check("o travado vai para 'fica com você' com o motivo",
              any(f.get("id") == "a2" and "Keycloak" in (f.get("texto") or "")
                  for f in fica), str(fica))
        check("o terminal imprime a ação numerada",
              "1. aterrissar" in p.stdout, p.stdout[-900:])
        check("...e o bloco 'Fica com você'",
              "Fica com você" in p.stdout, p.stdout[-900:])
        check("o resumo não sugere o /common:worktree-merge",
              "worktree-merge" not in p.stdout, p.stdout[-900:])


def test_2_cada_item_aparece_uma_vez_no_resumo():
    """A4: o WEGO-2320 aparecia em "Travados", "Build vermelho" e "Sem
    progresso", e lia-se como três problemas."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2"), item("a3")])
        binv = fake_claude(tmp, TRABALHA)
        p, _ = roda(raiz, binv, plano_de(raiz),
                    ["--for", "2h", "--verify", VERIFY],
                    extra_env={"FAKE_QUEBRA": "a2"})
        fim = p.stdout[p.stdout.find("── fim"):]
        for ident in ("a1", "a2", "a3"):
            check(f"{ident} aparece uma vez na lista de itens do fim",
                  fim.count(f"- {ident}:") == 1, fim)
        check("a linha do a2 diz volta vermelha e a lateral",
              "vermelho-a2" in fim and "volta vermelha" in fim, fim)


def test_2_run_sem_commit_termina_encerrado_sem_acao():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='dropped',"
                                " evidence='não precisa mais')")
        roda(raiz, binv, plano_de(raiz), ["--for", "2h"])
        est = estado_de(raiz) or {}
        check("sem commit e sem pendência, o estado é encerrado",
              est.get("estado") == "encerrado" and not est.get("acoes"),
              str(est))


# ── passo 1 entre runs: a tentativa do run anterior chega pela herança ──────

# Na 1ª chamada, os itens de FAKE_METADE commitam e ficam com uma rota humana
# aberta: o run A termina com eles pela metade, sem que o laço os repita.
METADE = TENTA.replace(
    "if ident not in lista('FAKE_DUAS') or n >= 2:\n",
    "if n == 1 and ident in lista('FAKE_METADE'):\n"
    "    marca(ident, human_pending='pela metade')\n"
    "elif ident not in lista('FAKE_DUAS') or n >= 2:\n", 1)


def run_ids(raiz):
    return [e["branch"] for e in ledger_de(raiz) if e["evento"] == "run_start"]


def libera(raiz, *idents):
    """O dono fecha a rota humana entre os dois runs e commita a fila (a
    largada recusa a fila modificada fora do que o run anterior tocou)."""
    p = yaml.safe_load(plano_de(raiz).read_text())
    for it in p["items"]:
        if it["id"] in idents:
            it["human_pending"] = None
    plano_de(raiz).write_text(yaml.safe_dump(p, allow_unicode=True))
    git(raiz, "add", str(plano_de(raiz)))
    git(raiz, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm",
        "dono: fecha a rota")


def test_1_tentativa_do_run_anterior_tambem_vai_para_a_lateral():
    """Achado do completion-auditor (2026-09-28): o reset voltava até o começo
    da 1ª tentativa DESTE run, que é depois da mescla da herança, e os commits
    do run anterior ficavam na branch da noite sem passar pelo build.

    O a2 entra na fila só no run B e fecha verde depois do a1: é ele que mantém
    a branch da noite do run B viva para o teste olhar dentro dela."""
    import time
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2", status="dropped")])
        binv = fake_claude(tmp, METADE)
        env = {"FAKE_METADE": "a1", "FAKE_QUEBRA": "a1"}
        roda(raiz, binv, plano_de(raiz), ["--for", "2h", "--verify", VERIFY],
             extra_env=env)
        libera(raiz, "a1")
        p_ = yaml.safe_load(plano_de(raiz).read_text())
        for it in p_["items"]:
            if it["id"] == "a2":
                it["status"] = "pending"
        plano_de(raiz).write_text(yaml.safe_dump(p_, allow_unicode=True))
        git(raiz, "add", str(plano_de(raiz)))
        git(raiz, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm",
            "dono: a2 entra na fila")
        time.sleep(61)  # o id do run é por minuto
        p, _ = roda(raiz, binv, plano_de(raiz),
                    ["--for", "2h", "--verify", VERIFY], extra_env=env)
        runs = run_ids(raiz)
        check("o run B herdou a branch do run A",
              len(runs) == 2 and "herda" in p.stdout, p.stdout[:900])
        check("...e o a2 fechou verde nele",
              status(raiz, "a2")["status"] == "done", str(status(raiz, "a2")))
        noite_b = git(raiz, "log", "--format=%s", runs[-1]).splitlines()
        check("a branch da noite do run B não tem o commit do run A",
              "a2-t1" in noite_b and "a1-t1" not in noite_b, str(noite_b))
        lateral = git(raiz, "log", "--format=%s",
                      f"{runs[-1]}-vermelho-a1").splitlines()
        check("...que está na lateral da 1ª volta",
              "a1-t1" in lateral and "a1-t2" in lateral, str(lateral))


def test_1_heranca_com_outro_item_aberto_para_em_vez_de_resetar():
    import time
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, METADE)
        roda(raiz, binv, plano_de(raiz), ["--for", "2h", "--verify", VERIFY],
             extra_env={"FAKE_METADE": "a1,a2"})
        libera(raiz, "a1")
        time.sleep(61)
        roda(raiz, binv, plano_de(raiz), ["--for", "2h", "--verify", VERIFY],
             extra_env={"FAKE_METADE": "a1,a2", "FAKE_QUEBRA": "a1"})
        ev = ledger_de(raiz)
        fim = [e for e in ev if e["evento"] == "run_end"][-1]
        check("o run B para no vermelho", fim["motivo"] == "verify-vermelho",
              str(fim))
        check("...e o aviso nomeia o outro item herdado",
              "a2" in (fim.get("detalhe") or ""), str(fim))
        noite_b = git(raiz, "log", "--format=%s", run_ids(raiz)[-1]).splitlines()
        check("o trabalho do a2 continua na branch da noite",
              "a2-t1" in noite_b, str(noite_b))


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
