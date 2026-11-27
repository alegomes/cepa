#!/usr/bin/env python3
"""The final report is a set of panels and the merge shows up once — CS-6 of
docs/spec/fim-do-until-sem-espera.md.

Run with `python3 tests/test_cepa_until_final_report.py`.
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    FAILURES, check, fake_claude, item, build_repo, run_until)
from test_cepa_until_run_branch import WORKS, VERIFY, plan_of  # noqa: E402
from test_cepa_until_land import state, with_origin  # noqa: E402
from test_cepa_until_decide import load_module  # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;]*m")
LONG_REASON = ("the keycloak realm refuses the token " * 11)[:400]


def stuck_run(tmp, extra_env=None, args=(), ids=("a1", "a2")):
    """The first item delivers a commit, the second ends `blocked` with a
    400-character reason."""
    root = build_repo(tmp, [item(ids[0]), item(ids[1])])
    body = WORKS.replace(
        "marca(ident, status='done', evidence='ok')\n",
        f"if ident == {ids[1]!r}:\n"
        f"    marca(ident, status='blocked', evidence={LONG_REASON!r})\n"
        "else:\n"
        "    marca(ident, status='done', evidence='ok')\n")
    binv = fake_claude(tmp, body)
    env = {"COLUMNS": "100"}
    env.update(extra_env or {})
    p, _ = run_until(root, binv, plan_of(root),
                     ["--for", "2h", "--verify", VERIFY, "--no-analysis", *args],
                     extra_env=env)
    return root, p, ANSI.sub("", p.stdout + p.stderr)


def test_the_end_of_a_run_with_a_long_reason_fits_the_terminal_and_names_the_merge_once():
    with tempfile.TemporaryDirectory() as tmp:
        _, p, out = stuck_run(tmp)
        check("a run termina", p.returncode == 0, out[-1500:])
        check("o motivo de 400 caracteres existe no ambiente do teste",
              len(LONG_REASON) == 400)
        # The end of the run: from the header panel on (the launch card and the
        # per-item step lines above it are not part of the report).
        end = out[out.find("ended at"):]
        check("o relatório do fim começa no cabeçalho", "ended at" in out)
        wide = [l for l in end.splitlines() if len(l) > 100
                and not l.startswith("   side branch:")]
        check("nenhuma linha do fim passa de 100 colunas", not wide,
              "\n".join(wide[:5]))
        check("merge into aparece exatamente uma vez",
              out.count("merge into") == 1, f"{out.count('merge into')}x\n" + out[-2500:])
        for gone in ("Actions:", "Left with you", "waiting on you"):
            check(f"a tela não traz {gone!r}", gone not in out, out[-2500:])


def end_of(out):
    """The report: from the line of the header panel on."""
    at = out.find("ended at")
    report = out[out.rfind("\n", 0, at) + 1:]
    # The three-part block (`What happened:` ...) comes after the paths line and
    # has its own test (test_cepa_run_closing_screen.py); the full side-branch
    # name in it is never cut to the width.
    return report.split("\nWhat happened:")[0] + "\n"


def test_panels_come_in_order_and_the_paths_line_closes_the_report():
    with tempfile.TemporaryDirectory() as tmp:
        _, p, out = stuck_run(tmp)
        end = end_of(out)
        marks = [end.find(m) for m in ("── ended at", "── Items (2)", "── Next")]
        check("sem terminal: cabeçalho, Items e Next, nessa ordem",
              all(m >= 0 for m in marks) and marks == sorted(marks), end)
        lines = [l for l in end.splitlines() if l.strip()]
        check("a última linha traz os caminhos do registro e do log",
              "{jsonl,log}" in lines[-1] and lines[-1].lstrip().startswith("record, log:"),
              lines[-1])
        check("...e o painel Next é o último painel",
              end.rfind("── ") == end.find("── Next"), end)
        check("...e cabe em 100 colunas", len(lines[-1]) <= 100, lines[-1])
        check("sem terminal não há borda nem cor",
              "┌" not in end and "│" not in end and "\x1b[" not in p.stdout[
                  p.stdout.find("ended at"):], end)


def test_header_has_the_window_the_totals_and_no_waiting_on_you_wording():
    with tempfile.TemporaryDirectory() as tmp:
        _, _, out = stuck_run(tmp)
        end = end_of(out)
        header = end.split("── Items")[0]
        check("o cabeçalho traz o motivo da parada", "end-of-queue" in header, header)
        check("...a janela com a barra", re.search(r"window \d\d:\d\d → \d\d:\d\d  [▰▱]{24}",
                                                    header) is not None, header)
        check("...e uma linha de totais com entregues, travados e para você",
              re.search(r"1 delivered · 1 stuck · 0 no progress · 1 for you",
                        header) is not None, header)
        check("...e uma linha de commits que separa o branch da run da lateral",
              re.search(r"commits: 1 on the run branch · 1 on 1 side branch\(es\)",
                        header) is not None, header)


def test_items_panel_aligns_the_id_column_and_cuts_the_reason_but_not_the_state():
    with tempfile.TemporaryDirectory() as tmp:
        root, _, out = stuck_run(tmp, ids=("a1", "alfa-longo-2"))
        rows = [l for l in end_of(out).split("── Items")[1].split("── Next")[0]
                .splitlines() if l.startswith("   - ")]
        check("uma linha por item", len(rows) == 2, str(rows))
        cols = {l.index("delivered") if "delivered" in l else l.index("`blocked`")
                for l in rows}
        check("o motivo começa na mesma coluna nas duas linhas", len(cols) == 1,
              "\n".join(rows))
        stuck = rows[1]
        check("o motivo longo é cortado com reticências e o fim fica",
              "…" in stuck and len(stuck) <= 100, stuck)
        itens = state(root).get("itens") or []
        full = [i["texto"] for i in itens if i["id"] == "alfa-longo-2"]
        check("o estado grava o motivo sem corte (mais longo que a linha da tela)",
              full and len(full[0]) > len(stuck) and "…" not in full[0], str(full))


def test_borders_exist_with_color_always_and_not_with_no_color():
    with tempfile.TemporaryDirectory() as tmp:
        _, p, out = stuck_run(tmp, extra_env={"CEPA_RUN_COLOR": "sempre"})
        end = end_of(out)
        for title in ("┌─ ended at", "┌─ Items (2)", "┌─ Next"):
            check(f"com cor sempre: {title}", title in end, end[-1500:])
        check("...com a base └─ e a borda │",
              end.count("└─") == 3 and "│ " in end, end[-1500:])
        check("...e a cor está na saída crua", "\x1b[" in p.stdout[p.stdout.find(
            "ended at") - 30:], p.stdout[-300:])
        wide = [l for l in end.splitlines() if len(l) > 100]
        check("...e nenhuma linha passa de 100 colunas", not wide, "\n".join(wide))
        check("com cor sempre, o merge também aparece uma vez",
              out.count("merge into") == 1, end)
    with tempfile.TemporaryDirectory() as tmp:
        _, p, out = stuck_run(tmp, extra_env={"NO_COLOR": "1"})
        raw = p.stdout[p.stdout.find("ended at"):]
        check("com NO_COLOR: texto simples, sem borda nem cor",
              "┌" not in raw and "│" not in raw and "\x1b[" not in raw
              and "── Items (2)" in raw, raw[:600])


def test_decisions_are_grouped_by_item_with_the_commit():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        body = WORKS.replace(
            "marca(ident, status='done', evidence='ok')\n",
            "sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], "
            "text=True).strip()\n"
            "marca(ident, status='done', evidence='ok', decisions=[\n"
            "    {'texto': 'usei o formato curto em ' + ident, 'commit': sha},\n"
            "    {'texto': 'nomeei o campo por extenso em ' + ident, "
            "'commit': sha}])\n")
        binv = fake_claude(tmp, body)
        p, _ = run_until(root, binv, plan_of(root),
                         ["--for", "2h", "--verify", VERIFY, "--no-analysis"],
                         extra_env={"COLUMNS": "100"})
        out = ANSI.sub("", p.stdout)
        end = end_of(out)
        panel = end.split("── Decisions")[1].split("── Next")[0]
        rows = [l for l in panel.splitlines() if "decided" in l and "· commit" in l]
        check("o painel Decisions (4) existe entre Items e Next",
              "── Decisions (4)" in end
              and end.find("── Items") < end.find("── Decisions") < end.find("── Next"),
              end)
        check("quatro linhas, uma por decisão", len(rows) == 4, str(rows))
        check("o id aparece só na primeira linha de cada item",
              [r[3:5].strip() for r in rows] == ["a1", "", "a2", ""], str(rows))
        sha = subprocess.run(["git", "log", "--format=%H", "-n", "1", "--grep", "^a1$",
                              "--all"], cwd=root, capture_output=True, text=True).stdout.strip()
        check("cada linha termina com o commit",
              all(re.search(r"· commit [0-9a-f]{10}$", r) for r in rows)
              and sha[:10] in rows[0], str(rows))
        check("...e diz decided", all("decided" in r for r in rows), str(rows))
        check("o estado não ganhou campo novo para isso",
              "decisoes" not in state(root), str(sorted(state(root))))


def test_a_long_decision_is_cut_but_its_commit_stays_whole():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        body = WORKS.replace(
            "marca(ident, status='done', evidence='ok')\n",
            "sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], "
            "text=True).strip()\n"
            "marca(ident, status='done', evidence='ok', decisions=[\n"
            "    {'texto': 'escolhi o caminho mais longo possivel ' * 12, "
            "'commit': sha}])\n")
        binv = fake_claude(tmp, body)
        p, _ = run_until(root, binv, plan_of(root),
                         ["--for", "2h", "--verify", VERIFY, "--no-analysis"],
                         extra_env={"COLUMNS": "60"})
        out = ANSI.sub("", p.stdout)
        panel = end_of(out).split("── Decisions")[1].split("── Next")[0]
        rows = [l for l in panel.splitlines() if l.startswith("   a1 ") and "decided" in l]
        sha = subprocess.run(["git", "log", "--format=%H", "-n", "1", "--grep", "^a1$",
                              "--all"], cwd=root, capture_output=True, text=True).stdout.strip()
        check("uma linha de decisão", len(rows) == 1, str(rows))
        check("a linha cabe em 60 colunas", all(len(r) <= 60 for r in rows), str(rows))
        check("o texto foi cortado (tinha mais de 400 caracteres)",
              all("…" in r for r in rows), str(rows))
        check("o commit continua inteiro no fim da linha",
              bool(sha) and all(r.endswith("· commit " + sha[:10]) for r in rows),
              f"{sha[:10]} {rows}")


def test_next_says_why_the_merge_is_not_recommended_and_only_a_clean_run_recommends():
    with tempfile.TemporaryDirectory() as tmp:
        _, _, out = stuck_run(tmp)
        nxt = end_of(out).split("── Next")[1]
        check("run não limpa: a linha diz por que não recomenda",
              "not recommended: a2 is stuck" in nxt, nxt)
        check("...e o merge continua oferecido, com o comando",
              re.search(r"1\. merge into `main`: cepa run land fila/\S+ --yes", nxt),
              nxt)
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, WORKS)
        p, _ = run_until(root, binv, plan_of(root),
                         ["--for", "2h", "--verify", VERIFY, "--no-analysis"])
        nxt = p.stdout.split("── Next")[1]
        check("run limpa: recomenda, sem 'not recommended'",
              "recommended: the run is clean" in nxt and "not recommended" not in nxt,
              nxt)
        check("...e não há pergunta do dono", "owner question" not in nxt, nxt)


def test_next_is_numbered_merge_then_owner_questions_then_reinstall():
    m = load_module()
    m.not_clean_reason = lambda *a, **k: "a2 is stuck"
    st = {"estado": "esperando-dono",
          "acoes": [{"id": "aterrissar", "destino": "main", "frase": "x"}],
          "itens": [{"id": "a2", "desfecho": "travado", "texto": "t"}],
          "fica_com_voce": [
              {"id": "a2", "texto": "t"},
              {"id": "reinstalar-plugin", "texto": "the run branch changes hooks"}]}
    report = {"deferred": [{"id": "a2", "reason": "human_pending",
                            "question": "Libero o acesso?"}]}
    rows = m.next_rows(Path("/nao/existe"), "fila", "r1", st, "/nao/existe", report)
    lines = ["".join(sg[1] for sg in r) for r in rows]
    heads = [l for l in lines if re.match(r"\d\. ", l)]
    check("três itens numerados, na ordem merge, perguntas, reinstalação",
          len(heads) == 3 and heads[0].startswith("1. merge into `main`: cepa run land "
                                                  "fila/r1 --yes")
          and heads[1].startswith("2. 1 owner question(s): a2")
          and heads[2].startswith("3. after the merge, run `bin/install.sh`"),
          "\n".join(lines))
    check("a pergunta e o comando decide vêm sob o item 2",
          lines.index("   a2: Libero o acesso?") < lines.index(
              "   cepa run decide fila/r1 (one by one, in a terminal)")
          and lines.index(heads[1]) < lines.index("   a2: Libero o acesso?")
          < lines.index(heads[2]), "\n".join(lines))
    check("o motivo de não recomendar vem sob o merge",
          "   not recommended: a2 is stuck" in lines
          and lines.index(heads[0]) < lines.index("   not recommended: a2 is stuck")
          < lines.index(heads[1]), "\n".join(lines))
    st2 = dict(st, estado="aterrissado", fica_com_voce=[])
    lines = ["".join(sg[1] for sg in r) for r in
             m.next_rows(Path("/nao/existe"), "fila", "r1", st2, "/nao/existe", {})]
    check("run que fundiu sozinha diz isso e não oferece o comando",
          lines[0].startswith("1. merged into `main` by this run")
          and not any("cepa run land" in l for l in lines), "\n".join(lines))
    lines = ["".join(sg[1] for sg in r) for r in
             m.next_rows(Path("/nao/existe"), "fila", "r1",
                         {"estado": "encerrado"}, "/nao/existe", {})]
    check("sem nada para o dono, uma linha só",
          lines == ["nothing left for you"], str(lines))


def test_more_than_five_owner_questions_are_counted_not_spelled_out():
    m = load_module()
    report = {"deferred": [{"id": f"q{n}", "reason": "human_pending",
                            "question": f"Pergunta {n}?"} for n in range(1, 9)]}
    rows = m.next_rows(Path("/nao/existe"), "fila", "r1", {"estado": "encerrado"},
                       "/nao/existe", report)
    lines = ["".join(sg[1] for sg in r) for r in rows]
    check("as oito perguntas são contadas e só cinco aparecem por extenso",
          lines[0].startswith("1. 8 owner question(s): q1, q2")
          and "   q5: Pergunta 5?" in lines and "   q6: Pergunta 6?" not in lines
          and "   ... and 3 more, all in `decide`" in lines, "\n".join(lines))


def test_auto_landed_run_says_so_in_next_and_names_no_second_merge():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        with_origin(root)
        binv = fake_claude(tmp, WORKS)
        p, _ = run_until(root, binv, plan_of(root),
                         ["--for", "2h", "--verify", VERIFY, "--no-analysis",
                          "--auto-land"])
        nxt = p.stdout.split("── Next")[-1]
        check("o estado terminou aterrissado", state(root).get("estado") == "aterrissado",
              p.stdout[-1500:])
        check("o Next diz que a run fundiu sozinha",
              "1. merged into `main` by this run (--auto-land): nothing to do" in nxt, nxt)
        check("...e não oferece o comando do merge", "cepa run land" not in nxt, nxt)


def test_a_long_item_id_and_wide_terminal_values_still_fit():
    for cols in ("60", "120"):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, out = stuck_run(tmp, extra_env={"COLUMNS": cols})
            end = end_of(out)
            # (the `commit:` line is `commit_run_end`'s, printed between the panels)
            wide = [l for l in end.splitlines()
                    if len(l) > int(cols) and not l.startswith("   commit:")]
            check(f"COLUMNS={cols}: nenhuma linha do fim passa da largura", not wide,
                  "\n".join(wide[:4]))
            check(f"COLUMNS={cols}: o merge aparece uma vez", out.count("merge into") == 1,
                  end)


def test_paths_line_is_whole_when_it_fits_and_braced_when_it_does_not():
    m = load_module()
    entries = [("record", "r/2026.jsonl"), ("log", "r/2026.log"),
               ("analysis", "r/2026.review.md")]
    check("cabendo, cada caminho por inteiro",
          m.paths_line(entries, 100)
          == "record: r/2026.jsonl · log: r/2026.log · analysis: r/2026.review.md")
    long_dir = ".claude/programs/fila/until"
    entries = [("record", f"{long_dir}/2026-11-19-1725.jsonl"),
               ("log", f"{long_dir}/2026-11-19-1725.log"),
               ("analysis", f"{long_dir}/2026-11-19-1725.review.md")]
    line = m.paths_line(entries, 97)
    check("não cabendo, a pasta e o nome saem uma vez, com as extensões em chaves",
          line == "record, log, analysis: .claude/programs/fila/until/"
                  "2026-11-19-1725.{jsonl,log,review.md}" and len(line) <= 97, line)
    check("e nunca passa da largura", len(m.paths_line(entries, 40)) <= 40)


def test_an_item_already_asked_in_this_run_is_named_but_its_question_is_not_repeated():
    m = load_module()
    asked_only = {"deferred": [], "asked": ["a1"]}
    lines = ["".join(sg[1] for sg in r) for r in
             m.next_rows(Path("/nao/existe"), "fila", "r1", {"estado": "encerrado"},
                         "/nao/existe", asked_only)]
    check("só perguntado: item numerado com o comando para responder de novo",
          lines[0] == "1. already asked in this run, still open: a1"
          and lines[1] == "   cepa run decide fila/r1 (to answer again)", "\n".join(lines))
    both = {"deferred": [{"id": "b2", "reason": "human_pending", "question": "Libero?"}],
            "asked": ["a1"]}
    lines = ["".join(sg[1] for sg in r) for r in
             m.next_rows(Path("/nao/existe"), "fila", "r1", {"estado": "encerrado"},
                         "/nao/existe", both)]
    check("com outra pergunta aberta: uma linha a mais, sem repetir a pergunta do a1",
          "   already asked in this run: a1" in lines
          and lines[0].startswith("1. 1 owner question(s): b2"), "\n".join(lines))


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            fn()
    sys.exit(1 if FAILURES else 0)
