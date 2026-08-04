"""Cola entre os dois estilos de teste que convivem neste diretório.

Boa parte das suítes daqui são scripts: funções `test_*(tmp)` chamadas por um
`main()` que cria o diretório temporário e passa adiante
(`python3 tests/test_maestro_run_cores.py` → "all green"). O pytest coleta essas
mesmas funções pelo nome, vê o parâmetro `tmp` e procura uma fixture com esse
nome — não acha, e reporta 4 ERROs que parecem teste quebrado sem nenhum teste
quebrado. Suíte que reporta vermelho sem defeito ensina a ignorar vermelho.

A fixture abaixo entrega a `tmp` que o `main()` entregaria, com os mesmos
subdiretórios, para os dois caminhos darem o mesmo resultado.
"""
import tempfile

import pytest

# Os subdiretórios que o main() de test_maestro_run_cores.py cria antes de
# chamar as funções: cada cenário de poll precisa do seu, senão um vaza no outro.
SUBDIRS = "a b c d e f g".split()


@pytest.fixture
def tmp():
    with tempfile.TemporaryDirectory() as d:
        from pathlib import Path
        for sub in SUBDIRS:
            (Path(d) / sub).mkdir()
        yield d
