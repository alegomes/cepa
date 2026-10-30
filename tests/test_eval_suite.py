#!/usr/bin/env python3
"""Structural tests of the golden-task suite (P1-4, review 2026-08-17).

No dependencies — run with `python3 tests/test_eval_suite.py`.

These cases are **cheap**: they read the manifests and the runner, without creating a worktree
or spending model. They do NOT replace `python3 tests/eval/run-eval.py
--validate`, which is the proof that each task requires real work — that one costs
about a minute and runs on demand, not on every suite.

What is locked here:

  - every manifest declares the fields without which the measurement does not exist;
  - `base_commit` and `fix_commit` are real AND different commits (equal = the
    task is born green, which is the self-delusion the whole suite exists to
    avoid);
  - the acceptance test exists in `fix_commit` and does NOT exist in `base_commit`
    — if it existed in both, the agent could be measured against a
    test that was already there;
  - the statement does not give away the solution;
  - the suite has varied difficulty — only-hard and only-easy measure equally
    little.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EVAL = REPO / "tests" / "eval"
sys.path.insert(0, str(EVAL))

FAILURES = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok  {label}")
    else:
        FAILURES.append(f"{label}{' — ' + detail if detail else ''}")
        print(f"  FAIL {label}{' — ' + detail if detail else ''}")


def load_runner():
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("run_eval", str(EVAL / "run-eval.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def git(*args):
    return subprocess.run(["git", *args], cwd=str(REPO), capture_output=True, text=True)


def test_parser_reads_multiline_block():
    """The statement is a `|` block; read wrong, the task measures something else."""
    m = load_runner()
    d = m.parse_task_yaml(
        'id: x\ntitulo: "com espaço"\nprompt: |\n  linha um\n  linha dois\n'
        'dificuldade: alta\n'
    )
    check("parser lê escalar", d.get("id") == "x")
    check("parser tira aspas do escalar", d.get("titulo") == "com espaço")
    check("parser lê bloco multilinha inteiro",
          d.get("prompt") == "linha um\nlinha dois", repr(d.get("prompt")))
    check("parser volta a ler escalar depois do bloco", d.get("dificuldade") == "alta")


def test_manifests_complete():
    m = load_runner()
    tasks = m.load_tasks()
    check("há tarefas declaradas", len(tasks) >= 3, f"{len(tasks)}")
    for t in tasks:
        tid = t["id"]
        for field in ("titulo", "fix_commit", "base_commit", "acceptance_test",
                      "acceptance_cmd", "prompt", "dificuldade"):
            check(f"{tid}: campo {field}", bool(t.get(field)))


def test_commits_real_and_distinct():
    m = load_runner()
    for t in m.load_tasks():
        tid = t["id"]
        for field in ("base_commit", "fix_commit"):
            r = git("cat-file", "-t", t[field])
            check(f"{tid}: {field} é um commit real",
                  r.returncode == 0 and r.stdout.strip() == "commit", r.stderr.strip()[:80])
        base = git("rev-parse", t["base_commit"]).stdout.strip()
        fix = git("rev-parse", t["fix_commit"]).stdout.strip()
        check(f"{tid}: base ≠ fix (senão a tarefa nasce verde)", base != fix)
        # the fix must descend from the base, otherwise the test does not apply
        r = git("merge-base", "--is-ancestor", t["base_commit"], t["fix_commit"])
        check(f"{tid}: base é ancestral do conserto", r.returncode == 0)


def test_acceptance_only_exists_after_the_fix():
    """If the test were already in the base, it would not measure the agent's work."""
    m = load_runner()
    for t in m.load_tasks():
        tid, path = t["id"], t["acceptance_test"]
        r_fix = git("cat-file", "-e", f"{t['fix_commit']}:{path}")
        check(f"{tid}: aceitação existe no fix_commit", r_fix.returncode == 0, path)
        r_base = git("cat-file", "-e", f"{t['base_commit']}:{path}")
        check(f"{tid}: aceitação NÃO existe no base_commit", r_base.returncode != 0,
              f"{path} já estava lá — o agente seria medido contra um teste preexistente")


def test_statement_does_not_give_away_the_solution():
    """The STATEMENT describes the problem; whoever names the file is the contract.

    The separation was born from the first real run, which scored 0/3. The cause was not
    difficulty: the acceptance tests require the exact path and name of the original fix's
    file, and the statements — on purpose — said nothing of the kind. The suite was
    measuring the ability to GUESS the original design, not to solve the problem,
    and no agent would pass.

    So the manifest has two fields with opposite roles, and this case guards both
    sides: the `prompt` remains forbidden to name the fix's files
    (otherwise it becomes a transcript), and the `contrato` is obliged to name them (otherwise it becomes
    guesswork).
    """
    m = load_runner()
    for t in m.load_tasks():
        tid = t["id"]
        r = git("show", "--name-only", "--diff-filter=A", "--format=", t["fix_commit"])
        created = [f for f in r.stdout.split() if f.endswith(".py")
                   and not f.startswith("tests/")]
        leaked = [f for f in created if Path(f).name in t["prompt"]]
        check(f"{tid}: o enunciado não nomeia os arquivos criados pelo conserto",
              not leaked, f"vazou: {leaked}")
        check(f"{tid}: o enunciado descreve o problema (tem tamanho de enunciado)",
              len(t["prompt"]) > 400, f"{len(t['prompt'])} chars")
        # the contract must name the file the acceptance will look for
        target = Path(t["acceptance_test"]).name
        check(f"{tid}: o contrato nomeia o teste que julga o trabalho",
              target in t["contrato"], f"{target} ausente do contrato")
        check(f"{tid}: o contrato entra no que o agente recebe",
              "COMO O SEU TRABALHO SERÁ CONFERIDO" in m.build_prompt(t))


