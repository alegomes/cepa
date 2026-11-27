#!/usr/bin/env python3
"""cepa-run — the closing screen says what happened, what is pending and what to
run (feedback fb-20261126-4 and fb-20261126-6, run all/2026-11-26-0838).

In that run one item had 39 commits on a side branch, the supervisor's full build
rejected it on two tests, and the screen said `RED (exited 1)`, `0 commit(s)`,
"1 owner question(s)" (the analysis said 2 decisions and 4 tasks) and, for the
commit of the run records, git's generic hint instead of the cause. Contract:

  - the screen ends with three parts, in this order: `What happened:`,
    `Pending for you:` and `Run now:` (one command, written `cepa <sub>`);
  - the pending count is the one the `<run>.review.md` gives; with no analysis the
    block still comes, from the run's own record, and says the analysis is missing;
  - a build rejection shows the failed tests and the first line of each, read
    from the build output in the `.log` (Maven surefire, pytest, unittest, this
    repo's `FAIL` lines; the last lines when nothing matches);
  - the commit count separates the run branch from side branches and the full
    side-branch name is printed, whatever the terminal width;
  - the commit of the run records leaves out what git ignores, says which and
    why, and the by-hand command it suggests exits 0 in a repo that ignores
    `.claude/*` with the queue file tracked.

Run with `python3 tests/test_cepa_run_closing_screen.py`.
"""

import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_cepa_until as base  # noqa: E402
from test_cepa_until import check, fake_claude, item, ledger_of, build_repo, run_until  # noqa: E402
from test_cepa_until_run_branch import WORKS, plan_of  # noqa: E402

FAILURES = base.FAILURES

LONG_ID = "etapa-1-c1-49-sugestao-de-especialidade-do-medico-pelo-cbo"
SURE_FIRE = ("[ERROR]   RotasSimuladasMarcaE2ETest.contagemDoContrato:89 "
             "operacoes do contrato ==> expected: <59> but was: <63>")
# Fake full build: red, in Maven's words, when the item left `quebra.txt`.
MAVEN_VERIFY = (f"if [ -f quebra.txt ]; then echo '[INFO] Running tests'; "
                f"echo '[ERROR] Failures: '; echo '{SURE_FIRE}'; "
                "echo '[ERROR]   OutroE2ETest.passo1:12 rotas ==> expected: <59> "
                "but was: <63>'; echo '[ERROR] Tests run: 2111, Failures: 2'; "
                "exit 1; fi")

REVIEW = ("# run review\\n\\nThe item is finished on a side branch.\\n\\n"
          "**For you:** 2 decisions and 4 tasks.\\n\\n### Technical detail\\n\\nx\\n\\n"
          "```json cepa-decisoes\\n{\\\"itens\\\": []}\\n```")

WITH_REVIEW = (
    "if any('run-review' in a for a in ARGS):\n"
    f"    print('{REVIEW}')\n"
    "    sys.exit(0)\n"
    + WORKS)


def red_run(tmp, analysis=True):
    root = build_repo(tmp, [item(LONG_ID)])
    binv = fake_claude(tmp, WITH_REVIEW)
    args = ["--for", "2h", "--verify", MAVEN_VERIFY]
    if analysis:
        args.append("--com-analise")
    p, _ = run_until(root, binv, plan_of(root), args,
                     extra_env={"FAKE_QUEBRA": LONG_ID, "COLUMNS": "80"})
    branch = [e for e in ledger_of(root) if e["evento"] == "run_start"][0]["branch"]
    return root, p, branch


def block_of(out):
    """The closing block: from `What happened:` to the end of the screen."""
    at = out.find("What happened:")
    return out[at:] if at >= 0 else ""


