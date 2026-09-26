# Investigação: os 5 STALE e os 86 maven_reactor_block do wego-assinatura-backend

Item da fila: `stale-e-reactor-no-wego` (`.claude/programs/cepa/plan.yaml:197`).
Data: 2026-09-25. Modo: só leitura (este arquivo é a única escrita).

## Resposta curta

O sinal que motivou o item era, quase todo, ensaio e não uso. Dos 86 bloqueios
de reator contados em 28/07, 83 vieram da suíte de testes do próprio cepa rodando
o hook num diretório descartável chamado `multi`; só 3 eram do
wego-assinatura-backend. Esse vazamento de teste para o ledger foi consertado em
26/08 (commit `83109c1`) e parou naquele mesmo dia. Os STALE são outro mecanismo
(o gate de commit depois de editar código sem rodar build) e coincidem com um
bloqueio de reator só uma vez em doze. No wego-assinatura-backend o problema não
existe mais: zero eventos de qualquer um dos dois tipos desde 03/08.

**Veredito: no-issue** para a pergunta do item. Há um achado lateral, em outro
repo (wego-acesso-backend), que vale um item novo do tipo feature-or-refactor
(seção 5).

## Glossário (termos usados abaixo)

- **ledger de telemetria**: os arquivos `~/.claude/cepa-telemetry/events-AAAA-MM.jsonl`,
  uma linha JSON por evento, gravados pelos hooks do cepa via `common/hooks/_telemetry.py`.
- **`maven_reactor_block`**: evento gravado pelo hook `common/hooks/maven-reactor-guard.py`
  quando ele barra um comando Maven com `-pl <módulo>` sem `-am`.
- **`-pl` / `-am`**: `-pl` pede ao Maven para construir só alguns módulos de um
  projeto multi-módulo ("reator"); `-am` ("also make") manda recompilar junto os
  módulos dos quais esses dependem. Sem `-am`, o Maven usa as cópias já
  instaladas em `~/.m2`, que podem estar velhas.
- **`stale-ok`**: comentário que o agente põe no comando para dizer "acabei de
  instalar o reator, o `~/.m2` está fresco" e passar pelo hook de reator.
- **STALE**: evento `gate_block` com `reason: "stale"`, gravado pelo hook
  `common/hooks/gate-advance.py` quando o agente tenta `git commit` (ou push/PR)
  e o arquivo `.claude/last-build.json` diz que houve edição de código depois do
  último build verde.
- **`multi`**: nome do diretório temporário que `tests/test_maven_reactor_guard.py:77`
  cria como reator de mentira. Como `_telemetry._repo_name()` usa o nome do
  diretório como nome do repo, os bloqueios da suíte aparecem no ledger como repo `multi`.

## 1. Contagens por mês

Consulta (repo e mês a partir do campo `ts`):

```sh
cd ~/.claude/cepa-telemetry
for f in events-2026-0{7,8,9}.jsonl; do
  jq -r 'select(.event=="maven_reactor_block") | .repo' $f | sort | uniq -c
  jq -r 'select(.event=="gate_block") | [.repo,.reason] | @tsv' $f | sort | uniq -c
done
```

### maven_reactor_block

| repo | jul | ago | set | total |
|---|---:|---:|---:|---:|
| `multi` (suíte de testes do cepa) | 227 | 948 | 0 | 1175 |
| wego-assinatura-backend | 5 | 2 | 0 | 7 |
| wego-acesso-backend | 0 | 153 | 328 | 481 |
| **total** | 232 | 1103 | 328 | 1663 |

Conta do total: 227+5 = 232; 948+2+153 = 1103; 328 = 328; 232+1103+328 = 1663,
que bate com `jq 'select(.event=="maven_reactor_block")' | wc -l` sobre os 3 arquivos (1663).

### STALE (gate_block, reason=stale)

| repo | jul | ago | set |
|---|---:|---:|---:|
| wego-assinatura-backend | 10 | 2 | 0 |
| wego-acesso-backend | 0 | 15 | 4 |
| outros (`mymobilespacesaver` 3, `sem-git` 1 em ago) | 0 | 4 | 0 |

`sem-git` é outro repo de mentira da suíte (listado em `tests/test_telemetria_isolada.py:6-9`).

### De onde vieram "5 STALE" e "86 reactor_block"

Reconstruído com Python sobre `events-2026-07.jsonl`:

- **86 reactor_block**: o 86º evento `maven_reactor_block` de julho tem
  `ts = 2026-07-28T19:56:37Z`. Até esse instante o ledger tinha 402 eventos, logo
  86 / 402 = 21,4%, o "20% de todos os eventos" do item. A divisão por repo
  desses 86: `multi` = 83, wego-assinatura-backend = 3.
- **5 STALE**: os `gate_block` stale do wego-assinatura-backend com `ts < 2026-07-29`
  são exatamente 5 (21/07 13:40; 22/07 23:01:12 e 23:01:31; 28/07 17:04:02 e 17:04:19).

