#!/usr/bin/env python3
"""Testes do aviso repo↔cache no boot da sessão (P0-4 da revisão 2026-08-17).

Sem dependências — rode com `python3 tests/test_pluginver_boot.py`.
Sai não-zero em falha.

O que está sendo travado, e por quê cada caso existe:

  - **Divergência avisa.** É a falha nº 1 do projeto (conserto commitado, não
    instalado, todos operando como se estivesse valendo). Se este caso passar a
    ficar verde com o aviso ausente, o alarme sumiu.
  - **Silêncio quando em dia.** Aviso que aparece toda sessão vira ruído e
    treina o olho a pular o dia em que importa. O silêncio é requisito, não
    acaso.
  - **Cache vazio conta como divergência.** "Nada instalado" é a versão extrema
    de "o que roda não é o repo".
  - **A mensagem nomeia o custo, não só o fato.** Dizer "0.28.0 → 0.27.1" para
    quem não conhece o esquema de versões não informa nada; o aviso tem que
    dizer o que NÃO está valendo.
  - **Nunca quebra o boot.** Um comparador que derruba o SessionStart seria
    desligado, e aí não protege ninguém. Diretório inexistente, JSON corrompido
    e permissão negada precisam sair como silêncio, não como exceção.
"""

import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

# Este teste cita hook emissor de telemetria. Hoje ele não chega a executá-lo,
# mas citar e executar são um passo um do outro, e foi essa distância que
# deixou 7 testes poluindo o ledger real por um mês. Ver
# tests/_telemetria_isolada.py.
from _telemetria_isolada import isola

isola()


REPO = Path(__file__).resolve().parent.parent
MOD = REPO / "common" / "hooks" / "_pluginver.py"

FAILURES = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok  {label}")
    else:
        FAILURES.append(f"{label}{' — ' + detail if detail else ''}")
        print(f"  FAIL {label}{' — ' + detail if detail else ''}")


def load(home: Path):
    """Carrega _pluginver com HOME apontando para um mundo de mentira.

    CLAUDE_DIR é resolvido no import (module-level), então cada cenário precisa
    de um import fresco — daí o loader manual em vez de um import comum.
    """
    os.environ["HOME"] = str(home)
    Path.home.cache_clear() if hasattr(Path.home, "cache_clear") else None
    loader = importlib.machinery.SourceFileLoader(f"_pv_{home.name}", str(MOD))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def make_world(tmp: Path, repo_versions: dict, cache_versions: dict, install=None):
    """Monta um ~/.claude + um clone do repo com as versões pedidas."""
    home = tmp
    claude = home / ".claude"
    repo = home / "src" / "cepa"
    for name, ver in repo_versions.items():
        d = repo / name / ".claude-plugin"
        d.mkdir(parents=True, exist_ok=True)
        (d / "plugin.json").write_text(json.dumps({"name": name, "version": ver}))
    for name, vers in cache_versions.items():
        for v in vers:
            (claude / "plugins" / "cache" / "cepa" / name / v).mkdir(parents=True, exist_ok=True)
    (claude / "plugins").mkdir(parents=True, exist_ok=True)
    (claude / "plugins" / "known_marketplaces.json").write_text(
        json.dumps({"cepa": {"installLocation": str(repo)}})
    )
    if install is not None:
        (claude / "ops").mkdir(parents=True, exist_ok=True)
        (claude / "ops" / "last-install.json").write_text(json.dumps(install))
    return home


# ── casos ────────────────────────────────────────────────────────────────────

def test_drift_avisa(tmp):
    home = make_world(
        Path(tmp) / "a",
        repo_versions={"common": "0.28.0", "board-flow": "0.12.0"},
        cache_versions={"common": ["0.27.1"], "board-flow": ["0.12.0"]},
    )
    m = load(home)
    n = m.boot_notice()
    check("divergência produz aviso", n is not None)
    if n:
        check("o aviso nomeia o plugin defasado", "common" in n)
        check("o aviso mostra as duas versões", "0.28.0" in n and "0.27.1" in n)
        check("o aviso NÃO acusa quem está em dia", "board-flow" not in n)
        check("o aviso diz o que não está valendo (custo, não só o fato)",
              "fora do ar" in n or "não está valendo" in n.lower())
        check("o aviso nomeia a saída", "install.sh" in n)


def test_em_dia_cala(tmp):
    home = make_world(
        Path(tmp) / "b",
        repo_versions={"common": "0.27.1"},
        cache_versions={"common": ["0.27.0", "0.27.1"]},
    )
    m = load(home)
    check("repo == cache → silêncio", m.boot_notice() is None)


