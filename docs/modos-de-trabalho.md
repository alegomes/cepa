# Modos de trabalho

> Status: **desenho aprovado, não construído.** Escrito em 2026-08-18.
> Decisões 1–4 desta rodada aprovadas pelo dono; o código vem depois.

## O problema que isto resolve

O sintoma, nas palavras do dono: *"eu começo a especificar uma funcionalidade,
pulo pro seu desenvolvimento, mergulho em vários micro-ajustes e gasto energia
na documentação antes mesmo de finalizar o desenvolvimento"*.

O diagnóstico **não** é falta de nome para as atividades — cinco das oito já
existem como topologia instalada. É falta de **destino para o desvio**: quando
você está construindo e enxerga um ajuste, hoje só existem duas opções — fazer
agora, ou perder. A terceira opção (registrar e seguir) precisa existir
mecanicamente, não como boa intenção.

## Modo não é Rotina

A distinção que faz o desenho fechar:

| | Rotina | Modo |
|---|---|---|
| O que é | uma tarefa que termina | um estado que dura |
| Exemplo | `/board-flow:prove-drain` | "estou construindo" |
| Termina quando | o lote acabou | a **condição de saída** é satisfeita |
| Obrigatório? | não | **sim** |

**Uma sessão = um modo obrigatório + no máximo uma rotina.** Modo sem rotina é
válido (exploração e reflexão são conversa disciplinada por fronteira, não
pipeline). Rotina sem modo, não.

O erro a evitar: fazer a sessão morrer junto com a rotina. A rotina acaba, você
continua ali, e é exatamente nesse intervalo que o micro-ajuste entra.

## Os oito modos

Para cada um: o que precisa ser verdade para **entrar**, o que ele produz, e o
que precisa ser verdade para **sair**. A condição de saída é a parte difícil —
sem ela o modo é rótulo, não fronteira.

### 1. Exploração

- **Entrada:** uma dor em linguagem natural. Explicitamente *sem* solução
  proposta — se você já sabe a solução, não é exploração.
- **Produz:** um documento de estratégia com pelo menos dois caminhos
  considerados, um recomendado, e a dor reformulada com o que se aprendeu.
- **Saída:** painel `/common:advisors` rodado sobre o documento, com as
  discordâncias entre lentes **nomeadas** (não mediadas), e sua decisão
  registrada sobre cada uma.
- **Gate:** existe parcialmente (`advisors`). Falta o veredito.

### 2. Descoberta

- **Entrada:** um comportamento desejado — vindo da exploração ou direto.
- **Produz:** oportunidade enquadrada, evidência coletada, e **os critérios de
  aceite escritos na altitude em que serão cobrados**.
- **Saída:** `evidence-auditor` → `Confirmed` nas suposições de risco, mais os
  critérios de aceite escritos **e o teste vermelho que cada um produz**. O
  teste vermelho é artefato da Descoberta, não da Construção.
- **Gate:** existe (`discovery`), mas hoje ele não cobra os critérios de aceite.
  **Esta é a mudança mais importante do documento inteiro** — ver "O buraco do
  critério" abaixo.

### 3. Design

- **Entrada:** oportunidade validada.
- **Produz:** fluxos, estados, spec visual reconciliada com o design system,
  protótipo compartilhável.
- **Saída:** `design-critic` → `SHIP`.
- **Gate:** existe e funciona (topologia `design`).

### 4. Construção

- **Entrada:** **um teste vermelho escrito a partir do critério de aceite** —
  antes do código, por quem não vai implementar. Sem isso o modo não abre; não
  é aviso, é bloqueio. Ver "O buraco do critério" abaixo.
- **Produz:** código + testes.
- **Saída:** os dois gates, nesta ordem:
  1. `completion-auditor` → `COMPLETE` — *fizemos o que foi pedido?*
  2. `proof-reviewer` → `PROVEN` — *o que fizemos está sustentado?*
- **Gate:** existe e é o mais maduro do sistema. Ver "Os dois gates" abaixo.

### 5. Reforma

- **Entrada:** **orçamento declarado** — a lista fechada do que será reformado e
  o limite. Reforma sem orçamento nunca termina: sempre tem mais um ajuste.
- **Produz:** código reorganizado, comportamento externo idêntico.
- **Saída:** três condições, todas necessárias:
  1. o orçamento declarado foi exaurido (ou você o encerrou);
  2. build verde;
  3. **nenhum teste externo foi editado.** Este é o gate real da reforma: se
     você precisou mudar o teste que já passava, o comportamento observável
     mudou — não foi reforma, foi construção, e deveria ter tido critério de
     aceite.