Ou seja: o título do item atribuiu os 86 ao wego-assinatura-backend, mas 83/86 =
96,5% eram a suíte de testes.

Prova de que `multi` é a suíte: os comandos barrados em `multi` são literalmente
os casos de teste de `tests/test_maven_reactor_guard.py:91-109`
(`./mvnw test -pl bootstrap` 392 vezes, `./mvnw test -pl domain -amd` 98,
`mvn test --projects=bootstrap` 98, `PLUGSIGN_API_KEY=xxx ./mvnw test -pl bootstrap` 98...),
chegam em rajadas múltiplas de 12 por dia (84, 72, 36, 108, 288...) e o último
é de `2026-08-26T11:24:00Z` (08:24 em Brasília), seis minutos antes do commit que
isolou a suíte (`83109c1`, 2026-08-26T08:30:36-03:00).

## 2. O que cada bloqueio pega

### Hook de reator: `common/hooks/maven-reactor-guard.py`

- `:148`: `if _has_pl(args) and not _has_am(args): return seg`. Bloqueia qualquer
  segmento Maven com `-pl`/`--projects` sem `-am`/`--also-make` (`-amd` não conta, `:127-129`).
- `:165`: libera se o comando contém `stale-ok`.
- `:169`: só age se o `pom.xml` do cwd tem `<modules>` (`:132-137`).
- `:176`: `T.emit("maven_reactor_block", ...)` e `exit 2`.

O hook NÃO olha qual goal está rodando nem se o módulo tem dependência dentro do reator.

### Hook de STALE: `common/hooks/gate-advance.py`

- `:258-259`: status `SUCCESS` em `.claude/last-build.json` libera.
- `:273-275`: status `STALE` monta o motivo "build is STALE since edit to ...".
- `:291-294`: `T.emit("gate_block", ..., reason=status.lower())` e `exit 2`.
- `:88-101`: comandos `mvnw`/`mvn` estão na lista de isentos. **O gate de STALE
  nunca barra um comando Maven**; ele barra `git commit`/push/PR. O STALE é
  escrito por `common/hooks/mark-build-stale.py:138` depois de um Edit/Write em
  código-fonte e limpo por `capture-build-result.py` em qualquer saída Maven com `BUILD SUCCESS`.

### Os comandos barrados no wego-assinatura-backend (todos os 7)

| ts (UTC) | segmento barrado | o bloqueio protegeu algo? |
|---|---|---|
| 2026-07-21 22:49 | `./mvnw test -pl bootstrap` | sim (é o caso WEGO-1949; o hook nasceu nesse minuto, `b7a7c72`) |
| 2026-07-22 23:09 | `./mvnw -pl bootstrap,api-rest,application,infrastructure,domain clean` | não: `clean` não resolve dependência |
| 2026-07-24 19:21 | `./mvnw test -pl application,api-rest` | sim (api-rest depende de application, que depende de domain) |
| 2026-07-30 22:37 | `./mvnw -pl domain -o validate` | não: `domain` não depende de nenhum módulo do reator |
| 2026-07-31 00:17 | `./mvnw -q -pl . test -Dtest=GlobalExceptionMapperTest ...` | não: `-pl .` é o pom raiz |
| 2026-08-01 23:33 | `./mvnw -pl domain install -DskipTests -q` | não: é a própria cura (instalar) num módulo folha |
| 2026-08-03 22:55 | `mvn -f .../pom.xml -pl bootstrap dependency:tree` | não: só lê a árvore de dependências |

Layout do reator (`wego-assinatura-backend/pom.xml:16-20`): domain, application,
api-rest, infrastructure, bootstrap. Dependências internas lidas dos `*/pom.xml`:
domain depende só de libs externas (`wego-platform-commons-*`); application → domain;
infrastructure → application; api-rest → application, domain; bootstrap → api-rest, infrastructure.

Contagem: 2 dos 7 (28,6%) pegaram o risco real; 5 dos 7 (71,4%) barraram comando
sem risco de vermelho falso.

### Formas mais comuns (top 5), para contraste, no wego-acesso-backend (481 bloqueios)

Normalização: `-pl X` vira `-pl <M>` e `-Dtest=Y` vira `-Dtest=<X>`.

| n | forma |
|---:|---|
| 111 | `./mvnw -pl <M> test -Dtest=<X> 2>` |
| 41 | `./mvnw -pl <M> test -Dtest=<X> -Dsurefire.failIfNoSpecifiedTests=false 2>` |
| 38 | `./mvnw -pl <M> test 2>` |
| 23 | `./mvnw -B -pl <M> test -Dtest=<X> -Dsurefire.failIfNoSpecifiedTests=false 2>` |
| 18 | `./mvnw test -pl <M> -Dtest=<X> 2>` |

Módulo alvo: bootstrap 291, application 55, api-rest 34, infrastructure 30,
`domain,application` 24, domain 19 (demais < 7). Goal: `test` 406 de 481.

