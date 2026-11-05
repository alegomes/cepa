#!/usr/bin/env python3
"""Tests of /common:queue-status and of the `cepa-plan status` it calls.

Run with `python3 tests/test_common_queue_status.py` (it only needs PyYAML).

The pain: on 2026-09-28 the owner asked which command lists the queue and there was
none. `queue` hides what closed and stops at the first jam, and
/common:next points to one step only. These tests hold the three promises of the
new command: shows ALL the items, in the recorded order, and does not touch the file.
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
CMD = REPO / "common" / "commands" / "queue-status.md"

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


def git_repo(base, given_name):
    d = Path(base) / given_name
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


def write_queue(d, items, given_name="fila"):
    p = d / f"itens-{given_name}.json"
    p.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    r = run(d, "write", given_name, "--items", str(p), "--source", "teste",
            "--quando", "2026-09-28", "--repo", ".")
    assert r.returncode == 0, r.stderr
    return d / ".claude" / "queues" / given_name / "queue.yaml"


ITEMS = [
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


def test_lists_all_items_in_recorded_order(base):
    d = git_repo(base, "todos")
    write_queue(d, ITEMS)
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


def test_text_groups_and_shows_reason_and_human_action(base):
    d = git_repo(base, "texto")
    write_queue(d, ITEMS)
    r = run(d, "status", "fila", "--repo", ".")
    t = r.stdout
    check("cabeçalho com as contagens",
          "0 em andamento · 2 pendentes · 1 bloqueados · 1 concluídos · "
          "1 descartados · 5 no total" in t, t)
    order = [t.find(g) for g in ("\npendentes (2)", "\nbloqueados (1)",
                                 "\nconcluídos (1)", "\ndescartados (1)")]
    check("grupos na ordem pendentes, bloqueados, concluídos, descartados",
          all(x >= 0 for x in order) and order == sorted(order), order)
    check("bloqueado mostra o motivo da evidência",
          "motivo: Condicao de fora: o dono precisa decidir X" in t, t)
    check("pendente mostra de quem depende", "espera: b-pendente" in t, t)
    check("ação humana aberta aparece no item e no cabeçalho",
          "ação humana: validar à mão no navegador" in t
          and "esperam você: 2 itens parados (c-travado, e-espera)" in t, t)
    check("concluído sai numa linha só, sem evidência",
          "commit abc" not in t and "1. a-feito — item a-feito" in t, t)


def test_filter_by_status(base):
    d = git_repo(base, "filtro")
    write_queue(d, ITEMS)
    _, out = status_json(d, "fila", "--status", "pending")
    check("--status pending traz só os pendentes",
          [i["id"] for i in out["items"]] == ["b-pendente", "e-espera"])
    check("mas a contagem continua da fila inteira", out["total"] == 5)
    r = run(d, "status", "fila", "--status", "xyz", "--repo", ".")
    check("status desconhecido é recusado", r.returncode != 0)


def test_omitted_name(base):
    d = git_repo(base, "uma")
    write_queue(d, ITEMS, "unica")
    r, out = status_json(d)
    check("com uma fila só, usa ela", r.returncode == 0
          and out and out["program"] == "unica", r.stderr)
    write_queue(d, ITEMS[:1], "outra")
    r, _ = status_json(d)
    check("com duas, recusa e nomeia as duas", r.returncode == 2
          and "outra" in r.stderr and "unica" in r.stderr, r.stderr)
    empty = git_repo(base, "vazio")
    r, _ = status_json(empty)
    check("sem fila, recusa apontando o /common:queue", r.returncode == 2
          and "/common:queue" in r.stderr, r.stderr)


def test_does_not_touch_the_file(base):
    d = git_repo(base, "leitura")
    target = write_queue(d, ITEMS)
    before = (target.read_bytes(), target.stat().st_mtime_ns)
    run(d, "status", "fila", "--repo", ".")
    status_json(d, "fila")
    check("o plan.yaml sai byte a byte igual e sem ser tocado",
          (target.read_bytes(), target.stat().st_mtime_ns) == before)


def test_refuses_wave_plan(base):
    d = git_repo(base, "ondas")
    target = d / ".claude" / "programs" / "ondas" / "plan.yaml"
    target.parent.mkdir(parents=True)
    target.write_text(yaml.safe_dump({"schema_version": 2,
                                    "mode": "parallel-waves", "waves": []}))
    r, _ = status_json(d, "ondas")
    check("plano de ondas sai com código 3", r.returncode == 3, r.stderr)


def test_from_inside_a_worktree_reads_the_main_clone(base):
    d = git_repo(base, "principal")
    write_queue(d, ITEMS)
    wt = Path(base) / "wt-fila"
    subprocess.run(["git", "-C", str(d), "worktree", "add", "-q", "--detach",
                    str(wt)], check=True)
    r, out = status_json(wt, "fila")
    check("a worktree enxerga a fila do clone principal",
          r.returncode == 0 and out and out["total"] == 5, r.stderr)


def test_command_contract(_base):
    t = CMD.read_text(encoding="utf-8")
    check("o comando chama o `cepa-plan status`",
          'bin/cepa-plan" status $ARGUMENTS' in t)
    check("manda mostrar a saída na íntegra", "**in full**" in t)
    check("declara que só lê", "**Read-only.**" in t)
    check("o título é /common:queue-status", "# /common:queue-status" in t)


def test_old_name_fila_is_deprecated_alias(_base):
    t = (REPO / "common" / "commands" / "fila.md").read_text(encoding="utf-8")
    check("/common:fila continua existindo como alias deprecado",
          "# /common:fila (deprecated)" in t)
    check("...e manda rodar /common:queue-status com os mesmos argumentos",
          "/common:queue-status" in t and "$ARGUMENTS" in t)
    check("...sem manter segunda cópia dos passos", "cepa-plan" not in t)


def test_one_item_in_full(base):
    d = git_repo(base, "um-item")
    longo = "validar à mão no navegador. " + "detalhe " * 60 + "FIM-DO-TEXTO"
    write_queue(d, ITEMS[:4] + [item("e-espera", blocked_by=["b-pendente"],
                                     human_pending=longo)])
    r = run(d, "status", "fila", "e-espera", "--repo", ".")
    t = r.stdout
    check("item sozinho sai com código 0", r.returncode == 0, r.stderr)
    check("mostra a ação humana inteira, sem corte",
          "FIM-DO-TEXTO" in t and "…" not in t, t)
    check("mostra o porquê e a espera", "porque e-espera" in t
          and "b-pendente" in t, t)
    check("não lista os outros itens", "item a-feito" not in t, t)
    r, out = status_json(d, "fila", "c-travado")
    check("--json traz um item só, com a evidência",
          out and out["item"]["id"] == "c-travado"
          and out["item"]["evidence"].startswith("Condicao de fora"), r.stderr)
    r = run(d, "status", "fila", "nao-existe", "--repo", ".")
    check("id desconhecido sai com 2 e lista os ids",
          r.returncode == 2 and "a-feito" in r.stderr, r.stderr)


def test_one_item_on_the_terminal_screen(base):
    import os, re
    d = git_repo(base, "um-item-tela")
    longo = "validar à mão. " + "detalhe " * 60 + "FIM-DO-TEXTO"
    write_queue(d, [item("a"), item("b", human_pending=longo)])
    env = dict(os.environ, CEPA_COR="sempre", COLUMNS="80")
    r = subprocess.run([sys.executable, str(CEPA_PLAN), "status", "fila", "b",
                        "--repo", "."], capture_output=True, text=True,
                       cwd=str(d), env=env)
    plain = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout)
    check("tela decorada liga (campo em negrito, sem dois-pontos)",
          "\x1b[1mação humana\x1b[0m" in r.stdout
          and "ação humana:" not in plain, r.stdout)
    check("tela decorada traz a ação humana inteira",
          "FIM-DO-TEXTO" in plain and "…" not in plain, plain)
    check("tela decorada não lista os outros itens", "item a" not in plain, plain)
    check("tela decorada esconde campo vazio", "None" not in plain, plain)


def test_reserved_item_shows_owner(base):
    d = git_repo(base, "um-item-reservado")
    write_queue(d, [item("a"), item("b")])
    r = run(d, "start", "fila", "a", "--repo", ".")
    check("start reserva o item", r.returncode == 0, r.stderr)
    r = run(d, "status", "fila", "a", "--repo", ".")
    check("item reservado mostra a sessão dona",
          "reservado:" in r.stdout and "desde" in r.stdout, r.stdout)
    _, out = status_json(d, "fila", "a")
    check("--json traz claimed_by", bool(out and out["item"]["claimed_by"]), out)


def test_help_documents_item(base):
    r = run(base, "status", "--help")
    check("status --help documenta o id",
          "shows only this item" in r.stdout, r.stdout)
    r = run(base, "--help")
    check("--help geral tem o exemplo", "cepa-plan status wego S3" in r.stdout,
          r.stdout)


def test_one_item_shows_every_filled_field(base):
    d = git_repo(base, "um-item-campos")
    write_queue(d, [item("a", title="TITULO-A", evidence="EVID-A",
                         owner_summary="RESUMO-A")])
    r = run(d, "status", "fila", "a", "--repo", ".")
    t = r.stdout
    check("mostra título, evidência e resumo para o dono",
          all(x in t for x in ("TITULO-A", "EVID-A", "RESUMO-A")), t)
    check("item pronto diz que o próximo cepa-until pega",
          "pronto: o próximo cepa-until pega" in t, t)
    check("campo vazio não aparece", "None" not in t
          and "espera:" not in t and "ação humana:" not in t, t)


def main():
    with tempfile.TemporaryDirectory() as base:
        for fn in (test_lists_all_items_in_recorded_order,
                   test_text_groups_and_shows_reason_and_human_action,
                   test_filter_by_status,
                   test_one_item_in_full,
                   test_one_item_on_the_terminal_screen,
                   test_reserved_item_shows_owner,
                   test_help_documents_item,
                   test_one_item_shows_every_filled_field,
                   test_omitted_name,
                   test_does_not_touch_the_file,
                   test_refuses_wave_plan,
                   test_from_inside_a_worktree_reads_the_main_clone,
                   test_command_contract,
                   test_old_name_fila_is_deprecated_alias):
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
