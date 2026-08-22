# Manifesto de prova de UI — `docs/ui-proof.yaml`

Este é o artefato central do **P6** (o slice "ui-proof-gate" do programa
`melhorias-2026-07`, que cria um gate mecânico de prova para a superfície de
UI). O `proof-reviewer` (build-hex) prova o backend; a superfície onde o
usuário mais sofre — SPA e extensão Chrome — não tinha gate. O
`ui-proof-reviewer` (em `common/agents/ui-proof-reviewer.md`) fecha esse
buraco: ele sabe **como** provar (Playwright via Bash/npx, carregar extensão
unpacked, percorrer o fluxo, assertar efeito observável no backend). O que ele
**não** sabe é o que cada produto considera um fluxo que vale a pena provar —
isso é conhecimento do repo, não do harness. Este manifesto é onde o repo
declara **o que provar**.

> **Onde mora:** no repo do *projeto que usa o cepa*, em `docs/ui-proof.yaml`
> — versionado. O cepa em si não tem um; ele documenta o formato (este arquivo)
> e o consome (`ui-proof-reviewer`, `/common:prove-ui`).
>
> **Morava em `.claude/ui-proof.yaml` até 22/08/2026.** Nesses projetos
> `.claude/` é gitignored, então o manifesto era invisível para o git e sumia
> junto com a worktree descartável da sessão, levando os fluxos declarados
> embora. O mesmo valia para os scripts fixados e para o veredito. O agente
> ainda LÊ o caminho antigo quando o novo não existe, e avisa no relatório que
> o arquivo deve mudar de lugar; a partir daí tudo o que o gate produz é
> versionado.
>
> **Relação com o `env.yaml` (P3):** o **P3** é o slice do mesmo programa que
> criou o [manifesto de ambiente](env-manifest.md) `.claude/env.yaml` — a
> declaração do runtime do projeto (portas, serviços, como subir). Este
> manifesto declara outra coisa: os fluxos de UI e seus efeitos verificáveis.
> Eles se complementam: o campo `up` daqui pode simplesmente dizer `env.yaml`
> para reusar o `up:`/`healthcheck:` de lá, em vez de duplicar o comando.
>
> **Por que dois dialetos de YAML em `.claude/`?** O `env.yaml` é raso e
> parseado por hooks tolerantes-por-linha (sem pyyaml); este manifesto é
> aninhado (`flows` → `steps`/`assert`) e lido por um agente com YAML de
> verdade. A quebra é deliberada, não descuido: consumidores diferentes
> (hook fail-silent vs. agente que pode falhar alto) pedem contratos de
> parsing diferentes. A mesma justificativa está registrada no
> [env-manifest.md](env-manifest.md).

## Formato

Raso de propósito: dois níveis no máximo (`flows` é um mapa nomeado; cada
fluxo tem chaves escalares e uma lista `steps`). Diferente do `env.yaml` —
cujos consumidores são hooks com parse tolerante por linhas — este manifesto é
lido por um **agente**, que pode usar YAML de verdade (`python3 -c "import yaml"`
ou parse manual). Ainda assim, mantenha-o raso: ele é um declarador, não um
script de teste. A inteligência de execução fica no agente.

### Campos de topo

