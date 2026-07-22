# Versionamento dos plugins e release notes

Cada plugin do cepa (`common`, `board-flow`, `build-hex`, `maestro`, …) carrega
uma versão semver no seu `plugin.json`. Este doc formaliza o que já era feito de
fato: qual nível sobe, e o que a nota de release precisa dizer.

## Qual nível colapsou

O bump é escolhido pelo **nível mais alto que a mudança quebrou ou estendeu**,
não pelo tamanho do diff.

| Nível | Quando | Exemplo |
|---|---|---|
| **MAJOR** | um contrato de hook quebrou — algo que o agente ou o projeto consumidor dependia deixou de valer, ou passou a exigir o que antes era opcional | um gate passa a bloquear um formato que antes aceitava; um comando é renomeado; a forma de um artefato (`.claude/proof/*.yaml`) muda |
| **MINOR** | um gate ou feature novo, retrocompatível — a superfície cresceu, mas nada que funcionava parou | `handoff-seeds-gate` estreia; `install.sh` ganha `--rollback`; um agente ganha uma capacidade nova |
| **PATCH** | correção sem mudar contrato — o comportamento pretendido passou a valer onde não valia | um falso positivo de gate corrigido; um regex que lia `>=` como redirect; um typo em prosa normativa |

A pergunta operacional: **o que o próximo agente ou o próximo `install.sh`
passa a poder contar que antes não podia, ou deixa de poder contar que antes
podia?** Se algo deixou de poder ser contado, é MAJOR. Se só cresceu, MINOR. Se
só passou a fazer o que já prometia, PATCH.

### Dono único do bump por onda

Quando várias fatias de um mesmo programa tocam o mesmo `plugin.json`, o bump
tem **um dono por onda** — uma fatia sobe a versão e as outras não tocam o
campo. Bumps concorrentes no mesmo arquivo são clobber garantido. E antes de
subir, releia a versão atual no `plugin.json` em vez de confiar no plano: uma
sessão paralela pode ter consumido o número que você reservou (foi o que
aconteceu com o `0.17.0` do `common` neste programa).

## A nota de release cita o que foi conscientemente excluído

Uma nota de release que lista só o que entrou conta metade da história. A outra
metade — o que foi **deliberadamente deixado de fora** — é a que evita o
retrabalho e a pergunta repetida.

Toda nota de release (ou o commit de release) nomeia:

- **O que entrou** — a mudança, no nível que ela colapsou.
- **O que ficou de fora de propósito** — o follow-up capturado mas não
  absorvido, a superfície adjacente que se escolheu não tocar, a decisão
  adiada e sob qual condição ela volta. "Não fiz X porque Y" dito é diferente
  de X esquecido.

Isto é o [incomprimível](incomprimivel.md) aplicado ao release: a exclusão
consciente e a omissão produzem o mesmo silêncio no changelog, e só a primeira
protege o próximo leitor de reabrir uma decisão já tomada.

### Exemplo (deste próprio programa)

> **A8 — maestro 0.3.0 (MINOR).** Onda não aterrissa com slice em estado
> não-terminal (`check-terminal`); completion-auditor ganha a fronteira de
> mutação.
> **Fora de propósito:** o `proof-reviewer` NÃO foi editado — já tinha a regra
> "nunca edita"; a lacuna era só no completion-auditor. A parte de drain foi
> para o A5, não para cá.

O leitor que procurar "por que o A8 não mexeu no proof-reviewer" tem a resposta
na própria nota, em vez de reabrir a investigação.