- **Gate:** **não existe.** A condição 3 é mecânica (o diff dos arquivos de
  teste externo tem que ser vazio) e é o que precisa ser construído.

### 6. Reflexão

- **Entrada:** um **recorte** e uma **lente**, ambos escolhidos de menu — não
  escritos do zero. Reflexão sem recorte vira leitura infinita do repo.

  Recortes pré-configurados:

  | # | Recorte | O que entra |
  |---|---|---|
  | 1 | superfície pública | o que outros dependem |
  | 2 | módulo ou topologia | um alvo nomeado |
  | 3 | fronteiras | onde dois módulos se tocam |
  | 4 | delta | o que mudou desde a última reflexão |
  | 5 | fila | os cards abertos — duplicata, obsoleto |
  | 6 | promessa | o que entregamos moveu o que dizia que ia mover? |

  O recorte 6 fecha o único buraco de valor do desenho: o `evidence-auditor`
  valida as suposições **antes** de construir, e ninguém volta depois da entrega
  para conferir se o resultado prometido aconteceu. A oportunidade declara um
  resultado observável e a data de conferir; a Reflexão nesse recorte lê as
  oportunidades vencidas e compara o prometido com o ocorrido.

  Lentes: as do registro que já existe em `common/advisors/lenses.md` — 5 fixas
  (`contrarian`, `fundamentalista`, `expansionista`, `outsider`, `executor`) e
  as especialistas por área (segurança, api-contrato, dados, ux, arquitetura),
  teto de 7. **Ressalva:** o `advisors` é prospectivo (roda sobre um documento
  de decisão, antes de decidir) e a Reflexão é retrospectiva (roda sobre o
  construído). O vocabulário se reaproveita; os `system-prompt-fragment` de cada
  lente precisam ser reapontados de "o que se propõe" para "o que existe".
- **Produz:** um relatório de achados classificados.
- **Saída:** **nenhum achado sem destino** — cada achado ou virou card, ou foi
  descartado com motivo escrito. Um relatório com achados soltos não fecha o
  modo, porque achado solto é exatamente o que volta como micro-ajuste depois.
- **Gate:** **não existe.** Existem as ferramentas soltas (`investigate`,
  `/code-review`, `advisors`, `debrief`), nenhuma fronteira.

### 7. Documentação

- **Entrada:** código estável (não em construção ativa).
- **Produz:** a árvore Diátaxis fundamentada.
- **Saída:** `consistency-reviewer` → `PASS` e sua assinatura em `docs:finalize`.
- **Gate:** existe e funciona (topologia `docs`).

### 8. Deploy

**Fora desta rodada** — decisão do dono. É o único modo que depende de infra
externa (ambiente, credencial, pipeline) e travaria os outros se entrasse junto.

## O buraco do critério

O `proof-reviewer` é *change-driven*: prova que cada linha mudada é load-bearing,
**independente de qualquer critério mencionar aquilo**. Ele nunca soube se era
isso que você queria.

O `completion-auditor` é *criterion-driven*: lê os critérios de aceite literais e
exige, para cada um, um teste que o demonstre na altitude em que foi escrito.

Os dois cobrem "está sustentado" e "é o que foi pedido". Nenhum dos dois cobra
que **o critério exista e seja bom antes de a construção começar** — critério
vago passa pelo `completion-auditor` de forma vaga.

### A assimetria que já existe no repo

- Fluxo de **bug** (`reproduce-fix-verify`): *"the spec is the failing test"*.
  Começa vermelho, e o teste vermelho é escrito pelo `qa-engineer` — **não** por
  quem corrige. Bug vago demais para reproduzir → `BLOCKED`, sem adivinhação.
- Fluxo de **feature** (`plan-build-validate`): tem "failing test first", mas
  **dentro de cada Task, depois da decomposição, escrito por quem implementa**.

A disciplina existe. Está no momento errado e com o autor errado.

### A regra

A condição de entrada da Construção é:

> **Dá para escrever o teste que falha lendo só o critério, sem perguntar nada e
> sem olhar o código?**

- **Não dá** → o critério é vago. A Descoberta não terminou; a Construção não abre.
- **Dá** → o teste vermelho é o artefato de saída da Descoberta, e a Construção
  começa com ele na mão.

É o mesmo formato da perturbação: uma medida, não uma opinião sobre o critério.

### O que o teste vermelho NÃO prova

