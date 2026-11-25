#!/usr/bin/env python3
"""`cepa-run land --yes` prints numbered steps (CS-7 of fim-do-until-sem-espera).

The output opens with a header (run branch → destination, commit count, fast-forward
or not, return point), then `[1/3] merge`, `[2/3] full build` and `[3/3] push`, each
with its result and duration. The files outside git the run worktree held are
listed with where each goes ("move to" or "delete"), and the output closes with the
end time and "run worktree and branch removed".

Every case runs a real `cepa-until` night against a fake repo, then the landing.
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    CEPA_UNTIL, FAILURES, check, fake_claude, item, ledger_of, build_repo, run_until)
from test_cepa_until_land import night, land, with_origin, commit  # noqa: E402
from test_cepa_until_run_branch import WORKS, git, plan_of  # noqa: E402

STEP = re.compile(r"^\[(\d)/3\] (merge|full build|push)\s+(\S.*)$")


def steps(out):
    return {m.group(1): m.group(3) for m in map(STEP.match, out.splitlines()) if m}


def test_green_landing_numbers_the_three_steps():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        with_origin(root)
        run_id, branch, tree = night(root)
        before = git(root, "rev-parse", "HEAD")
        # Two files outside git in the run worktree: one the clone lacks, one it
        # already has with the same bytes. Ignored, as `.claude/` is in a client
        # repo: an untracked file that is not ignored makes the landing refuse.
        with open(root / ".git" / "info" / "exclude", "a") as f:
            f.write(".claude/notas/\n.claude/rescued/\n")
        (Path(tree) / ".claude" / "notas").mkdir(parents=True, exist_ok=True)
        (Path(tree) / ".claude" / "notas" / "nova.md").write_text("só na árvore")
        (root / ".claude" / "notas").mkdir(parents=True, exist_ok=True)
        (root / ".claude" / "notas" / "igual.md").write_text("mesmo conteúdo")
        (Path(tree) / ".claude" / "notas" / "igual.md").write_text("mesmo conteúdo")
        (root / ".claude" / "notas" / "outra.md").write_text("versão do clone")
        (Path(tree) / ".claude" / "notas" / "outra.md").write_text("versão da run")
        # A copy left by an earlier rescue of the same branch: this landing's copy
        # gets `.1`, and the hint must read that one, not the old one.
        old_copy = (root / ".claude" / "rescued" / branch.replace("/", "-") / "notas")
        old_copy.mkdir(parents=True, exist_ok=True)
        (old_copy / "igual.md").write_text("cópia antiga, diferente")
        p = land(root, run_id, "--yes")
        out = p.stdout
        check("aterrissa com saída 0", p.returncode == 0, p.stderr + out)
        lines = out.splitlines()
        check("cabeçalho: branch da run → destino",
              any(branch in l and "→" in l for l in lines[:3]), out)
        check("cabeçalho: número de commits e fast-forward",
              re.search(r"commits\s*: 1, fast-forward", out) is not None, out)
        check("cabeçalho: ponto de retorno",
              re.search(r"return point: `\S+` at " + before[:10], out) is not None, out)
        s = steps(out)
        check("as três etapas aparecem, numeradas e nesta ordem",
              [l[:5] for l in lines if STEP.match(l)] == ["[1/3]", "[2/3]", "[3/3]"],
              out)
        check("[1/3] merge com resultado e duração",
              re.match(r"done: [0-9a-f]{10} \(\d+s\)$", s.get("1", "")) is not None, out)
        check("[2/3] full build com resultado e duração",
              re.match(r"green \(\d+(s|min)\)", s.get("2", "")) is not None, out)
        check("[3/3] push com resultado e duração",
              re.match(r"done: .*\(\d+s\)$", s.get("3", "")) is not None, out)
        check("o arquivo novo diz para onde mover",
              ".claude/notas/nova.md: move to .claude/notas/nova.md" in out, out)
        check("o arquivo igual ao do clone pode ser apagado",
              ".claude/notas/igual.md: delete (same as .claude/notas/igual.md)" in out,
              out)
        check("o arquivo diferente do clone pede comparação, não apagar",
              ".claude/notas/outra.md: compare with .claude/notas/outra.md" in out,
              out)
        check("...e o bloco diz onde estão as cópias",
              ".claude/rescued/" in out, out)
        check("fecha com a hora do fim e a remoção",
              re.search(r"^landed at \d\d:\d\d: .*run worktree and branch removed$",
                        lines[-1]) is not None, lines[-1:])
        check("sai sem os textos antigos sem número",
              "pushed" not in lines and not any(l.startswith("full build:") for l in lines),
              out)


def test_no_upstream_and_moved_destination():
    """`main` moved after the run (not a fast-forward) and has no upstream: the
    push step still shows, saying why it was skipped."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        run_id, _, _ = night(root)
        commit(root, "outro.txt", "x", "main andou")
        p = land(root, run_id, "--yes")
        out = p.stdout
        check("aterrissa com saída 0", p.returncode == 0, p.stderr + out)
        check("cabeçalho diz que não é fast-forward e quanto o destino andou",
              re.search(r"not a fast-forward \(`\S+` has 1 other commit", out) is not None, out)
        s = steps(out)
        check("[3/3] push pulado com o motivo", s.get("3", "").startswith("skipped:")
              and "no upstream" in s.get("3", ""), out)
        check("sem arquivos fora do git, não há bloco de arquivos",
              "outside git" not in out, out)


