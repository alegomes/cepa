# Manifesto de prova de UI — `.claude/ui-proof.yaml`

O `proof-reviewer` (build-hex) prova o backend; a superfície onde o usuário
mais sofre — SPA e extensão Chrome — não tinha gate. O `ui-proof-reviewer`
(em `common/agents/ui-proof-reviewer.md`) fecha esse buraco: ele sabe **como**
provar (Playwright via Bash/npx, carregar extensão unpacked, percorrer o
fluxo, assertar efeito observável no backend). O que ele **não** sabe é o que
cada produto considera um fluxo que vale a pena provar — isso é conhecimento
do repo, não do harness. Este manifesto é onde o repo declara **o que provar**.

> **Onde mora:** no repo do *projeto que usa o cepa*, em `.claude/ui-proof.yaml`.
> O cepa em si não tem um — ele documenta o formato (este arquivo) e o consome
> (`ui-proof-reviewer`, `/common:prove-ui`).
>
> **Relação com o `env.yaml` (P3):** o [manifesto de ambiente](env-manifest.md)
> declara o runtime (portas, serviços, como subir); este manifesto declara os
> fluxos de UI e seus efeitos verificáveis. Eles se complementam: o campo `up`
> daqui pode simplesmente dizer `env.yaml` para reusar o `up:`/`healthcheck:`
> de lá, em vez de duplicar o comando.

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
| `up` | string | sim | Como subir o app. Ou um comando literal, ou a string `env.yaml` para delegar ao `up:`/`healthcheck:` do manifesto de ambiente do P3. |
| `base_url` | string | sim | URL raiz onde o app responde depois de subir. Respeite as portas declaradas no `env.yaml`, se houver. |
| `extension_dir` | string | não | Path (relativo à raiz do repo) da extensão Chrome **unpacked** — o diretório que contém o `manifest.json`. Presente → os fluxos rodam num Chromium com a extensão carregada. |
| `credentials_ref` | string | não | Path de um arquivo **gitignorado** com credenciais de dev (ex.: `.env.ui-proof`), formato `CHAVE=valor` por linha. **NUNCA credenciais inline no manifesto** — o manifesto é versionado; o arquivo referenciado, não. Ausente ou inexistente com fluxo que exige login → o fluxo não roda (vira `NEEDS-HUMAN`, nunca um chute). |
| `flows` | mapa | sim | Fluxos nomeados a provar. Cada nome é o identificador usado em `/common:prove-ui <fluxo>`. |

### Campos de cada fluxo

| Campo | Tipo | Obrigatório | O que declara |
|---|---|---|---|
| `steps` | lista de strings | sim | Prosa **estruturada**, um passo por item, no vocabulário navegar/clicar/preencher/aguardar. O agente traduz cada passo para Playwright — então seja concreto: nomeie o texto do botão, o label do campo, a URL. Prosa vaga ("use o app normalmente") não é traduzível e será reportada como fluxo inexecutável. |
| `assert` | mapa | sim | O efeito observável que prova o fluxo. Duas chaves: `screen` (o que deve aparecer na tela) e `backend` (o efeito verificável fora da tela). Pelo menos uma é obrigatória; **só `screen` é evidência fraca** — veja abaixo. |
| `covers` | lista de strings | não | Globs de arquivos de produção que este fluxo cobre (ex.: `extension/src/**`). Usado pelo agente para escolher qual fluxo re-rodar na prova green→red→green quando o diff da mudança é conhecido. |

### O `assert` — por que `backend` importa

A filosofia é a mesma do proof-reviewer: **verde não é evidência; verde que
fica vermelho quando o comportamento quebra é evidência.** Uma asserção
só-visual ("apareceu o toast de sucesso") prova que a tela reagiu — não prova
que o efeito aconteceu. O toast pode aparecer com o POST falhando em silêncio.

- `screen`: string — texto/elemento que deve estar visível ao fim do fluxo.
- `backend`: mapa com `check` (comando shell OU `method` + `url` de endpoint)
  e `expect` (o que a saída deve conter para o assert passar). É o comando de
  verificação **declarado**, executável pelo agente sem adivinhação.

Um fluxo cujo `assert` tem só `screen` roda e é reportado, mas conta como
**evidência fraca**: sozinho, nunca sustenta um veredito PROVEN.

## Exemplo completo

Caso realista: extensão Chrome (`wego-acesso`) que registra ações do usuário
num backend. O fluxo abre uma página, aciona a extensão e o registro tem que
aparecer no endpoint de auditoria do backend.

```yaml
# .claude/ui-proof.yaml — fluxos de UI declarados do projeto

up: env.yaml                       # reusa up:/healthcheck: do .claude/env.yaml
base_url: http://localhost:8083
extension_dir: extension/dist      # extensão unpacked (contém manifest.json)
credentials_ref: .env.ui-proof     # gitignorado; ex.: UI_PROOF_USER=..., UI_PROOF_PASS=...

flows:
  registrar-acesso:
    steps:
      - "navegar para {base_url}/painel"
      - "preencher o campo 'E-mail' com {UI_PROOF_USER} e 'Senha' com {UI_PROOF_PASS}, clicar em 'Entrar'"
      - "aguardar o texto 'Bem-vindo' aparecer"
      - "clicar no ícone da extensão wego-acesso na toolbar e clicar em 'Registrar acesso'"
      - "aguardar o toast 'Acesso registrado'"
    assert:
      screen: "toast 'Acesso registrado' visível"
      backend:
        check: "curl -sf {base_url}/api/acessos?limit=1"
        expect: '"origem": "extensao"'   # o registro recém-criado aparece no endpoint
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

- `{base_url}` interpola o campo de topo; `{NOME}` interpola variáveis do
  arquivo de `credentials_ref`. O agente faz a substituição antes de gerar o
  script — os valores de credencial **nunca** aparecem no script gerado em
  `.claude/ui-proof/runs/` (o script lê do env em runtime).
- `assert.backend.check` também aceita a forma estruturada
  `{ method: GET, url: "{base_url}/api/acessos?limit=1" }` — equivalente ao
  `curl` acima; use a que preferir.

## Quem consome

- **`common/agents/ui-proof-reviewer.md`** — o agente que executa: sobe o app
  conforme `up`, gera um script Playwright por fluxo em
  `.claude/ui-proof/runs/`, roda, e computa PROVEN / UNPROVEN / NEEDS-HUMAN
  mecanicamente, gravando `.claude/proof/ui-<slug>.yaml`.
- **`/common:prove-ui [fluxo|--all]`** (`common/commands/prove-ui.md`) — o
  comando fino que delega ao agente e aplica o contrato de relatório em pt-BR.

## Aceite (do backlog P6)

Regressão plantada na extensão (ex.: wego-acesso) é pega pelo gate: com o
manifesto declarado, quebrar o handler de registro faz o fluxo
`registrar-acesso` falhar no `assert.backend` — e o veredito sai UNPROVEN
apontando o fluxo e o efeito ausente.
