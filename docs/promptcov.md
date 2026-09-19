# Cobertura de checkpoints em comandos conversacionais

Um comando com `interaction: conversational` no frontmatter (ex.
`maestro/commands/program-plan.md`) é prosa que um agente Claude segue numa
sessão — não código que um interpretador executa. Não existe função para
chamar, e por isso não existe "cobertura de linha" no sentido usual.

O card `P1-sweep-mode` (docs/spec/planejador-de-lotes-paralelos.md) esbarrou
nisso: o proof-reviewer não conseguiu emitir `PROVEN` porque `l2_coverage`
ficava `assumed` — nenhuma ferramenta media quanto da prosa tinha, de fato,
uma checagem vigiando. `common/bin/cepa-promptcov` fecha essa lacuna
especificamente, sem fingir que fecha mais do que fecha.

## O que a ferramenta mede

Um comando anota blocos de comportamento com `**[tag:id]**` (negrito +
colchetes). Um teste de regressão da prosa embute o mesmo `tag:id` no nome de
cada `check()`. `cepa-promptcov <comando.md> <teste.py>` cruza os dois
conjuntos e aponta todo `id` do comando sem nenhuma checagem correspondente.

```
python3 common/bin/cepa-promptcov --tag sweep maestro/commands/program-plan.md tests/test_program_plan_sweep.py
python3 common/bin/cepa-promptcov --tag from-plan maestro/commands/program-plan.md tests/test_program_plan_from_plan.py
```

A ferramenta aceita um arquivo de teste só. Quando um comando tem mais de uma
família de checkpoints e cada família é vigiada por um teste diferente (o
`program-plan.md` tem `sweep:*` e `from-plan:*`), meça uma família por vez com
`--tag <família>`. Sem `--tag`, ela conta todas as `[tag:id]` do comando contra
o único teste passado, e o exemplo acima sem `--tag` sai com exit 1 e "4/11
cobertos", porque os sete `from-plan:*` são vigiados por outro arquivo.

`--json` troca o relatório legível por um objeto com `measured`,
`checkpoints`, `covered` e `uncovered`, para outro script (um revisor de prova,
por exemplo) consumir.

Exit 0 = todo checkpoint tem ao menos uma checagem. Exit 1 = há checkpoint
órfão. Exit 2 = não havia nenhum checkpoint do tag pedido — a ferramenta
recusa declarar 100% por vacuidade (mesmo espírito de CS-3 do
`cepa-hotspots`: sem dado, diz que não tem dado).

## O que a ferramenta NÃO mede

- Se a checagem é semanticamente correta (uma checagem pode existir e ainda
  assim testar a coisa errada — isso é revisão de código, não desta ferramenta).
- Se um agente, numa sessão real, seguiu a prosa do jeito certo. Essa prova é
  outra: perturbar a checagem (proof-reviewer) e/ou rodar o comando de verdade
  com um agente independente e comparar o artefato produzido contra o gate
  mecânico que julga esse artefato — ver `docs/proof/P1-sweep-mode.yaml` para
  o caso concreto que motivou este documento.

Cobertura de checkpoint é uma rede contra regressão silenciosa da prosa — não
substitui provar que o comportamento documentado é o comportamento certo.
