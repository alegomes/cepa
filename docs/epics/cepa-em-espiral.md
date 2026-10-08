# Epic: Cepa em espiral

**Status:** rascunho · **Aberto em:** 2026-10-08 · **Origem:** `docs/estrategia-cepa-proximo-nivel.md` (rev. 3, decisões 1 a 10 respondidas "sim" em 2026-10-08)
**Repositório:** cepa · **Construção:** filas `single-track` em `.claude/programs/cepa-espiral-c<N>/plan.yaml`, uma por ciclo, drenadas por `cepa-until` à noite · **Aceite:** o roteiro de demonstração de cada ciclo, assistido pelo dono.

Este é o primeiro documento no formato que o P1 da estratégia descreve, escrito à mão para o próprio Cepa. O formato é testado aqui antes de servir ao Epic de produto.

## Intenção

O dono escreve o que quer em prosa e responde, por ciclo, "o que alguém vê funcionando que não via antes". O harness faz o resto, inclusive abrir as sessões. Hoje o dono é o escalonador: ele abre cada sessão, escolhe o modo, cola o brief e decide quando a próxima começa. Este Epic tira o dono desse papel sem tirar dele as decisões que são dele.

## Invariantes (nunca regridem)

- As noites de `cepa-until` continuam funcionando: `docs/proof/cepa-until.yaml` e `docs/proof/cepa-until-cota.yaml` passam ao fim de todo ciclo.
- Sessão interativa continua com um modo só e gate de escrita (Peça 2b). A revogação da decisão 3 vale só para filhos do condutor.
- `plan.yaml` continua com dois modos. Nenhum consumidor passa a recusar um plano de hoje.
- A `main` do cepa só muda com o dono presente (R1).

## Escada de valor

| Ciclo | Roteiro de demonstração (o que o dono vê) | O que atravessa | Quando |
|---|---|---|---|
| 1. Encadear | O dono encerra uma sessão no cepa com `/common:wrap-up` e, sem digitar mais nada, a próxima sessão abre no repo certo (`wego-product`), no modo certo (descoberta), com o brief do handoff na tela. `/common:metrics` imprime o scorecard com os três números que já existem (turnos após rotina, builds vermelhos, fração de sessões no cepa). `cepa-plan` aceita o campo `demonstra:` no cabeçalho de uma fila `single-track` e `/common:plan` o escreve a partir de um `docs/epics/<nome>.md`. | launcher `cepa` → handoff → `cepa-plan` → `cepa-metrics` | próximas noites de `cepa-until`, em paralelo ao ciclo 1 do Epic Contratos |
| 2. Conduzir | Com a escada do Epic Contratos aprovada, o dono vai dormir e de manhã o ciclo 2 do Contratos está demonstrável: construção (drain), prova (`ui-proof-reviewer` com nonce) e aterrissagem em branch própria rodaram sozinhas, em worktrees filhas com o modo de cada estágio. Um needs-human em item com dependentes parou o ciclo em `aguardando-dono` e a pergunta está no terminal. | `cepa-until` como tronco + fork de filhos e merge train extraídos do Maestro como biblioteca; `/maestro:run` deprecado | depois de um ciclo inteiro do Contratos medido com o dono como condutor manual |
| 3. Aprender e podar | O mesmo bloqueio de hook pela terceira vez no mesmo repo vira uma linha na memória do projeto e o filho seguinte não repete o erro. Toda mensagem de bloqueio cabe numa linha. Todo evento de telemetria traz a versão do plugin. O scorecard mostra que número cada mudança moveu, e o BACKLOG perde o que não move nenhum. | hooks → memória do projeto → `_telemetry.py` → `cepa-metrics` | depois do ciclo 2, guiado pelo scorecard |
| 4. Descoberta assistida | O condutor abre a sessão de descoberta do próximo ciclo de um Epic com o mapa de cobertura já montado (tipos de cláusula vistos vs. modelados) e as perguntas que só o dono responde. Decisões mecânicas do condutor (classificar needs-human, detectar reincidência) avaliadas contra um modelo de decisão tipada (Jev). | condutor → `/common:spec` → mapa de cobertura | quando houver dois Epics de produto com ciclo fechado |

## Como os ciclos se cruzam com o Epic de produto

Os dois Epics andam intercalados. O ciclo 1 do Contratos começa com a ferramenta de hoje e o dono fazendo à mão o que o ciclo 2 deste Epic vai automatizar; é dele que saem os números de base. O ciclo 1 deste Epic roda nas noites de `cepa-until` enquanto isso. O ciclo 2 deste Epic só começa quando houver um ciclo do Contratos medido de ponta a ponta.

## Decidido sem perguntar (vete aqui)

- O Epic de produto Contratos e Regras tem documento próprio em `wego-product/docs/epics/`, não aqui.
- A demo do Contratos vive em repositório próprio `wego-contratos-demo`, como diz o ADR 0013 (decisão do dono em 2026-10-08). Por isso o ciclo 1 do Contratos é multi-repo desde o início, e o `demonstra:` de uma fila pode apontar para a prova de UI em outro repositório.

## Perguntas em aberto

- [ ] Quantos contratos de operadora existem em mãos além do Cassi 2004 e dos instrumentos de 2022? Decide se o mapa de cobertura é possível no ciclo 1 do Contratos.
- [ ] Quem escreve o roteiro de demonstração do ciclo 1 do Contratos: o dono em prosa, para o harness derivar os itens. Isso exige uma sessão com o dono; o ciclo 1 deste Epic faz o harness abri-la.