def test_red_item_ends_with_the_three_part_block():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, branch = red_run(tmp)
        out = p.stdout
        block = block_of(out)
        i1, i2, i3 = (block.find(k) for k in
                      ("What happened:", "Pending for you:", "Run now:"))
        check("o bloco tem as três partes, nesta ordem", 0 <= i1 < i2 < i3,
              out[-1500:])
        check("o bloco é a última coisa da tela: depois do comando só a frase que o explica",
              all(l.startswith("   ")
                  for l in out[out.find("Run now:"):].rstrip().splitlines()[1:]),
              out[-600:])
        side = f"{branch}-vermelho-{LONG_ID}"
        check("a lateral aparece inteira, sem corte pela largura",
              len(side) > 80 and f"side branch: {side}" in block, block)
        check("o bloco diz que nada entrou no branch da run",
              "Nothing entered the run branch" in block, block)
        check("a contagem separa branch da run e lateral",
              "commits: 0 on the run branch" in out
              and "on 2 side branch(es)" in out, out[-2500:])
        check("a linha do branch da run não diz mais 'no commits, removed'",
              "no commits, removed" not in out, out)


def test_the_count_comes_from_the_review_and_the_command_is_cepa_run():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, branch = red_run(tmp)
        block = block_of(p.stdout)
        check("o pendente repete a contagem do review.md",
              "Pending for you: 2 decisions and 4 tasks" in block, block)
        run_id = branch.split("/", 1)[1]
        check("um comando só, escrito como `cepa run decide`",
              f"Run now: cepa run decide fila/{run_id}" in block
              and block.count("Run now:") == 1, block)
        check("o bloco não usa o nome antigo do comando",
              "cepa-run" not in block and "cepa-until" not in block, block)


def test_next_panel_and_the_block_state_the_same_count_and_spell_cepa_run():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, branch = red_run(tmp)
        out = p.stdout
        nxt = out[out.find("── Next"):]
        panel = nxt[:nxt.find("What happened:")]
        block = block_of(out)
        check("o painel Next traz a contagem da análise",
              "2 decisions and 4 tasks" in panel, panel)
        check("...a mesma que o 'Pending for you'",
              "Pending for you: 2 decisions and 4 tasks" in block, block)
        check("...sem o número da fila ('1 owner question') ao lado",
              "1 owner question" not in nxt, nxt)
        check("o painel ainda lista a pergunta que a fila sabe nomear",
              f"{LONG_ID}:" in panel, panel)
        check("o bloco não traz mais a nota sobre o painel",
              "the Next panel above" not in block, block)
        check("de `── Next` até o fim não há `cepa-run`", "cepa-run" not in nxt, nxt)
        run_id = branch.split("/", 1)[1]
        check("o painel manda rodar `cepa run decide`",
              f"cepa run decide fila/{run_id}" in panel, panel)


def test_without_the_analysis_the_block_still_comes_and_says_so():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, branch = red_run(tmp, analysis=False)
        block = block_of(p.stdout)
        check("o bloco sai mesmo sem análise", "Pending for you:" in block
              and "Run now:" in block, p.stdout[-1500:])
        check("...e diz que a análise falta",
              "the analysis is missing" in block, block)
        check("...com a lateral inteira", f"{branch}-vermelho-{LONG_ID}" in block,
              block)


def test_the_failed_tests_and_their_first_line_are_on_the_screen():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, branch = red_run(tmp)
        out = p.stdout
        check("o painel traz o teste que falhou e a mensagem",
              "RotasSimuladasMarcaE2ETest.contagemDoContrato:89" in out
              and "expected: <59> but was: <63>" in out, out[-3000:])
        check("...e diz quantos testes falharam",
              "2 test(s) failed in the full build" in " ".join(out.split()),
              out[-3000:])
        events = [e for e in ledger_of(root) if e["evento"] == "verify_vermelho"]
        check("o registro grava as linhas da falha",
              events and any("expected: <59>" in l for l in events[0].get("falhas", [])),
              str(events))


