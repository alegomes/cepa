#!/usr/bin/env python3
"""cepa-until — item que andou sem fechar, e a retomada no run seguinte.

O run 2026-09-27-1632 do wego-acessos-backend mostrou dois defeitos no mesmo
item, o WEGO-2283:

  - morto pela folga (exit 143) com 15 commits na branch da noite, o
    `item_end` saiu `progresso: false`. O disjuntor e o teto de tentativas
    leem esse campo: um item que andou muito era tratado como parado;
  - o run seguinte criou `until/<run>` a partir do HEAD do clone. O `start`
    reivindicou a reserva órfã do 2283, mas os 15 commits dela ficaram em
    `until/2026-09-27-1632` e não entraram na branch nova: o item recomeçava
    do zero, e o contorno era mesclar a branch antiga à mão antes do run.

Os casos abaixo fixam o conserto:
  - commit na branch da noite conta como progresso, mesmo sem desfecho;
  - a branch da noite herda a branch do run anterior quando ela guarda commits
    de um item que ficou pela metade e ainda não foi mesclada;
  - branch já mesclada não é herdada;
  - herança que conflita recusa a largada, sem deixar worktree nem branch.
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

ANTIGO = "2026-01-01-0000"
BRANCH_ANTIGA = f"until/{ANTIGO}"


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


def commit(raiz, msg):
    subprocess.run(["git", "add", "-A"], cwd=raiz, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", msg], cwd=raiz, check=True)


def orfao(ident):
    """Item `in_progress` cuja reserva é de outra máquina e passou das 24h:
    o `cepa-plan queue` o devolve como executável."""
    it = item(ident, status="in_progress")
    it["claimed_by"] = {"session_id": "morta", "pid": 1,
                        "hostname": "outra-maquina", "cwd": "/nao/existe",
                        "branch": BRANCH_ANTIGA,
                        "started_at": "2026-01-01T00:00:00+00:00"}
    return it


def run_anterior(raiz, arquivo="parcial.txt", conteudo="metade do a1\n",
                 commits=1):
    """O que o run morto deixou: a branch da noite com o trabalho do a1 pela
    metade e o registro dizendo que o a1 saiu com commits e sem desfecho."""
    base = git(raiz, "rev-parse", "HEAD")
    subprocess.run(["git", "branch", BRANCH_ANTIGA], cwd=raiz, check=True)
    subprocess.run(["git", "checkout", "-q", BRANCH_ANTIGA], cwd=raiz, check=True)
    (raiz / arquivo).write_text(conteudo)
    commit(raiz, "a1 pela metade")
    subprocess.run(["git", "checkout", "-q", "-"], cwd=raiz, check=True)
    d = raiz / ".claude" / "programs" / "fila" / "until"
    d.mkdir(parents=True, exist_ok=True)
    eventos = [
        {"evento": "run_start", "branch": BRANCH_ANTIGA, "base": base,
         "arvore": "/nao/existe"},
        {"evento": "item_start", "id": "a1", "tentativa": 1},
        {"evento": "item_end", "id": "a1", "status": "in_progress",
         "exit_code": 143, "timeout": True, "commits": commits,
         "progresso": False},
        {"evento": "run_end", "motivo": "prazo"},
    ]
    (d / f"{ANTIGO}.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in eventos))


# O `claude` falso da retomada: diz se enxergou o trabalho do run anterior,
# commita e fecha o a1.
RETOMA = (
    "import subprocess\n"
    "viu = os.path.exists('parcial.txt')\n"
    "with open(os.environ['FAKE_CHAMADAS'] + '.viu', 'a') as f:\n"
    "    f.write(json.dumps({'viu_parcial': viu}) + '\\n')\n"
    "open('a1.txt', 'w').write('feito')\n"
    "subprocess.run(['git', 'add', '-A'], check=True)\n"
    "subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t',\n"
    "                'commit', '-qm', 'a1 fechado'], check=True)\n"
    "marca('a1', status='done', evidence='ok')\n")


def viu(raiz):
    f = Path(raiz).parent / "chamadas.jsonl.viu"
    return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


def novos_runs(ev):
    return [e for e in ev if e["evento"] == "run_start"
            and e.get("branch") != BRANCH_ANTIGA]


# ── 1. commit é progresso ───────────────────────────────────────────────────

def test_item_que_commitou_sem_fechar_conta_como_progresso():
    """Com `--tentativas-por-item 1`, a tentativa que commitou e saiu sem
    desfecho marcava o item `blocked` pelo teto. Andou: a vez seguinte fecha."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        corpo = (
            "import subprocess\n"
            "n = len(open(os.environ['FAKE_CHAMADAS']).read().splitlines())\n"
            "open(f'passo{n}.txt', 'w').write('x')\n"
            "subprocess.run(['git', 'add', '-A'], check=True)\n"
            "subprocess.run(['git', '-c', 'user.email=t@t', '-c',"
            " 'user.name=t', 'commit', '-qm', f'passo {n}'], check=True)\n"
            "if n >= 2:\n"
            "    marca('a1', status='done', evidence='ok')\n")
        binv = fake_claude(tmp, corpo)
        p, chamadas = roda(raiz, binv, plano_de(raiz),
                           ["--for", "2h", "--tentativas-por-item", "1",
                            "--max-falhas", "1"])
        fins = [e for e in ledger_de(raiz) if e["evento"] == "item_end"]
        check("a 1ª tentativa sai com commit e sem desfecho",
              fins and fins[0]["commits"] == 1
              and fins[0]["status"] == "pending", str(fins))
        check("...e o registro diz progresso",
              fins and fins[0]["progresso"] is True, str(fins))
        check("o teto de tentativas não tira o item da frente",
              status(raiz, "a1")["status"] == "done",
              str(status(raiz, "a1")) + p.stdout[-600:])
        check("o disjuntor não dispara",
              "· disjuntor" not in p.stdout and len(chamadas) == 2,
              p.stdout[-600:])
        check("a tela diz que andou sem fechar",
              "commit(s) sem fechar" in p.stdout, p.stdout[-600:])


