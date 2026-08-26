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


# --- hook session-mode.py ---------------------------------------------------
HOOK = REPO / "common" / "hooks" / "session-mode.py"


def run_hook(cwd, env=None):
    import json as _json
    e = {**os.environ}
    e.update(env or {})
    return subprocess.run(
        [sys.executable, str(HOOK)], input=_json.dumps({"cwd": str(cwd)}),
        capture_output=True, text=True, timeout=15, env=e,
    )


def ctx(proc):
    """O texto que o modelo de fato recebe — decodificado, não o JSON cru."""
    import json as _json
    if not proc.stdout.strip():
        return ""
    return _json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]


def write_mode(repo, body):
    d = repo.path / ".claude"
    d.mkdir(exist_ok=True)
    (d / "session-mode").write_text(body, encoding="utf-8")


def test_hook_injeta_modo_e_saida():
    with Repo() as r:
        write_mode(r, "modo: construcao\nrotina: null\norcamento: null\n")
        p = run_hook(r.path)
        check("hook: rc=0", p.returncode == 0, p.stderr)
        c = ctx(p)
        check("hook: nomeia o modo", "construcao" in c, c)
        check("hook: dá a condição de saída",
              "completion-auditor" in c and "PROVEN" in c, c)
        check("hook: manda capturar o desvio", "off-mode-capture" in c, c)


def test_hook_reforma_mostra_orcamento():
    with Repo() as r:
        write_mode(r, 'modo: reforma\norcamento: "só o módulo de auth"\n')
        p = run_hook(r.path)
        c = ctx(p)
        check("hook reforma: mostra o orçamento", "só o módulo de auth" in c, c)
        check("hook reforma: cobra teste externo não editado",
              "teste" in c and "externo" in c, c)


def test_hook_silencioso_sem_modo():
    with Repo() as r:
        p = run_hook(r.path)
        check("hook: silencioso sem arquivo de modo", p.stdout.strip() == "",
              repr(p.stdout))
        check("hook: rc=0 sem arquivo", p.returncode == 0, p.stderr)


def test_hook_respeita_kill_switch():
    with Repo() as r:
        write_mode(r, "modo: construcao\n")
        p = run_hook(r.path, env={"CEPA_MODO": "off"})
        check("hook: CEPA_MODO=off silencia", p.stdout.strip() == "", repr(p.stdout))


def test_hook_nunca_quebra_o_turno():
    with Repo() as r:
        write_mode(r, "lixo que não é yaml\n:::\n")
        p = run_hook(r.path)
        check("hook: arquivo corrompido não quebra", p.returncode == 0, p.stderr)
        check("hook: arquivo corrompido não injeta nada",
              p.stdout.strip() == "", repr(p.stdout))


# --- ajuda do menu de modos -------------------------------------------------
# O menu do `cepa` listava os sete nomes e mais nada. Quem não lembra o que
# "reforma" cobra escolhia pelo nome — e o modo, que é fronteira, virava rótulo.
# A ajuda mostra o propósito de cada modo lido de _modos.py (fonte única), sem
# abrir o doc de 307 linhas.

def test_ajuda_nao_interativa():
    """`cepa --modo ajuda` imprime os propósitos e NÃO sobe sessão nenhuma."""
    with Repo() as r:
        p = r.run("--modo", "ajuda")
        saida = p.stdout + p.stderr
        check("ajuda: rc=0", p.returncode == 0, str(p.returncode) + saida)
        check("ajuda: não lança o claude", "CLAUDE_ARGS" not in p.stdout, p.stdout)
        check("ajuda: não grava modo", not r.mode_file.exists())
        check("ajuda: nomeia os sete modos",
              all(m in saida for m in
                  ("exploracao", "descoberta", "design", "construcao",
                   "reforma", "reflexao", "documentacao")), saida)
        check("ajuda: diz o propósito, não só o nome",
              "comportamento externo" in saida or "sem mudar nada que se veja" in saida,
              saida)


def _pty_run(repo, teclado):
    """Roda o cepa com um terminal de verdade e digita `teclado` nele.

    O `cepa` lê de /dev/tty, então não basta um pipe: o processo precisa de um
    terminal de controle próprio (setsid + TIOCSCTTY), senão /dev/tty apontaria
    para o terminal de quem roda os testes.
    """
    import fcntl, pty, termios, time
    mestre, escravo = pty.openpty()

    def ctty():
        os.setsid()
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)

    proc = subprocess.Popen(
        [str(CEPA), "--resume"], cwd=repo.path,
        env={**os.environ, "CLAUDE_WT_CLAUDE_BIN": str(repo.fake),
             "CEPA_PREFLIGHT": "off"},
        stdin=escravo, stdout=escravo, stderr=escravo,
        preexec_fn=ctty, close_fds=True,
    )
    os.close(escravo)
    for tecla in teclado:
        time.sleep(0.4)
        os.write(mestre, tecla.encode())
    buf = b""
    fim = time.time() + 20
    while time.time() < fim:
        try:
            pedaco = os.read(mestre, 65536)
        except OSError:
            break
        if not pedaco:
            break
        buf += pedaco
        if proc.poll() is not None and b"CLAUDE_ARGS" in buf:
            break
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    os.close(mestre)
    return proc.returncode, buf.decode("utf-8", "replace")


def test_ajuda_no_menu_e_reapresenta():
    """No menu, `?` mostra os propósitos e o menu volta — não é escolha inválida."""
    with Repo() as r:
        rc, saida = _pty_run(r, ["?\n", "construcao\n"])
        check("menu: oferece a ajuda", "?" in saida and "ajuda" in saida, saida)
        check("menu ?: mostra o propósito",
              "comportamento externo" in saida or "sem mudar nada que se veja" in saida,
              saida)
        check("menu ?: não trata como modo desconhecido",
              "modo desconhecido" not in saida, saida)
        check("menu ?: pergunta de novo", saida.count("modo?") >= 2, saida)
        check("menu ?: a escolha seguinte vale", rc == 0, str(rc) + saida)
        body = r.mode_file.read_text() if r.mode_file.exists() else ""
        check("menu ?: grava o modo escolhido", "modo: construcao" in body, body)


def main():
    print("test_cepa_modo")
    for fn in (test_modo_valido, test_modo_invalido, test_sem_modo_sem_tty,
               test_kill_switch, test_reforma_orcamento,
               test_ajuda_nao_interativa, test_ajuda_no_menu_e_reapresenta,
               test_hook_injeta_modo_e_saida, test_hook_reforma_mostra_orcamento,
               test_hook_silencioso_sem_modo, test_hook_respeita_kill_switch,
               test_hook_nunca_quebra_o_turno):
        fn()
    if failures:
        print(f"\n{len(failures)} falha(s): {', '.join(failures)}")
        return 1
    print("\ntudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
