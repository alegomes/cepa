#!/usr/bin/env python3
"""`cepa-until land --yes` prints numbered steps (CS-7 of fim-do-until-sem-espera).

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
from test_cepa_until import FAILURES, check, item, build_repo  # noqa: E402
from test_cepa_until_land import night, land, with_origin, commit  # noqa: E402
from test_cepa_until_run_branch import git  # noqa: E402

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
            f.write(".claude/notas/\n")
        (Path(tree) / ".claude" / "notas").mkdir(parents=True, exist_ok=True)
        (Path(tree) / ".claude" / "notas" / "nova.md").write_text("só na árvore")
        (root / ".claude" / "notas").mkdir(parents=True, exist_ok=True)
        (root / ".claude" / "notas" / "igual.md").write_text("mesmo conteúdo")
        (Path(tree) / ".claude" / "notas" / "igual.md").write_text("mesmo conteúdo")
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