def test_item_sem_commit_e_sem_desfecho_continua_sem_progresso():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "pass")
        p, _ = roda(raiz, binv, plano_de(raiz),
                    ["--for", "2h", "--tentativas-por-item", "1",
                     "--max-falhas", "1"])
        fins = [e for e in ledger_de(raiz) if e["evento"] == "item_end"]
        check("sem commit, o registro segue dizendo sem progresso",
              fins and fins[0]["progresso"] is False
              and fins[0]["commits"] == 0, str(fins))
        check("...e o disjuntor dispara", "· disjuntor" in p.stdout,
              p.stdout[-400:])


# ── 2. a retomada herda a branch do run anterior ────────────────────────────

def test_retomada_da_reserva_orfa_herda_os_commits_do_run_anterior():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [orfao("a1")])
        run_anterior(raiz)
        binv = fake_claude(tmp, RETOMA)
        p, _ = roda(raiz, binv, plano_de(raiz), ["--for", "2h"])
        vistos = viu(raiz)
        check("o item retomado acorda com o trabalho do run anterior",
              vistos and vistos[0]["viu_parcial"], str(vistos) + p.stdout[-800:]
              + p.stderr[-400:])
        inicio = novos_runs(ledger_de(raiz))
        herdou = (inicio[0].get("herdou") or []) if inicio else []
        check("a largada registra de qual branch herdou",
              [(h.get("branch"), h.get("itens"), h.get("commits"))
               for h in herdou] == [(BRANCH_ANTIGA, ["a1"], 1)], str(inicio))
        check("...e a tela avisa", BRANCH_ANTIGA in p.stdout
              and "herd" in p.stdout, p.stdout[:1500])
        branch = inicio[0]["branch"] if inicio else "?"
        log = git(raiz, "log", "--format=%s", branch).splitlines()
        check("a branch nova tem o commit antigo e o novo",
              "a1 pela metade" in log and "a1 fechado" in log, str(log))
        check("o clone principal não recebeu nada",
              "a1 pela metade" not in git(raiz, "log", "--format=%s"))


def test_branch_ja_mesclada_nao_e_herdada():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [orfao("a1")])
        run_anterior(raiz)
        subprocess.run(["git", "merge", "-q", "--ff-only", BRANCH_ANTIGA],
                       cwd=raiz, check=True)
        binv = fake_claude(tmp, RETOMA)
        p, _ = roda(raiz, binv, plano_de(raiz), ["--for", "2h"])
        inicio = novos_runs(ledger_de(raiz))
        check("nada a herdar: a largada não registra herança",
              inicio and not inicio[0].get("herdou"), str(inicio))
        check("...e o item vê o trabalho (veio pela main)",
              viu(raiz) and viu(raiz)[0]["viu_parcial"], str(viu(raiz)))


def test_run_anterior_sem_commit_do_item_nao_e_herdado():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [orfao("a1")])
        run_anterior(raiz, commits=0)
        binv = fake_claude(tmp, RETOMA)
        p, _ = roda(raiz, binv, plano_de(raiz), ["--for", "2h"])
        inicio = novos_runs(ledger_de(raiz))
        check("item que saiu sem commit não puxa a branch antiga",
              inicio and not inicio[0].get("herdou"), str(inicio))


def test_heranca_que_conflita_recusa_a_largada_sem_deixar_rastro():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [orfao("a1")])
        run_anterior(raiz)
        (raiz / "parcial.txt").write_text("outra coisa na main\n")
        commit(raiz, "main mexeu no mesmo arquivo")
        binv = fake_claude(tmp, RETOMA)
        p, chamadas = roda(raiz, binv, plano_de(raiz), ["--for", "2h"])
        check("a largada é recusada", p.returncode == 2,
              f"rc={p.returncode} {p.stdout[-400:]} {p.stderr[-400:]}")
        check("...nomeando a branch e o que fazer",
              BRANCH_ANTIGA in p.stderr and "git merge" in p.stderr,
              p.stderr[-600:])
        check("nenhum item roda", not chamadas, str(chamadas))
        check("não sobra branch da noite nova",
              git(raiz, "branch", "--list", "until/*").split()
              == [BRANCH_ANTIGA], git(raiz, "branch", "--list", "until/*"))
        casa = Path(tmp) / "worktrees"
        check("...nem worktree", not casa.exists() or not any(casa.iterdir()),
              str(list(casa.iterdir())) if casa.exists() else "")
        check("a reserva órfã continua onde estava",
              status(raiz, "a1")["status"] == "in_progress")


def main():
    print("cepa-until — retomada\n")
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
