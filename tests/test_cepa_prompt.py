#!/usr/bin/env python3
"""Regression tests para `--prompt` / `--prompt-substitui` em common/bin/cepa.

O cepa aceita um system prompt customizado e o entrega ao claude como flag.
Contratos guardados aqui:

  - `--prompt <caminho>` vira `--append-system-prompt <conteúdo>`, ou seja SOMA
    ao system prompt padrão do Claude Code (o que ensina ferramentas, hooks e
    CLAUDE.md) em vez de apagá-lo;
  - `--prompt-substitui <caminho>` vira `--system-prompt <conteúdo>`, o modo
    destrutivo, e só ele;
  - a flag entra ANTES dos args do usuário e não engole nenhum deles;
  - nome solto (sem barra) é procurado na biblioteca — $CEPA_PROMPTS_HOME e
    <repo>/.claude/prompts — com e sem o sufixo .md;
  - prompt inexistente ou vazio é erro (rc=2) e a sessão NÃO sobe: abrir calado
    sem o prompt pedido é pior que não abrir;
  - CEPA_PROMPT/CEPA_PROMPT_MODO dão o default persistente;
  - sem --prompt, nada muda (o cepa de antes).

Sem deps de terceiros — rode com `python3 tests/test_cepa_prompt.py`.
"""

import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CEPA = REPO / "common" / "bin" / "cepa"

# Um claude falso que imprime cada argumento numa linha, para o teste ver
# fronteira de argumento (um prompt multilinha não pode virar vários args).
MARK = "---CEPA-ARG---"
FAKE_CLAUDE = f'#!/bin/sh\nfor a in "$@"; do printf "%s\\n{MARK}\\n" "$a"; done\n'

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


class Repo:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "repo"
        self.path.mkdir()
        subprocess.run(["git", "init", "-q", "."], cwd=self.path, check=True)
        fake = Path(self.tmp.name) / "fakeclaude"
        fake.write_text(FAKE_CLAUDE)
        fake.chmod(0o755)
        self.fake = fake
        self.lib = Path(self.tmp.name) / "prompts"
        self.lib.mkdir()
        return self

    def __exit__(self, *a):
        self.tmp.cleanup()

    def run(self, *args, env=None):
        e = {**os.environ,
             "CLAUDE_WT_CLAUDE_BIN": str(self.fake),
             "CEPA_PREFLIGHT": "off",
             "CEPA_MODO": "off",
             "CEPA_PROMPTS_HOME": str(self.lib)}
        e.update(env or {})
        return subprocess.run(
            [str(CEPA), *args], cwd=self.path, env=e,
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30,
        )


def args_of(proc):
    """Os argumentos exatos que o claude recebeu — separados por um marcador,
    e não por linha, porque um prompt multilinha é UM argumento só."""
    parts = proc.stdout.split(f"\n{MARK}\n")
    return parts[:-1]


PROMPT_FLAGS = ("--append-system-prompt", "--system-prompt")
# Flags que o PRÓPRIO cepa acrescenta, e que portanto não são "args do usuário":
# hoje só a de permissão (toda sessão nasce em bypassPermissions).
FLAGS_DO_CEPA = ("--dangerously-skip-permissions", "--permission-mode")


def prompt_par(a):
    """(flag de prompt, conteúdo, args do usuário depois dela).

    O contrato guardado é a ordem RELATIVA — a flag de prompt vem antes do que
    você digitou — e não o índice absoluto: o cepa prefixa flags próprias antes
    das do usuário, e uma flag nova não pode quebrar este teste."""
    for i, x in enumerate(a):
        if x in PROMPT_FLAGS:
            return x, (a[i + 1] if i + 1 < len(a) else None), a[i + 2:]
    return None, None, a


def do_usuario(a):
    """Só o que o usuário digitou — sem as flags do próprio cepa nem o par
    flag-de-prompt + conteúdo."""
    fora, i = [], 0
    while i < len(a):
        x = a[i]
        if x in PROMPT_FLAGS:
            i += 2
        elif x.split("=")[0] in FLAGS_DO_CEPA:
            i += 1
        else:
            fora.append(x)
            i += 1
    return fora


def test_append_e_o_default():
    with Repo() as r:
        f = r.path / "p.md"
        f.write_text("SEJA CONCISO\nlinha dois\n")
        p = r.run("--prompt", str(f), "--resume")
        a = args_of(p)
        check("append: rc=0", p.returncode == 0, p.stderr)
        flag, conteudo, depois = prompt_par(a)
        check("append: usa --append-system-prompt", flag == "--append-system-prompt", a)
        check("append: entrega o conteúdo como UM argumento",
              conteudo == "SEJA CONCISO\nlinha dois", a)
        check("append: preserva os args do usuário", depois == ["--resume"], a)
        check("append: diz qual prompt subiu", "system prompt (append)" in p.stderr, p.stderr)


