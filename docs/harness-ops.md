# Updates operacionais do harness

## O que conta como operacional

Mudança em `common/hooks/**`, `*/bin/**`, `settings.json` ou em qualquer
`plugin.json` é um **update operacional**: ela não muda o que um agente
entrega, muda **a superfície em que o próximo agente opera**. Um hook novo
começa a bloquear coisas; um hook removido para de bloquear; um comando
renomeado deixa de existir para quem chamá-lo.

O que torna essa classe perigosa não é o tamanho — quase sempre é pequena — é
que ela é **invisível de dentro da sessão**. Um agente não sente que os hooks
que ele carregou na memória são de duas versões atrás. Ele só age errado com
confiança.

**Na dúvida, é operacional.** O custo de tratar uma mudança comum como
operacional é escrever três linhas a mais. O custo do inverso já apareceu aqui
várias vezes com o mesmo nome: *"NOT live until reinstall"*.

## A rota mínima

Todo update operacional carrega quatro coisas. Nenhuma delas é opcional, e a
ordem importa:

| Etapa | Pergunta | Onde vive hoje |
|---|---|---|
| **Estado** | o que está live agora? | `~/.claude/ops/last-install.json` → `versions_before` |
| **Alvo** | o que passa a estar live? | mesmo arquivo → `versions_target` |
| **Rollback** | como volto se piorar? | `bin/install.sh --rollback` |
| **Validação** | como sei que pegou? | `/common:doctor` |

**A ausência de rota de recuperação é um fato que o humano vê ANTES, não
depois.** É por isso que `--clean` deixou de apagar o cache: ele agora move o
cache anterior para `<cache>.prev`, e o `--rollback` o traz de volta. Antes,
"desfazer" significava reinstalar de um commit antigo e torcer.

## Na prática

```sh
bin/install.sh --clean      # instala; preserva o cache anterior
/common:doctor              # confirma que pegou (e acusa o que não pegou)
bin/install.sh --rollback   # desfaz o último --clean
```

Depois de qualquer um dos dois: **reinicie o Claude Code**. Uma sessão viva
segue com os hooks que carregou no boot — o cache no disco estar certo não
significa que a sessão que está rodando esteja.

## O que o doctor acusa

- **Install que não terminou.** O registro é escrito em `in_progress` antes do
  teardown e só fecha em `ok` na última linha do script. Um install que morreu
  no meio deixa `in_progress` no disco, e isso vira uma **falha** no doctor —
  não silêncio. Sem isso, o harness fica num estado que ninguém escolheu e a
  próxima sessão não tem como saber.
- **Drift live-vs-repo, com idade.** "O repo está em 0.18.0, o cache em 0.17.0"
  é um aviso; "…e o último install foi há 12 dias" é o que separa *acabei de
  editar* de *faz duas semanas que trabalho contra um harness que não é o
  instalado*.
- **Rollback recente.** Se o último evento foi um `--rollback`, o cache live é
  o **anterior** ao install que você tentou. É um estado legítimo e fácil de
  esquecer, então o doctor o diz em voz alta.

## Limites conhecidos

O registro é **global** (`~/.claude/ops/`), porque o cache de plugins que ele
descreve é global: uma máquina, um harness live, seja qual for o repositório em
que você esteja. Ele guarda `repo_dir` justamente para você saber de qual clone
veio o que está instalado.

O `--rollback` restaura **um** passo. Não é um histórico — é a rota de saída do
último `--clean`. O cache substituído por um rollback fica em
`<cache>.rolledback`, então nada é destruído em silêncio, mas não conte com
uma cadeia de desfazer.
