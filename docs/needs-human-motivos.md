# Os sete motivos de NEEDS-HUMAN

Quando o [proof-gate](proof-gate.md) devolve `NEEDS-HUMAN`, ele está dizendo
"não tenho evidência para liberar nem para devolver". Só que isso acontece por
razões muito diferentes, e a etiqueta única esconde a diferença: metade dos
casos não é decisão de ninguém, é máquina que não subiu.

Este arquivo fixa os sete motivos em que `/board-flow:decide` classifica cada
card, lendo `.claude/proof/<KEY>.yaml` — nunca a descrição do card.

Cinco vieram do desenho; os motivos 6 e 7 vieram do piloto de 03/08/2026 sobre
33 artefatos reais (`wego-assinatura-backend`, `wego-tasy-gateway`) — não
cabiam em nenhum dos cinco. A classificação de referência desses 33 é a suíte
de regressão em `tests/test_needs_human_motivos.py`.

**O slug é interno** (vive no script de classificação e no nome do arquivo em
`.claude/waivers/`). O que aparece na tela é sempre a frase.

## A ordem importa

A fila sai nesta ordem, que é ordem de risco — não a prioridade do Jira. Quem
desiste no meio da lista desiste da parte menos grave.

---

## 1. "A prova não chegou a rodar" · `nao-rodou`

O Docker não subiu, o commit-base sumiu do histórico, ou o projeto não tem a
ferramenta de cobertura instalada. Não se sabe **nada** sobre o código: quem
falhou foi a máquina.

Entra aqui também a trava do próprio harness que impediu a prova de escrever no
worktree descartável (WEGO-1785).

**Não** entra o commit-base que não compila: aí a máquina rodou, e quem impede
a prova é a forma do código — isso é o motivo 2.

- **Decide quem:** ninguém. Não vira pergunta.
- **Ação:** re-run automático. Se falhar de novo, um card de infra agregando
  todos os cards travados pelo mesmo motivo.
- **Vem de:** `base_commit_resolved: false`, `status: skipped` com razão de
  ambiente, ausência de `quarkus-jacoco` ou do PIT no projeto.
- **Piloto 03/08/2026:** 16 dos 33. É o maior grupo, e nenhum deles é decisão
  sua — daí vem quase todo o encolhimento da fila.

## 2. "O teste não consegue enxergar essa mudança" · `teste-cego`

Existe teste, ele passa — e ele passaria igual se o código estivesse quebrado.
Ou porque um dublê (objeto falso que substitui o de verdade) engole o sinal, ou
porque nenhum teste externo passa por aquele caminho.

O caso de referência é o mock no-op do PlugSign: o `422` acontece, mas não
chega a aparecer na resposta HTTP, então não há como um teste externo notar.

Duas variantes que o piloto encontrou e que pertencem aqui, não a outro motivo:
a prova que só funciona **em conjunto** (dois portões perturbados juntos, nunca
um de cada vez — WEGO-1778) e o vermelho-no-commit-base que não é produzível
porque reverter só aquele pedaço não compila, restando um argumento analítico
(WEGO-1710). Em todos, a máquina rodou; quem não deixa provar é o desenho do
código ou do teste.

- **Decide quem:** você. Aceito a prova interna aqui, ou abro card para o teste
  externo que falta?
- **Vem de:** `perturbation: skipped` por dublê no-op, nenhum `@QuarkusTest`
  cobrindo o caminho, perturbação só coletiva, nível `assumed` por argumento
  analítico.
- **Piloto 03/08/2026:** 11 dos 33 — o maior grupo que é de fato decisão sua.

## 3. "Apareceu comportamento que nenhum teste confere" · `sem-cobertura`

O fuzzer bateu no endpoint que a mudança tocou e achou uma resposta que nenhum
assert cobre. Pode ser bug, pode ser aceitável — só quem conhece o produto
decide.

Cuidado com o nome: aqui a linha **é** exercitada por teste (senão o card teria
sido devolvido como UNPROVEN pelo L2). O que falta é alguém conferir o
resultado, não alguém passar por ali.

- **Decide quem:** você. É a única dos sete que é decisão de produto de
  verdade.
- **Vem de:** `l4_adversarial_input.status: findings`.
- **Não é mecanizável até o fim.** O campo `findings:` guarda prosa, não
  estado: WEGO-1819 está marcado `findings` e o texto diz que o achado **já foi
  fechado nesse mesmo diff**. O comando lista o texto e você lê uma linha; ele
  não tem como afirmar que o achado está aberto.
- **Piloto 03/08/2026:** 1 dos 33 — e é justamente o WEGO-1819, possivelmente
  já resolvido.

## 4. "Os testes rodam, mas seguram pouco" · `guarda-fraca`

