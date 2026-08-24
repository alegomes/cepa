#!/usr/bin/env python3
"""Regression tests for maestro/bin/maestro-programs.

Run with `python3 tests/test_maestro_programs.py` (no third-party deps beyond
the PyYAML the script itself needs). Exits non-zero on first failure.

O que estes testes seguram é a razão do script existir: ele responde "o que dá
para rodar aqui?" e essa resposta só vale se BATER com a recusa do
/maestro:run. Um listador que diz RODA sobre um plano single-track (ou sobre um
plano sem schema_version) é pior que nenhum listador — manda o usuário para uma
recusa que ele já poderia ter visto. Daí os casos 2-5 serem todos de recusa.

O caso 6 segura o invariante de costura: chamado de dentro de uma worktree
ligada, o script tem que enxergar os programas do CLONE PRINCIPAL — a mesma
raiz que o /maestro:run usa. Se divergir, a listagem mostra um programa que a
execução não acha (ou esconde o que ela acharia).
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "maestro" / "bin" / "maestro-programs"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo)] + list(args),
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {args} failed: {r.stderr}")
    return r


def run(repo, *extra):
    return subprocess.run([sys.executable, str(SCRIPT), str(repo)] + list(extra),
                          capture_output=True, text=True)


def as_json(repo):
    r = run(repo, "--json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    return {p["nome"]: p for p in data["programas"]}, data["raiz"]


def write_program(repo, nome, texto):
    d = Path(repo) / ".claude" / "programs" / nome
    d.mkdir(parents=True, exist_ok=True)
    (d / "plan.yaml").write_text(texto)
    return d


ONDAS_PENDENTES = """\
schema_version: 2
mode: parallel-waves
program: com-onda
waves:
  - id: 1
    slices: [S1, S2]
    status: pending
  - id: 2
    slices: [S3]
    status: pending
"""

TUDO_DONE = """\
schema_version: 2
mode: parallel-waves
program: acabado
waves:
  - id: 1
    slices: [S1]
    status: done
"""

SINGLE_TRACK = """\
schema_version: 2
mode: single-track
program: fila
items:
  - id: ITEM-1
    title: primeiro
    status: done
  - id: ITEM-2
    title: segundo
    status: pending
"""

SEM_SCHEMA = """\
program: legado-sem-versao
waves:
  - id: 1
    slices: [S1]
    status: pending