def test_failure_extraction_styles():
    import importlib.machinery
    import importlib.util
    path = str(base.CEPA_UNTIL)
    loader = importlib.machinery.SourceFileLoader("cepa_run_mod", path)
    spec = importlib.util.spec_from_loader("cepa_run_mod", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    n, lines, found = mod.build_failures(
        "[ERROR] Failures: \n[ERROR]   A.b:89 msg ==> expected: <1> but was: <2>\n"
        "[ERROR]   A.b:89 msg ==> expected: <1> but was: <2>\n"
        "[ERROR]   C.d:5 other\n[ERROR] Tests run: 3\n")
    check("surefire: dois testes, sem repetir", n == 2 and found
          and lines[0].startswith("A.b:89"), str((n, lines)))
    n, lines, found = mod.build_failures(
        "..F\n=== short test summary info ===\n"
        "FAILED tests/test_x.py::test_y - AssertionError: 1 != 2\n1 failed\n")
    check("pytest", n == 1 and lines == [
        "FAILED tests/test_x.py::test_y - AssertionError: 1 != 2"], str(lines))
    n, lines, found = mod.build_failures(
        "FAIL: test_a (mod.Case)\n----\nTraceback (most recent call last):\n"
        '  File "x.py", line 3\nAssertionError: 1 != 2\n\nRan 1 test\n')
    check("unittest: nome e a linha do erro", n == 1 and lines == [
        "FAIL: test_a (mod.Case): AssertionError: 1 != 2"], str(lines))
    n, lines, found = mod.build_failures("  ok  a\nFAIL  caso b  detalhe\n")
    check("script do repo: linha FAIL", n == 1 and lines == ["FAIL  caso b  detalhe"],
          str(lines))
    n, lines, found = mod.build_failures("one\n\ntwo\nthree\nfour\nfive\nsix\nseven\n")
    check("sem padrão: as últimas linhas, em número limitado",
          not found and lines == ["two", "three", "four", "five", "six", "seven"],
          str(lines))


# ── the commit of the run records leaves out what git ignores ────────────────

def ignoring_repo(tmp):
    root = build_repo(tmp, [item("a1")])
    (root / ".gitignore").write_text(".claude/*\n", encoding="utf-8")
    git = lambda *a: subprocess.run(["git", *a], cwd=root, capture_output=True,  # noqa: E731
                                    text=True)
    git("add", ".gitignore")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "ignore")
    return root


def test_commit_leaves_out_the_ignored_records_and_says_which():
    with tempfile.TemporaryDirectory() as tmp:
        root = ignoring_repo(tmp)
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        p, _ = run_until(root, binv, plan_of(root), ["--for", "2h"])
        out = p.stdout + p.stderr
        files = subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"],
                               cwd=root, capture_output=True, text=True).stdout.split()
        check("o commit leva só a fila, que é versionada",
              files == [".claude/programs/fila/plan.yaml"], str(files))
        check("a tela diz o que ficou de fora e por quê",
              "left out of the commit because git ignores them" in out
              and ".jsonl" in out and ".gitignore:1: .claude/*" in out, out[-900:])
        check("a dica genérica do git não vira motivo",
              "advice.addIgnoredFile" not in out, out[-900:])


def test_refused_commit_suggests_a_command_that_runs_with_exit_0():
    with tempfile.TemporaryDirectory() as tmp:
        root = ignoring_repo(tmp)
        hook = root / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\necho 'lint: 3 erros' >&2\nexit 1\n")
        hook.chmod(0o755)
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        p, _ = run_until(root, binv, plan_of(root), ["--for", "2h"])
        out = p.stdout + p.stderr
        marker = "to commit by hand: "
        cmds = [l.split(marker, 1)[1].strip() for l in out.splitlines() if marker in l]
        check("a tela traz o comando manual", len(cmds) == 1, out[-900:])
        check("o comando não nomeia arquivo ignorado",
              bool(cmds) and ".jsonl" not in cmds[0] and "plan.yaml" in cmds[0],
              cmds)
        check("o motivo é o do hook, não a dica do git",
              "lint: 3 erros" in out and "advice.addIgnoredFile" not in out,
              out[-900:])
        hook.unlink()
        r = subprocess.run(["sh", "-c", cmds[0]], cwd=tmp, capture_output=True,
                           text=True) if cmds else None
        check("o comando sai com 0", r is not None and r.returncode == 0,
              r and (r.stdout + r.stderr))


