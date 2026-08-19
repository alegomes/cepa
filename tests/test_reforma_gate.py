#!/usr/bin/env python3
"""Regression tests for common/hooks/reforma-gate.py.

A Reforma reorganiza o código SEM mudar o comportamento observável. Se o teste
que já passava precisou mudar, o comportamento mudou — não era reforma, era
construção. Esse gate é a parte mecânica da condição de saída do modo
(docs/modos-de-trabalho.md).

Contratos guardados aqui:
  - teste EXTERNO editado durante reforma → bloqueia (rc=2), com o motivo;
  - teste INTERNO (unidade) segue livre — renomear classe obriga a mexer nele,
    e isso é reforma legítima;
  - código de produção segue livre;
  - fora do modo reforma o gate é mudo, mesmo mexendo em teste externo;
  - Bash não é rota de fuga: `>`, `>>`, `sed -i` e `tee` no alvo bloqueiam
    igual — bloquear só Write já deixou agentes escaparem por sed/cat neste
    repo antes;
  - `>=` numa condição não vira redirecionamento (esse falso bloqueio já
    aconteceu no bash-path-lock e silenciou perturbações);
  - .claude/external-tests sobrescreve os padrões default;
  - CEPA_MODO=off desliga o gate.

Sem deps de terceiros — rode com `python3 tests/test_reforma_gate.py`.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / "common" / "hooks" / "reforma-gate.py"

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


class Repo:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "repo"
        (self.path / ".claude").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "."], cwd=self.path, check=True)
        return self

    def __exit__(self, *a):
        self.tmp.cleanup()

    def modo(self, nome, orcamento=None):
        body = f"modo: {nome}\n"
        body += f'orcamento: "{orcamento}"\n' if orcamento else "orcamento: null\n"
        (self.path / ".claude" / "session-mode").write_text(body, encoding="utf-8")

    def externos(self, *globs):
        (self.path / ".claude" / "external-tests").write_text(
            "\n".join(globs) + "\n", encoding="utf-8")

    def call(self, tool, tool_input, env=None):
        e = {**os.environ}
        e.update(env or {})
        return subprocess.run(
            [sys.executable, str(GATE)],
            input=json.dumps({"cwd": str(self.path), "tool_name": tool,
                              "tool_input": tool_input}),
            capture_output=True, text=True, timeout=15, env=e,
        )

    def edit(self, path, **kw):
        return self.call("Edit", {"file_path": path}, **kw)

    def bash(self, cmd, **kw):
        return self.call("Bash", {"command": cmd}, **kw)


def test_bloqueia_teste_externo():
    with Repo() as r:
        r.modo("reforma", "só o módulo de auth")
        p = r.edit("src/test/java/com/x/AuthResourceIT.java")
        check("reforma: bloqueia teste externo", p.returncode == 2, str(p.returncode))
        check("reforma: explica que virou construção",
              "construção" in p.stderr, p.stderr)
        check("reforma: mostra o orçamento", "só o módulo de auth" in p.stderr, p.stderr)
        check("reforma: oferece a captura do desvio",
              "off-mode-capture" in p.stderr, p.stderr)


def test_libera_teste_interno_e_producao():
    with Repo() as r:
        r.modo("reforma")
        for alvo in ("src/test/java/com/x/AuthServiceTest.java",
                     "src/main/java/com/x/AuthService.java",
                     "tests/test_parser.py"):
            p = r.edit(alvo)
            check(f"reforma: libera {os.path.basename(alvo)}",
                  p.returncode == 0, p.stderr)


def test_mudo_fora_do_modo():
    with Repo() as r:
        r.modo("construcao")
        p = r.edit("src/test/java/com/x/AuthResourceIT.java")
        check("fora de reforma: gate é mudo", p.returncode == 0, p.stderr)
    with Repo() as r:
        p = r.edit("e2e/checkout.spec.ts")
        check("sem modo: gate é mudo", p.returncode == 0, p.stderr)


def test_bash_nao_e_rota_de_fuga():
    with Repo() as r:
        r.modo("reforma")
        for cmd in ('echo x > e2e/checkout.spec.ts',
                    'cat foo >> tests/e2e/login.py',
                    "sed -i '' 's/a/b/' src/test/java/AuthResourceIT.java",
                    'tee cypress/specs/pay.cy.js < /dev/null'):
            p = r.bash(cmd)
            check(f"bash bloqueado: {cmd[:28]}", p.returncode == 2, p.stderr[:120])


def test_ge_nao_e_redirecionamento():
    with Repo() as r:
        r.modo("reforma")
        p = r.bash('if [ "$n" >= 3 ]; then echo e2e; fi')
        check(">= não vira redirecionamento", p.returncode == 0, p.stderr)


def test_diretorio_na_raiz():
    """*/cypress/* precisa casar tanto em a/cypress/x quanto em cypress/x na
    raiz. Um gate que pega alguns casos e parece cobrir todos é pior que gate
    nenhum — foi assim que este aqui passou verde na primeira rodada."""
    with Repo() as r:
        r.modo("reforma")
        for alvo in ("cypress/specs/pay.cy.js", "app/cypress/specs/pay.cy.js",
                     "e2e/checkout.spec.ts", "sub/e2e/checkout.spec.ts",
                     "integration/pay_test.go"):
            p = r.edit(alvo)
            check(f"raiz e subdir: bloqueia {alvo}", p.returncode == 2, p.stderr[:80])


def test_override_do_repo():
    with Repo() as r:
        r.modo("reforma")
        r.externos("*/contract/*")
        p = r.edit("src/contract/PayContract.java")
        check("override: bloqueia o que o repo declarou", p.returncode == 2, p.stderr)
        p = r.edit("src/test/java/AuthResourceIT.java")
        check("override: substitui os defaults", p.returncode == 0, p.stderr)


def test_kill_switch():
    with Repo() as r:
        r.modo("reforma")
        p = r.edit("e2e/checkout.spec.ts", env={"CEPA_MODO": "off"})
        check("CEPA_MODO=off desliga o gate", p.returncode == 0, p.stderr)


def main():
    print("test_reforma_gate")
    for fn in (test_bloqueia_teste_externo, test_libera_teste_interno_e_producao,
               test_mudo_fora_do_modo, test_bash_nao_e_rota_de_fuga,
               test_ge_nao_e_redirecionamento, test_diretorio_na_raiz,
               test_override_do_repo,
               test_kill_switch):
        fn()
    if failures:
        print(f"\n{len(failures)} falha(s): {', '.join(failures)}")
        return 1
    print("\ntudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
