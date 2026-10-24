#!/usr/bin/env python3
"""CS-1 of cycle 1 of the Cepa in a spiral Epic: `demonstrates:` in the queue header.

Run with `python3 tests/test_cepa_plan_demonstrates.py`. Surface: the CLI
`common/bin/cepa-plan`, called as a subprocess.

The field says what the queue DEMONSTRATES when it ends ("the operator loads the PDF and sees
3 answers"). It is optional: a queue without it stays valid. What these tests
charge:

  - `validate` accepts a queue with the field, and refuses a value that is not text;
  - `show` prints the text, and says when the queue does not have the field;
  - a reprioritization (`write` over the existing queue) does not erase it silently,
    nor do `start`/`finish`, which rewrite the file.
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

DEMONSTRA = "o operador carrega o PDF e vê 3 respostas"


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def run(repo, *args):
    return subprocess.run([sys.executable, str(CEPA_PLAN)] + list(args),
                          capture_output=True, text=True, cwd=str(repo))


def git_repo(base, given_name):
    d = Path(base) / given_name
    d.mkdir(parents=True)
    subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
    return d


def write_plan(d, extra_header, given_name="fila"):
    target = d / ".claude" / "programs" / given_name / "plan.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    body = {"schema_version": 2, "mode": "single-track", "program": given_name,
             "source": "docs/spec/x.md", **extra_header,
             "items": [{"id": "CS-1", "title": "um", "why": "primeiro",
                        "status": "pending", "blocked_by": [],
                        "human_pending": None}]}
    target.write_text(yaml.dump(body, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")
    return target


def reads(target):
    return yaml.safe_load(target.read_text(encoding="utf-8"))


def test_validate_accepts_demonstrates(base):
    d = git_repo(base, "valida")
    target = write_plan(d, {"demonstrates": DEMONSTRA})
    r = run(d, "validate", str(target))
    check("validate aceita a fila com `demonstrates:`", r.returncode == 0,
          r.stdout + r.stderr)

    without_ = write_plan(d, {}, given_name="sem")
    check("fila sem `demonstrates:` continua válida",
          run(d, "validate", str(without_)).returncode == 0)


def test_validate_refuses_demonstrates_that_is_not_text(base):
    d = git_repo(base, "tipo")
    for rot, value in (("lista", ["a", "b"]), ("vazio", "  ")):
        target = write_plan(d, {"demonstrates": value}, given_name=rot)
        r = run(d, "validate", str(target))
        check(f"validate recusa `demonstrates:` {rot}", r.returncode == 2,
              r.stdout + r.stderr)
        check(f"e nomeia o campo na recusa ({rot})", "demonstrates" in r.stderr,
              r.stderr)


def test_show_prints_the_text(base):
    d = git_repo(base, "show")
    write_plan(d, {"demonstrates": DEMONSTRA})
    r = run(d, "show", "fila", "--repo", ".")
    check("show sai 0", r.returncode == 0, r.stderr)
    check("show imprime o texto do `demonstrates:`", DEMONSTRA in r.stdout, r.stdout)

    r = run(d, "show", "fila", "--repo", ".", "--json")
    data = json.loads(r.stdout) if r.returncode == 0 else {}
    check("show --json traz o campo", data.get("demonstrates") == DEMONSTRA,
          r.stdout + r.stderr)

    write_plan(d, {}, given_name="sem")
    r = run(d, "show", "sem", "--repo", ".")
    check("show de fila sem o campo diz que não tem",
          r.returncode == 0 and "sem `demonstrates:`" in r.stdout,
          r.stdout + r.stderr)


def test_rewrite_preserves_demonstrates(base):
    d = git_repo(base, "reescrita")
    target = write_plan(d, {"demonstrates": DEMONSTRA})
    items = d / "itens.json"
    items.write_text(json.dumps([{"id": "CS-1", "title": "um",
                                  "why": "outro motivo",
                                  "human_pending": None}]), encoding="utf-8")
    r = run(d, "write", "fila", "--items", str(items), "--repo", ".")
    check("repriorização grava", r.returncode == 0, r.stderr)
    check("e não apaga o `demonstrates:` do disco",
          reads(target).get("demonstrates") == DEMONSTRA, str(reads(target)))

    run(d, "start", "fila", "CS-1", "--repo", ".")
    run(d, "finish", "fila", "CS-1", "--status", "done",
        "--evidence", "teste", "--repo", ".")
    check("start/finish também não o apagam",
          reads(target).get("demonstrates") == DEMONSTRA, str(reads(target)))


def test_old_demonstra_key_is_still_read(base):
    d = git_repo(base, "antiga")
    target = write_plan(d, {"demonstra": DEMONSTRA})
    r = run(d, "validate", str(target))
    check("validate aceita a fila gravada com a chave antiga `demonstra:`",
          r.returncode == 0, r.stderr)
    r = run(d, "show", "fila", "--repo", ".")
    check("show imprime o texto da chave antiga", DEMONSTRA in r.stdout, r.stdout)
    r = run(d, "show", "fila", "--repo", ".", "--json")
    data = json.loads(r.stdout) if r.returncode == 0 else {}
    check("show --json devolve o texto da chave antiga como `demonstrates`",
          data.get("demonstrates") == DEMONSTRA, r.stdout + r.stderr)
    write_plan(d, {"demonstra": ""}, given_name="vazia")
    r = run(d, "validate", str(d / ".claude" / "programs" / "vazia" / "plan.yaml"))
    check("validate recusa a chave antiga vazia", r.returncode == 2, r.stderr)
    items = d / "itens.json"
    items.write_text(json.dumps([{"id": "CS-1", "title": "um",
                                  "why": "outro motivo",
                                  "human_pending": None}]), encoding="utf-8")
    r = run(d, "write", "fila", "--items", str(items), "--repo", ".")
    check("repriorização sobre a fila de chave antiga grava", r.returncode == 0,
          r.stderr)
    plan = reads(target)
    check("e o roteiro sobrevive, regravado como `demonstrates:`",
          plan.get("demonstrates") == DEMONSTRA and "demonstra" not in plan,
          str(plan))


def main():
    with tempfile.TemporaryDirectory() as base:
        for fn in (test_validate_accepts_demonstrates,
                   test_validate_refuses_demonstrates_that_is_not_text,
                   test_show_prints_the_text,
                   test_rewrite_preserves_demonstrates,
                   test_old_demonstra_key_is_still_read):
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