def test_varied_difficulty():
    m = load_runner()
    levels = {t.get("dificuldade") for t in m.load_tasks()}
    check("a suíte tem dificuldade variada (não só fácil, não só difícil)",
          len(levels) >= 2, f"níveis: {sorted(levels)}")


def test_validate_is_mandatory_in_readme():
    """The guard against an empty task must be documented, not just exist."""
    readme = (EVAL / "README.md").read_text(encoding="utf-8")
    check("README explica o --validate", "--validate" in readme)
    check("README declara o estado real da suíte (rodou? tem A/B?)",
          re.search(r"não re-rodada|nunca rodada", readme, re.I) is not None)
    check("README registra o achado da 1ª corrida (0/3 mediu a própria suíte)",
          "0/3" in readme and "contrato" in readme.lower())


def test_failing_run_keeps_the_diff_and_leaves_no_worktree():
    """A failing task used to keep the whole worktree in /tmp/cepa-eval as
    evidence, registered in the repo's `git worktree list` forever (3 of them
    on 2026-09-26). The evidence is what the agent wrote: it becomes a .patch next
    to the result, and the worktree leaves the registry in any outcome.

    Runs the real `cmd_run` against a disposable repo, with a fake `claude`
    that writes a file and an acceptance that fails.
    """
    import os
    import tempfile
    run = load_runner()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp).resolve()
        repo = tmp / "repo"
        repo.mkdir()
        g = lambda *a, cwd=repo: subprocess.run(
            ["git", *a], cwd=str(cwd), capture_output=True, text=True)
        g("init", "-q")
        (repo / "tests").mkdir()
        (repo / "base.txt").write_text("base\n")
        g("add", "-A")
        g("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "base")
        base = g("rev-parse", "HEAD").stdout.strip()
        (repo / "tests" / "test_x.py").write_text("raise SystemExit(1)\n")
        g("add", "-A")
        g("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "fix")
        fix = g("rev-parse", "HEAD").stdout.strip()
        g("checkout", "-q", base)

        binv = tmp / "bin"
        binv.mkdir()
        claude = binv / "claude"
        claude.write_text("#!/bin/sh\necho 'ESCRITO PELO AGENTE' > agente.txt\n"
                          "echo '{\"num_turns\": 1, \"total_cost_usd\": 0}'\n")
        claude.chmod(0o755)

        orig_git = run.git
        run.git = lambda *a, cwd=repo, check=True: orig_git(*a, cwd=cwd, check=check)
        run.WORKTREE_ROOT = tmp / "wts"
        run.RESULTS_DIR = tmp / "results"
        old_path = os.environ["PATH"]
        os.environ["PATH"] = f"{binv}:{old_path}"
        try:
            task = {"id": "t1", "base_commit": base, "fix_commit": fix,
                    "acceptance_test": "tests/test_x.py",
                    "acceptance_cmd": "python3 tests/test_x.py",
                    "prompt": "faça", "contrato": ""}
            run.cmd_run([task], "lbl", 1)
        finally:
            os.environ["PATH"] = old_path
            run.git = orig_git

        listing = g("worktree", "list", "--porcelain").stdout
        check("nenhuma worktree da corrida fica registrada",
              listing.count("worktree ") == 1, listing)
        leftovers = list((tmp / "wts").glob("*")) if (tmp / "wts").exists() else []
        check("nem o diretório dela fica no disco", not leftovers, str(leftovers))
        res = json.loads((tmp / "results" / "lbl.json").read_text())["results"][0]
        check("a tarefa falhou, como devia", res.get("passed") is False, str(res))
        patch = Path(res.get("evidencia_patch") or "/nao/existe")
        check("o resultado aponta o .patch com o que o agente escreveu",
              patch.is_file() and "ESCRITO PELO AGENTE" in patch.read_text(),
              str(res))
        check("o .patch mora ao lado do resultado, não em /tmp",
              patch.parent == tmp / "results", str(patch))
        check("não sobra o campo que apontava a worktree", "worktree_kept" not in res)


def main():
    test_parser_reads_multiline_block()
    test_manifests_complete()
    test_commits_real_and_distinct()
    test_acceptance_only_exists_after_the_fix()
    test_statement_does_not_give_away_the_solution()
    test_varied_difficulty()
    test_validate_is_mandatory_in_readme()
    test_failing_run_keeps_the_diff_and_leaves_no_worktree()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} falha(s):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("all green")
    print("\nLembrete: isto é o barato. A prova de que cada tarefa exige trabalho "
          "real é `python3 tests/eval/run-eval.py --validate`.")


if __name__ == "__main__":
    main()
