# Manifesto de ambiente — `.claude/env.yaml`

O cepa modela código, não runtime — e as fricções de sessões paralelas são
quase todas de runtime: dev server subindo numa porta já ocupada, worktree
novo sem `.env`, container dependente parado, `~/.m2` servindo artefato
stale. O manifesto de ambiente declara esse runtime **por projeto-hospedeiro**
para que os rituais do harness o tratem mecanicamente, em vez de cada sessão
redescobri-lo na base do erro.

> **Onde mora:** no repo do *projeto que usa o cepa*, em `.claude/env.yaml`.
> O cepa em si não tem um — ele documenta o formato (este arquivo) e o
> consome (doctor, seed, preflight).

## Formato

Raso de propósito: só chaves de topo, valores escalares ou listas. Os
consumidores fazem parse tolerante por linhas (sem dependência de pyyaml),
então **não use aninhamento** além de um nível de lista.

```yaml
# .claude/env.yaml — runtime declarado do projeto

# Portas TCP que o dev server / serviços locais do projeto usam.
ports:
  - 8083
  - 3000

# Dependências de serviço, por NOME de container docker.
services:
  - postgres-projeto
  - redis-projeto

# Comando que sobe o ambiente (documentação executável — quem roda é o
# humano ou um comando interativo, nunca um hook).
up: docker compose up -d

# Comando que retorna exit 0 quando o ambiente está saudável.
healthcheck: curl -sf http://localhost:8083/q/health

# Globs (relativos à raiz do repo) de arquivos GITIGNORADOS a copiar para
# worktrees novos. Complementa o .claude/worktree-seed: os globs daqui são
# SOMADOS aos das outras fontes, nunca os substituem.
seed:
  - .env
  - .env.local
  - config/application-local.properties
```

Listas inline também valem: `ports: [8083, 3000]`.

### Campos

| Campo | Tipo | O que declara |
|---|---|---|
| `ports` | lista de inteiros | Portas TCP que o projeto ocupa quando roda localmente. |
| `services` | lista de strings | Containers docker (por nome) dos quais o projeto depende. |
| `up` | string (comando) | Como subir o ambiente do zero. |
| `healthcheck` | string (comando) | Retorna 0 quando o ambiente está saudável. |
| `seed` | lista de globs | Arquivos gitignorados a copiar para worktrees novos. |

Todos os campos são opcionais. Um manifesto só com `ports:` já paga o custo.

## Quem consome

- **`cepa-doctor`** (área `ambiente`): para cada porta de `ports`, checa via
  `lsof` se está ocupada por processo de **outro** diretório — e avisa quem
  ocupa (comando, pid, cwd), para você subir numa porta livre em vez de matar
  o dev server de uma worktree irmã. Para cada nome de `services`, confere o
  `docker ps` (best-effort: docker ausente ou daemon parado → skip
  silencioso). O `healthcheck:` **nunca é executado** pelo doctor — ele é só
  leitura; quem roda healthcheck é você (ou um comando interativo que peça
  permissão).
- **`seed-worktree.py`** (hook de criação de worktree): soma os globs de
  `seed:` às fontes existentes (`$CEPA_SEED` > `.claude/worktree-seed` >
  default `.env`/`.env.local`). Fail-silent: manifesto ausente ou malformado
  nunca quebra a criação da worktree.
- **`/common:worktree-start`** (passo "Preflight de ambiente"): quando o
  manifesto existe, as portas checadas no preflight vêm de `ports:` — fonte
  mecânica — em vez da lista chutada `8080,8083,3000`.

## Aceite (do backlog P3)

- O doctor acusa porta declarada no manifest ocupada por outro processo.
- O worktree-start seeda o que o manifest lista.

## Notas de parsing

O parser (em `common/hooks/_wtlib.py::env_manifest_list` e replicado no
`cepa-doctor`) é tolerante por regex/linhas: ignora comentários (`#`),
aceita `- item` em bloco e `[a, b]` inline, remove aspas simples/duplas dos
itens. Qualquer erro (arquivo ilegível, formato inesperado) resulta em lista
vazia — os consumidores seguem em frente sem o manifesto. Se você precisar
de estrutura mais rica que isso, o env.yaml é o lugar errado: ele é um
declarador, não um orquestrador.

> **Por que o `.claude/ui-proof.yaml` (P6) usa outro dialeto?** Deliberado:
> o env.yaml é consumido por hooks fail-silent com parse por linhas, então é
> raso; o [manifesto de prova de UI](ui-proof-manifest.md) é consumido por um
> agente com YAML de verdade e precisa de aninhamento (`flows` → `steps`).
> Consumidores diferentes, contratos de parsing diferentes — a mesma
> justificativa está registrada lá.