| Campo | Tipo | Obrigatório | O que declara |
|---|---|---|---|
| `up` | string | sim | Como subir a instância **primária** do app. Ou um comando literal, ou a string `env.yaml` para delegar ao `up:`/`healthcheck:` do manifesto de ambiente do P3. |
| `base_url` | string | sim | URL raiz onde a instância primária responde depois de subir. Respeite as portas declaradas no `env.yaml`, se houver. |
| `build` | string | não* | Como **compilar o app a partir de um diretório arbitrário** — o agente roda este comando com o cwd apontando para o checkout em teste (a raiz do repo, ou a worktree descartável na prova green→red→green). `{dir}` interpola o path absoluto desse checkout, para comandos que precisam dele explícito (ex.: `npm --prefix {dir}/extension run build`). *Obrigatório se você quer a prova de perturbação: sem `build`, perturbar `src/` não muda o `dist/` servido e a perturbação sai `assumed`. |
| `serve` | string | não* | Como **servir o app compilado numa porta arbitrária** — comando com o template `{port}` obrigatório (ex.: `npm run preview -- --port {port}`), rodado com cwd no checkout em teste. O agente escolhe uma porta livre (respeitando `ports:` do `env.yaml`) e interpola. *Mesma condição do `build`: sem `serve`, não há como subir a instância perturbada sem sequestrar a primária. |
| `extension_dir` | string | não | Path (relativo à raiz do **checkout em teste**) da extensão Chrome **unpacked** — o diretório que contém o `manifest.json`. Presente → os fluxos rodam num Chromium com a extensão carregada. Na prova de perturbação, resolve dentro da worktree (recompilada via `build`), nunca no `dist/` do repo primário. |
| `credentials_ref` | string | não | Path de um arquivo **gitignorado** com credenciais de dev (ex.: `.env.ui-proof`), formato `CHAVE=valor` por linha. **NUNCA credenciais inline no manifesto** — o manifesto é versionado; o arquivo referenciado, não. Ausente ou inexistente com fluxo que exige login → o fluxo não roda (vira `NEEDS-HUMAN`, nunca um chute). |
| `flows` | mapa | sim | Fluxos nomeados a provar. Cada nome é o identificador usado em `/common:prove-ui <fluxo>`. |

### Campos de cada fluxo

| Campo | Tipo | Obrigatório | O que declara |
|---|---|---|---|
| `steps` | lista de strings | sim | Prosa **estruturada**, um passo por item, no vocabulário navegar/clicar/preencher/aguardar. O agente traduz cada passo para Playwright — então seja concreto: nomeie o texto do botão, o label do campo, a URL. Prosa vaga ("use o app normalmente") não é traduzível e será reportada como fluxo inexecutável. |
| `assert` | mapa | sim | O efeito observável que prova o fluxo. Duas chaves: `screen` (o que deve aparecer na tela) e `backend` (o efeito verificável fora da tela). Pelo menos uma é obrigatória; **só `screen` é evidência fraca** — veja abaixo. |
| `covers` | lista de strings | não | Globs de arquivos de produção que este fluxo cobre (ex.: `extension/src/**`). Usado pelo agente para escolher qual fluxo re-rodar na prova green→red→green quando o diff da mudança é conhecido. |

### Interpolação — `{base_url}` é sempre a instância EM TESTE

Um run pode envolver **duas instâncias** do app: a **primária** (subida via
`up`, no `base_url` de topo) e a **perturbada** (compilada via `build` e
servida via `serve` numa porta livre, a partir da worktree descartável, na
prova green→red→green). A regra de resolução é uma só e não tem exceção:

1. Cada execução de fluxo acontece contra **uma** instância — a primária no
   run GREEN, a perturbada no run RED.
2. Antes de gerar o script e de rodar o `assert.backend`, o agente resolve
   `{base_url}` para a URL **da instância daquela execução**: literal do topo
   no GREEN; no RED, o `base_url` de topo com o componente de porta trocado
   pela porta livre escolhida (parse de URL, troca só a porta — host e path
   preservados).
3. A substituição vale para **todas** as ocorrências — em `steps`, em
   `assert.backend.check` e em `assert.backend.url`. Não existe "`{base_url}`
   fixo": um check que apontasse para a primária durante o run RED validaria a
   instância errada e produziria RED/GREEN falso.
4. Os demais placeholders: `{port}` só existe dentro de `serve`; `{dir}` só
   dentro de `build`; `{NOME}` (maiúsculas) vem do `credentials_ref`;
   `{nonce}` é o marcador de frescor do run (abaixo).

### O `assert` — por que `backend` importa

A filosofia é a mesma do proof-reviewer: **verde não é evidência; verde que
fica vermelho quando o comportamento quebra é evidência.** Uma asserção
só-visual ("apareceu o toast de sucesso") prova que a tela reagiu — não prova
que o efeito aconteceu. O toast pode aparecer com o POST falhando em silêncio.

