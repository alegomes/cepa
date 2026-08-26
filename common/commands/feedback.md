---
description: Registra, a qualquer momento da sessão, um feedback sobre a própria Cepa — o comando que perguntou demais, o gate que barrou o que não devia, o relatório ilegível, o agente que fez o que não foi pedido. O registro é GLOBAL (~/.claude/cepa-feedback/), porque o incômodo acontece no repo do cliente e o alvo é o harness; repo, branch e modo da sessão entram sozinhos. Sem argumento, lista o que está aberto. Com --triar, e só dentro do repo da Cepa, converte os abertos em itens do BACKLOG.md e marca cada um com o destino. Não conserta nada e não interrompe o trabalho do turno.
argument-hint: [<texto do feedback>] | [--alvo X] | [--listar [--todos]] | [--triar]
interaction: routine
---

# /common:feedback

## Purpose

Dar destino ao incômodo no instante em que ele aparece.

O feedback sobre o harness nasce no meio de outra tarefa, num repo que quase
nunca é o da Cepa. As duas saídas que existiam eram largar a tarefa para abrir o
`BACKLOG.md` de outro repositório, ou seguir e esquecer — e seguir e esquecer
sempre ganha. O resultado media-se em anedota: "o harness pergunta demais" é
verdadeiro e não é acionável, porque o episódio que o provaria não foi guardado.

Este comando guarda o episódio: o texto do dono verbatim, mais o contexto que o
torna reconstruível meses depois (repo, branch, modo da sessão, alvo).

## Variables

- `$ARGUMENTS` — uma das quatro formas:
  - **texto** → registra o feedback (forma default).
  - **vazio** ou `--listar` → lista os feedbacks abertos (`--todos` inclui os já triados).
  - `--alvo <x>` → acompanha o texto; nomeia o comando/hook/agente responsável.
  - `--triar` → converte os abertos em itens de `BACKLOG.md`. Só faz sentido no repo da Cepa.

## Onde mora o registro

`~/.claude/cepa-feedback/feedback-AAAA-MM.jsonl` — global e append-only
(`CEPA_FEEDBACK_DIR` sobrescreve). Global e não por repo porque o alvo é a Cepa e
o incômodo acontece no repo do cliente: um arquivo por projeto espalharia a mesma
queixa por cinco lugares que ninguém relê. Append-only porque a triagem é outra
linha citando o `id`, nunca uma reescrita do que o dono disse.

O escritor é o `cepa-feedback` (o bin do plugin), nunca o seu editor de texto:
ele é quem recusa registro vazio ou de uma palavra, gera o `id`, captura
repo/branch/modo e replica o estado `aberto`/`triado` do ledger.

## Workflow

### 1. Registrar (forma default)

Quando `$ARGUMENTS` traz texto:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-feedback" add \
  "<texto do dono, verbatim>" --alvo <alvo se houver> --origem comando
```

**Verbatim.** Não resuma, não reescreva, não "melhore" a redação do dono. Se ele
escreveu quatro linhas de irritação, as quatro linhas entram. O resumo troca a
queixa pela sua leitura dela — e é a sua leitura que costuma ser o problema.

O `--alvo` você preenche do contexto do turno quando ele for claro (o comando que
acabou de rodar, o hook que acabou de barrar, o agente que acabou de devolver o
relatório). Não invente: sem alvo evidente, grave sem ele.

Saída ao dono: **uma linha** com o id e o alvo. Depois disso, volte ao que ele
estava pedindo. O turno pertence à tarefa, não à queixa.

Se o bin recusar (texto curto demais, vazio), repasse a recusa em uma linha e
peça a frase completa — sem transformar isso em interrogatório.

### 2. Listar

Sem argumento, ou com `--listar`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-feedback" list --sem-cor
python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-feedback" list --status todos --sem-cor   # com --todos
```

Repasse a lista como veio, agrupada por alvo quando houver mais de cinco itens.
Não classifique, não priorize, não proponha correção: aqui você é vitrine.

### 3. Triar (`--triar`) — só no repo da Cepa

Triar é o que impede o ledger de virar arquivo morto: cada feedback aberto sai
dali com um destino nomeado.

1. **Confira que este é o repo da Cepa** — existe `BACKLOG.md` na raiz e o
   `common/.claude-plugin/plugin.json`. Se não for, pare e diga em uma linha que
   a triagem roda no repo do harness (o registro é global; a conversão em card,
   não).
2. Leia os abertos com `list --status aberto --json`.
3. Para cada um, decida entre três destinos — e **decida você**, com
   recomendação registrada, sem perguntar item a item (`default-yes`):
   - **Item novo no `BACKLOG.md`** — o incômodo não está descrito em nenhuma
     seção existente. Escreva a seção no formato do arquivo (título, `**Status:**
     pendente · **Lar provável:** <plugin> · **Origem:** feedback `<id>`,
     `<data>`), com o texto do dono citado e o contexto do registro.
   - **Anexo a um item existente** — já existe seção sobre aquele incômodo.
     Acrescente o episódio ali, com o id, em vez de abrir uma seção rival.
   - **Já resolvido** — o comportamento reclamado não existe mais. O destino é o
     commit ou a versão que o resolveu, e você só marca a triagem.
4. Marque cada um:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-feedback" triar <id> \
     --destino "BACKLOG.md § <título>" --nota "<uma linha, se ajudar>"
   ```
   O bin recusa destino vazio, id inexistente e re-triagem — a segunda triagem
   apagaria a primeira decisão em silêncio.
5. Relate no formato `plain-report`: quantos vieram, quantos viraram item novo,
   quantos foram anexados, quantos já estavam resolvidos.

## Limites

- **Não conserta.** Nem o incômodo trivial, nem no repo da Cepa. Registrar e
  consertar no mesmo turno é exatamente o desvio que o modo de trabalho existe
  para barrar; o conserto entra pela fila, como qualquer item.
- **Não julga.** "O gate estava certo" pode ser verdade e não é assunto do
  registro. O ledger guarda o episódio; a triagem confere os fatos.
- **Não é card de projeto.** Bug no código do cliente, API de terceiro, build
  quebrado → `/board-flow:capture` ou `.claude/desvios.md`. O teste é uma
  pergunta: reinstalar a Cepa em outra máquina levaria o incômodo junto?

## Relação com o resto

- O skill `common:feedback-capture` faz o mesmo registro **sem você digitar
  comando nenhum** — basta reclamar em prosa. O hook `feedback-nudge`
  (UserPromptSubmit) é quem garante que a hora de gravar seja notada, uma vez por
  sessão.
- O `/common:metrics` mede o harness pelo lado mecânico (bloqueios, vereditos,
  atrito das pontas). Este comando é o lado que só o dono enxerga: o que
  incomodou, com as palavras dele.
