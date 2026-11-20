# Especificação: os comandos do Cepa rodam em qualquer repo sem pedir `pip install pyyaml`

**Status:** ready-to-build
**Aberta em:** 2026-11-19            **Fechada em:** 2026-11-20
**Fontes lidas:** common/bin/cepa-plan (linhas 254-261), common/bin/cepa-dor, common/bin/cepa-until, common/bin/cepa-until-digest, common/bin/cepa, common/bin/cepa-doctor, maestro/bin/*, board-flow/bin/cepa-plan, board-flow/bin/waivers.py, board-flow/bin/classify_needs_human.py, board-flow/board-flow-fleet-validate.sh, common/hooks/merge-truth-gate.py, common/hooks/acceptance-gate.py, common/hooks/_autonomy.py, common/hooks/_jiramut.py, build-hex/hooks/proof-verdict-guard.py, common/commands/consolidate.md, bin/install.sh, bin/gen-locks.py, docs/internals/extending.md, docs/spec/registro-de-plugins-pasta-estavel.md, README.md, ~/coding/fin/.python-version

## Como chegamos aqui
"E esta dependência?" (dono, 2026-11-19, mostrando no terminal, dentro de `~/coding/fin`: `cepa plan ready` respondendo `cepa-plan precisa de PyYAML (pip install pyyaml)`)

## Problema
Os executáveis do Cepa começam com `#!/usr/bin/env python3` e importam PyYAML, uma biblioteca que não vem com o Python. Quem decide qual `python3` roda é o repo onde o dono está, não o Cepa. Em `~/coding/fin` o `python3` é o do Homebrew (3.15), sem PyYAML, e `cepa plan ready` morre com "precisa de PyYAML". No repo do Cepa funciona só porque o Python do pyenv (3.14.0rc1) por acaso tem PyYAML 6.0.3.

Os hooks que importam PyYAML não morrem: quando a biblioteca falta eles devolvem vazio e seguem (por exemplo `acceptance-gate.py`, linhas 136-140, lê o `board-flow.yaml` como vazio). O efeito é um portão que deixa de conferir sem avisar ninguém.

PyYAML é a única biblioteca de fora do Python que o Cepa importa fora de `tests/` (varredura de todos os imports em 2026-11-19). Onde ela é importada:
- executáveis e scripts (12): `common/bin/cepa-plan`, `cepa-dor`, `cepa-until`, `cepa-until-digest`; `maestro/bin/maestro-poll`, `maestro-fork-settings`, `maestro-programs`, `maestro-wave-state`, `maestro-prune`; `board-flow/bin/waivers.py`, `classify_needs_human.py`; `board-flow/board-flow-fleet-validate.sh`.
- hooks (9): `common/hooks/merge-truth-gate.py`, `ui-proof-verdict-guard.py`, `expertise-append.py`, `_autonomy.py`, `acceptance-gate.py`, `_jiramut.py`, `reflection-gate.py`, `jira-create-fields-gate.py`; `build-hex/hooks/proof-verdict-guard.py`.

## Escopo
### Entra
- Uma cópia do PyYAML 6.0.3, só os arquivos `.py` e a licença dele, em `<plugin>/_vendor/yaml/` de cada plugin que lê YAML: `common`, `board-flow`, `maestro`, `build-hex`.
- Os 21 arquivos da lista acima passam a importar `yaml` da cópia do próprio plugin, colocada na frente de qualquer PyYAML instalado no Python.
- Um script `bin/gen-vendor.py` que gera as cópias de `board-flow`, `maestro` e `build-hex` a partir da de `common` (`--write`) e acusa divergência (`--check`), no mesmo molde do `bin/gen-locks.py`.
- Um hook que não consegue importar a cópia escreve uma linha no stderr dizendo qual hook não conferiu e por quê, e segue sem bloquear.
- Some o texto "precisa de PyYAML (pip install pyyaml)" dos executáveis; a regra de `docs/internals/extending.md` que proíbe dependência externa passa a dizer que YAML se lê pela cópia.
- O trecho de `common/commands/consolidate.md` que valida o arquivo com `python3 -c "import yaml..."` passa a apontar para a cópia de `common`.
### Não entra
- Python próprio (venv) do Cepa: descartado na rodada 1, pede rede e quebra em atualização do Homebrew.
- Leitor próprio de YAML no lugar do PyYAML: as filas e provas são YAML aninhado.
- Os arquivos de `tests/` que importam `yaml` direto: rodam no Python de quem desenvolve o Cepa, que já tem PyYAML.
- Checagem nova no `cepa-doctor`: com a cópia dentro do plugin não há mais o que instalar.
- Python abaixo de 3.8 (o mínimo do PyYAML 6.0.3): o Cepa já não roda nele por outros motivos.
- O item do BACKLOG.md sobre `head_commit` lido como número: é comportamento do PyYAML, igual com ou sem a cópia.

## Estado e migração
Nenhum dado muda de formato. O PyYAML que já estiver instalado em algum Python fica onde está e deixa de ser usado pelo Cepa. Para a cópia chegar à pasta instalada (`~/.claude/cepa-live`) é preciso rodar `bin/install.sh` uma vez depois do merge; o instalador já copia a pasta inteira de cada plugin, então `_vendor/` vai junto sem mudança nele.

## Critérios de sucesso

### CS-1: `cepa plan ready` lista os itens prontos num repo cujo `python3` não tem PyYAML
**Surface:** cli
**Red test:** num repo temporário com uma fila de um item pronto, e com um `python3` na frente do PATH que roda o Python real com `-S` (opção que desliga as bibliotecas instaladas), `common/bin/cepa-plan ready` sai com código 0 e mostra o item. Hoje sai com código 2 e "cepa-plan precisa de PyYAML".

### CS-2: os outros 11 executáveis e scripts da lista rodam com o mesmo `python3` sem PyYAML
**Surface:** cli
**Red test:** com o mesmo `python3` sem bibliotecas instaladas no PATH, cada um dos 11 (`cepa-dor`, `cepa-until`, `cepa-until-digest`, os cinco `maestro-*`, `waivers.py`, `classify_needs_human.py`, `board-flow-fleet-validate.sh` lendo um `board-flow.yaml`) lê um arquivo YAML de exemplo e termina sem a palavra "PyYAML" no stderr. Hoje `cepa-dor`, `cepa-until` e os cinco `maestro-*` saem com "precisa de PyYAML", e o `board-flow-fleet-validate.sh` sai com "PyYAML missing".

### CS-3: os hooks leem o YAML de verdade quando o `python3` não tem PyYAML
**Surface:** event
**Red test:** com o `python3` sem bibliotecas instaladas, a leitura do `board-flow.yaml` feita por `acceptance-gate.py`, `merge-truth-gate.py` e `_jiramut.py` devolve o conteúdo do arquivo de exemplo, e `proof-verdict-guard.py` lê o veredito de uma prova de exemplo. Hoje as três primeiras devolvem vazio e a quarta levanta erro de import.

### CS-4: um hook que não consegue carregar a cópia avisa em uma linha e não bloqueia
**Surface:** event
**Red test:** numa cópia temporária do plugin `common` sem a pasta `_vendor/yaml`, e com o `python3` sem bibliotecas instaladas, `acceptance-gate.py` recebe um evento de exemplo, sai com código 0 e escreve no stderr uma linha com o nome do hook e o motivo. Hoje sai com código 0 e stderr vazio.

### CS-5: as quatro cópias são idênticas e o desvio é acusado
**Surface:** cli
**Red test:** `python3 bin/gen-vendor.py --check` sai com código 0 com as quatro cópias iguais, e sai diferente de 0 nomeando o arquivo quando um byte de `maestro/_vendor/yaml/scanner.py` é alterado. Hoje o script e as cópias não existem.

### CS-6: a cópia do Cepa vale mesmo quando o Python tem outro PyYAML instalado
**Surface:** cli
**Red test:** com `PYTHONPATH` apontando para uma pasta que tem um `yaml/__init__.py` falso que levanta erro ao ser importado, `common/bin/cepa-plan ready` sai com código 0 no repo temporário do CS-1. Hoje o falso é importado e o comando quebra.

## Perguntas em aberto
- [x] Caminho: o Cepa carrega uma cópia do PyYAML dentro do próprio repo, cria um Python próprio (venv) na instalação, ou troca o PyYAML por leitor próprio de YAML? — Cópia do PyYAML dentro do repo (dono, 2026-11-19). O venv saiu porque pede rede na instalação, quebra quando o Homebrew atualiza o Python e os executáveis rodam do clone, não da pasta instalada.
- [x] Fronteira: só os 12 executáveis e scripts, ou também os 9 hooks que hoje ficam cegos em silêncio quando o PyYAML falta? — Os 21 arquivos, executáveis e hooks (dono, 2026-11-19).
- [x] Hook sem PyYAML: depois da mudança, se mesmo assim o import falhar, o hook segue calado como hoje ou avisa na tela? — Avisa em uma linha no stderr e segue sem bloquear (dono, 2026-11-19).
- [x] Onde mora a cópia: uma por plugin que usa YAML (`common`, `board-flow`, `maestro`, `build-hex`), geradas de uma origem só e travadas por teste, ou uma única em `common` que os outros plugins procuram? — Uma por plugin, geradas de uma origem e travadas por teste (dono, 2026-11-19).
- [x] Quando o Python do repo também tem PyYAML instalado, qual vale: sempre a cópia do Cepa, ou a instalada primeiro e a cópia só como reserva? — Sempre a cópia (dono, 2026-11-19).

## Decided without asking
- A versão copiada é o PyYAML 6.0.3, só os `.py`, sem o módulo acelerado em C — é a versão que o Cepa já usa hoje nesta máquina, e o módulo em C é específico de cada Python. Vete aqui se discordar. · mantida em 2026-11-20
- A pasta se chama `_vendor/yaml/` na raiz de cada plugin, e a de `common` é a origem das outras três — o sublinhado segue o nome dos módulos internos (`_tui`, `_clihelp`). Vete aqui se discordar. · mantida em 2026-11-20
- A licença MIT do PyYAML vai junto em cada cópia — a licença exige o texto acompanhando o código. Vete aqui se discordar. · mantida em 2026-11-20
- O script gerador é `bin/gen-vendor.py` com `--write` e `--check`, e um teste em `tests/` chama o `--check` — mesmo desenho do `bin/gen-locks.py`, que o repo já conhece. Vete aqui se discordar. · mantida em 2026-11-20
- Subir a versão do PyYAML é manual: trocar os arquivos em `common/_vendor/yaml/` e rodar `--write`. Sem comando que baixa da internet — acontece raramente e não justifica código com rede. Vete aqui se discordar. · mantida em 2026-11-20
- O aviso do hook (CS-4) sai toda vez que o hook roda, sem "uma vez por sessão" — com a cópia dentro do plugin o caso é raro, e guardar estado só para calar um aviso raro custa mais que o ruído. Vete aqui se discordar. · mantida em 2026-11-20
- O teste simula "Python sem PyYAML" com um `python3` no PATH que chama o Python real com `-S`, sem instalar outro Python — roda em qualquer máquina e no CI. Vete aqui se discordar. · mantida em 2026-11-20
- O trecho de `consolidate.md` entra no escopo — é um comando do Cepa que falharia em `~/coding/fin` pelo mesmo motivo. Vete aqui se discordar. · mantida em 2026-11-20

## Riscos e o que ficou de fora desta especificação
- Correção de segurança do PyYAML não chega sozinha: alguém precisa subir a cópia à mão. O Cepa só usa `safe_load` em arquivos do próprio repo, o que limita a exposição.
- O repo cresce 868 KB (4 cópias x 217 KB, medido em `site-packages/yaml/*.py` do PyYAML 6.0.3).
- Sessões abertas antes do `bin/install.sh` seguem com os hooks antigos até reiniciar.
- `tests/` continua pedindo PyYAML no Python de quem desenvolve.
