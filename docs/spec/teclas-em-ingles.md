# Especificação: teclas de resposta do cepa-until em inglês

**Status:** ready-to-build
**Aberta em:** 2026-11-20            **Fechada em:** 2026-11-20
**Fontes lidas:** common/bin/cepa-until (linhas 3375-3476, 3838-3875, 4106-4259, 4874-4989), docs/spec/perguntas-da-largada-legiveis.md, docs/spec/campo-de-resposta-until.md, docs/spec/fim-do-until-sem-espera.md, tests/test_cepa_until_screen_english.py

## Como chegamos aqui
"Adjust response options for english words" (dono, 2026-11-20), com o print da largada da run `kairos-etapa-1` mostrando `[s] yes, go with the agent's default` e o prompt `[s/n/t, Enter keeps the default]`.

## Problema
A tela do `cepa-until` está em inglês desde o item `interface-in-english` (2026-10-23), mas a tecla do "yes" continua sendo `s`, de "sim". O dono lê `[s] yes` e a letra não corresponde à palavra ao lado. `y` e `yes` já funcionam, só que a tela não mostra.

## Escopo
### Entra
- A tela das escolhas da leitura prévia (`ask_preferences`) mostra `y` no lugar de `s` e `w` no lugar de `t`: na nota de abertura, nas fichas do menu e no prompt, que vira `[y/n/w, Enter keeps the default]`.
- O painel das rotas (`cepa-until decide`) mostra `[y] yes` e `[w] I write the answer` nas fichas e na legenda, e a recomendação da análise marca `y` como "(recommended)".
- `s` e `t` deixam de ser aceitos nos dois menus. Quem digita um deles recebe uma linha com a tecla nova ("s is now y", "t is now w"), nada é gravado e o menu pergunta de novo.
- `sim`, `não` e `nao` deixam de ser aceitos nos dois menus e caem na mensagem de opção inválida, que passa a dizer "type w first".
- Nas confirmações `[y/N]` ("Land now?", "Send the item back to the queue with that answer?"), `s` e `sim` deixam de valer como yes e contam como no, como qualquer outro texto.

### Não entra
- O texto que a resposta grava na fila ("sim: ...", "não: ... Em vez disso: ..."): é dado, não tela. O `cepa-plan` e o `cepa-until` procuram "sim" e "não" nele, e as filas antigas já têm esse formato.
- As teclas `v`, `d`, `e`, `?` e `q` do painel das rotas: já são iniciais de palavras em inglês ou símbolo.
- Os campos `se_sim`, `se_nao` e `recomendo: sim|não` que a análise escreve: são dados entre agentes, a tela já os mostra como yes/no.

## Estado e migração
Nada. Nenhum arquivo gravado muda de formato: filas, estados de run e registros `.jsonl` continuam como estão.

## Critérios de sucesso

### CS-1: a tela das escolhas da leitura prévia mostra e aceita `y`, `n` e `w`
**Surface:** cli
**Red test:** num pseudo-terminal, com um leitor falso que devolve uma preferência, a largada do `cepa-until` mostra `[y] yes, go with the agent's default`, `[w] I write the answer` e `[y/n/w, Enter keeps the default]`, e não mostra `[s]`, `[t]` nem `s/n/t`. Digitar `y` grava no evento `largada` do registro a escolha igual ao padrão do agente com `fonte` "dono"; digitar `w` e uma linha grava essa linha. Hoje a tela mostra `[s]`, `[t]` e `s/n/t`, e `w` cai em opção inválida.

### CS-2: o painel das rotas mostra e aceita `y` e `w`
**Surface:** cli
**Red test:** num pseudo-terminal, `cepa-until decide <fila>` sobre um item com rota aberta e análise com `recomendo: sim` mostra `[y] yes (recommended)` e `[w] I write the answer`, a legenda tem uma linha começando com `y = ` e outra com `w = `, e a saída não contém `[s]`, `[t]`, `s = ` nem `t = `. Digitar `y` e Enter devolve o item à fila com o texto "sim: ..." no `evidence`; digitar `w`, uma linha e `y` devolve o item com essa linha. Hoje o painel mostra `[s] yes` e `[t]`, e `w` cai em opção inválida.