A classe mudada está coberta, só que quebrando ela na mão a maioria dos testes
continua verde. É dívida, não defeito: nada está errado hoje, mas a próxima
mudança ali não vai ser acusada por ninguém.

- **Decide quem:** você. Registro como dívida com gatilho de revisita, ou trato
  agora?
- **Vem de:** PIT com taxa de morte baixa numa classe que o diff tocou.

## 5. "Dois cards, uma mudança só" · `nao-separavel`

A prova cobre o pedaço de código, mas não dá para dizer qual dos dois cards ela
sustenta. O `proof-reviewer` recusa veredito agregado por desenho — é assim que
um card não provado sairia de Review pendurado no vizinho.

- **Decide quem:** você, mas é arrumação: qual card leva a evidência, e o outro
  fecha como duplicado?
- **Vem de:** o `proof-reviewer` devolvendo `NEEDS-HUMAN` nomeando os cards que
  não conseguiu separar.
- **Piloto 03/08/2026:** 0 dos 33. Existe no desenho do `proof-reviewer`, nunca
  disparou. Mantido de propósito: sem ele, o dia em que acontecer cai em "não
  cabe em nenhum motivo".

## 6. "Não havia o que provar aqui" · `nada-a-provar`

Duas situações com a mesma pergunta para você:

- O diff não tem código de produção — um ADR, um arquivo de documentação, só
  teste. Não há o que quebrar, logo não há o que provar (WEGO-1709, WEGO-1658).
- Existe código provado, mas **uma das checagens** não se aplica àquele tipo de
  mudança: o fuzzer bate em endpoint HTTP, e o defeito era vazamento no log de
  um adaptador que não tem endpoint próprio (WEGO-1962). Nada ficou por provar;
  o gate é que não sabe dizer "essa checagem não cabe".

- **Decide quem:** você, e é barato: "confirmo que não fazia sentido provar isso
  aqui?"
- **Piloto 03/08/2026:** 3 dos 33.

## 7. "Depende de alguém de fora" · `fora-do-alcance`

A pendência não é sobre o código nem sobre o teste: é uma ação operacional ou
um terceiro. No WEGO-1757 são duas ao mesmo tempo — o agendamento no Bitbucket
aponta para o branch errado (ninguém dentro da sessão faz merge nem edita
schedule) e um limite de quota nunca foi confirmado com a Tecnospeed.

- **Decide quem:** você, mas a decisão é *para quem eu mando isso*, não
  aceito-ou-recuso.
- **Piloto 03/08/2026:** 1 dos 33.

---

## O artefato não é a fila — o board é

No piloto de 03/08/2026, dos 33 cards com artefato `needs-human` no disco, **29
já estavam Done** no Jira, 3 voltaram para To Do e 1 seguia em Review. O
artefato registra o veredito daquela rodada e nunca é reescrito quando o card
anda depois.

Consequência para `/board-flow:decide`: a fila são os cards que **estão** na
coluna Review agora; o artefato entra só como contexto de cada um. Montar a
fila a partir dos arquivos produziria uma fila fantasma de dezenas de perguntas
sobre cards fechados — pior do que o problema que o comando existe para
resolver.

## Dois esquemas de nome no disco

Os artefatos existentes usam duas grafias para os mesmos níveis. Qualquer coisa
que leia `.claude/proof/*.yaml` precisa aceitar as duas, ou lê metade da base:

| schema 2 (documentado) | grafia antiga, ainda no disco |
|---|---|
| `l2_coverage` | `l2_external_coverage` |
| `l3_load_bearing` | `l3_diff_mutation` |
| `bugfix_regression_red_at_base` | `bugfix_regression_red_on_base` |

Na primeira rodada do piloto isso classificou errado 7 dos 33 — entre eles o
WEGO-1698, que é o caso de referência da própria documentação.

## A lista é fechada

Caso que não cabe em nenhum dos sete **para o comando e avisa** — nunca vira um
oitavo motivo inventado na hora. Motivo inventado em runtime é o que faz uma
decisão sua gravada em `.claude/waivers/` casar depois com o card errado.

## Prova interna e prova externa

Os dois termos aparecem no motivo 2 e valem para o gate inteiro. É *de onde se
olha* ao quebrar o código de propósito:

- **Prova interna** — quebro a classe e um teste **dela** fica vermelho. Provei
  que a peça funciona sozinha.
- **Prova externa** — quebro a mesma classe e chamo o endpoint HTTP como um
  cliente de verdade chamaria. Provei que a peça está **ligada** ao que o
  usuário final vê.

A falha que o revisor mais teme é a peça certa que nunca foi plugada: passa em
todo teste interno e não muda nada na aplicação. Por isso prova interna nunca
substitui prova externa quando a mudança é observável de fora.