def test_cache_mais_novo_cala(tmp):
    """Cache à frente do repo não é o problema deste alarme.

    Acontece de verdade: outro clone instalou uma versão mais nova. Isso merece
    o doctor, não um alarme no boot — o aviso existe para "editei e não
    instalei", e disparar aqui só ensinaria a ignorá-lo.
    """
    home = make_world(
        Path(tmp) / "c",
        repo_versions={"common": "0.27.0"},
        cache_versions={"common": ["0.28.0"]},
    )
    m = load(home)
    check("cache à frente do repo → silêncio", m.boot_notice() is None)


def test_cache_vazio_avisa(tmp):
    home = make_world(
        Path(tmp) / "d",
        repo_versions={"common": "0.27.1"},
        cache_versions={},
    )
    m = load(home)
    n = m.boot_notice()
    check("plugin sem nada no cache avisa", n is not None)
    if n:
        check("diz que não há nada instalado", "nada instalado" in n)


def test_idade_do_install_entra(tmp):
    home = make_world(
        Path(tmp) / "e",
        repo_versions={"common": "0.28.0"},
        cache_versions={"common": ["0.27.1"]},
        install={"status": "ok", "finished_at": "2026-08-01T10:00:00+00:00"},
    )
    m = load(home)
    n = m.boot_notice() or ""
    check("a idade do último install aparece", "último install há" in n)


def test_nunca_quebra_o_boot(tmp):
    # 1. ~/.claude inexistente
    home = Path(tmp) / "f"
    home.mkdir(parents=True, exist_ok=True)
    m = load(home)
    try:
        check("sem ~/.claude → None, sem exceção", m.boot_notice() is None)
    except Exception as e:  # noqa: BLE001
        check("sem ~/.claude → None, sem exceção", False, repr(e))

    # 2. known_marketplaces.json corrompido
    home2 = Path(tmp) / "g"
    (home2 / ".claude" / "plugins").mkdir(parents=True, exist_ok=True)
    (home2 / ".claude" / "plugins" / "known_marketplaces.json").write_text("{isto não é json")
    m2 = load(home2)
    try:
        check("marketplaces corrompido → None, sem exceção", m2.boot_notice() is None)
    except Exception as e:  # noqa: BLE001
        check("marketplaces corrompido → None, sem exceção", False, repr(e))

    # 3. plugin.json ilegível no repo — o plugin some do scan, os outros seguem
    home3 = make_world(
        Path(tmp) / "h",
        repo_versions={"common": "0.28.0"},
        cache_versions={"common": ["0.27.1"], "design": ["0.1.0"]},
    )
    bad = home3 / "src" / "cepa" / "design" / ".claude-plugin"
    bad.mkdir(parents=True, exist_ok=True)
    (bad / "plugin.json").write_text("{quebrado")
    m3 = load(home3)
    try:
        n = m3.boot_notice()
        check("plugin.json quebrado não derruba o resto", n is not None and "common" in n)
    except Exception as e:  # noqa: BLE001
        check("plugin.json quebrado não derruba o resto", False, repr(e))


def test_hook_importa_o_modulo():
    """O session-registry precisa realmente chamar isto — não basta existir.

    Perturbação equivalente: apagar a chamada em session-registry.py deixa este
    caso vermelho. É o que separa "módulo escrito" de "alarme ligado".
    """
    src = (REPO / "common" / "hooks" / "session-registry.py").read_text(encoding="utf-8")
    check("session-registry importa _pluginver", "import _pluginver" in src)
    check("session-registry chama boot_notice", "boot_notice()" in src)
    # O aviso precisa ser o PRIMEIRO da lista: um drift de versão contamina a
    # leitura de todos os outros avisos da sessão.
    i_drift = src.find("boot_notice()")
    i_overlap = src.find("other live session")
    check("o aviso de versão vem antes do de overlap",
          i_drift != -1 and i_overlap != -1 and i_drift < i_overlap)


def main():
    real_home = os.environ.get("HOME")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            test_drift_avisa(tmp)
            test_em_dia_cala(tmp)
            test_cache_mais_novo_cala(tmp)
            test_cache_vazio_avisa(tmp)
            test_idade_do_install_entra(tmp)
            test_nunca_quebra_o_boot(tmp)
        finally:
            if real_home:
                os.environ["HOME"] = real_home
    test_hook_importa_o_modulo()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} falha(s):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("all green")


if __name__ == "__main__":
    main()