### CS-3: a tecla antiga recebe uma linha com a tecla nova e não grava nada
**Surface:** cli
**Red test:** num pseudo-terminal, digitar `s` no menu do `cepa-until decide <fila>` mostra uma linha com "s is now y", o `queue.yaml` não muda e o menu pergunta de novo; digitar `t` mostra "t is now w" do mesmo jeito; digitar `sim` mostra a mensagem de opção inválida com "type w first". O mesmo vale para `s`, `t` e `sim` na tela das escolhas da leitura prévia, onde a preferência fica com `fonte` "padrao". Hoje `s` e `sim` devolvem o item à fila e `t` abre a linha de resposta.

### CS-4: nas confirmações `[y/N]`, `s` e `sim` contam como no
**Surface:** cli
**Red test:** num pseudo-terminal, em `cepa-until decide <fila>` o dono digita `w`, uma linha, e responde `s` em "Send the item back to the queue with that answer? [y/N]": o item continua fora da fila, com a linha gravada. No fim de uma run com integração pendente, responder `sim` em "Land now?" não integra a branch. Hoje, nos dois casos, `s` e `sim` valem como yes.


## Perguntas em aberto
- [x] Q1. O painel das rotas (`cepa-until decide`), que também mostra `[s] yes`, troca para `y` junto com a tela das escolhas da leitura prévia? — As duas telas (dono, 2026-11-20).
- [x] Q2. `s` e `sim` continuam aceitos, sem aparecer na tela? — Não, `s` vira erro (dono, 2026-11-20).
- [x] Q3. A tecla `t` ("I write the answer") continua `t` ou muda de letra? — Muda para `w`, de "write" (dono, 2026-11-20).
- [x] Q4. O texto que a resposta grava na fila ("sim: ...", "não: ... Em vez disso: ...") continua em português? — Fica fora, continua em português (dono, 2026-11-20).
- [x] Q5. Nas confirmações `[y/N]` ("Send the item back to the queue with that answer?", "Land now?"), `s` e `sim` hoje valem como yes. Deixam de valer também? — Sim, deixam de valer e contam como no (dono, 2026-11-20).
- [x] Q6. Quem digitar a tecla antiga (`s` ou `t`) recebe a mensagem genérica de opção inválida ou uma linha dizendo qual é a tecla nova? — Uma linha com a tecla nova, e o menu pergunta de novo (dono, 2026-11-20).

## Decided without asking
- `n` continua `n`: é a inicial de "no" e de "não". Vete aqui se discordar.
- `t` deixa de abrir a linha de resposta, como `s` deixa de valer como yes: segue a resposta da Q2, tecla antiga não fica escondida. Vete aqui se discordar.
- A linha da tecla nova (Q6) vale só para `s` e `t`; `sim`, `não` e `nao` recebem a mensagem de opção inválida. Vete aqui se discordar.
- As palavras `não` e `nao` deixam de ser aceitas nos dois menus, como `sim`; `yes` e `no` por extenso continuam aceitas. Segue a resposta da Q2. Vete aqui se discordar.
- O texto das confirmações `[y/N]` e `[Y/n]` não muda na tela: já está em inglês. Só o que elas aceitam muda (Q5). Vete aqui se discordar.
- A confirmação "Use this text? [Y/n]" continua recusando qualquer resposta que começa com `n`, inclusive "não": ali Enter mantém o texto e a recusa é o lado seguro. Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação
- 28 arquivos de teste em `tests/` citam ou digitam a tecla `s` (contagem: `grep -lE` pelos padrões `[s]`, `s/n`, `"s"` e `s accepts` em `tests/*.py`, 2026-11-20). Os que conferem o texto da tela mudam junto com a troca. Como `s` e `t` viram erro (Q2, Q3), os que digitam `s` ou `t` nos dois menus também mudam.
- Hábito: o dono digita `s` e `t` nesses menus desde 2026-11-13. A linha com a tecla nova (Q6) cobre os menus; nas confirmações `[y/N]` um `s` por hábito conta como no sem aviso (Q5).