"""


def fixture_repo(base):
    repo = Path(base) / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    (repo / "README.md").write_text("x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "seed")
    return repo


def test_elegivel_aponta_a_proxima_onda(tmp):
    repo = fixture_repo(tmp)
    write_program(repo, "com-onda", ONDAS_PENDENTES)
    progs, _ = as_json(repo)
    p = progs["com-onda"]
    check("plano com onda pendente é elegível", p["elegivel"], p["motivo"])
    check("aponta a PRIMEIRA onda pendente",
          p["proxima_onda"] and p["proxima_onda"]["id"] == 1, p["proxima_onda"])
    saida = run(repo).stdout
    check("saída humana traz a linha de comando pronta",
          "/maestro:run com-onda --wave 1" in saida, saida)


def test_ondas_todas_done_nao_roda(tmp):
    repo = fixture_repo(tmp)
    write_program(repo, "acabado", TUDO_DONE)
    progs, _ = as_json(repo)
    p = progs["acabado"]
    check("programa acabado não é elegível", not p["elegivel"])
    check("motivo diz que as ondas acabaram", "done" in (p["motivo"] or ""), p["motivo"])


def test_single_track_recusado_com_a_rota_certa(tmp):
    repo = fixture_repo(tmp)
    write_program(repo, "fila", SINGLE_TRACK)
    progs, _ = as_json(repo)
    p = progs["fila"]
    check("single-track não é elegível (igual ao /maestro:run)", not p["elegivel"])
    check("motivo nomeia /common:next", "/common:next" in (p["motivo"] or ""), p["motivo"])
    check("motivo nomeia o próximo item pendente",
          "ITEM-2" in (p["motivo"] or ""), p["motivo"])


def test_sem_schema_version_recusa_igual_ao_run(tmp):
    repo = fixture_repo(tmp)
    write_program(repo, "legado", SEM_SCHEMA)
    progs, _ = as_json(repo)
    p = progs["legado"]
    check("plano sem schema_version não é elegível", not p["elegivel"])
    check("motivo cita schema_version", "schema_version" in (p["motivo"] or ""), p["motivo"])


def test_diretorio_sem_plano_aparece_como_tal(tmp):
    repo = fixture_repo(tmp)
    (Path(repo) / ".claude" / "programs" / "vazio").mkdir(parents=True)
    progs, _ = as_json(repo)
    p = progs["vazio"]
    check("diretório sem plan.yaml não é elegível", not p["elegivel"])
    check("motivo é 'sem plan.yaml'", p["motivo"] == "sem plan.yaml", p["motivo"])


def test_de_dentro_da_worktree_le_o_clone_principal(tmp):
    repo = fixture_repo(tmp)
    write_program(repo, "com-onda", ONDAS_PENDENTES)
    wt = Path(tmp) / "wt"
    git(repo, "worktree", "add", "-q", "-b", "session/x", str(wt))
    progs, raiz = as_json(wt)
    check("worktree ligada enxerga o programa do clone principal",
          "com-onda" in progs, list(progs))
    check("a raiz reportada é a do clone principal",
          Path(raiz).resolve() == repo.resolve(), raiz)


def test_fora_de_repo_git_sai_2(tmp):
    fora = Path(tmp) / "nao-repo"
    fora.mkdir()
    r = run(fora)
    check("diretório sem git sai com 2", r.returncode == 2, r.returncode)
    check("e diz por quê", "git" in r.stderr, r.stderr)


def test_check_name_recusa_fila_do_board(tmp):
    repo = fixture_repo(tmp)
    write_program(repo, "WEGO", SINGLE_TRACK)
    r = run(repo, "--check-name", "WEGO")
    check("nome ocupado por fila single-track sai com 3", r.returncode == 3, r.returncode)
    check("a mensagem diz que a fila é do board",
          "single-track" in r.stderr and "COLIS" in r.stderr, r.stderr)
    check("e nomeia quem escreveu aquilo",
          "/board-flow:triage" in r.stderr, r.stderr)


def test_check_name_libera_replanejar_as_proprias_ondas(tmp):
    repo = fixture_repo(tmp)
    write_program(repo, "com-onda", ONDAS_PENDENTES)
    r = run(repo, "--check-name", "com-onda")
    check("reescrever plano de ondas é liberado", r.returncode == 0, r.stderr)
    check("mas avisa que o nome está ocupado",
          "ocupado" in r.stdout, r.stdout)


def test_check_name_libera_nome_novo(tmp):
    repo = fixture_repo(tmp)
    r = run(repo, "--check-name", "ainda-nao-existe")
    check("nome inédito é livre", r.returncode == 0, r.stderr)
    check("e diz que o caminho não existe", "livre" in r.stdout, r.stdout)


def test_program_plan_chama_a_checagem_antes_de_gravar(tmp):
    """Contrato de prompt: o passo 4 do /maestro:program-plan tem que rodar a
    checagem ANTES da escrita. Sem isto o script existe e ninguém o chama."""
    cmd = (REPO / "maestro" / "commands" / "program-plan.md").read_text()
    check("o passo 4 chama --check-name", "--check-name" in cmd)
    check("e trata o exit 3 como parada", "Exit 3" in cmd and "pare" in cmd.lower())
    i_check = cmd.find("--check-name")
    i_write = cmd.find("escreva\n   `<raiz-principal>/.claude/programs/")
    check("a checagem vem antes da escrita",
          i_check != -1 and i_write != -1 and i_check < i_write,
          f"check={i_check} write={i_write}")


def main():
    tests = [test_elegivel_aponta_a_proxima_onda,
             test_ondas_todas_done_nao_roda,
             test_single_track_recusado_com_a_rota_certa,
             test_sem_schema_version_recusa_igual_ao_run,
             test_diretorio_sem_plano_aparece_como_tal,
             test_de_dentro_da_worktree_le_o_clone_principal,
             test_fora_de_repo_git_sai_2,
             test_check_name_recusa_fila_do_board,
             test_check_name_libera_replanejar_as_proprias_ondas,
             test_check_name_libera_nome_novo,
             test_program_plan_chama_a_checagem_antes_de_gravar]
    for t in tests:
        print(t.__name__)
        with tempfile.TemporaryDirectory() as d:
            t(d)
    if FAILURES:
        print(f"\n{len(FAILURES)} failing: {', '.join(FAILURES)}")
        return 1
    print("\nall green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
