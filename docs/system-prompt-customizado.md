# System prompt customizado

O `cepa` — o lançador que você usa no lugar do `claude` — aceita um arquivo de
texto seu como **system prompt**: a instrução que chega ao modelo antes da sua
primeira mensagem e vale a sessão inteira. É onde mora regra de estilo ("seja
conciso", "nunca use a palavra X"), papel, ou qualquer coisa que você repetiria
em todo turno se não estivesse ali.

```
cepa --modo construcao --prompt smartass
```

## As duas flags, e por que são duas

| Flag | Vira, na chamada do `claude` | Efeito |
|---|---|---|
| `--prompt <nome\|caminho>` | `--append-system-prompt` | **Soma** o seu texto ao system prompt padrão do Claude Code |
| `--prompt-substitui <nome\|caminho>` | `--system-prompt` | **Apaga** esse padrão e põe o seu no lugar |

O system prompt padrão do Claude Code não é enfeite: é ele que ensina ao modelo
quais ferramentas existem, como os hooks se comportam e que o `CLAUDE.md` deve
ser carregado. Trocá-lo por um texto de estilo tira essas instruções do ar, e a
sessão passa a errar com confiança. Por isso o modo destrutivo tem nome próprio
(`--prompt-substitui`) em vez de ser uma opção do mesmo flag: ninguém cai nele
por descuido. Use-o só com um prompt escrito para se sustentar sozinho.

**Na dúvida, `--prompt`.**

## Onde os prompts ficam

O argumento pode ser um caminho (`~/prompts/x.md`, `./p.md`) ou um **nome
solto**. Nome solto é procurado, com e sem o sufixo `.md`, em duas pastas nesta
ordem:

1. `~/.claude/cepa-prompts` — sua biblioteca pessoal, vale em qualquer repo.
   Muda com `CEPA_PROMPTS_HOME`.
2. `<repo>/.claude/prompts` — a biblioteca do projeto, para um prompt que só faz
   sentido ali.

Homônimo: a sua ganha da do repo.

Um argumento **com barra** é caminho e só ele é tentado. Se você errar o
caminho, o `cepa` não sai procurando um homônimo na biblioteca — errar caminho é
erro de digitação, não convite para adivinhar.

Um prompt que mora em outro repositório entra na biblioteca por atalho, e aí
editar o original já vale na próxima sessão:

```
ln -s ~/coding/fixing-smartass-opus-5/sr_opus_5_system_prompt.md \
      ~/.claude/cepa-prompts/smartass.md
```

## Ligar por default, sem digitar a flag

`CEPA_PROMPT` guarda o mesmo `<nome|caminho>` que a flag aceitaria, e
`CEPA_PROMPT_MODO` escolhe entre `append` (o default) e `substitui`. No
`~/.zshrc`:

```sh
export CEPA_PROMPT=smartass          # toda sessão sobe com ele, somado ao padrão
# export CEPA_PROMPT_MODO=substitui  # só se o prompt se sustenta sozinho
```

A flag na linha de comando vence a variável, então `cepa --prompt outro` troca o
prompt naquela sessão sem mexer no `.zshrc`.

Isso é conveniência com um preço: um prompt que vale sempre some da sua atenção.
Quando uma sessão sair estranha, o `export` é o primeiro lugar a olhar — o
`cepa` imprime na subida qual prompt entrou e em que modo:

```
◆ system prompt (append): /Users/você/.claude/cepa-prompts/smartass.md
```

Enquanto você ainda está decidindo se gosta de um prompt, prefira a flag: ligar
e desligar por sessão é o que deixa a comparação possível.

## Quando ele recusa subir

Prompt inexistente, ou arquivo vazio: o `cepa` sai com erro (código 2), diz onde
procurou, e **não** abre a sessão. Abrir calado sem o prompt que você pediu é o
pior dos mundos — você conversaria uma hora achando que ele está valendo.

A flag entra antes de qualquer caminho de lançamento, então vale igual fora de
repositório git, na raiz do repo, e quando o `cepa` isola a sessão numa worktree
própria.

Contratos guardados em `tests/test_cepa_prompt.py`.
