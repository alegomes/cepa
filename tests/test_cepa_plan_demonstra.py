#!/usr/bin/env python3
"""CS-1 do ciclo 1 do Epic Cepa em espiral: `demonstra:` no cabeçalho da fila.

Rode com `python3 tests/test_cepa_plan_demonstra.py`. Superfície: a CLI
`common/bin/cepa-plan`, chamada como subprocesso.

O campo diz o que a fila DEMONSTRA quando acaba ("o operador carrega o PDF e vê
3 respostas"). É opcional: fila sem ele continua válida. O que estes testes
cobram:

  - `validate` aceita uma fila com o campo, e recusa um valor que não é texto;
  - `show` imprime o texto, e diz quando a fila não tem o campo;
  - uma repriorização (`write` sobre a fila existente) não o apaga em silêncio,
    nem o `start`/`finish` que regravam o arquivo.
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


def repo_git(base, nome):
    d = Path(base) / nome
    d.mkdir(parents=True)
    subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
    return d


def grava_plano(d, cabecalho_extra, nome="fila"):
    alvo = d / ".claude" / "programs" / nome / "plan.yaml"
    alvo.parent.mkdir(parents=True, exist_ok=True)
    corpo = {"schema_version": 2, "mode": "single-track", "program": nome,
             "source": "docs/spec/x.md", **cabecalho_extra,
             "items": [{"id": "CS-1", "title": "um", "why": "primeiro",
                        "status": "pending", "blocked_by": [],
                        "human_pending": None}]}
    alvo.write_text(yaml.dump(corpo, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")
    return alvo


def le(alvo):
    return yaml.safe_load(alvo.read_text(encoding="utf-8"))


def test_validate_aceita_demonstra(base):
    d = repo_git(base, "valida")
    alvo = grava_plano(d, {"demonstra": DEMONSTRA})
    r = run(d, "validate", str(alvo))
    check("validate aceita a fila com `demonstra:`", r.returncode == 0,
          r.stdout + r.stderr)

    sem = grava_plano(d, {}, nome="sem")
    check("fila sem `demonstra:` continua válida",
          run(d, "validate", str(sem)).returncode == 0)


def test_validate_recusa_demonstra_que_nao_e_texto(base):
    d = repo_git(base, "tipo")
    for rot, valor in (("lista", ["a", "b"]), ("vazio", "  ")):
        alvo = grava_plano(d, {"demonstra": valor}, nome=rot)
        r = run(d, "validate", str(alvo))
        check(f"validate recusa `demonstra:` {rot}", r.returncode == 2,
              r.stdout + r.stderr)
        check(f"e nomeia o campo na recusa ({rot})", "demonstra" in r.stderr,
              r.stderr)


def test_show_imprime_o_texto(base):
    d = repo_git(base, "show")
    grava_plano(d, {"demonstra": DEMONSTRA})
    r = run(d, "show", "fila", "--repo", ".")
    check("show sai 0", r.returncode == 0, r.stderr)
    check("show imprime o texto do `demonstra:`", DEMONSTRA in r.stdout, r.stdout)

    r = run(d, "show", "fila", "--repo", ".", "--json")
    dados = json.loads(r.stdout) if r.returncode == 0 else {}
    check("show --json traz o campo", dados.get("demonstra") == DEMONSTRA,
          r.stdout + r.stderr)

    grava_plano(d, {}, nome="sem")
    r = run(d, "show", "sem", "--repo", ".")
    check("show de fila sem o campo diz que não tem",
          r.returncode == 0 and "sem `demonstra:`" in r.stdout,
          r.stdout + r.stderr)


def test_reescrita_preserva_demonstra(base):
    d = repo_git(base, "reescrita")
    alvo = grava_plano(d, {"demonstra": DEMONSTRA})
    itens = d / "itens.json"
    itens.write_text(json.dumps([{"id": "CS-1", "title": "um",
                                  "why": "outro motivo",
                                  "human_pending": None}]), encoding="utf-8")
    r = run(d, "write", "fila", "--items", str(itens), "--repo", ".")
    check("repriorização grava", r.returncode == 0, r.stderr)
    check("e não apaga o `demonstra:` do disco",
          le(alvo).get("demonstra") == DEMONSTRA, str(le(alvo)))

    run(d, "start", "fila", "CS-1", "--repo", ".")
    run(d, "finish", "fila", "CS-1", "--status", "done",
        "--evidence", "teste", "--repo", ".")
    check("start/finish também não o apagam",
          le(alvo).get("demonstra") == DEMONSTRA, str(le(alvo)))


def main():
    with tempfile.TemporaryDirectory() as base:
        for fn in (test_validate_aceita_demonstra,
                   test_validate_recusa_demonstra_que_nao_e_texto,
                   test_show_imprime_o_texto,
                   test_reescrita_preserva_demonstra):
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