def test_pair_check_with_a_green_middle_keeps_the_failure_of_the_red_build():
    """Pair a2+a3 red twice, the middle commit green, a3 returned: the last section
    of the `.log` is then the GREEN middle build, and the screen and the event
    must still name the test of the pair's red build."""
    import test_cepa_run_pair_verify as pv
    original = pv.FAKE_SUITE
    pv.FAKE_SUITE = original.replace(
        "    print('com falha: 1')\n",
        "    print('FAIL  caso-do-par  expected 59 but was 63')\n"
        "    print('com falha: 1')\n")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root, p, seen, led = pv.run(tmp, ["a1", "a2", "a3"], breaks="a3")
    finally:
        pv.FAKE_SUITE = original
    full = p.stdout
    out = " ".join(full[full.find("Why the full build failed"):
                        full.find("Next", full.find("Why the full build failed"))].split())
    check("o meio ficou verde e a3 voltou",
          pv.ev(led, "volta_vermelha", id="a3")
          and not pv.ev(led, "volta_vermelha", id="a2"), str(led)[-600:])
    check("a tela nomeia o teste que falhou no build do par",
          "FAIL caso-do-par expected 59 but was 63" in out
          and "no test name found" not in out, out[-1800:])
    events = pv.ev(led, "verify_vermelho", id="a3")
    check("o evento grava a mesma falha",
          events and any("caso-do-par" in l for l in events[0].get("falhas", [])),
          str(events))


def test_auto_landed_run_says_it_landed_and_offers_no_land_command():
    from test_cepa_until_auto_land import with_origin
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        with_origin(root)
        binv = fake_claude(root.parent, WORKS)
        p, _ = run_until(root, binv, plan_of(root),
                         ["--for", "2h", "--verify", "true", "--no-analysis",
                          "--auto-land"])
        block = block_of(p.stdout)
        check("o bloco diz que a run já fundiu na main",
              "already merged into `main` by this run" in block, p.stdout[-1200:])
        check("...não diz 'not merged' nem manda rodar land",
              "not merged" not in p.stdout and "cepa run land" not in block, block)
        check("...e não há comando a rodar", "Run now: nothing" in block, block)


def _module():
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("cepa_run_mod4", str(base.CEPA_UNTIL))
    spec = importlib.util.spec_from_loader("cepa_run_mod4", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _panel_and_block(for_you, questions):
    """The `Next` panel's owner row and the block's pending/command lines for a
    review whose `**For you:**` line is `for_you`, with `questions` open in the queue."""
    mod = _module()
    with tempfile.TemporaryDirectory() as tmp:
        review = Path(tmp) / "r.review.md"
        review.write_text(f"# review\n\n**For you:** {for_you}\n")
        deferred = [{"id": f"a{i + 1}", "reason": "human_pending",
                     "question": f"pergunta {i + 1}?"} for i in range(questions)]
        rows = mod.next_rows(Path(tmp), "fila", "r1", {}, review,
                             {"deferred": deferred}, review=review)
        panel = [" ".join(t for _c, t, *_r in row) for row in rows]
        block = mod.closing_block("fila", "r1", False, "until/r1", 0, 0, 0, 0, [],
                                  0, review, None, questions, False, [], Path(tmp))
    return panel, block


def _agree(label, for_you, questions, expected_count):
    panel, block = _panel_and_block(for_you, questions)
    owner_row = next((r for r in panel if r.startswith("1. ")), "")
    pending = next((l for l in block if l.startswith("Pending for you:")), "")
    count = pending[len("Pending for you: "):]
    check(f"{label}: a linha do dono no painel tem a contagem esperada",
          expected_count in owner_row, owner_row)
    check(f"{label}: a contagem do painel é a do 'Pending for you'",
          owner_row[len("1. "):].split(": ")[0].strip() == count.strip(),
          f"{owner_row!r} vs {pending!r}")
    check(f"{label}: a linha do dono não diz 'nothing'",
          "nothing" not in owner_row and "nothing" not in pending, owner_row)
    check(f"{label}: o comando é o decide", "Run now: cepa run decide fila/r1" in block,
          str(block))


def test_open_question_with_an_analysis_that_counts_no_decision():
    _agree("análise 'nothing'", "nothing.", 1, "1 owner question(s)")
    _agree("análise '0 decisions and 2 tasks'", "0 decisions and 2 tasks", 1,
           "1 owner question(s) and 2 task(s)")
    _agree("análise '3 tasks.'", "3 tasks.", 1,
           "1 owner question(s) and 3 task(s)")


def test_real_run_with_open_question_and_an_analysis_of_nothing():
    review = ("# run review\\n\\n**For you:** nothing.\\n\\n### Technical detail\\n\\nx")
    body = ("if any('run-review' in a for a in ARGS):\n"
            f"    print('{review}')\n    sys.exit(0)\n" + WORKS)
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item(LONG_ID)])
        binv = fake_claude(tmp, body)
        p, _ = run_until(root, binv, plan_of(root),
                         ["--for", "2h", "--verify", MAVEN_VERIFY, "--com-analise"],
                         extra_env={"FAKE_QUEBRA": LONG_ID, "COLUMNS": "80"})
        out = p.stdout
        nxt = out[out.find("── Next"):]
        panel = nxt[:nxt.find("What happened:")]
        block = block_of(out)
        check("o painel diz a contagem da fila, não 'nothing'",
              "1. 1 owner question(s)" in panel and "nothing" not in panel, panel)
        check("o bloco diz a mesma contagem",
              "Pending for you: 1 owner question(s)" in block, block)
        check("e o comando é o decide", "Run now: cepa run decide fila/" in block,
              block)