def test_run_without_build_skips_step_two():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(Path(tmp), WORKS)
        run_until(root, binv, plan_of(root), ["--for", "2h", "--no-verify"])
        start = [e for e in ledger_of(root) if e["evento"] == "run_start"][0]
        run_id = start["branch"].split("/", 1)[1]
        p = land(root, run_id, "--yes")
        check("aterrissa com saída 0", p.returncode == 0, p.stderr + p.stdout)
        s = steps(p.stdout)
        check("[2/3] full build pulado, dizendo que a run dispensou o build",
              s.get("2") == "skipped: the run waived the build", p.stdout)
        check("...e as três etapas continuam numeradas",
              sorted(s) == ["1", "2", "3"], p.stdout)


def cepa_until_module():
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("cepa_until_mod", str(CEPA_UNTIL))
    spec = importlib.util.spec_from_loader("cepa_until_mod", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def test_newest_rescued_copy_takes_the_highest_suffix():
    """`rescue_artifacts` adds `.1`, `.2`, ... on collision: the copy of THIS
    landing is the highest number, not the first, the last listed, nor the
    lexicographically greatest (`.2` > `.10` as text)."""
    mod = cepa_until_module()
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        for name in ("plano.md.2", "plano.md", "plano.md.10", "plano.md.1",
                     "plano.md.x", "plano.mdx.99", "outro.md.50"):
            (d / name).write_text(name)
        got = mod.newest_rescued_copy(d / "plano.md")
        check("a cópia de maior número vence (.10)", got.name == "plano.md.10", got.name)
        # Independent of the order the disk lists them: with the numbered copies
        # listed ascending and descending, neither "first" nor "last" wins.
        import pathlib
        real_iterdir = pathlib.Path.iterdir
        numbered = ["plano.md.1", "plano.md.2", "plano.md.10"]
        for label, order in (("crescente", numbered), ("decrescente", numbered[::-1])):
            listing = [d / n for n in ["plano.md", *order, "plano.md.x"]]
            pathlib.Path.iterdir = lambda self, _l=listing: iter(_l)
            try:
                got = mod.newest_rescued_copy(d / "plano.md")
            finally:
                pathlib.Path.iterdir = real_iterdir
            check(f"listagem em ordem {label}: ainda vence a .10",
                  got.name == "plano.md.10", got.name)
        (d / "solo.md").write_text("x")
        got = mod.newest_rescued_copy(d / "solo.md")
        check("sem cópias numeradas, o próprio nome", got.name == "solo.md", got.name)


def test_step_duration_switches_to_minutes():
    mod = cepa_until_module()
    check("abaixo de um minuto, em segundos", mod.step_duration(42) == "42s",
          mod.step_duration(42))
    check("de um minuto em diante, em minutos", mod.step_duration(75) == "1min",
          mod.step_duration(75))
    check("acima de uma hora, em horas", mod.step_duration(3900) == "1h05",
          mod.step_duration(3900))


def test_red_build_numbers_the_steps_and_skips_the_push():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        with_origin(root)
        run_id, _, _ = night(root)
        commit(root, "quebra.txt", "x", "main andou")
        git(root, "push", "-q")
        p = land(root, run_id, "--yes")
        out = p.stdout
        check("sai com 5", p.returncode == 5, out + p.stderr)
        s = steps(out)
        check("[2/3] full build RED com duração",
              re.match(r"RED \(\d+(s|min)\)", s.get("2", "")) is not None, out)
        check("[3/3] push não roda", s.get("3") == "not run", out)

        git(root, "rm", "-q", "quebra.txt")
        git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "fix")
        p = land(root, run_id, "--yes")
        s = steps(p.stdout)
        check("rodar de novo: [1/3] diz que o merge já estava feito",
              s.get("1", "").startswith("already done"), p.stdout)
        check("...e o cabeçalho conta os commits a partir do ponto de retorno",
              re.search(r"commits\s*: 1,", p.stdout) is not None, p.stdout)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    if FAILURES:
        print(f"{len(FAILURES)} FAIL")
        sys.exit(1)
    print("ok")
