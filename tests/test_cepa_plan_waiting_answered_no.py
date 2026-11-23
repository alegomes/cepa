#!/usr/bin/env python3
"""`cepa plan waiting` shows routes the owner already answered "não" only as a
count per queue, with the date of the last one and the command that revisits
them (spec docs/spec/decisoes-de-todas-as-filas.md, CS-3; Q4: a route answered
"no" is not asked again, and is not listed as a line either).

"Answered no" is the rule `cepa-until decide` already uses (one reader,
`_ownertext.last_owner_no`): the owner's LAST answer, which `cepa-plan answer`
prepends to the evidence, is a "não".

Against the real CLI, in a temporary git repo:

  - CS-3 red test: `a1` with a "não" of 2026-11-18 is not a line, and the
    queue prints "1 que você já respondeu \"não\" (última em 18/11)" with
    `cepa until decide a`
  - the count and the date are the queue's: two "não", the latest wins; a
    route answered "sim" later, or a "não" further down, is still a line
  - a queue holding only answered routes still shows its section
  - a blocked item answered "não" counts too (same owner reasons as decide)
  - `--json` carries `respondidas_nao` per queue, and `total_itens` counts
    only the lines
  - a queue with nothing answered "não" prints no count line
  - the latest date wins even when the first answered route is the oldest
  - the section and the command use the queue's own name, not its folder
  - "nãox" is not a "não" (the word must end there)
  - `waiting --help` tells the answered routes are only counted

Run with `python3 tests/test_cepa_plan_waiting_answered_no.py`.
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
FAILURES = []


def check(name, cond, detail=""):
    print(f"  ok  {name}" if cond else f"FAIL  {name}  {detail}")
    if not cond:
        FAILURES.append(name)


def run(repo, *args):
    return subprocess.run([sys.executable, str(CEPA_PLAN), *args],
                          capture_output=True, text=True, cwd=str(repo))


def answered(date, text="não: deixa como está", older=""):
    """Evidence as `cepa-plan answer` leaves it: the last answer first."""
    ev = f"Resposta do dono em {date}: {text}"
    return ev + (f"\n\n{older}" if older else "\n\nevidência original")


def item(ident, status="pending", **extra):
    it = {"id": ident, "title": f"item {ident}", "why": "porque",
          "status": status, "blocked_by": [], "human_pending": None,
          "evidence": None}
    it.update(extra)
    return it


def route(ident, status="pending", **extra):
    return item(ident, status, human_pending=f"Fazer {ident} à mão",
                owner_question=f"Faço {ident} à mão?", **extra)


def write_queue(root, name, items, header=None):
    d = root / ".claude" / "queues" / name
    d.mkdir(parents=True)
    plan = {"schema_version": 2, "mode": "single-track", "queue": header or name,
            "source": "teste", "items": items}
    (d / "queue.yaml").write_text(yaml.safe_dump(plan, allow_unicode=True),
                                  encoding="utf-8")


def git_repo(tmp):
    root = Path(tmp) / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    return root


def section(out, name):
    """The lines of `fila <name>`, up to the next blank line."""
    lines = out.splitlines()
    try:
        i = lines.index(f"fila {name}")
    except ValueError:
        return None
    out_lines = []
    for l in lines[i + 1:]:
        if not l.strip():
            break
        out_lines.append(l)
    return out_lines


def red_test():
    print("CS-3: `a1` respondido \"não\" em 2026-11-18")
    with tempfile.TemporaryDirectory() as tmp:
        root = git_repo(tmp)
        write_queue(root, "a", [route("a1", evidence=answered("2026-11-18")),
                                route("a2")])
        p = run(root, "waiting")
        check("sai com 0", p.returncode == 0, p.stderr)
        sec = section(p.stdout, "a") or []
        check("`a1` não aparece como linha",
              not any(" a1 " in l for l in sec), p.stdout)
        check("`a2`, sem resposta, continua como linha",
              any(" a2 — " in l for l in sec), p.stdout)
        check("a contagem com a data e o comando para revisitar",
              any("1 que você já respondeu \"não\" (última em 18/11)" in l
                  and "cepa until decide a" in l for l in sec), p.stdout)
        check("a linha exata da contagem",
              "  1 que você já respondeu \"não\" (última em 18/11): para "
              "revisitar, cepa until decide a" in sec, sec)
        check("a contagem vem depois das linhas de item",
              sec and "já respondeu" in sec[-1], sec)
        check("o cabeçalho conta só as linhas",
              p.stdout.startswith("esperam você · 1 filas · 1 itens"), p.stdout)


def latest_and_rules():
    print("contagem da fila: a última data vale; só a ÚLTIMA resposta conta")
    with tempfile.TemporaryDirectory() as tmp:
        root = git_repo(tmp)
        write_queue(root, "a", [
            route("a1", evidence=answered("2026-11-18")),
            route("a2", evidence=answered("2026-11-03", "NAO: depois")),
            route("a3", evidence=answered("2026-11-19", "sim: pode",
                                          older=answered("2026-11-10"))),
            route("a4", evidence="investiguei.\n\n" + answered("2026-11-10")),
            item("a5", "blocked", owner_question="Rodo X à mão?",
                 evidence=answered("2026-11-05")),
        ])
        p = run(root, "waiting")
        sec = section(p.stdout, "a") or []
        check("três respondidos \"não\" (um deles travado), última em 18/11",
              "  3 que você já respondeu \"não\" (última em 18/11): para "
              "revisitar, cepa until decide a" in sec, sec)
        check("um \"sim\" depois de um \"não\" continua como linha",
              any(" a3 — " in l for l in sec), sec)
        check("um \"não\" que não é a última resposta continua como linha",
              any(" a4 — " in l for l in sec), sec)
        check("o travado respondido \"não\" sai das linhas",
              not any(" a5 " in l for l in sec), sec)
        check("`a1` e `a2` saem das linhas",
              not any(" a1 " in l or " a2 " in l for l in sec), sec)


def only_answered_queue():
    print("fila só com rotas respondidas \"não\" ainda mostra a seção")
    with tempfile.TemporaryDirectory() as tmp:
        root = git_repo(tmp)
        write_queue(root, "a", [route("a1", evidence=answered("2026-11-18"))])
        write_queue(root, "b", [route("b1", "done")])
        p = run(root, "waiting")
        check("sai com 0", p.returncode == 0, p.stderr)
        check("a seção `a` existe, com só a contagem",
              section(p.stdout, "a") == [
                  "  1 que você já respondeu \"não\" (última em 18/11): para "
                  "revisitar, cepa until decide a"], p.stdout)
        check("a seção `a` vem antes de `b`",
              0 <= p.stdout.find("fila a\n") < p.stdout.find("fila b\n"),
              p.stdout)
        check("a fila `b` não ganha linha de contagem",
              not any("já respondeu" in l for l in section(p.stdout, "b") or []),
              p.stdout)
        check("o cabeçalho conta as duas filas e um item",
              p.stdout.startswith("esperam você · 2 filas · 1 itens"), p.stdout)
        j = run(root, "waiting", "--json")
        check("--json sai com 0", j.returncode == 0, j.stderr)
        data = json.loads(j.stdout)
        qs = {q["queue"]: q for q in data["filas"]}
        check("--json traz a fila `a` sem itens",
              "a" in qs and qs["a"]["itens"] == [], data)
        check("--json: `respondidas_nao` da fila `a`",
              qs.get("a", {}).get("respondidas_nao") ==
              {"total": 1, "ultima": "2026-11-18",
               "comando": "cepa until decide a"}, qs.get("a"))
        check("--json: `respondidas_nao` nulo na fila sem \"não\"",
              "respondidas_nao" in qs.get("b", {})
              and qs["b"]["respondidas_nao"] is None, qs.get("b"))
        check("--json: total_itens conta só as linhas",
              data["total_itens"] == 1, data)


def dropped_and_done_without_route():
    print("item descartado ou concluído sem rota não conta, mesmo com \"não\"")
    with tempfile.TemporaryDirectory() as tmp:
        root = git_repo(tmp)
        write_queue(root, "a", [
            route("a1", "dropped", evidence=answered("2026-11-18")),
            item("a2", "done", evidence=answered("2026-11-18")),
            item("a3", "pending", evidence=answered("2026-11-18")),
            route("a4"),
        ])
        p = run(root, "waiting")
        sec = section(p.stdout, "a") or []
        check("nenhuma contagem", not any("já respondeu" in l for l in sec), sec)
        check("só `a4` como linha", len(sec) == 1 and " a4 — " in sec[0], sec)


def oldest_first_and_header_name():
    print("a primeira rota respondida é a mais antiga; o nome é o da fila")
    with tempfile.TemporaryDirectory() as tmp:
        root = git_repo(tmp)
        write_queue(root, "pasta", [
            route("a1", evidence=answered("2026-11-02")),
            route("a2", evidence=answered("2026-11-19")),
            route("a3", evidence=answered("2026-11-07")),
        ], header="minha-fila")
        p = run(root, "waiting")
        check("a seção usa o nome da fila, não o da pasta",
              section(p.stdout, "minha-fila") is not None
              and section(p.stdout, "pasta") is None, p.stdout)
        check("a data é a mais recente (19/11), não a da primeira rota",
              section(p.stdout, "minha-fila") == [
                  "  3 que você já respondeu \"não\" (última em 19/11): para "
                  "revisitar, cepa until decide minha-fila"], p.stdout)
        data = json.loads(run(root, "waiting", "--json").stdout)
        check("--json: última e comando com o nome da fila",
              data["filas"][0]["respondidas_nao"] ==
              {"total": 3, "ultima": "2026-11-19",
               "comando": "cepa until decide minha-fila"}, data)


def word_must_end():
    print("\"nãox\" não é um \"não\"")
    with tempfile.TemporaryDirectory() as tmp:
        root = git_repo(tmp)
        write_queue(root, "a", [
            route("a1", evidence=answered("2026-11-18", "nãoxyz: outra coisa")),
            route("a2", evidence=answered("2026-11-18", "naozinho")),
        ])
        p = run(root, "waiting")
        sec = section(p.stdout, "a") or []
        check("as duas rotas continuam como linhas",
              any(" a1 — " in l for l in sec) and any(" a2 — " in l for l in sec),
              sec)
        check("nenhuma contagem", not any("já respondeu" in l for l in sec), sec)


def help_tells():
    print("`waiting --help` explica a contagem")
    with tempfile.TemporaryDirectory() as tmp:
        root = git_repo(tmp)
        p = run(root, "waiting", "--help")
        flat = " ".join(p.stdout.split())
        check("sai com 0", p.returncode == 0, p.stderr)
        check("a ajuda diz que a rota respondida \"não\" só é contada",
              'A route whose last answer was "não" is not a line' in flat
              and "with the date of the last one and the command that "
                  "revisits them" in flat, p.stdout)
        check("a ajuda nomeia `respondidas_nao`",
              "`respondidas_nao` in --json" in flat, p.stdout)


def main():
    red_test()
    oldest_first_and_header_name()
    word_must_end()
    help_tells()
    latest_and_rules()
    only_answered_queue()
    dropped_and_done_without_route()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        return 1
    print("\ntodos passaram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