## 3. É a mesma causa?

**Não.** Evidência:

1. **Mecanismo**: o gate de STALE isenta Maven (`gate-advance.py:90-91`) e só barra
   commit/push; o hook de reator só barra Maven. Um não pode disparar o outro.
2. **Tempo**: para cada um dos 12 STALE do wego-assinatura-backend, o bloqueio de
   reator mais próximo no tempo:
   - 22/07 23:01 (2 STALE): reator 8 a 9 min depois (o `clean` da tabela acima). Única proximidade.
   - 21/07 13:40: reator mais próximo 549 min depois (e o hook de reator ainda nem existia).
   - 28/07 (2), 29/07 (4), 30/07 (1): reator mais próximo de 672 a 3214 min depois.
   - 02/08 (2): reator mais próximo 1248 a 1267 min antes.
   Conta: 2 de 12 STALE (16,7%) têm um reator a menos de 1 h; 10 de 12 não.
3. **Sessão**: os eventos de bloqueio não carregam id de sessão; cruzei com as
   janelas `session_start`/`session_end` do mesmo repo. Só o par de 22/07 cai na
   mesma janela (sessões `dfddb8a2`/`cb8e9fc8`). As sessões dos STALE de 28-29/07
   (`41ac897c`, `d69c6aee`) não têm nenhum bloqueio de reator. Os transcripts de
   julho desse repo não existem mais em `~/.claude/projects/` (a pasta tem 3
   arquivos, todos de setembro), então não dá para ler a conversa.
4. **O que o STALE indica**: em 10 dos 12, o último `build_result` antes do STALE
   foi `SUCCESS` minutos antes. É o gate funcionando: houve edição depois do verde
   e o agente tentou commitar sem rodar build de novo. `age_days` = 0,0 em todos,
   então não é baseline velha herdada de outra worktree.

## 4. Ainda acontece em setembro?

- wego-assinatura-backend: **não**. Último reator em 2026-08-03, último STALE em
  2026-08-02; setembro tem 0 e 0. Não houve commit consertando: o repo só parou de
  receber trabalho com esse padrão (último commit dele é `5e53226c`, 2026-08-15).
- `multi` (o grosso dos 86): **parou**, consertado por `83109c1` ("fix(tests): a
  suite para de escrever no ledger de telemetria real", 2026-08-26). Setembro: 0.
- O hook de reator só mudou duas vezes desde 28/07 (`023c7f2` e `d2db292`, ambos
  23/08, sobre texto entre aspas não ser lido como comando). Nenhum dos dois muda
  o que é barrado nos 7 casos acima.
- **wego-acesso-backend**: sim, e crescendo: 153 em agosto, 328 em setembro
  (até 26/09). Ver seção 5.

## 5. Veredito e próximo passo

**Veredito para o item: no-issue.** O "maior sinal isolado" era ensaio da suíte de
testes (83 de 86), já consertado em `83109c1`; os STALE são o gate de commit
fazendo o que deve, sem ligação com o reator, e os dois zeraram no
wego-assinatura-backend desde o começo de agosto. Recomendo fechar
`stale-e-reactor-no-wego` como `done` com este arquivo como evidência.

**Achado lateral (feature-or-refactor, item novo sugerido)**: no wego-acesso-backend
o hook de reator virou pedágio. Lendo os transcripts desse repo (incluindo
subagentes, `~/.claude/projects/*wego-acesso*/**/*.jsonl`), achei 360 bloqueios
e olhei o comando Bash seguinte a cada um:

| o que o agente fez em seguida | n | % de 360 |
|---|---:|---:|
| repetiu com `# stale-ok` | 223 | 61,9% |
| repetiu com `-am` | 107 | 29,7% |
| outro comando Maven | 17 | 4,7% |
| outra coisa | 12 | 3,3% |
| nada | 1 | 0,3% |

Dos 223 `stale-ok`, 219 (98,2%) tinham um `mvn ... install` no mesmo comando (6)
ou nos 15 comandos Bash anteriores (213). Ou seja: o agente já tinha feito a coisa
certa, instalou o reator, e o hook o barrou mesmo assim, custando um turno por
bloqueio. Em setembro isso foram 328 turnos jogados fora. O menor conserto:
em `common/hooks/maven-reactor-guard.py`, liberar sem exigir `stale-ok` quando
(a) o goal não compila nem testa (`clean`, `validate`, `install`,
`dependency:*`), e (b) o `~/.m2` foi instalado a partir deste reator depois da
última edição de código-fonte, o que dá para saber gravando o horário do último
`install` verde (no `capture-build-result.py`, que já vê toda saída Maven) e
comparando com o `since` que o `mark-build-stale.py` grava. Antes de mexer,
vale confirmar numa amostra de 10 casos que o `install` anterior foi mesmo depois
da última edição, porque os 98,2% acima só olham se houve install, não quando.