- `screen`: string — texto/elemento que deve estar visível ao fim do fluxo.
- `backend`: mapa com `check` (comando shell OU `method` + `url` de endpoint)
  e `expect` (o que a saída deve conter para o assert passar). É o comando de
  verificação **declarado**, executável pelo agente sem adivinhação.
  Opcionalmente `count` (comando que imprime um número) — a alternativa de
  frescor por contagem antes/depois, ver abaixo.

Um fluxo cujo `assert` tem só `screen` roda e é reportado, mas conta como
**evidência fraca**: sozinho, nunca sustenta um veredito PROVEN.

### Frescor — o `expect` tem que provar que o efeito é DESTE run

Um `expect` por substring em endpoint compartilhado passa com **dado residual
de run anterior** — PROVEN falso. Um `assert.backend` só conta como evidência
forte se declarar frescor por um destes dois mecanismos:

- **Nonce do run (`{nonce}`)**: o agente gera um marcador único por run
  (ex.: `uiproof-<slug>-<epoch>`) e o injeta nos dados do fluxo — qualquer
  step que preencha um campo pode interpolar `{nonce}` no valor. O `expect`
  então referencia `{nonce}`: só o registro criado NESTE run satisfaz o
  check.
- **Contagem antes/depois declarada**: `assert.backend.count` com um comando
  que imprime um número (ex.: `curl -sf {base_url}/api/acessos/count`). O
  agente roda ANTES dos steps e DEPOIS; o assert passa se o valor aumentou.
  Use quando o fluxo não tem campo livre onde plantar o nonce.

Um `assert.backend` **sem nenhum dos dois** roda e é reportado, mas com o
status próprio `pass-stale` — "verde, mas pode ser dado residual" — que é
evidência fraca e **rebaixa o veredito** (nunca sustenta PROVEN sozinho),
exatamente como `pass-visual-only`.

## Exemplo completo

Caso realista: extensão Chrome (`wego-acesso`) que registra ações do usuário
num backend. O fluxo abre uma página, aciona a extensão e o registro tem que
aparecer no endpoint de auditoria do backend.

```yaml
# docs/ui-proof.yaml — fluxos de UI declarados do projeto

up: env.yaml                       # reusa up:/healthcheck: do .claude/env.yaml
base_url: http://localhost:8083
build: "npm --prefix {dir}/extension run build"   # recompila do checkout em teste ({dir})
serve: "npm run serve:app -- --port {port}"       # sobe o app compilado na porta escolhida
extension_dir: extension/dist      # extensão unpacked (contém manifest.json), relativa ao checkout em teste
credentials_ref: .env.ui-proof     # gitignorado; ex.: UI_PROOF_USER=..., UI_PROOF_PASS=...

flows:
  registrar-acesso:
    steps:
      - "navegar para {base_url}/painel"
      - "preencher o campo 'E-mail' com {UI_PROOF_USER} e 'Senha' com {UI_PROOF_PASS}, clicar em 'Entrar'"
      - "aguardar o texto 'Bem-vindo' aparecer"
      - "abrir o popup da extensão (chrome-extension://<id>/popup.html), preencher 'Observação' com {nonce} e clicar em 'Registrar acesso'"
      - "aguardar o toast 'Acesso registrado'"
    assert:
      screen: "toast 'Acesso registrado' visível"
      backend:
        check: "curl -sf {base_url}/api/acessos?limit=1"
        expect: "{nonce}"          # frescor: só o registro criado NESTE run satisfaz
    covers:
      - extension/src/**
      - src/main/java/**/acesso/**

  listar-historico:
    steps:
      - "navegar para {base_url}/painel/historico"
      - "aguardar a tabela de acessos carregar"
    assert:
      screen: "pelo menos uma linha na tabela com a coluna 'Origem'"
      # sem backend: → este fluxo é evidência fraca por declaração, e o
      # relatório vai dizer isso. Aceitável para fluxo somente-leitura.
```

Convenções do exemplo:

- `{base_url}` interpola a URL da **instância em teste** (ver "Interpolação"
  acima) — a primária no run GREEN, a perturbada no run RED; `{NOME}`
  interpola variáveis do arquivo de `credentials_ref`; `{nonce}` interpola o
  marcador de frescor do run. O agente faz a substituição antes de gerar o
  script — os valores de credencial **nunca** aparecem no script gerado em
  `docs/ui-proof/runs/` (o script lê do env em runtime).
