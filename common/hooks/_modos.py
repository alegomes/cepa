#!/usr/bin/env python3
"""_modos — a tabela dos modos de trabalho, em UM lugar só.

## Por que existe

O modo de uma sessão é um ESTADO que dura (`docs/modos-de-trabalho.md`), e cada
modo tem entrada, produto e condição de saída. Essa informação estava em três
lugares que não conversavam:

- `common/bin/cepa` — a lista de nomes válidos (`MODOS=`), para validar `--modo`;
- `common/hooks/session-mode.py` — só as condições de saída, para injetar no turno;
- `docs/modos-de-trabalho.md` — a prosa completa, que ninguém lê no meio da sessão.

Quem esquece o propósito de um modo no meio do trabalho não vai abrir um doc de
307 linhas. E três cópias da mesma tabela é o padrão que este repo já pagou caro
(memória `hooks-texto-citado-nao-e-shell`: 7 cópias do mesmo parser, conserto
aplicado em 5). Aqui a tabela é uma; o hook importa, o `cepa-modos` imprime, e
`tests/test_modos_fonte_unica.py` reprova se a lista do `cepa` divergir daqui.

Cada modo declara também `escrita`: a lista branca de DESTINOS que ele produz,
lida pelo `modo-escrita-gate.py`. `"tudo"` significa que o modo não tem lista —
não que ele é livre de cobrança: na construção quem cobra são o
completion-auditor e o proof-reviewer, e na reforma o `reforma-gate.py`.

`deploy` NÃO está aqui de propósito: é o 8º modo do documento, deixado fora da
rodada por decisão do dono (é o único que depende de infra externa). Quando
entrar, entra aqui primeiro.
"""

# ordem = a ordem do ciclo de trabalho, não alfabética
MODOS = {
    "exploracao": {
        "proposito": "entender uma dor que ainda não tem solução proposta, e sair com um caminho recomendado",
        "entrada": "uma dor em linguagem natural, SEM solução proposta — se você "
                   "já sabe a solução, não é exploração",
        "produz": "um documento de estratégia com 2+ caminhos considerados, um "
                  "recomendado, e a dor reformulada com o que se aprendeu",
        "saida": "um documento de estratégia com 2+ caminhos considerados, "
                 "passado pelo painel /common:advisors com as discordâncias nomeadas",
        "gate": "parcial — o painel existe, o veredito não; o modo-escrita-gate já barra escrita fora de docs/**",
        "escrita": ["docs/**", ".claude/**", "BACKLOG.md"],
    },
    "descoberta": {
        "proposito": "virar um comportamento desejado em critério de aceite cobrável, com evidência atrás",
        "entrada": "um comportamento desejado, vindo da exploração ou direto",
        "produz": "oportunidade enquadrada, evidência coletada, e os critérios de "
                  "aceite escritos NA ALTITUDE em que serão cobrados",
        "saida": "evidence-auditor Confirmed nas suposições de risco + os "
                 "critérios de aceite escritos na altitude + o teste vermelho de cada um",
        "gate": "em parte: o spec-readiness-gate barra especificação pronta sem superfície e teste vermelho declarados por critério, mas não roda o teste; o modo-escrita-gate barra escrita fora de docs/discovery e docs/spec",
        "escrita": ["docs/discovery/**", "docs/spec/**", ".claude/**", "BACKLOG.md"],
    },
    "design": {
        "proposito": "desenhar como a coisa funciona e como ela se parece, antes de existir código",
        "entrada": "oportunidade validada",
        "produz": "fluxos, estados, spec visual reconciliada com o design system, "
                  "protótipo compartilhável",
        "saida": "design-critic devolvendo SHIP",
        "gate": "existe e funciona (topologia design); o modo-escrita-gate barra escrita fora de docs/design",
        "escrita": ["docs/design/**", ".claude/**", "BACKLOG.md"],
    },
    "construcao": {
        "proposito": "escrever o código que faz o teste vermelho do critério ficar verde",
        "entrada": "UM TESTE VERMELHO escrito a partir do critério de aceite, antes "
                   "do código, por quem não vai implementar",
        "produz": "código + testes",
        "saida": "completion-auditor COMPLETE e proof-reviewer PROVEN",
        "gate": "existe e funciona (os dois gates, nesta ordem)",
        "escrita": "tudo",
    },
    "reforma": {
        "proposito": "reorganizar código já entregue sem mudar nada que se veja de fora",
        "entrada": "ORÇAMENTO DECLARADO — a lista fechada do que será reformado e o "
                   "limite; sem orçamento a reforma nunca termina",
        "produz": "código reorganizado, comportamento externo idêntico",
        "saida": "o orçamento declarado exaurido, build verde, e NENHUM teste "
                 "externo editado (teste editado = mudou comportamento = não era reforma)",
        "gate": "reforma-gate.py bloqueia editar teste externo enquanto o modo dura",
        "escrita": "tudo",
    },
    "reflexao": {
        "proposito": "olhar o que já existe por uma lente escolhida e transformar cada achado em destino",
        "entrada": "um RECORTE e uma LENTE, ambos escolhidos de menu — reflexão sem "
                   "recorte vira leitura infinita do repo",
        "produz": "um relatório de achados classificados",
        "saida": "nenhum achado sem destino — cada um virou card ou foi "
                 "descartado com motivo escrito",
        "gate": "reflexao-gate.py barra relatório fechado com achado solto, e o modo-escrita-gate barra escrita fora de docs/** e .claude/reflexao",
        "escrita": [".claude/reflexao/**", "docs/**", "BACKLOG.md"],
    },
    "documentacao": {
        "proposito": "documentar código estável na árvore Diátaxis, com cada porquê citando sua fonte",
        "entrada": "código estável, não em construção ativa",
        "produz": "a árvore Diátaxis fundamentada",
        "saida": "consistency-reviewer PASS e sua assinatura em /docs:finalize",
        "gate": "existe e funciona (topologia docs); o modo-escrita-gate barra escrita fora de docs/**",
        "escrita": ["docs/**", ".claude/**", "BACKLOG.md"],
    },
}

# O que `session-mode.py` injeta a cada turno — só a condição de saída.
SAIDA = {nome: d["saida"] for nome, d in MODOS.items()}
