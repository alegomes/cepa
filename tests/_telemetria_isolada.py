"""Manda a telemetria de um teste para um ledger descartável, nunca para o seu.

O defeito (medido em 26/08/2026 pelo próprio `/common:metrics`): os hooks gravam
eventos em `~/.claude/cepa-telemetry/` e a suíte executa esses mesmos hooks. Só
3 dos 53 arquivos de teste definiam `CEPA_TELEMETRY_DIR`; outros 7 executavam
hook emissor sem isolar e escreviam no ledger de verdade — o arquivo que o
`/common:metrics` lê para dizer como o harness se comporta no seu uso real.

O estrago não é volume (81 eventos por rodada da suíte), é leitura errada: o
relatório de 26/08 listava repos que não existem — `main-repo` com 206 verdes e
206 vermelhos, e empate exato é assinatura de fixture, não de trabalho — além de
`r2`, `r3`, `r4`, `pert2`, `sem-git`. As duas linhas de maior volume das
"Leituras sugeridas" daquele relatório (`r3: 39 bloqueios`, `?: 310 artefatos
proven barrados`) eram ensaio, não uso. Métrica que mistura ensaio com uso
mede o ensaio.

Uso, no topo do teste, antes de qualquer subprocesso:

    from _telemetria_isolada import isola
    isola()

O import cru funciona porque `python3 tests/test_x.py` põe `tests/` como
sys.path[0]. Foi tentado antes um `tests/sitecustomize.py`, que pegaria os 7 de
uma vez sem tocar em nenhum: não funciona: o módulo `site` importa o
`sitecustomize` no arranque do interpretador, ANTES de o diretório do script
entrar no sys.path. A chamada explícita em cada arquivo é mais chata e é a que
funciona — e aparece na leitura do teste, em vez de agir à distância.

Quem mais chama: `tests/conftest.py` (família pytest) e `tests/run-all.sh`
(export próprio, para o isolamento ficar à vista de quem lê o runner).

Nunca sobrescreve um `CEPA_TELEMETRY_DIR` já definido — vários testes apontam
para o próprio tmpdir e conferem o que escreveram lá.
"""

import os
import tempfile
from pathlib import Path

# Caminho fixo, não um mkdtemp por processo: a suíte roda dezenas de processos e
# um temporário novo em cada um encheria o /tmp de lixo que ninguém olha. Fixo,
# dá para inspecionar quando um teste de telemetria falha.
NOME = "cepa-telemetry-tests"


def isola() -> str:
    """Aponta CEPA_TELEMETRY_DIR para o ledger descartável, se ninguém apontou.

    Devolve o diretório em uso (o já definido, ou o descartável)."""
    ja = os.environ.get("CEPA_TELEMETRY_DIR")
    if ja:
        return ja
    d = Path(tempfile.gettempdir()) / NOME
    os.environ["CEPA_TELEMETRY_DIR"] = str(d)
    return str(d)
