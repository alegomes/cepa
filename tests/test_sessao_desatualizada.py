#!/usr/bin/env python3
"""Regression tests para a foto de versão que a sessão carrega no boot.

O harness ja sabia dizer "voce editou o repo e nao reinstalou" (_pluginver.scan
compara REPO com CACHE). Ele nao sabia dizer o oposto, que e mais traicoeiro:
voce reinstalou COM a sessao aberta — o cache fica novo, a sessao segue
executando os hooks que leu na abertura, e nada na tela distingue os dois.

A foto (`plugin_versions` na entrada do registry) e o que torna a pergunta
respondivel: comparando o que a sessao carregou com o que o cache tem AGORA.

Contratos guardados aqui:
  - sessao cuja foto bate com o cache → nada a dizer;
  - sessao cuja foto ficou para tras → aparece, com as duas versoes;
  - sessao SEM foto (aberta antes deste check existir) → silencio, nunca um
    alarme inventado a partir de dado que nao existe;
  - plugin que sumiu do cache nao vira alerta — some da comparacao;
  - session-registry.py grava a foto no SessionStart.

Rode com `python3 tests/test_sessao_desatualizada.py`.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "common" / "hooks"))
import _pluginver as V  # noqa: E402

# Este teste cita hook emissor de telemetria. Hoje ele não chega a executá-lo,
# mas citar e executar são um passo um do outro, e foi essa distância que
# deixou 7 testes poluindo o ledger real por um mês. Ver
# tests/_telemetria_isolada.py.
from _telemetria_isolada import isola

isola()


failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def com_cache(mapa):
    """Troca o cache real por um fixo, para o teste nao depender da maquina."""
    original = V.loaded_now
    V.loaded_now = lambda: mapa
    return original


def test_em_dia():
    orig = com_cache({"common": "1.0.0", "board-flow": "0.15.0"})
    try:
        r = V.session_stale({"plugin_versions": {"common": "1.0.0",
                                                 "board-flow": "0.15.0"}})
        check("em dia: nada a dizer", r == [], str(r))
    finally:
        V.loaded_now = orig


def test_ficou_para_tras():
    orig = com_cache({"common": "1.0.0", "board-flow": "0.15.0"})
    try:
        r = V.session_stale({"plugin_versions": {"common": "0.30.0",
                                                 "board-flow": "0.15.0"}})
        check("atrasada: aparece", len(r) == 1, str(r))
        check("atrasada: diz as duas versões",
              r == [("common", "0.30.0", "1.0.0")], str(r))
    finally:
        V.loaded_now = orig


def test_sem_foto_e_silencio():
    orig = com_cache({"common": "1.0.0"})
    try:
        check("sem chave: silêncio", V.session_stale({}) == [])
        check("foto vazia: silêncio", V.session_stale({"plugin_versions": {}}) == [])
        check("entrada None: silêncio", V.session_stale(None) == [])
    finally:
        V.loaded_now = orig


def test_plugin_sumido_do_cache():
    orig = com_cache({"common": "1.0.0"})
    try:
        r = V.session_stale({"plugin_versions": {"common": "1.0.0",
                                                 "extinto": "0.1.0"}})
        check("plugin fora do cache não vira alerta", r == [], str(r))
    finally:
        V.loaded_now = orig


def test_registry_grava_a_foto():
    src = (REPO / "common" / "hooks" / "session-registry.py").read_text()
    check("session-registry grava plugin_versions",
          'entry.setdefault("plugin_versions", V.loaded_now())' in src)


def test_loaded_now_nao_levanta():
    """O contrato do módulo: nada aqui quebra quem chama. Um comparador que
    derruba o boot da sessão seria desligado, e aí não protege ninguém."""
    try:
        r = V.loaded_now()
        check("loaded_now devolve um mapa", isinstance(r, dict), str(type(r)))
    except Exception as e:  # noqa: BLE001
        check("loaded_now devolve um mapa", False, repr(e))


def main():
    print("test_sessao_desatualizada")
    for fn in (test_em_dia, test_ficou_para_tras, test_sem_foto_e_silencio,
               test_plugin_sumido_do_cache, test_registry_grava_a_foto,
               test_loaded_now_nao_levanta):
        fn()
    if failures:
        print(f"\n{len(failures)} falha(s): {', '.join(failures)}")
        return 1
    print("\ntudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