def test_substitui_e_explicito():
    with Repo() as r:
        f = r.path / "p.md"
        f.write_text("prompt inteiro\n")
        a = args_of(r.run("--prompt-substitui", str(f)))
        check("substitui: usa --system-prompt", prompt_par(a)[0] == "--system-prompt", a)
        check("substitui: não usa append",
              "--append-system-prompt" not in a, a)


def test_forma_com_igual():
    with Repo() as r:
        f = r.path / "p.md"
        f.write_text("x\n")
        a = args_of(r.run(f"--prompt={f}"))
        check("--prompt=<val>: reconhecida",
              prompt_par(a)[0] == "--append-system-prompt", a)
        a = args_of(r.run(f"--prompt-substitui={f}"))
        check("--prompt-substitui=<val>: reconhecida",
              prompt_par(a)[0] == "--system-prompt", a)


def test_nome_na_biblioteca():
    with Repo() as r:
        (r.lib / "smartass.md").write_text("da biblioteca\n")
        a = args_of(r.run("--prompt", "smartass"))
        check("nome: acha <nome>.md na biblioteca do usuário",
              prompt_par(a)[1] == "da biblioteca", a)


def test_nome_na_biblioteca_do_repo():
    with Repo() as r:
        d = r.path / ".claude" / "prompts"
        d.mkdir(parents=True)
        (d / "casa").write_text("do repo\n")
        a = args_of(r.run("--prompt", "casa"))
        check("nome: acha na biblioteca do repo (sem sufixo)",
              prompt_par(a)[1] == "do repo", a)


def test_biblioteca_do_usuario_ganha():
    with Repo() as r:
        (r.lib / "x.md").write_text("usuario\n")
        d = r.path / ".claude" / "prompts"
        d.mkdir(parents=True)
        (d / "x.md").write_text("repo\n")
        a = args_of(r.run("--prompt", "x"))
        check("nome homônimo: a biblioteca do usuário vence",
              prompt_par(a)[1] == "usuario", a)


def test_inexistente_recusa():
    with Repo() as r:
        p = r.run("--prompt", "naoexiste")
        check("inexistente: rc=2", p.returncode == 2, str(p.returncode))
        check("inexistente: não lançou o claude", MARK not in p.stdout, p.stdout)
        check("inexistente: diz onde procurou", "procurei em" in p.stderr, p.stderr)


def test_caminho_errado_nao_cai_na_biblioteca():
    with Repo() as r:
        (r.lib / "x.md").write_text("nao me use\n")
        p = r.run("--prompt", "./x")
        check("caminho errado: não substitui por homônimo da biblioteca",
              p.returncode == 2 and MARK not in p.stdout, p.stdout)


def test_vazio_recusa():
    with Repo() as r:
        f = r.path / "vazio.md"
        f.write_text("")
        p = r.run("--prompt-substitui", str(f))
        check("vazio: rc=2", p.returncode == 2, str(p.returncode))
        check("vazio: não lançou o claude", MARK not in p.stdout, p.stdout)


def test_sem_valor_recusa():
    with Repo() as r:
        p = r.run("--prompt")
        check("--prompt sem valor: rc=2", p.returncode == 2, str(p.returncode))


def test_env_default():
    with Repo() as r:
        (r.lib / "padrao.md").write_text("do env\n")
        a = args_of(r.run("--resume", env={"CEPA_PROMPT": "padrao"}))
        check("CEPA_PROMPT: aplica sem flag", prompt_par(a)[1] == "do env", a)
        a = args_of(r.run(env={"CEPA_PROMPT": "padrao",
                               "CEPA_PROMPT_MODO": "substitui"}))
        check("CEPA_PROMPT_MODO=substitui: troca a flag",
              prompt_par(a)[0] == "--system-prompt", a)
        p = r.run(env={"CEPA_PROMPT": "padrao", "CEPA_PROMPT_MODO": "xpto"})
        check("CEPA_PROMPT_MODO inválido: rc=2", p.returncode == 2, p.stderr)


def test_flag_vence_o_env():
    with Repo() as r:
        (r.lib / "padrao.md").write_text("do env\n")
        (r.lib / "outro.md").write_text("da flag\n")
        a = args_of(r.run("--prompt", "outro", env={"CEPA_PROMPT": "padrao"}))
        check("flag vence o env", prompt_par(a)[1] == "da flag", a)


def test_sem_prompt_nada_muda():
    with Repo() as r:
        a = args_of(r.run("--resume"))
        check("sem --prompt: repassa só os args do usuário",
              do_usuario(a) == ["--resume"], a)


for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
    print(fn.__name__)
    fn()

print()
if failures:
    print(f"✗ {len(failures)} falha(s): {', '.join(failures)}")
    raise SystemExit(1)
print("✓ todos os contratos de --prompt passam")
