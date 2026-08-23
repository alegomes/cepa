# Especificação: planejador de lotes paralelos do backlog

**Status:** pronta-para-construir
**Aberta em:** 2026-08-23            **Fechada em:** 2026-08-23

## Problema

Hoje, para tocar várias demandas do BACKLOG.md em paralelo, alguém escolhe a dedo
quais demandas entram e conversa com o `/maestro:program-plan` sobre elas. Ninguém
varre os 109 títulos do backlog inteiro e devolve "estes são os lotes que dá para
rodar ao mesmo tempo sem se atropelar". O trabalho de particionar é artesanal e não
escala com o tamanho do backlog.

## Medições que fundamentam esta especificação

Feitas em 2026-08-23 sobre `wego-assinatura-backend` e `wego-acesso-backend`
(refazendo a fusão de cada par de branches em memória com `git merge-tree`):

- Taxa de conflito entre trabalhos paralelos: ~11-13% nos quatro conjuntos medidos.
- **P(conflito | nenhum arquivo em comum) = 0** — 441 pares testados, zero conflitos.
- P(conflito | tocam arquivo comum) = 28% no assinatura (52/184), 100% no acesso (10/10).
- Custo da regra "exigir listas de arquivos disjuntas" no assinatura: proibiria 184
  de 461 pares (40%), dos quais 132 (72%) teriam fundido limpo.
- Concentração: 2 arquivos explicam 85% dos conflitos do assinatura
  (`api-rest/.../META-INF/openapi.yaml` + `bootstrap/.../db/seed/V900__dev_seed.sql`);
  1 arquivo explica 70% dos do acesso (`docs/pendencias.md`).
- Conflito semântico que quebra compilação (um lado remove símbolo, o outro passa a
  usá-lo): 0 em 487 pares que fundiram limpo. Detector validado em caso fabricado.
- Renomeação: 299 em 22 commits no assinatura, 1 no acesso; pares em que um lado
  renomeou arquivo que o outro editou: 0 em 487.

## Escopo

### Entra
- Um modo de varrimento no `/maestro:program-plan` que lê o BACKLOG.md inteiro e
  devolve uma **proposta** de ondas (tabela onda·slice·demanda·arquivos), que entra
  na conversa que o passo 3 do comando já tem hoje. Não grava plan.yaml sozinho.
- Um script próprio e reutilizável em `common/bin` que lê o `git log` do repo e
  devolve os arquivos-cartório ordenados por quantos pares conflitantes explicam.
  ("Arquivo-cartório" = arquivo que agrega contribuição de quase toda demanda, e por
  isso quase toda demanda escreve nele; ex.: `openapi.yaml`, `docs/pendencias.md`.)
  O `cepa-dor` passa a usar esse número medido no lugar da lista heurística de
  "alto atrito" que usa hoje.
- Regra de lote: proíbe duas demandas do mesmo lote escreverem no mesmo
  arquivo-cartório; sobreposição em qualquer outro arquivo é permitida.
- Campo novo no topo do plan.yaml listando os arquivos-cartório do repo, gravado
  pelo varrimento e lido pelo /maestro:run.
- O varrimento sugere o teto de slices da onda em vez de assumir o default de 3.
- Demanda cuja lista de arquivos o varrimento não consegue derivar entra **sozinha
  numa onda própria** (tratada como se tocasse o repo inteiro).

### Não entra
- Predição de conflito por co-mudança histórica — hipótese minha, medição não sustentou.
- Particionar o backlog inteiro de uma vez; o varrimento para nas próximas 2-3 ondas.
- Escrever plan.yaml sem passar pela sua revisão.
- Detecção/predição de renomeação no planejador — medição não achou ocorrência; o
  risco que sobrou é de trava de escrita, não de particionamento.
- Verify pós-merge no merge train — **já existe** em `maestro/commands/run.md:130-141`.

## Estado e migração

- O plan.yaml ganha um campo novo e **opcional** no topo (lista de arquivos-cartório).
  Sem bump de `schema_version`: plano sem o campo continua válido e se comporta como
  hoje (nenhum arquivo serializado). Mesmo precedente dos planos v1, que seguem lidos
  sem migração.
- O `cepa-dor` muda de regra: hoje ele **derruba os dois slices** sempre que as listas
  de arquivos se cruzam (`common/bin/cepa-dor:292`). Passa a derrubar só quando o
  cruzamento é num arquivo-cartório; cruzamento em qualquer outro arquivo vira aviso.
  Planos existentes que já eram disjuntos continuam READY — a mudança só afrouxa.
- A lista heurística de "alto atrito" do cepa-dor é substituída pelo número medido do
  script. Onde o script não tem dado, o aviso simplesmente não sai.

## Critérios de sucesso

### CS-1: o varrimento produz uma proposta que o gate aprova
Rodar o modo de varrimento sobre o `BACKLOG.md` do próprio cepa produz uma proposta de
ondas cuja onda 1, gravada como plan.yaml, sai READY no `cepa-dor` sem nenhum NOT-READY.
**Superfície:** cli
**Teste vermelho:** hoje o modo de varrimento não existe — invocar
`/maestro:program-plan <nome> --sweep` não produz proposta nenhuma, então não há plano
para o `cepa-dor` julgar.

