#!/usr/bin/env python3
"""Regression tests: check_twg_version do cepa-doctor.

## Por que este check existe

A CLI `twg` (Atlassian) instala um agendador `launchd`
(`com.atlassian.twg.upkeep.plist`) que checa atualização sozinho a cada 12
minutos — a versão pode trocar ENTRE dois cards do mesmo lote desatendido, sem
sinal nenhum. O doctor confere a instalada contra a declarada em
`twg_version:` no manifesto de ambiente (docs/env.yaml, ou o legado
.claude/env.yaml — ver docs/env-manifest.md).

## Por que o aviso é GATEADO na declaração, e não solto

Sem `twg_version:` declarado, o doctor fica em silêncio total. Ele roda em
toda abertura de sessão, e um aviso sobre uma ferramenta que ninguém pediu
para acompanhar é o ruído que se aprende a pular.

Run: python3 tests/test_doctor_twg_version.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
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


def fake_twg_dir(tmp, versao):
    """Diretório com um `twg` falso (script sh) que ecoa `versao`."""
    d = Path(tmp) / "faketwg"
    d.mkdir()
    script = d / "twg"
    script.write_text(f"#!/bin/sh\necho 'twg version {versao}'\n", encoding="utf-8")
    script.chmod(0o755)
    return d


def path_essenciais(tmp):
    """Diretório só com symlinks para git/python3/lsof — o mínimo que o
    doctor precisa para rodar `--projeto` sem o `twg` no PATH."""
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


def test_sem_twg_version_declarado_e_silenciosa():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta(tmp, docs_env="ports: [8083]\n")
        fake = fake_twg_dir(tmp, "1.3.1")
        out = roda(raiz, [fake, path_essenciais(tmp)])
        check("sem twg_version declarado → nenhuma linha menciona twg",
              "twg" not in out.lower(), out)


def test_docs_env_yaml_versao_igual_da_ok():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta(tmp, docs_env="twg_version: 1.3.1\n")
        fake = fake_twg_dir(tmp, "1.3.1")
        out = roda(raiz, [fake, path_essenciais(tmp)])
        check("versão igual → linha ok com a versão",
              "✓ [ambiente]" in out and "1.3.1" in out, out)


def test_docs_env_yaml_versao_diferente_avisa():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta(tmp, docs_env="twg_version: 1.3.1\n")
        fake = fake_twg_dir(tmp, "1.4.0")
        out = roda(raiz, [fake, path_essenciais(tmp)])
        check("versão diferente → aviso nomeando as duas",
              "⚠ [ambiente]" in out and "1.3.1" in out and "1.4.0" in out, out)
        check("...e nomeia o agendador responsável",
              "com.atlassian.twg.upkeep" in out, out)


def test_legado_claude_env_yaml_tambem_avisa():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta(tmp, legado_env="twg_version: 1.3.1\n")
        fake = fake_twg_dir(tmp, "1.4.0")
        out = roda(raiz, [fake, path_essenciais(tmp)])
        check(".claude/env.yaml (legado) também dispara o check",
              "⚠ [ambiente]" in out and "1.3.1" in out and "1.4.0" in out, out)


def test_twg_ausente_do_path_avisa():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta(tmp, docs_env="twg_version: 1.3.1\n")
        out = roda(raiz, [path_essenciais(tmp)])
        check("twg fora do PATH → aviso de ausente",
              "⚠ [ambiente]" in out and "1.3.1" in out
              and ("não está instalada" in out or "não está no PATH" in out), out)


def test_docs_env_yaml_ganha_do_legado():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta(tmp, docs_env="twg_version: 1.3.1\n",
                     legado_env="twg_version: 9.9.9\n")
        fake = fake_twg_dir(tmp, "1.3.1")
        out = roda(raiz, [fake, path_essenciais(tmp)])
        check("docs/env.yaml ganha do legado (compara com 1.3.1, não 9.9.9)",
              "✓ [ambiente]" in out and "1.3.1" in out and "9.9.9" not in out, out)


def main():
    print("cepa-doctor — check_twg_version\n")
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
