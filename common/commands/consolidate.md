---
description: Consolidação periódica dos mental-models (common/expertise/*.yaml) — funde entries redundantes, aposenta os que o código atual contradiz (SEMPRE verificando contra o repo antes) e mantém intocado o que segue válido. Produz um diff antes/depois com a evidência de cada aposentadoria e SÓ grava após aprovação explícita do usuário. Complementa o prune por contagem do expertise-append.py, que evita crescimento mas nunca re-verifica fatos.
argument-hint: [agente | --all]   (ex.: proof-reviewer, backend-dev; --all varre todos os *-mental-model.yaml)
---

# /common:consolidate

## Purpose

Entries de expertise acumulam via `common/hooks/expertise-append.py` com prune
por CONTAGEM (cap 20 no `feedback:`, exceto `tag: principle`) — nunca por
VALIDADE. Um fato escrito em fevereiro pode estar contradito pelo código de
julho e continuar sendo lido em todo boot do agente. É o mesmo defeito dos
handoffs pré-disciplina "handoff é hipótese": memória tratada como fato
consumado.

Este comando fecha esse buraco: relê cada entry do(s) mental-model(s) alvo,
verifica os que citam artefatos concretos contra o estado atual do repo, funde
redundâncias e propõe um diff revisável. **Nada é gravado sem aprovação
explícita do usuário** — este é o gate humano do fluxo.

## Variables

- `$ARGUMENTS`:
  - `<agente>` — consolida só `common/expertise/<agente>-mental-model.yaml`
    (aceite também o nome do arquivo ou o path completo).
  - `--all` — varre todos os `common/expertise/*-mental-model.yaml`.
  - vazio — liste os arquivos disponíveis com contagem de entries por seção e
    pergunte qual consolidar (sugira o mais gordo).

Os arquivos vivem em `common/expertise/` no repo do plugin; em projetos host,
`.claude/expertise/` é um symlink para esse mesmo diretório (ver
`common/skills/mental-model/SKILL.md`). Resolva pelo symlink se estiver num
host; o arquivo físico é um só.

## Steps

### 1. Ler e inventariar

Para cada arquivo alvo, leia-o na íntegra e inventarie as seções com schema
(`feedback:`, `heuristics:`, `ecosystem_gotchas:`) e as chaves livres.
Preserve mentalmente três coisas que a gravação final NÃO pode perder:

- o cabeçalho de comentários (`# Mental model — <agente>` etc.) e
  `last_updated:`;
- a ordem cronológica dos entries dentro de cada seção (oldest-first — é o que
  o prune do append assume);
- a formatação manual (block scalars `|`, linha em branco entre items).

### 2. Classificar cada entry — com verificação, não com opinião

Classifique cada entry em exatamente uma categoria:

- **(a) redundante** — diz o mesmo que outro entry (ou um subconjunto dele).
  Proposta: fundir mantendo o entry mais rico como base e incorporando
  qualquer detalhe único do(s) absorvido(s); no entry resultante, anote os
  `run_id`/ids absorvidos (ex.: `merged_from: [<run_id>, ...]` num entry de
  feedback, ou parêntese no texto de uma heurística curta).
- **(b) contradito** — o código/estado atual do repo diz o oposto do que o
  entry afirma. Proposta: aposentar (remover), com evidência.
- **(c) vencido** — referencia coisa renomeada, removida ou substituída
  (hook que não existe mais, flag extinta, comando renomeado). Proposta:
  aposentar OU reescrever apontando para o sucessor, se a regra em si segue
  valendo.
- **(d) válido** — segue correto. Manter **intocado**: nem reescrever, nem
  "melhorar" a redação. Consolidação não é editorial.

**Regra de verificação (rigor de proof-reviewer): aposentadoria sem evidência
citada é violação.** Antes de classificar qualquer entry como (b) ou (c):

- Se o entry cita um **arquivo ou path**, verifique que ele existe (Glob/Read)
  e — quando o entry descreve comportamento — que o trecho relevante ainda se
  comporta como descrito (leia o código, não o nome do arquivo).
- Se cita uma **flag, allowlist, config ou constante**, abra a fonte e cite a
  linha atual que confirma ou contradiz.
- Se cita um **comando/CLI**, confirme que existe (`command -v`, `--help`, ou
  o script no repo); execute só se for read-only e barato.
- Registre a evidência no formato `evidência: <arquivo:linha ou comando> — <o
  que foi observado>`. "Parece obsoleto", "provavelmente mudou" ou memória de
  sessão anterior **não são evidência** — sem verificação mecânica, o entry é
  (d) por default.
- **Não-verificável ≠ contradito.** Expertise é agent-global e cross-project:
  um entry pode citar artefato de OUTRO repo que não está no seu disco. Nesse
  caso marque `não-verificável neste repo` e mantenha como (d) — no máximo
  liste-o numa seção "não pude verificar" do relatório para o usuário decidir.

**Entries `tag: principle` nunca entram em (b)/(c) automaticamente.** São a
memória disciplinar do agente (o append nunca os pruna; este comando também
não). Se a verificação sugerir que um principle envelheceu, apresente como
**proposta separada e destacada**, exigindo aprovação individual explícita —
nunca dentro de um "aprova tudo".

### 3. Produzir o diff proposto e apresentar ao usuário

Monte, por arquivo, um relatório antes/depois:

```
## <agente>-mental-model.yaml — proposta de consolidação

Entries: N → M  (fundidos: x · aposentados: y · mantidos: z)

### Fusões
- [feedback] <run_id A> + <run_id B> → mantém A (mais rico), absorve o detalhe
  "<...>" de B.
  ANTES: <os dois entries, verbatim>
  DEPOIS: <entry fundido>

### Aposentadorias  (cada uma com evidência — obrigatório)
- [heuristics] "<texto do entry>"
  motivo: contradito
  evidência: common/hooks/gate-advance.py:41 — a flag citada foi removida;
  o gate agora lê `.claude/last-build.json` direto.

### Propostas sobre `tag: principle` (aprovação individual)
- <se houver>

### Não pude verificar (mantidos)
- <entries cross-project ou sem artefato citável>

### Mantidos intocados
- <lista curta, só identificadores>
```

Apresente e **pare**. Aceite aprovação total, parcial ("aprova as fusões, não
a aposentadoria 2") ou rejeição. **Nunca grave sem um "sim" explícito do
usuário nesta sessão** — silêncio, "parece bom continuar analisando" ou
autonomous-mode NÃO contam; em autonomous-mode este comando para aqui e
reporta o diff como pendência humana.

### 4. Gravar (só após aprovação)

Aplique exatamente o que foi aprovado, por Edit/Write direto no arquivo
(consolidação é reescrita de entries existentes — o helper
`expertise-append.py` só faz append; não serve aqui). Preserve:

- o cabeçalho de comentários e todas as chaves livres não tocadas;
- entries `tag: principle` (intactos, salvo aprovação individual do passo 3);
- a ordem cronológica dos entries remanescentes (um entry fundido fica na
  posição do entry-base mantido);
- a formatação (block scalars `|`, dois espaços de indent, linha em branco
  entre items de feedback) — não round-trip por `yaml.dump`.

Atualize `last_updated:` para a data de hoje. Atenção à concorrência: o flock
do helper só protege appends; esta reescrita direta pode colidir com outra
sessão escrevendo o mesmo arquivo. Consolide com as outras sessões paradas
(ou avise o usuário do risco).

Releia o arquivo gravado e valide que é YAML parseável
(`python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" <arquivo>`).
Se não parsear, reverta e reporte.

### 5. Telemetria

Ao final, um evento por agente consolidado:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/_telemetry.py" emit mm_consolidation \
  agent=<nome> merged=<n> retired=<n> kept=<n>
```

(`merged` = entries absorvidos em fusões; `retired` = aposentados; `kept` =
entries no arquivo final. Se o usuário rejeitou tudo, emita mesmo assim com
`merged=0 retired=0` — a tentativa também é sinal.) Se `${CLAUDE_PLUGIN_ROOT}`
não estiver no ambiente, use o path absoluto de `common/hooks/_telemetry.py`.

### 6. Relatório final

- Por arquivo: N → M entries, o que foi fundido/aposentado/mantido, e o que
  ficou pendente (rejeições, principles não aprovados, não-verificáveis).
- Aparece em `/common:metrics` como evento custom `mm_consolidation`.

## Notes

- **Aceite do slice (BACKLOG P4):** rodar no expertise mais gordo reduz
  entries sem perder nenhuma regra ainda-válida — o diff revisável do passo 3
  é o que garante isso.
- `feedback:` é normalmente escrito só por `/common:debrief`
  (`common/commands/debrief.md`); este comando é a segunda exceção sancionada,
  e só sob aprovação humana.
- Consolidação é sobre VALIDADE, não sobre tamanho. Um arquivo com 6 entries
  todos válidos sai intocado — isso é sucesso, não fracasso do comando.
- Cadência sugerida: quando um arquivo encostar no cap de 20 do `feedback:`,
  ou a cada poucas semanas de uso intenso de autonomous-mode + debrief.
