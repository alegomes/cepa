#!/usr/bin/env python3
"""Regression tests for the `--modo` gate in common/bin/cepa.

Toda sessão declara em qual dos sete modos de trabalho ela opera
(docs/modos-de-trabalho.md). O modo é gravado em .claude/session-mode no
diretório onde a sessão vai de fato rodar. Sem modo o cepa não sobe: um default
silencioso reconstruiria exatamente o vazamento entre atividades que o modo
existe para fechar.

Contratos guardados aqui:
  - modo válido grava o arquivo e repassa os demais args ao claude;
  - modo desconhecido é erro (rc=2), nunca vira pergunta nem chute;
  - sem modo e sem tty → recusa subir, e NÃO grava arquivo;
  - CEPA_MODO=off desliga a exigência inteira (escape hatch);
  - reforma sem orçamento é recusada — reforma sem escopo fechado não termina;
  - a detecção de "há humano para perguntar" olha stdin, não só /dev/tty:
    /dev/tty segue legível com stdin redirecionado, e sozinho ele deixaria um
    script pipe-alimentado parar num menu interativo.

Sem deps de terceiros — rode com `python3 tests/test_cepa_modo.py`.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CEPA = REPO / "common" / "bin" / "cepa"

FAKE_CLAUDE = '#!/bin/sh\nprintf "CLAUDE_ARGS:%s\\n" "$*"\n'

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


class Repo:
    """Um git repo descartável com um `claude` falso no lugar do de verdade."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "repo"
        self.path.mkdir()
        subprocess.run(["git", "init", "-q", "."], cwd=self.path, check=True)
        subprocess.run(
            ["git", "commit", "-q", "--allow-empty", "-m", "init"],
            cwd=self.path, check=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
        )
        fake = Path(self.tmp.name) / "fakeclaude"
        fake.write_text(FAKE_CLAUDE)
        fake.chmod(0o755)
        self.fake = fake
        return self

    def __exit__(self, *a):
        self.tmp.cleanup()

    def run(self, *args, env=None):
        e = {**os.environ,
             "CLAUDE_WT_CLAUDE_BIN": str(self.fake),
             "CEPA_PREFLIGHT": "off"}
        e.update(env or {})
        return subprocess.run(
            [str(CEPA), *args], cwd=self.path, env=e,
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30,
        )

    @property
    def mode_file(self):
        return self.path / ".claude" / "session-mode"


def test_modo_valido():
    with Repo() as r:
        p = r.run("--modo", "construcao", "--resume")
        check("modo válido: rc=0", p.returncode == 0, p.stderr)
        check("modo válido: grava o arquivo", r.mode_file.exists())
        body = r.mode_file.read_text() if r.mode_file.exists() else ""
        check("modo válido: registra o modo", "modo: construcao" in body, body)
        check("modo válido: repassa os args ao claude",
              "CLAUDE_ARGS:--resume" in p.stdout, p.stdout)


def test_modo_invalido():
    with Repo() as r:
        p = r.run("--modo=xpto")
        check("modo inválido: rc=2", p.returncode == 2, str(p.returncode))
        check("modo inválido: não grava", not r.mode_file.exists())
        check("modo inválido: lista os válidos", "construcao" in p.stderr, p.stderr)


def test_sem_modo_sem_tty():
    with Repo() as r:
        p = r.run()
        check("sem modo: recusa subir", p.returncode == 2, str(p.returncode))
        check("sem modo: não grava", not r.mode_file.exists())
        check("sem modo: não caiu no menu interativo",
              "Em qual modo" not in p.stderr, p.stderr)
        check("sem modo: ensina o escape", "CEPA_MODO=off" in p.stderr, p.stderr)


def test_kill_switch():
    with Repo() as r:
        p = r.run("--resume", env={"CEPA_MODO": "off"})
        check("CEPA_MODO=off: sobe", p.returncode == 0, p.stderr)
        check("CEPA_MODO=off: não grava", not r.mode_file.exists())
        check("CEPA_MODO=off: entrega ao claude",
              "CLAUDE_ARGS:--resume" in p.stdout, p.stdout)


def test_reforma_orcamento():
    with Repo() as r:
        p = r.run("--modo", "reforma")
        check("reforma sem orçamento: recusa", p.returncode == 2, str(p.returncode))
        check("reforma sem orçamento: não grava", not r.mode_file.exists())
    with Repo() as r:
        p = r.run("--modo", "reforma", "--orcamento", "só o módulo de auth")
        check("reforma com orçamento: rc=0", p.returncode == 0, p.stderr)
        body = r.mode_file.read_text() if r.mode_file.exists() else ""
        check("reforma com orçamento: registra o escopo",
              'orcamento: "só o módulo de auth"' in body, body)



def main():
    print("test_cepa_modo")
    for fn in (test_modo_valido, test_modo_invalido, test_sem_modo_sem_tty,
               test_kill_switch, test_reforma_orcamento):
        fn()
    if failures:
        print(f"\n{len(failures)} falha(s): {', '.join(failures)}")
        return 1
    print("\ntudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
