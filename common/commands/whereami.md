---
description: Responde "onde estamos?" a qualquer momento da sessão: propósito, para quando, o plano com o passo atual marcado e há quanto tempo o cursor está nele. Lê a intenção gravada em .claude/session-intent (escrita só pelo cepa-intencao) e confere o cursor contra os últimos prompts do session-log. Só propõe avançar o cursor, nunca avança sozinho. Sem intenção gravada, ensina o caminho; numa rodada do cepa-until, delega ao /common:next.
argument-hint: (nenhum)
interaction: routine
---

# /common:whereami

## Purpose

A sessão deriva: duas horas depois ninguém diz com precisão o que se queria, em
que passo se está e quando parar. A intenção da sessão (propósito, ponto de
parada, plano, cursor) fica num arquivo por worktree, e este comando imprime as
quatro respostas por extenso: **o que estamos fazendo, para quando, qual o
plano, onde estamos nele.**

Desenho: `docs/estrategia-intencao-da-sessao.md` (D4 e "Estados do `whereami`").

## Instructions

Read-only. **Quem classifica o estado é o comando, não o seu olho**; o seu
trabalho é só a conferência contra o log (passo 2). Nunca edite
`.claude/session-intent` à mão: o único escritor é o `cepa-intencao`.

## Workflow

### 1. Ler o estado

```
python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-intencao" estado
```

A primeira linha da saída é `estado: <vazio|normal|cumprido|outra-sessao>`. Mostre
ao dono o resto da saída, em português, sem reescrever os fatos, conforme o estado:

- **`vazio`**: a saída diz "Esta sessão não tem intenção gravada. Diga o propósito
  e eu proponho o plano." Diga isso e pare; quando o dono disser o propósito,
  proponha em três linhas (propósito, para quando, plano numerado) e grave com
  `cepa-intencao gravar`. Se a saída trouxer `delegar: /common:next` (rodada do
  `cepa-until`, onde a intenção é o item do `plan.yaml`), **execute o
  `/common:next`** e traga a resposta dele no lugar desta.
- **`outra-sessao`**: o arquivo foi gravado por outra sessão. Mostre a data e a
  pergunta que a saída traz ("continuo ou abro nova?") e espere o dono. Continuar
  é `cepa-intencao continuar`; abrir nova é `cepa-intencao gravar ... --motivo "..."`.
  Não trate a intenção como a desta sessão e não faça a conferência do passo 2.
- **`cumprido`**: a saída diz "Os M passos estão feitos. Ponto de parada: ...
  Próximo: `/common:wrap-up`." Repita isso; não há cursor para conferir.
- **`normal`**: mostre as quatro respostas (propósito, para quando, plano com o
  `>` no passo atual, passo atual com a idade) e siga para o passo 2.

### 2. Conferir o cursor contra o log (só no estado `normal`)

Leia os últimos prompts de `.claude/session-log.md` (os posteriores à data de
`passo desde`, ou os 3 últimos se forem poucos) e compare com o plano. Se eles
parecem de outro passo que não o marcado, diga com as duas pontas: "o arquivo diz
passo 2; os últimos 3 prompts parecem do passo 3. Avanço?". Se o cursor está
parado há muito e os prompts ainda batem com o passo, diga só a idade. Se não há
log ou ele é inconclusivo, diga que não conferiu; não chute.

**Você propõe; o dono decide.** Só depois de o dono dizer sim, avance com
`python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-intencao" --passo N` (N = o passo que
passa a estar em andamento; `N = M+1` é plano cumprido).

## Constraints

- **Read-only.** A única escrita possível é o `--passo N` aprovado pelo dono.
- **Nunca avança o cursor por conta própria**, nem "porque o passo acabou".
- **Nunca reclassifica o estado de olho**: se a saída diz `vazio`, é `vazio`.
- Tamanho: curto. Este comando é lido no meio da sessão, quando a atenção já foi gasta.
