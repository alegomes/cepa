---
description: Abre uma sessão com propósito declarado e a leva do início ao fim sem pingue-pongue — deixa o harness pronto (doctor --fix em lote), faz TODAS as perguntas na largada (inclusive as que a rotina só encontraria no meio), executa a rotina inteira sem parar, entrega UM relatório final e oferece o wrap-up. Substitui o padrão "rode o doctor → siga as recomendações → rode a rotina → responda o vaivém do fim", que consumia mais atenção que a própria tarefa.
argument-hint: <rotina> [args da rotina] | --help [rotina]   ex.: /common:session prove-drain --max 5
interaction: routine
---

# /common:session

## Purpose

Uma sessão tem UM propósito. Hoje ela cobra do usuário três coisas antes de
chegar nele (diagnóstico, correções em cascata, confirmações da rotina) e mais
uma depois (vaivém até ter certeza de que acabou). Esse comando faz a jornada
inteira caber em: **você diz o que quer → responde uma vez → recebe o
relatório → encerra.**

Não é um modo autônomo: você continua decidindo o que é irreversível. Muda
*quando* você decide — tudo junto na largada, nada pingado no meio.

## Variables

- `$ARGUMENTS` — o nome da rotina e os argumentos dela.
  Rotinas reconhecidas: `prove-drain`, `drain`, `drain-plan`, `triage`,
  `decide`, `execute`, `autonomous`, `docs`, ou qualquer comando de barra
  instalado (passe o nome sem o `/`, ex.: `board-flow:prove-drain`).
- `--help [rotina]` — lista as rotinas e os parâmetros de cada uma, e não roda
  nada (ver passo 0). Com uma rotina, mostra só a dela.

## Instructions

Você é o condutor da sessão. Ative os skills `default-yes` (decidir em vez de
perguntar; perguntas só nas pontas) e `till-done` (não parar no meio). O
`plain-report` vale para o relatório final.

**A regra que rege este comando:** entre a largada e o relatório, você não
pergunta nada. Se aparecer uma escolha irreversível no meio, você a registra,
segue com o resto do lote e a traz no relatório — só interrompe se ela
bloquear literalmente a continuação da rotina.

## Workflow

### 0. `--help` (só leitura, encerra aqui)

Se o primeiro token de `$ARGUMENTS` é `--help` ou `-h`, **não** rode o doctor,
não pergunte nada e não execute rotina nenhuma. Responda e pare.

Leia os parâmetros **dos arquivos dos comandos-alvo agora**, nunca de uma cópia
escrita aqui: uma lista copiada envelhece calada quando um comando ganha flag.
Para cada apelido do passo 1 (ou só o pedido, se veio `--help <rotina>`):

1. resolva o apelido para o comando real e abra o arquivo dele (a cópia
   instalada; no repo do cepa, `<plugin>/commands/<cmd>.md`, com `docs` em
   `docs-topology/`);
2. junte o `argument-hint:` do frontmatter com a seção `## Variables`. Os dois
   às vezes divergem (uma flag documentada só num deles); liste a união e marque
   com "(só no cabeçalho)" ou "(só em Variables)" a flag que aparece num só.

Formato da resposta, em pt-BR leigo:

- uma tabela `apelido → comando real`;
- uma lista numerada por rotina: cada parâmetro em uma linha com o que faz e o
  padrão quando omitido;
- uma linha dizendo que qualquer comando instalado vale pelo nome com `:`, e
  que os comandos com `interaction: conversational` são recusados (liste-os com
  `grep -rl "^interaction: conversational"` nos plugins instalados).

### 1. Resolver a rotina (sem perguntar)

Mapeie o primeiro token de `$ARGUMENTS` para o comando real: `prove-drain` →
`/board-flow:prove-drain`, `drain` → `/board-flow:drain`, `drain-plan` →
`/common:drain-plan` (o lote da fila do plano, sem Jira), `triage` →
`/board-flow:triage`, `decide` → `/board-flow:decide`, `execute` →
`/board-flow:execute`, `autonomous` → `/common:autonomous-start`, `docs` →
`/docs:survey`. Um nome com `:` é usado literalmente.

Se a rotina não existir ou o plugin dela não estiver instalado, pare aqui e
diga qual é — é o único aborto silencioso permitido.

**Rotina conversacional é recusada aqui.** Abra o arquivo do comando-alvo e
olhe o campo `interaction:` do frontmatter. Se ele disser `conversational`,
**não rode**: diga ao dono para chamar o comando direto e pare. O hook
`session-routine-guard` já barra a invocação antes de você ver o prompt; esta
regra existe para o caso de ele não estar instalado.

