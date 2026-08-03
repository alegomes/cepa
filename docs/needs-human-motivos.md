# Os cinco motivos de NEEDS-HUMAN

Quando o [proof-gate](proof-gate.md) devolve `NEEDS-HUMAN`, ele está dizendo
"não tenho evidência para liberar nem para devolver". Só que isso acontece por
razões muito diferentes, e a etiqueta única esconde a diferença: metade dos
casos não é decisão de ninguém, é máquina que não subiu.

Este arquivo fixa os cinco motivos em que `/board-flow:decide` classifica cada
card, lendo `.claude/proof/<KEY>.yaml` — nunca a descrição do card.

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

- **Decide quem:** ninguém. Não vira pergunta.
- **Ação:** re-run automático. Se falhar de novo, um card de infra agregando
  todos os cards travados pelo mesmo motivo.
- **Vem de:** `base_commit_resolved: false`, `status: skipped` com razão de
  ambiente, ausência de `quarkus-jacoco`.

## 2. "O teste não consegue enxergar essa mudança" · `teste-cego`

Existe teste, ele passa — e ele passaria igual se o código estivesse quebrado.
Ou porque um dublê (objeto falso que substitui o de verdade) engole o sinal, ou
porque nenhum teste externo passa por aquele caminho.

O caso de referência é o mock no-op do PlugSign: o `422` acontece, mas não
chega a aparecer na resposta HTTP, então não há como um teste externo notar.

- **Decide quem:** você. Aceito a prova interna aqui, ou abro card para o teste
  externo que falta?
- **Vem de:** `perturbation: skipped` por dublê no-op, ou nenhum `@QuarkusTest`
  cobrindo o caminho.

## 3. "Apareceu comportamento que nenhum teste confere" · `sem-cobertura`

O fuzzer bateu no endpoint que a mudança tocou e achou uma resposta que nenhum
assert cobre. Pode ser bug, pode ser aceitável — só quem conhece o produto
decide.

Cuidado com o nome: aqui a linha **é** exercitada por teste (senão o card teria
sido devolvido como UNPROVEN pelo L2). O que falta é alguém conferir o
resultado, não alguém passar por ali.

- **Decide quem:** você. É a única das cinco que é decisão de produto de
  verdade.
- **Vem de:** `l4_adversarial_input.status: findings`.

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

---

## A lista é fechada

Caso que não cabe em nenhum dos cinco **para o comando e avisa** — nunca vira
um sexto motivo inventado na hora. Motivo inventado em runtime é o que faz uma
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