Ele prova que o critério é **verificável**, nunca que é **valioso**. Um critério
pode ser perfeitamente verificável e completamente inútil — e nesse caso todos os
gates ficam verdes enquanto o time constrói com precisão algo que ninguém pediu.
Deixar o teste vermelho ocupar o lugar da pergunta de valor é o pior desfecho
possível deste desenho.

Quem cuida do valor: o `assumption-tester` escreve o critério de sucesso **antes**
do teste rodar, e o `evidence-auditor` julga estritamente contra o que foi
declarado antes. Depois da entrega, o recorte 6 da Reflexão ("promessa").

Três camadas definem o teste vermelho, e só a terceira é escolha de alguém:

1. **Altitude** — derivada do critério, não escolhida. Regra do `completion-auditor`.
2. **Qualidade** — mecânica: o teste tem que falhar **por asserção sobre o
   comportamento declarado**, não por "isso ainda não existe". Vermelho por 404 ou
   por não compilar prova que o código não foi escrito, o que já se sabia.
3. **Autor** — quem escreve não é quem faz passar. É o arranjo que o fluxo de bug
   já usa (`qa-engineer` escreve, outro corrige).

Três consequências: a feature ganha a disciplina que o bug já tem; o
`completion-auditor` para de julgar critério vago, porque o critério já foi
provado escrevível; e o `proof-reviewer` passa a ter *regression-red-at-base* (a
prova de que o teste ficava vermelho antes da mudança) também para features —
hoje ele só aplica isso a bugs.

É por isso que a entrada da Construção é a saída da Descoberta. A fronteira entre
os modos 2 e 4 não é organizacional: é o que dá dente ao gate que já existe.

## A mecânica de fronteira

Três peças. As duas primeiras não existem; a terceira existe e precisa ser
invertida.

### Peça 1 — o modo é declarado no launcher, não num comando

`cepa --modo <modo> [rotina]` grava o modo em `.claude/session-mode` **antes** do
`claude` subir. Sem `--modo`, o `cepa` pergunta e não sobe sem resposta.

O lugar importa: se a declaração morasse num comando de barra, a fronteira
dependeria de você lembrar de rodá-lo. No launcher, ela é a porta de entrada.

O preflight (`cepa-doctor --fix`) **já vive no `cepa`** — função `preflight()`,
roda `--fix --brief --if-stale 12h`, nunca impede a sessão de abrir, desligável
com `CEPA_PREFLIGHT=off`. Não há nada a mover. Os passos do `/common:session` que
exigem o modelo (ler o `.md` do comando-alvo para antecipar as perguntas,
executar, relatar) continuam no comando.

Conteúdo do arquivo:

```yaml
modo: construcao
rotina: board-flow:execute        # opcional
orcamento: null                   # obrigatório se modo == reforma
aberto_em: 2026-08-18T19:40:00Z
```

### Peça 2 — desvio é capturado sozinho e reportado no fim

Hoje a skill `board-flow:suggest-capture` faz o oposto: *"suggest capturing —
don't do it silently"* e *"give the user a one-line suggestion and wait"*.

O argumento dela para não capturar sozinha é bom: classificar todo turno como
"isso é trabalho novo?" custaria uma chamada de LLM por turno e ainda erraria.

**Esse argumento morre quando existe modo ativo.** Com modo declarado, a pergunta
não é "isso é trabalho?" e sim "isso é *deste* modo?" — e essa o agente já sabe
sem classificar nada, porque quem ia executar a ação era ele.

Mudança: com modo ativo, capturar e seguir, e listar as capturas no relatório
final. Sem modo ativo, o comportamento atual (sugerir e esperar) permanece.

### Peça 3 — a saída é o gate do modo, não o fim da rotina

A sessão não fecha porque a rotina acabou. Fecha quando a condição de saída da
tabela acima é satisfeita — ou quando você a dispensa explicitamente, que é uma
decisão sua e fica registrada como tal.

## O que precisa ser construído

Em ordem:

1. **`.claude/session-mode` + `cepa --modo`** — a declaração e a persistência.
2. **A captura automática** — inverter a `suggest-capture` sob modo ativo.
3. **Gate da Reforma** — a checagem mecânica de "nenhum teste externo editado".
4. **Gate da Reflexão** — "nenhum achado sem destino".
5. **Gate da Exploração** — o veredito que falta ao `advisors`.
6. **Cobrança do critério de aceite na saída da Descoberta / entrada da
   Construção** — a peça que dá dente ao `completion-auditor`.
7. **Modo Deploy** — rodada futura.

Os itens 1 e 2 são a mecânica de fronteira e valem para os oito modos. Os itens
3–6 são os gates que faltam, e sem 1 e 2 eles não têm onde se prender.