def test_analysis_decisions_without_a_nameable_question_still_show_row_and_command():
    panel, block = _panel_and_block("2 decisions and 4 tasks.", 0)
    row = next((r for r in panel if r.startswith("1. ")), "")
    check("d: a linha existe com a frase da análise",
          "2 decisions and 4 tasks (from the analysis)" in row, str(panel))
    check("d: o comando decide aparece", any("cepa run decide fila/r1" in r
                                              for r in panel), str(panel))
    check("d: o bloco manda rodar o decide",
          "Run now: cepa run decide fila/r1" in block, str(block))


def test_a_review_without_a_count_is_not_called_missing():
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("cepa_run_mod2", str(base.CEPA_UNTIL))
    spec = importlib.util.spec_from_loader("cepa_run_mod2", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    with tempfile.TemporaryDirectory() as tmp:
        review = Path(tmp) / "r.review.md"
        review.write_text("# review\n\nno count here\n")
        args = ("fila", "r1", False, "until/r1", 0, 0, 0, 0,
                [("until/r1-vermelho-x", 3), ("until/r1-travado-y", 3)], 4)
        lines = mod.closing_block(*args, review, None, 0, False, [], Path(tmp))
        text = " ".join(lines)
        check("a análise existe sem contagem: o bloco diz a verdade",
              "the analysis exists but gives no count" in text
              and "analysis is missing" not in text, text)
        check("o total de lateral é o informado (união), não a soma",
              "4 commit(s) were saved" in text, text)
        check("a frase vale para vermelho e para tentativas esgotadas",
              "used up their attempts" in text, text)
        lines = mod.closing_block(*args, None, "failed (x)", 0, False, [], Path(tmp))
        check("sem arquivo de análise: diz que falta",
              "the analysis is missing" in " ".join(lines), " ".join(lines))


def test_left_out_note_gives_each_rule_and_prints_once():
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("cepa_run_mod3", str(base.CEPA_UNTIL))
    spec = importlib.util.spec_from_loader("cepa_run_mod3", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    said = []
    mod.LEFT_OUT.extend([("a.jsonl", ".gitignore:1: .claude/*"),
                         ("b.md", ".git/info/exclude:2: *.md")])
    mod.note_left_out(said.append)
    mod.LEFT_OUT.extend([("a.jsonl", ".gitignore:1: .claude/*")])
    mod.note_left_out(said.append)
    check("uma nota só, com a regra de cada arquivo",
          len(said) == 1 and "a.jsonl (rule .gitignore:1: .claude/*)" in said[0]
          and "b.md (rule .git/info/exclude:2: *.md)" in said[0], str(said))


def main():
    print("cepa-run — tela de fechamento\n")
    wanted = set(sys.argv[1:])
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn) and (not wanted or name in wanted):
            print(f"{name}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
