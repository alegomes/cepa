#!/usr/bin/env python3
"""Testes do /common:fila e do `cepa-plan status` que ele chama.

Rode com `python3 tests/test_common_fila.py` (só precisa do PyYAML).

A dor: em 2026-09-28 o dono perguntou qual comando lista a fila e não havia
nenhum. O `queue` esconde o que fechou e para no primeiro travamento, e o
/common:next aponta um passo só. Estes testes prendem as três promessas do
comando novo: mostra TODOS os itens, na ordem gravada, e não toca no arquivo.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    print("✗ precisa de PyYAML (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

REPO = Path(__file__).resolve().parent.parent
CEPA_PLAN = REPO / "common" / "bin" / "cepa-plan"
CMD = REPO / "common" / "commands" / "fila.md"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def run(cwd, *args):
    return subprocess.run([sys.executable, str(CEPA_PLAN)] + list(args),
                          capture_output=True, text=True, cwd=str(cwd))


def repo_git(base, nome):
    d = Path(base) / nome
    d.mkdir(parents=True)
    subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(d), "-c", "user.email=t@t", "-c",
                    "user.name=t", "commit", "-q", "--allow-empty", "-m", "0"],
                   check=True)
    return d


def item(ident, **kw):
    base = {"id": ident, "title": f"item {ident}", "why": f"porque {ident}",
            "status": "pending", "blocked_by": [], "human_pending": None}
    base.update(kw)
    return base


def escreve_fila(d, itens, nome="fila"):
    p = d / f"itens-{nome}.json"
    p.write_text(json.dumps(itens, ensure_ascii=False), encoding="utf-8")
    r = run(d, "write", nome, "--items", str(p), "--source", "teste",
            "--quando", "2026-09-28", "--repo", ".")
    assert r.returncode == 0, r.stderr
    return d / ".claude" / "programs" / nome / "plan.yaml"


ITENS = [
    item("a-feito", status="done", evidence="commit abc"),
    item("b-pendente"),
    item("c-travado", status="blocked",
         evidence="Condicao de fora: o dono precisa decidir X"),
    item("d-descartado", status="dropped"),
    item("e-espera", blocked_by=["b-pendente"],
         human_pending="validar à mão no navegador"),
]


def status_json(d, *extra):
    r = run(d, "status", *extra, "--json", "--repo", ".")
    return r, (json.loads(r.stdout) if r.returncode == 0 else None)


def test_lista_todos_os_itens_na_ordem_gravada(base):
    d = repo_git(base, "todos")
    escreve_fila(d, ITENS)
    r, out = status_json(d, "fila")
    check("sai com código 0", r.returncode == 0, r.stderr)
    ids = [i["id"] for i in out["items"]]
    check("traz os 5 itens, inclusive concluído e descartado",
          ids == ["a-feito", "b-pendente", "c-travado", "d-descartado",
                  "e-espera"], ids)
    check("a posição é a da fila gravada",
          [i["posicao"] for i in out["items"]] == [1, 2, 3, 4, 5])
    check("conta por status",
          out["por_status"] == {"pending": 2, "in_progress": 0, "done": 1,
                                "blocked": 1, "dropped": 1}, out["por_status"])
    check("total bate", out["total"] == 5)


def test_texto_agrupa_e_mostra_motivo_e_acao_humana(base):
    d = repo_git(base, "texto")
    escreve_fila(d, ITENS)
    r = run(d, "status", "fila", "--repo", ".")
    t = r.stdout
    check("cabeçalho com as contagens",
          "0 em andamento · 2 pendentes · 1 bloqueados · 1 concluídos · "
          "1 descartados · 5 no total" in t, t)
    ordem = [t.find(g) for g in ("\npendentes (2)", "\nbloqueados (1)",
                                 "\nconcluídos (1)", "\ndescartados (1)")]
    check("grupos na ordem pendentes, bloqueados, concluídos, descartados",
          all(x >= 0 for x in ordem) and ordem == sorted(ordem), ordem)
    check("bloqueado mostra o motivo da evidência",
          "motivo: Condicao de fora: o dono precisa decidir X" in t, t)
    check("pendente mostra de quem depende", "espera: b-pendente" in t, t)
    check("ação humana aberta aparece no item e no cabeçalho",
          "ação humana: validar à mão no navegador" in t
          and "1 com ação humana aberta: e-espera" in t, t)
    check("concluído sai numa linha só, sem evidência",
          "commit abc" not in t and "1. a-feito — item a-feito" in t, t)


def test_filtro_por_status(base):
    d = repo_git(base, "filtro")
    escreve_fila(d, ITENS)
    _, out = status_json(d, "fila", "--status", "pending")
    check("--status pending traz só os pendentes",
          [i["id"] for i in out["items"]] == ["b-pendente", "e-espera"])
    check("mas a contagem continua da fila inteira", out["total"] == 5)
    r = run(d, "status", "fila", "--status", "xyz", "--repo", ".")
    check("status desconhecido é recusado", r.returncode != 0)


def test_nome_omitido(base):
    d = repo_git(base, "uma")
    escreve_fila(d, ITENS, "unica")
    r, out = status_json(d)
    check("com uma fila só, usa ela", r.returncode == 0
          and out and out["program"] == "unica", r.stderr)
    escreve_fila(d, ITENS[:1], "outra")
    r, _ = status_json(d)
    check("com duas, recusa e nomeia as duas", r.returncode == 2
          and "outra" in r.stderr and "unica" in r.stderr, r.stderr)
    vazio = repo_git(base, "vazio")
    r, _ = status_json(vazio)
    check("sem fila, recusa apontando o /common:plan", r.returncode == 2
          and "/common:plan" in r.stderr, r.stderr)


def test_nao_toca_no_arquivo(base):
    d = repo_git(base, "leitura")
    alvo = escreve_fila(d, ITENS)
    antes = (alvo.read_bytes(), alvo.stat().st_mtime_ns)
    run(d, "status", "fila", "--repo", ".")
    status_json(d, "fila")
    check("o plan.yaml sai byte a byte igual e sem ser tocado",
          (alvo.read_bytes(), alvo.stat().st_mtime_ns) == antes)


def test_recusa_plano_de_ondas(base):
    d = repo_git(base, "ondas")
    alvo = d / ".claude" / "programs" / "ondas" / "plan.yaml"
    alvo.parent.mkdir(parents=True)
    alvo.write_text(yaml.safe_dump({"schema_version": 2,
                                    "mode": "parallel-waves", "waves": []}))
    r, _ = status_json(d, "ondas")
    check("plano de ondas sai com código 3", r.returncode == 3, r.stderr)


def test_de_dentro_de_uma_worktree_le_o_clone_principal(base):
    d = repo_git(base, "principal")
    escreve_fila(d, ITENS)
    wt = Path(base) / "wt-fila"
    subprocess.run(["git", "-C", str(d), "worktree", "add", "-q", "--detach",
                    str(wt)], check=True)
    r, out = status_json(wt, "fila")
    check("a worktree enxerga a fila do clone principal",
          r.returncode == 0 and out and out["total"] == 5, r.stderr)


def test_contrato_do_comando(_base):
    t = CMD.read_text(encoding="utf-8")
    check("o comando chama o `cepa-plan status`",
          'bin/cepa-plan" status $ARGUMENTS' in t)
    check("manda mostrar a saída na íntegra", "na íntegra" in t)
    check("declara que só lê", "Só leitura" in t)


def main():
    with tempfile.TemporaryDirectory() as base:
        for fn in (test_lista_todos_os_itens_na_ordem_gravada,
                   test_texto_agrupa_e_mostra_motivo_e_acao_humana,
                   test_filtro_por_status,
                   test_nome_omitido,
                   test_nao_toca_no_arquivo,
                   test_recusa_plano_de_ondas,
                   test_de_dentro_de_uma_worktree_le_o_clone_principal,
                   test_contrato_do_comando):
            print(f"\n{fn.__name__}")
            fn(base)
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