O motivo é que os dois se contradizem, não que um seja pior. Este comando ativa
a skill `default-yes` e antecipa no passo 3 tudo que o alvo perguntaria depois.
Um comando conversacional como `/common:spec` carrega a skill
`guided-interrogation`, que **suspende** a `default-yes`, e pergunta em rodadas
porque cada resposta decide quais são as próximas — ninguém pergunta sobre
migração de dado antes de saber a fronteira do escopo. Espremido numa rodada só,
o resto do trabalho dele seria adivinhado, e sairia bem formatado o bastante
para passar nos gates sem ninguém notar que as respostas não vieram do dono.

### 2. Preflight em lote (não delegue isso ao usuário)

```
python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-doctor" --fix
```

Reporte em **no máximo 3 linhas**: o que foi corrigido sozinho, e o que sobrou.
Não cole a saída inteira — o usuário não abriu a sessão para ler diagnóstico.

- Nada sobrou → siga direto para o passo 3.
- Sobrou algo do bloco **Precisa de você** → NÃO abra uma rodada de perguntas
  aqui. Leve esses itens para a pergunta única do passo 3, junto com os da
  rotina, cada um com sua recomendação.
- Um item impede a rotina de rodar (ex.: `board-flow.yaml` sem `status_map` e a
  rotina é do board) → aí sim ele é bloqueante: diga isso na pergunta do passo 3
  como o primeiro item.

### 3. Largada — TODAS as perguntas de uma vez

Leia o arquivo do comando-alvo e **antecipe todo ponto em que ele pararia para
confirmar**. Monte uma única rodada (`AskUserQuestion`, no máximo 4 perguntas)
com o que realmente muda o resultado:

- o que a rotina confirmaria antes de começar (a lista de cards, o `--max`, o
  escopo);
- o que ela perguntaria **no meio ou no fim** (o que fazer com cada card que
  para em NEEDS-HUMAN, se devolve ou segura, se aplica a recomendação padrão) —
  antecipar isso é o ponto do comando;
- o que sobrou do preflight.

Regras da rodada:

- Toda pergunta é **fechada**, com sua recomendação explícita e o porquê em uma
  linha; nada de "avalie você".
- Nada de jargão não apresentado nos rótulos das opções (`plain-report`).
- Se **nenhuma** pergunta é irreversível ou muda o plano, **não pergunte nada**:
  anuncie os defaults em duas linhas e vá para o passo 4.
- Ofereça, como uma das perguntas, a **política de parada**: "seguir até o fim
  aplicando as recomendações" (default) ou "parar e me chamar se aparecer X".

### 4. Execução — sem interrupções

Rode a rotina com os parâmetros já decididos. Durante ela:

- as confirmações internas do comando-alvo **já foram respondidas** no passo 3;
  não as repita ao usuário;
- decisão reversível ou que só registra (criar card de follow-up, devolver card
  com motivo, anotar débito, arquivar handoff) → **execute e anote**;
- decisão irreversível não bloqueante → **não execute, anote** para o relatório;
- assunto lateral que aparecer (worktree não integrada, débito de outro módulo,
  aviso de SessionStart) → **estacione**, não vire pergunta.

### 5. Relatório único

Um `plain-report` que fecha a sessão sozinho:

- o resultado da rotina (o que ela produziu, em linguagem leiga);
- **Decidi por você:** a lista do que você aplicou sozinho e por quê — é o que
  troca "pedir licença antes" por "prestar contas depois";
- **Estacionado:** os assuntos laterais que apareceram e que você deliberadamente
  não puxou, cada um em uma linha (eles são a pauta da próxima sessão, não desta);
- as perguntas fechadas que sobraram (irreversíveis), numeradas, com
  `Recomendo sim/não`;
- a última linha oferece o fechamento: `/common:wrap-up` (commit + handoff +
  merge) — e diga que ele é o próximo e último passo.

## Constraints

- **Uma rodada de perguntas, no máximo.** Se você se pegar perguntando duas
  vezes, a segunda deveria ter entrado na primeira ou virado default.
- **Preflight nunca vira conversa.** O `--fix` resolve o mecânico; o resto vai
  para a rodada única.
- **Não transforme estacionamento em trabalho.** Item estacionado é uma linha no
  relatório; puxá-lo é justamente o desvio que este comando existe para evitar.
- **O relatório é obrigatório mesmo em falha.** Rotina que abortou no meio ainda
  fecha com o que rodou, o que não rodou e o próximo passo.
- Rotina cara (drain, prove-drain, autonomous) continua respeitando `--max` e
  `scope-discipline` — autonomia de decisão não é autonomia de gasto.
