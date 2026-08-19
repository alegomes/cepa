#!/usr/bin/env python3
"""Regression tests: a suíte não pode trocar a instalação viva do dono.

`cepa-doctor --fix` tem uma correção que sai do projeto: `fix_install` roda o
`bin/install.sh` do repo do cepa e reinstala os plugins DA MÁQUINA, não importa
de qual diretório o doctor foi chamado. Isso é o que se quer no preflight de uma
sessão de verdade.

Em 2026-08-19 aconteceu o oposto: a suíte do próprio doctor, rodando `--fix` em
repositórios temporários, viu o repo à frente do cache e reinstalou o harness do
dono no meio de um `python3 tests/...`. Ninguém pediu, nada avisou, e a troca só
apareceu depois, no relatório do doctor. Um teste capaz de trocar o harness
instalado pode provocar exatamente a classe de falha que o doctor existe para
achar — e ainda apagar o rastro dela.

O que estes testes fixam:
  - CEPA_DOCTOR_INSTALL=off desliga a reinstalação;
  - doctor chamado de dentro de um diretório temporário também não reinstala
    (a rede para o teste que ainda não foi escrito e vai esquecer a variável);
  - fora do temporário e sem a variável, a reinstalação continua permitida —
    o preflight não pode perder a função;
  - bloqueada, ela NÃO vira "falhou ao corrigir": sai do lote e vai para o
    bloco de decisão do dono, com o comando à mão.

Run: python3 tests/test_doctor_install_guard.py
"""

import importlib.machinery
import importlib.util
import os
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


def load_doctor():
    """Carrega o cepa-doctor como módulo — ele é script, sem extensão .py."""
    spec = importlib.util.spec_from_loader(
        "cepa_doctor", importlib.machinery.SourceFileLoader("cepa_doctor", str(DOCTOR)))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_variavel_desliga():
    D = load_doctor()
    antes = os.environ.get("CEPA_DOCTOR_INSTALL")
    os.environ["CEPA_DOCTOR_INSTALL"] = "off"
    try:
        check("CEPA_DOCTOR_INSTALL=off desliga a reinstalação",
              D.install_automatico_permitido() is False)
        ok, msg = D.fix_install({"kind": "install", "repo": str(REPO)})
        check("e o fix_install recusa em vez de rodar o install.sh",
              ok is False and "instalação da máquina" in msg, msg)
    finally:
        os.environ.pop("CEPA_DOCTOR_INSTALL", None)
        if antes is not None:
            os.environ["CEPA_DOCTOR_INSTALL"] = antes


def test_diretorio_temporario_desliga():
    D = load_doctor()
    origem = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            check("doctor rodando de um diretório temporário não reinstala",
                  D.install_automatico_permitido() is False)
        finally:
            os.chdir(origem)


def test_tmp_tambem_conta_como_temporario():
    """No macOS o tempdir do Python é /var/folders/...; quem rodar de /tmp
    passaria batido se a lista tivesse só o gettempdir()."""
    D = load_doctor()
    origem = Path.cwd()
    alvo = Path("/private/tmp") if Path("/private/tmp").is_dir() else Path("/tmp")
    if not alvo.is_dir():
        return
    os.chdir(alvo)
    try:
        check("/tmp também conta como temporário",
              D.install_automatico_permitido() is False)
    finally:
        os.chdir(origem)


def test_uso_real_continua_permitido():
    D = load_doctor()
    origem = Path.cwd()
    os.chdir(REPO)
    try:
        check("fora do temporário e sem a variável, a reinstalação segue permitida",
              D.install_automatico_permitido() is True)
    finally:
        os.chdir(origem)


def test_bloqueada_vira_decisao_do_dono_nao_falha():
    D = load_doctor()
    os.environ["CEPA_DOCTOR_INSTALL"] = "off"
    try:
        D.RESULTS.clear()
        D.warn("plugins", "common: repo está em 9.9.9 mas o cache instalado é 1.0.0",
               fix={"kind": "install", "repo": str(REPO)})
        pend = D.pending_fixes()
        check("a reinstalação bloqueada sai do lote automático",
              all(f["kind"] != "install" for f in pend), pend)
        check("mas o achado continua no relatório para o dono decidir",
              any("cache instalado" in r[2] for r in D.RESULTS))
    finally:
        os.environ.pop("CEPA_DOCTOR_INSTALL", None)
        D.RESULTS.clear()