- `assert.backend.check` também aceita a forma estruturada
  `{ method: GET, url: "{base_url}/api/acessos?limit=1" }` — equivalente ao
  `curl` acima; use a que preferir.

## Extensão Chrome — a receita canônica do popup

"Clicar no ícone da extensão na toolbar" **não é DOM** — a toolbar do
navegador está fora do alcance de qualquer seletor Playwright, e um step
escrito assim é inexecutável. O caminho canônico é **navegar direto para a
página do popup**:

1. O Chromium sobe com a extensão unpacked
   (`--disable-extensions-except`/`--load-extension`).
2. O agente descobre o `<id>` da extensão em runtime — no MV3, pela URL do
   service worker do contexto (`context.serviceWorkers()[0].url()`, cujo host
   é o id).
3. O step "abrir o popup" vira `page.goto('chrome-extension://<id>/popup.html')`
   (troque `popup.html` pelo `default_popup` do `manifest.json` da extensão).
   A partir daí o popup é DOM normal: botões, campos e asserts funcionam.

Escreva os steps do manifesto já nesse vocabulário ("abrir o popup da
extensão"), nunca "clicar no ícone da toolbar".

## Teardown — nada de órfãos

Todo recurso que o run cria, o run remove — **com `trap` no script/mecânica
do agente**, para que valha também em falha parcial: a worktree descartável
(`git worktree remove --force`), o processo do `serve` (kill do PID capturado
ao subir) e, com ele, a porta ocupada. A instância primária (subida via `up`)
não é derrubada pelo agente — ela pertence ao ambiente do humano. Rede de
segurança: a área `ambiente` do `cepa-doctor` (o validador de instalação do
harness, `/common:doctor`) acusa portas ocupadas por processos de outro
diretório e worktrees penduradas — é ela que pega os órfãos de um run que
morreu antes do trap.

## Quem consome

- **`common/agents/ui-proof-reviewer.md`** — o agente que executa: sobe o app
  conforme `up`, gera (ou reusa — os scripts são **pinados** por hash dos
  steps) um script Playwright por fluxo em
  `docs/ui-proof/runs/<fluxo>.spec.ts`, roda, e computa PROVEN / UNPROVEN
  / NEEDS-HUMAN mecanicamente, gravando `docs/proof/ui-<slug>.yaml`.
- **`/common:prove-ui [fluxo|--all|--draft]`** (`common/commands/prove-ui.md`)
  — o comando fino que delega ao agente e aplica o contrato de relatório em
  pt-BR. O modo `--draft` PROPÕE um esqueleto comentado deste manifesto a
  partir da estrutura do repo — proposta explícita para o humano revisar,
  nunca uma prova.
- **`common/hooks/ui-proof-verdict-guard.py`** — guarda mecânica (PreToolUse
  Write): bloqueia um `docs/proof/ui-*.yaml` com `verdict: proven` que
  contradiga seus próprios statuses de fluxo/perturbação.

> **Por que em `common/` e não numa topologia?** A superfície de UI é
> transversal — qualquer topologia (build-hex, build-team, build-solo) pode
> ter uma SPA/extensão na frente do que constrói, então amarrar o gate a uma
> topologia o esconderia das demais. O precedente é o `completion-auditor`,
> que já mora em `common/agents/` pela mesma razão.
>
> **Por que Playwright via Bash e não o MCP de browser?** O gate precisa de
> execução **reprodutível e pinável** — um script versionável em
> `docs/ui-proof/runs/`, re-rodável idêntico no run RED e citável como
> evidência — e de recursos que a superfície MCP não expõe de forma estável
> (contexto persistente com extensão unpacked, trap de teardown). Bash + npx
> dá isso com o toolchain que o repo já declara.

## Aceite (do backlog P6)

Regressão plantada na extensão (ex.: wego-acesso) é pega pelo gate: com o
manifesto declarado, quebrar o handler de registro faz o fluxo
`registrar-acesso` falhar no `assert.backend` — e o veredito sai UNPROVEN
apontando o fluxo e o efeito ausente.
