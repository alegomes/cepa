#!/usr/bin/env python3
"""Regression tests: check_env_manifest do cepa-doctor lê docs/env.yaml.

## Por que este check existe

O manifesto de ambiente mudou de endereço em 2026-08-22: `docs/env.yaml`
ganha, com fallback para o legado `.claude/env.yaml` (ver
docs/env-manifest.md). `check_env_manifest` hardcodava `.claude/env.yaml` e
nunca via `docs/env.yaml` — regressão silenciosa, porque o check é
fail-silent por design (arquivo ausente → nenhum aviso). Este teste prova
que a porta declarada em `docs/env.yaml` é conferida.

Run: python3 tests/test_doctor_env_manifest_path.py
"""

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCTOR = REPO / "common" / "bin" / "cepa-doctor"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def monta(tmp, docs_env=None, legado_env=None):
    """Repo git mínimo, com docs/env.yaml e/ou .claude/env.yaml opcionais."""
    raiz = Path(tmp) / "repo"
    raiz.mkdir()
    (raiz / "README.md").write_text("base\n", encoding="utf-8")
    if docs_env is not None:
        d = raiz / "docs"
        d.mkdir(parents=True, exist_ok=True)
        (d / "env.yaml").write_text(docs_env, encoding="utf-8")
    if legado_env is not None:
        d = raiz / ".claude"
        d.mkdir(parents=True, exist_ok=True)
        (d / "env.yaml").write_text(legado_env, encoding="utf-8")
    subprocess.run(["git", "init", "-q", "."], cwd=raiz, check=True)
    subprocess.run(["git", "add", "-A"], cwd=raiz, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=raiz, check=True)
    return raiz


def path_essenciais(tmp):
    """Diretório só com symlinks para git/python3/lsof — o mínimo que o
    doctor precisa para rodar `--projeto`."""
    d = Path(tmp) / "minpath"
    d.mkdir()
    for nome in ("git", "python3", "lsof"):
        real = shutil.which(nome)
        if real:
            (d / nome).symlink_to(real)
    return d


def roda(raiz, path_dirs):
    env = dict(os.environ)
    env["PATH"] = ":".join(str(p) for p in path_dirs)
    p = subprocess.run([sys.executable, str(DOCTOR), "--projeto"], cwd=str(raiz),
                       capture_output=True, text=True, timeout=120, env=env)
    return p.stdout + p.stderr


class OuvinteDePorta:
    """Abre um socket TCP em 127.0.0.1:0 (porta livre escolhida pelo SO) e
    fica escutando numa thread — o suficiente para o `lsof` do doctor
    encontrar um LISTEN. O processo dono é este próprio interpretador
    Python, cujo cwd (o diretório de onde este teste foi invocado) NÃO fica
    dentro do repo temporário montado por `monta()` — condição que este
    teste depende para acionar o ramo "processo de OUTRO diretório"."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.sock.listen(1)
        self._parar = False
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
        time.sleep(0.2)  # dá tempo do lsof enxergar o LISTEN

    def _loop(self):
        self.sock.settimeout(0.5)
        while not self._parar:
            try:
                conn, _ = self.sock.accept()
                conn.close()
            except socket.timeout:
                continue
            except OSError:
                return

    def fechar(self):
        self._parar = True
        try:
            self.sock.close()
        except OSError:
            pass
        self._t.join(timeout=2)


def lsof_disponivel():
    return shutil.which("lsof") is not None


def test_docs_env_yaml_porta_ocupada_avisa():
    if not lsof_disponivel():
        print("  skip  lsof ausente no PATH — pulando (sem como o doctor achar o holder)")
        return
    ouvinte = OuvinteDePorta()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = monta(tmp, docs_env=f"ports: [{ouvinte.port}]\n")
            out = roda(raiz, [path_essenciais(tmp)])
            check("docs/env.yaml declara porta ocupada → warn nomeando a porta",
                  f"porta {ouvinte.port} ocupada" in out, out)
    finally:
        ouvinte.fechar()


def test_legado_claude_env_yaml_porta_ocupada_tambem_avisa():
    if not lsof_disponivel():
        print("  skip  lsof ausente no PATH — pulando (sem como o doctor achar o holder)")
        return
    ouvinte = OuvinteDePorta()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = monta(tmp, legado_env=f"ports: [{ouvinte.port}]\n")
            out = roda(raiz, [path_essenciais(tmp)])
            check(".claude/env.yaml (legado, sem docs/env.yaml) também dispara o aviso",
                  f"porta {ouvinte.port} ocupada" in out, out)
    finally:
        ouvinte.fechar()


def test_docs_env_yaml_ganha_do_legado_na_porta():
    if not lsof_disponivel():
        print("  skip  lsof ausente no PATH — pulando (sem como o doctor achar o holder)")
        return
    ouvinte = OuvinteDePorta()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            # porta livre garantida: abre e fecha na hora, só para reservar
            # um número que a chance de colisão com o ouvinte é desprezível
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", 0))
            porta_legado_livre = s.getsockname()[1]
            s.close()

            raiz = monta(tmp, docs_env=f"ports: [{ouvinte.port}]\n",
                         legado_env=f"ports: [{porta_legado_livre}]\n")
            out = roda(raiz, [path_essenciais(tmp)])
            check("docs/env.yaml ganha: avisa da porta do docs/env.yaml",
                  f"porta {ouvinte.port} ocupada" in out, out)
            check("...e NÃO menciona a porta do legado (docs/env.yaml venceu)",
                  str(porta_legado_livre) not in out, out)
    finally:
        ouvinte.fechar()


def main():
    print("cepa-doctor — check_env_manifest usa docs/env.yaml\n")
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            print(f"{nome}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