def test_ponta_a_ponta_o_install_sh_nao_roda():
    """A prova que interessa: o `bin/install.sh` não é EXECUTADO.

    Monta um HOME falso cujo marketplace aponta para um repo falso, cujo
    install.sh só escreve um marcador. Se o doctor rodar a reinstalação, o
    marcador aparece — foi assim que a instalação do dono foi trocada.
    """
    import json
    import subprocess
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        fake_home = tmpp / "home"
        (fake_home / ".claude" / "plugins").mkdir(parents=True)
        fake_repo = tmpp / "cepa-falso"
        (fake_repo / "bin").mkdir(parents=True)
        marcador = tmpp / "INSTALL-RODOU"
        (fake_repo / "bin" / "install.sh").write_text(
            f"#!/bin/sh\ntouch '{marcador}'\n", encoding="utf-8")
        (fake_repo / "bin" / "install.sh").chmod(0o755)
        for plug in ("common",):
            d = fake_repo / plug / ".claude-plugin"
            d.mkdir(parents=True)
            (d / "plugin.json").write_text(
                json.dumps({"name": plug, "version": "9.9.9"}), encoding="utf-8")
        (fake_home / ".claude" / "plugins" / "known_marketplaces.json").write_text(
            json.dumps({"cepa": {"installLocation": str(fake_repo)}}), encoding="utf-8")

        proj = tmpp / "proj"
        proj.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=proj)
        (proj / ".claude").mkdir()
        (proj / ".claude" / "no-build").touch()

        env = dict(os.environ, HOME=str(fake_home))
        env.pop("CEPA_DOCTOR_INSTALL", None)
        subprocess.run([sys.executable, str(DOCTOR), "--fix"], capture_output=True,
                       text=True, cwd=str(proj), env=env)
        check("o install.sh NÃO roda quando o doctor é chamado de um temporário",
              not marcador.exists())


def test_correcao_que_nao_resolve_roda_uma_vez_so():
    """O lote tenta cada correção UMA vez, mesmo que o achado sobreviva.

    O `--fix` re-diagnostica entre as passadas (uma correção muda o que as
    outras enxergam). Sem memória do que já foi tentado, a correção que não
    resolve o próprio achado voltava a ser aplicada a cada passada: três
    execuções do install.sh e a mesma linha repetida três vezes no relatório.
    """
    import json
    import subprocess
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        fake_home = tmpp / "home"
        (fake_home / ".claude" / "plugins").mkdir(parents=True)
        fake_repo = tmpp / "cepa-falso"
        (fake_repo / "bin").mkdir(parents=True)
        contador = tmpp / "execucoes"
        (fake_repo / "bin" / "install.sh").write_text(
            f"#!/bin/sh\necho x >> '{contador}'\n", encoding="utf-8")
        (fake_repo / "bin" / "install.sh").chmod(0o755)
        d = fake_repo / "common" / ".claude-plugin"
        d.mkdir(parents=True)
        (d / "plugin.json").write_text(
            json.dumps({"name": "common", "version": "9.9.9"}), encoding="utf-8")
        (fake_home / ".claude" / "plugins" / "known_marketplaces.json").write_text(
            json.dumps({"cepa": {"installLocation": str(fake_repo)}}), encoding="utf-8")

        proj = tmpp / "proj"
        proj.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=proj)
        (proj / ".claude").mkdir()
        (proj / ".claude" / "no-build").touch()

        # HOME=temporário mas cwd=repo real: a trava do temporário não vale
        # aqui, senão o install nem seria tentado e o teste não mediria nada.
        env = dict(os.environ, HOME=str(fake_home))
        env.pop("CEPA_DOCTOR_INSTALL", None)
        out = subprocess.run([sys.executable, str(DOCTOR), "--fix"], capture_output=True,
                             text=True, cwd=str(REPO), env=env)
        n = len(contador.read_text().splitlines()) if contador.exists() else 0
        check("a reinstalação que não resolve o achado roda UMA vez, não três",
              n == 1, f"{n} execuções\n{out.stdout[-800:]}")
        check("e o relatório não repete a mesma linha",
              out.stdout.count("plugins reinstalados a partir do repo") <= 1, out.stdout[-800:])


def main():
    test_variavel_desliga()
    test_diretorio_temporario_desliga()
    test_tmp_tambem_conta_como_temporario()
    test_uso_real_continua_permitido()
    test_bloqueada_vira_decisao_do_dono_nao_falha()
    test_ponta_a_ponta_o_install_sh_nao_roda()
    test_correcao_que_nao_resolve_roda_uma_vez_so()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
