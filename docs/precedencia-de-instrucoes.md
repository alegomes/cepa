# Precedência de instruções

Quando duas instruções se contradizem, o agente precisa de uma ordem fixa para
saber qual vence — e, mais importante, de uma regra sobre o que fazer quando o
conflito é com uma camada acima da sua. Sem isso, "seguir instruções" vira
adivinhação, e um agente autônomo adivinha na direção do que leu por último.

## A ordem (mais forte primeiro)

1. **Instrução da sessão** — o que o usuário pede AGORA, nesta conversa.
2. **Contrato do projeto** — o `CLAUDE.md` do repositório em que se trabalha.
3. **Preferências do usuário** — o `CLAUDE.md` global (`~/.claude/CLAUDE.md`).
4. **Defaults dos plugins** — o que os agentes, comandos e skills trazem de
   fábrica.
5. **Guidance geral** — o conhecimento e as boas práticas de base do modelo.

Camada mais alta ganha do conflito com a mais baixa. Uma instrução da sessão
que contraria um default de plugin: a sessão vence. Uma preferência do usuário
que contraria a guidance geral: a preferência vence.

## A regra que importa mais que a ordem

**Conflito com uma camada ACIMA da sua não se resolve sozinho — para e expõe.**

A ordem acima decide qual instrução prevalece quando a decisão é do agente. Mas
quando o que ele recebeu na sessão contradiz o contrato do projeto (camada 2),
ou uma preferência do usuário contradiz aquilo que o usuário pediu agora
(camada 1 vs 3), o agente não escolhe em silêncio o vencedor e segue. Ele
nomeia o conflito e devolve a decisão a quem é dono dela.

O motivo é que a força de uma camada mais alta muitas vezes vem de contexto que
o agente não tem. Uma instrução de sessão que quebra o contrato do projeto pode
ser exatamente o que o usuário quer (o contrato mudou e o `CLAUDE.md` está
velho), ou pode ser um pedido feito sem lembrar do contrato. Só o usuário sabe
qual. Escolher por ele troca uma pergunta barata por um erro caro.

Isto é o mesmo princípio do [incomprimível](incomprimivel.md): quando a
resposta certa depende de contexto que só o humano tem, a resposta honesta é a
pergunta, não um palpite bem-formatado.

## Exemplos

- Sessão pede "renomeia esse endpoint", contrato do projeto diz "endpoints são
  imutáveis, use deprecation window". → **Pare e exponha**: o pedido da sessão
  é mais forte, mas contradiz o contrato; o usuário decide se o contrato cede.
- Plugin default manda usar subset enxuto num DTO de lista; a preferência do
  usuário (registrada) manda espelhar o shape completo do detalhe. → A
  preferência (camada 3) ganha do default (camada 4); segue sem parar.
- Guidance geral sugere deprecation windows; a preferência do usuário diz "sem
  clientes ativos, big-bang rename". → A preferência ganha; segue sem parar.

## Para os agentes lead

Esta ordem é uma convenção para quem escreve ou revisa instruções de agente
(planning-lead, engineering-lead, validation-lead e os equivalentes por
topologia). Hoje nenhum agente, comando ou skill carrega este documento
sozinho: um lead só segue a ordem se a regra estiver escrita na própria
definição dele. Um lead que
absorve um conflito entre camadas — decidindo em silêncio que a sessão ganha do
contrato — está tomando uma decisão do usuário disfarçada de execução. A
disciplina é a mesma da fronteira de mutação do [A8](../maestro/commands/run.md):
achou uma decisão que não é sua, não a resolva; devolva-a nomeada.
