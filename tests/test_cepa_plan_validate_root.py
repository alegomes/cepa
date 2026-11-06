#!/usr/bin/env python3
"""`cepa-plan validate` resolves a queue NAME at the main clone, not the current folder.

Run with `python3 tests/test_cepa_plan_validate_root.py`. Surface: the CLI
`common/bin/cepa-plan`, called as a subprocess.

  - from a linked worktree, `validate <name>` finds the queue in the main clone;
  - a file path keeps working, even outside any git repository;
  - a name that resolves to nothing exits 2 naming the main-clone path;
  - an invalid queue by name exits 2 with the gaps named.
"""

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
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def run(cwd, *args):
    return subprocess.run([sys.executable, str(CEPA_PLAN)] + list(args),
                          capture_output=True, text=True, cwd=str(cwd))


def git(d, *args):
    subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True)


def git_repo(base, given_name):
    d = (Path(base) / given_name).resolve()
    d.mkdir(parents=True)
    git(d, "init", "-q")
    git(d, "config", "user.email", "t@t")
    git(d, "config", "user.name", "t")
    return d


def write_plan(target, why="primeiro", name="fila"):
    target.parent.mkdir(parents=True, exist_ok=True)
    body = {"schema_version": 2, "mode": "single-track", "program": name,
            "source": "docs/spec/x.md",
            "items": [{"id": "CS-1", "title": "um", "why": why,
                       "status": "pending", "blocked_by": [],
                       "human_pending": None}]}
    target.write_text(yaml.dump(body, allow_unicode=True, sort_keys=False),
                      encoding="utf-8")
    return target


def main_with_worktree(base):
    d = git_repo(base, "principal")
    (d / "README").write_text("x", encoding="utf-8")
    git(d, "add", "README")
    git(d, "commit", "-q", "-m", "init")
    wt = (Path(base) / "wt").resolve()
    git(d, "worktree", "add", "-q", "-b", "outra", str(wt))
    return d, wt


def test_name_from_worktree(base):
    d, wt = main_with_worktree(base)
    target = write_plan(d / ".claude" / "queues" / "fila" / "queue.yaml")
    check("pré-condição: a worktree não tem a fila",
          not (wt / ".claude" / "queues" / "fila" / "queue.yaml").exists())
    r = run(wt, "validate", "fila")
    check("nome a partir da worktree: sai 0", r.returncode == 0, r.stdout + r.stderr)
    check("nome a partir da worktree: a saída cita o clone principal",
          str(target) in r.stdout, r.stdout + r.stderr)
    r = run(base, "validate", "fila", "--repo", str(wt))
    check("--repo apontando para a worktree: sai 0 e cita o clone principal",
          r.returncode == 0 and str(target) in r.stdout, r.stdout + r.stderr)


def test_file_path_without_git(base):
    outside = Path(base) / "solto"
    outside.mkdir()
    f = write_plan(outside / "queue.yaml")
    r = run(outside, "validate", str(f))
    check("caminho de arquivo fora de qualquer repo git: sai 0",
          r.returncode == 0 and str(f) in r.stdout, r.stdout + r.stderr)
    r = run(outside, "validate", "queue.yaml")
    check("caminho relativo existente na pasta atual: sai 0",
          r.returncode == 0, r.stdout + r.stderr)
    r = run(outside, "validate", "fila-que-nao-existe")
    check("nome fora de um repo git: sai 2 dizendo que não é repositório",
          r.returncode == 2 and "repositório git" in r.stderr, r.stdout + r.stderr)


def test_missing_name(base):
    d, wt = main_with_worktree(base)
    r = run(wt, "validate", "fantasma")
    expected = d / ".claude"
    check("nome inexistente: sai 2 citando o caminho no clone principal",
          r.returncode == 2 and str(expected) in r.stderr and "fantasma" in r.stderr,
          r.stdout + r.stderr)
    check("nome inexistente: a mensagem diz que a fila não existe",
          "não existe" in r.stderr, r.stderr)


def test_invalid_by_name(base):
    d, wt = main_with_worktree(base)
    write_plan(d / ".claude" / "queues" / "ruim" / "queue.yaml", why="", name="ruim")
    r = run(wt, "validate", "ruim")
    check("fila inválida por nome: sai 2 com a lacuna nomeada",
          r.returncode == 2 and "lacuna" in r.stderr and "why" in r.stderr,
          r.stdout + r.stderr)


for fn in (test_name_from_worktree, test_file_path_without_git,
           test_missing_name, test_invalid_by_name):
    print(fn.__name__)
    with tempfile.TemporaryDirectory() as tmp:
        fn(Path(tmp).resolve())

if FAILURES:
    print(f"\n{len(FAILURES)} falha(s)")
    sys.exit(1)
print("\ntudo ok")