### CS-2: o script nomeia os arquivos-cartório do repo
`common/bin/cepa-hotspots <repo>` devolve os arquivos ordenados por quantos pares
conflitantes cada um explica, medidos refazendo as fusões do histórico.
**Superfície:** cli
**Teste vermelho:** num repositório-fixture com um conflito plantado num arquivo
conhecido, `common/bin/cepa-hotspots` hoje não existe — o comando falha por arquivo
inexistente antes de apontar o arquivo certo.

### CS-3: sem histórico, o script diz que não sabe
Em repo com menos pares do que o mínimo, o script devolve lista vazia e a frase
"histórico insuficiente: N pares, mínimo M" — nunca uma lista heurística.
**Superfície:** cli
**Teste vermelho:** num repositório-fixture com 2 commits e nenhum merge, o script hoje
não existe; quando existir, o teste falha se ele devolver qualquer arquivo.

### CS-4: o gate veta cartório e tolera o resto
Dois slices da mesma onda que escrevem no mesmo arquivo-cartório saem NOT-READY; dois
que se cruzam em qualquer outro arquivo saem READY com aviso.
**Superfície:** cli
**Teste vermelho:** hoje a segunda metade falha — `cepa-dor` derruba os dois slices em
qualquer interseção, então o par que só se cruza fora de cartório sai NOT-READY.

### CS-5 (acompanhante): a trava de escrita conta renomeação como escrita nos dois caminhos
Um slice travado para escrever em `api-rest/**` que renomeia um arquivo para
`application/**` é barrado, porque renomear conta como escrita na origem E no destino.
**Superfície:** cli
**Teste vermelho:** hoje um `git mv` de um caminho declarado para um caminho não
declarado passa pela trava sem ser barrado.

## Perguntas em aberto

- [x] O varrimento escreve o plan.yaml direto ou devolve proposta? — devolve
  **proposta**, que entra na conversa existente do program-plan.
- [x] A conta dos arquivos-cartório vira script próprio ou fica embutida? — **script
  próprio em `common/bin`**, reutilizado também pelo cepa-dor.
- [x] O que fazer com demanda cuja lista de arquivos não dá para derivar? — **entra
  sozinha numa onda própria**. (Escolha do dono; minha recomendação tinha sido
  deixar de fora com o motivo nomeado.)
- [x] Duas demandas podem dividir arquivo que não seja cartório? — **sim**, só os
  cartórios são serializados.
- [x] Como o varrimento descobre os arquivos de cada demanda? — **o agente lê e
  propõe**, como o passo 2 do program-plan já faz hoje; nenhuma peça nova.
- [x] Onde ficam registrados os arquivos-cartório? — **campo novo no topo do
  plan.yaml**, para não quebrar a invariante de que o /maestro:run lê só o plano.
- [x] Horizonte do varrimento? — **só as próximas 2-3 ondas**; o plano é hipótese e
  é revalidado por sessão.
- [x] Teto de slices por onda? — **o varrimento sugere o teto** em vez de fixar 3.
  (Escolha do dono; minha recomendação tinha sido manter 3.)
- [x] Quem cede na colisão com o veto do cepa-dor? — **o cepa-dor afrouxa junto**:
  veto só para coincidência em arquivo-cartório, cruzamento em outro arquivo vira aviso.
- [x] Planos antigos sem o campo novo? — **campo opcional**, sem bump de schema;
  ausente = nenhum arquivo serializado (comportamento de hoje).
- [x] Script em repo com histórico curto? — **lista vazia e aviso explícito**
  ("histórico insuficiente"), nunca heurística disfarçada de medição.
- [x] Qual o resultado observável de sucesso? — **varrimento no próprio cepa e o
  cepa-dor aprovar a onda 1 sem NOT-READY**.

## Decidido sem perguntar

- **CS-5 entra nesta especificação** mesmo sendo sobre a trava de escrita e não sobre o
  planejador. Motivo: foi a decisão que você aprovou como saída da investigação de
  renomeação e não tem outro lar; deixá-la solta a perderia. Vete aqui se preferir que
  ela vire uma demanda separada no BACKLOG.md.
- O comando é um modo do `/maestro:program-plan`, não um comando novo — o formato de
  saída (plan.yaml), o gate de entrada (cepa-dor) e a costura com `/maestro:run` já
  existem e um comando novo os duplicaria. Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação

- Conflito semântico que compila e quebra comportamento não é mensurável estaticamente;
  a defesa é o verify pós-merge, que já existe. Medição empírica rodou em 3 árvores
  fundidas do wego-assinatura-backend (~18min de suíte cada; baseline verde com 926
  testes): nenhuma quebra atribuível à fusão — a única quebra de compilação encontrada
  já existia num dos lados sozinho, confirmado por controle.
- A escolha "demanda indecidível entra sozinha numa onda" tem um custo que o dono
  aceitou de olhos abertos: cada demanda de prosa vaga consome uma onda inteira. Se o
  varrimento de 109 demandas produzir muitas ondas de uma slice só, o sintoma é este.
