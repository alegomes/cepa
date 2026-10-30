#!/usr/bin/env python3
"""Regression tests for common/hooks/refactor-gate.py.

A Reform reorganizes the code WITHOUT changing the observable behavior. If the test
that was already passing had to change, the behavior changed — it was not a reform, it was
construction. This gate is the mechanical part of the mode's exit condition
(docs/modos-de-trabalho.md).

Contracts guarded here:
  - an EXTERNAL test edited during a reform → blocks (rc=2), with the reason;
  - an INTERNAL (unit) test remains free — renaming a class forces touching it,
    and that is a legitimate reform;
  - production code remains free;
  - outside the refactor mode the gate is silent, even when touching an external test;
  - Bash is not an escape route: `>`, `>>`, `sed -i` and `tee` on the target block
    the same — blocking only Write has already let agents escape through sed/cat in this
    repo before;
  - `>=` in a condition does not become a redirect (that false block has already
    happened in the bash-path-lock and silenced perturbations);
  - .claude/external-tests overrides the default patterns;
  - CEPA_MODO=off turns the gate off.

No third-party deps — run with `python3 tests/test_refactor_gate.py`.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / "common" / "hooks" / "refactor-gate.py"

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

    def mode(self, name, budget=None):
        body = f"mode: {name}\n"
        body += f'budget: "{budget}"\n' if budget else "budget: null\n"
        (self.path / ".claude" / "session-mode").write_text(body, encoding="utf-8")

    def external(self, *globs):
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


def test_blocks_external_test():
    with Repo() as r:
        r.mode("refactor", "só o módulo de auth")
        p = r.edit("src/test/java/com/x/AuthResourceIT.java")
        check("reforma: bloqueia teste externo", p.returncode == 2, str(p.returncode))
        check("reforma: explica que virou construção",
              "construction" in p.stderr, p.stderr)
        check("reforma: mostra o orçamento", "só o módulo de auth" in p.stderr, p.stderr)
        check("reforma: oferece a captura do desvio",
              "off-mode-capture" in p.stderr, p.stderr)


def test_allows_internal_test_and_production():
    with Repo() as r:
        r.mode("refactor")
        for target in ("src/test/java/com/x/AuthServiceTest.java",
                     "src/main/java/com/x/AuthService.java",
                     "tests/test_parser.py"):
            p = r.edit(target)
            check(f"reforma: libera {os.path.basename(target)}",
                  p.returncode == 0, p.stderr)


def test_session_mode_in_old_format_applies():
    """`modo: reforma` + `orcamento:` (the old `cepa`) still activate the gate."""
    with Repo() as r:
        (r.path / ".claude" / "session-mode").write_text(
            'modo: reforma\nrotina: null\norcamento: "só o módulo de auth"\n', encoding="utf-8")
        p = r.edit("src/test/java/com/x/FooIT.java")
        check("antigo: modo: reforma bloqueia teste externo", p.returncode == 2, p.stderr)
        check("antigo: orcamento: aparece como orçamento", "só o módulo de auth" in p.stderr, p.stderr)
    with Repo() as r:
        (r.path / ".claude" / "session-mode").write_text("modo: construcao\n", encoding="utf-8")
        p = r.edit("src/test/java/com/x/FooIT.java")
        check("antigo: modo: construcao deixa o gate mudo", p.returncode == 0, p.stderr)


def test_silent_outside_the_mode():
    with Repo() as r:
        r.mode("construction")
        p = r.edit("src/test/java/com/x/AuthResourceIT.java")
        check("fora de reforma: gate é mudo", p.returncode == 0, p.stderr)
    with Repo() as r:
        p = r.edit("e2e/checkout.spec.ts")
        check("sem modo: gate é mudo", p.returncode == 0, p.stderr)


def test_bash_is_not_an_escape_route():
    with Repo() as r:
        r.mode("refactor")
        for cmd in ('echo x > e2e/checkout.spec.ts',
                    'cat foo >> tests/e2e/login.py',
                    "sed -i '' 's/a/b/' src/test/java/AuthResourceIT.java",
                    'tee cypress/specs/pay.cy.js < /dev/null'):
            p = r.bash(cmd)
            check(f"bash bloqueado: {cmd[:28]}", p.returncode == 2, p.stderr[:120])


def test_ge_is_not_a_redirect():
    with Repo() as r:
        r.mode("refactor")
        p = r.bash('if [ "$n" >= 3 ]; then echo e2e; fi')
        check(">= não vira redirecionamento", p.returncode == 0, p.stderr)


def test_directory_at_root():
    """*/cypress/* must match both in a/cypress/x and in cypress/x at the
    root. A gate that catches some cases and seems to cover all is worse than no gate
    at all — that is how this one passed green in the first round.
    """
    with Repo() as r:
        r.mode("refactor")
        for target in ("cypress/specs/pay.cy.js", "app/cypress/specs/pay.cy.js",
                     "e2e/checkout.spec.ts", "sub/e2e/checkout.spec.ts",
                     "integration/pay_test.go"):
            p = r.edit(target)
            check(f"raiz e subdir: bloqueia {target}", p.returncode == 2, p.stderr[:80])


def test_repo_override():
    with Repo() as r:
        r.mode("refactor")
        r.external("*/contract/*")
        p = r.edit("src/contract/PayContract.java")
        check("override: bloqueia o que o repo declarou", p.returncode == 2, p.stderr)
        p = r.edit("src/test/java/AuthResourceIT.java")
        check("override: substitui os defaults", p.returncode == 0, p.stderr)


def test_kill_switch():
    with Repo() as r:
        r.mode("refactor")
        p = r.edit("e2e/checkout.spec.ts", env={"CEPA_MODO": "off"})
        check("CEPA_MODO=off desliga o gate", p.returncode == 0, p.stderr)


def main():
    print("test_refactor_gate")
    for fn in (test_blocks_external_test, test_allows_internal_test_and_production,
               test_session_mode_in_old_format_applies, test_silent_outside_the_mode, test_bash_is_not_an_escape_route,
               test_ge_is_not_a_redirect, test_directory_at_root,
               test_repo_override,
               test_kill_switch):
        fn()
    if failures:
        print(f"\n{len(failures)} falha(s): {', '.join(failures)}")
        return 1
    print("\ntudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
