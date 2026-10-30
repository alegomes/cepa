#!/usr/bin/env python3
"""Regression tests for `--prompt` / `--prompt-substitui` in common/bin/cepa.

cepa accepts a custom system prompt and hands it to claude as a flag.
Contracts guarded here:

  - `--prompt <path>` becomes `--append-system-prompt <content>`, that is, it ADDS
    to Claude Code's default system prompt (the one that teaches tools, hooks and
    CLAUDE.md) instead of erasing it;
  - `--prompt-substitui <path>` becomes `--system-prompt <content>`, the destructive
    mode, and only it;
  - the flag goes BEFORE the user's args and swallows none of them;
  - a loose name (without a slash) is looked up in the library — $CEPA_PROMPTS_HOME and
    <repo>/.claude/prompts — with and without the .md suffix;
  - a missing or empty prompt is an error (rc=2) and the session does NOT start: opening
    silently without the requested prompt is worse than not opening;
  - CEPA_PROMPT/CEPA_PROMPT_MODO give the persistent default;
  - without --prompt, nothing changes (the cepa of before).

No third-party deps — run with `python3 tests/test_cepa_prompt.py`.
"""

import os
import subprocess
import tempfile
from pathlib import Path

# cepa reads CEPA_PROMPT/CEPA_PROMPT_MODO from the environment. Inherited from the shell of whoever
# runs the suite (cepa-until runs with them), they become a prompt the test did not
# ask for and break the "passes only the user's args". Whoever wants the prompt passes
# it in the env= of the case itself.
for _k in ("CEPA_PROMPT", "CEPA_PROMPT_MODO"):
    os.environ.pop(_k, None)

REPO = Path(__file__).resolve().parent.parent
CEPA = REPO / "common" / "bin" / "cepa"

# A fake claude that prints each argument on a line, so the test sees the
# argument boundary (a multiline prompt must not become several args).
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
    """The exact arguments claude received — separated by a marker,
    and not by line, because a multiline prompt is ONE argument only."""
    parts = proc.stdout.split(f"\n{MARK}\n")
    return parts[:-1]


PROMPT_FLAGS = ("--append-system-prompt", "--system-prompt")
# Flags that cepa ITSELF adds, and which therefore are not "user args":
# today only the permission one (every session is born in bypassPermissions).
CEPA_FLAGS = ("--dangerously-skip-permissions", "--permission-mode")


def prompt_par(a):
    """(prompt flag, content, user args after it).

    The contract guarded is the RELATIVE order — the prompt flag comes before what
    you typed — and not the absolute index: cepa prefixes its own flags before
    the user's, and a new flag must not break this test."""
    for i, x in enumerate(a):
        if x in PROMPT_FLAGS:
            return x, (a[i + 1] if i + 1 < len(a) else None), a[i + 2:]
    return None, None, a


def from_user(a):
    """Only what the user typed — without cepa's own flags nor the pair
    prompt-flag + content."""
    outside, i = [], 0
    while i < len(a):
        x = a[i]
        if x in PROMPT_FLAGS:
            i += 2
        elif x.split("=")[0] in CEPA_FLAGS:
            i += 1
        else:
            outside.append(x)
            i += 1
    return outside


def test_append_is_the_default():
    with Repo() as r:
        f = r.path / "p.md"
        f.write_text("SEJA CONCISO\nlinha dois\n")
        p = r.run("--prompt", str(f), "--resume")
        a = args_of(p)
        check("append: rc=0", p.returncode == 0, p.stderr)
        flag, content, after = prompt_par(a)
        check("append: usa --append-system-prompt", flag == "--append-system-prompt", a)
        check("append: entrega o conteúdo como UM argumento",
              content == "SEJA CONCISO\nlinha dois", a)
        check("append: preserva os args do usuário", after == ["--resume"], a)
        check("append: diz qual prompt subiu", "system prompt (append)" in p.stderr, p.stderr)


def test_replace_is_explicit():
    with Repo() as r:
        f = r.path / "p.md"
        f.write_text("prompt inteiro\n")
        a = args_of(r.run("--prompt-substitui", str(f)))
        check("substitui: usa --system-prompt", prompt_par(a)[0] == "--system-prompt", a)
        check("substitui: não usa append",
              "--append-system-prompt" not in a, a)


def test_form_with_equals():
    with Repo() as r:
        f = r.path / "p.md"
        f.write_text("x\n")
        a = args_of(r.run(f"--prompt={f}"))
        check("--prompt=<val>: reconhecida",
              prompt_par(a)[0] == "--append-system-prompt", a)
        a = args_of(r.run(f"--prompt-substitui={f}"))
        check("--prompt-substitui=<val>: reconhecida",
              prompt_par(a)[0] == "--system-prompt", a)


def test_name_in_the_library():
    with Repo() as r:
        (r.lib / "smartass.md").write_text("da biblioteca\n")
        a = args_of(r.run("--prompt", "smartass"))
        check("nome: acha <nome>.md na biblioteca do usuário",
              prompt_par(a)[1] == "da biblioteca", a)


def test_name_in_the_repo_library():
    with Repo() as r:
        d = r.path / ".claude" / "prompts"
        d.mkdir(parents=True)
        (d / "casa").write_text("do repo\n")
        a = args_of(r.run("--prompt", "casa"))
        check("nome: acha na biblioteca do repo (sem sufixo)",
              prompt_par(a)[1] == "do repo", a)


def test_user_library_wins():
    with Repo() as r:
        (r.lib / "x.md").write_text("usuario\n")
        d = r.path / ".claude" / "prompts"
        d.mkdir(parents=True)
        (d / "x.md").write_text("repo\n")
        a = args_of(r.run("--prompt", "x"))
        check("nome homônimo: a biblioteca do usuário vence",
              prompt_par(a)[1] == "usuario", a)


def test_missing_refuses():
    with Repo() as r:
        p = r.run("--prompt", "naoexiste")
        check("inexistente: rc=2", p.returncode == 2, str(p.returncode))
        check("inexistente: não lançou o claude", MARK not in p.stdout, p.stdout)
        check("inexistente: diz onde procurou", "procurei em" in p.stderr, p.stderr)


def test_wrong_path_does_not_fall_to_the_library():
    with Repo() as r:
        (r.lib / "x.md").write_text("nao me use\n")
        p = r.run("--prompt", "./x")
        check("caminho errado: não substitui por homônimo da biblioteca",
              p.returncode == 2 and MARK not in p.stdout, p.stdout)


def test_empty_refuses():
    with Repo() as r:
        f = r.path / "vazio.md"
        f.write_text("")
        p = r.run("--prompt-substitui", str(f))
        check("vazio: rc=2", p.returncode == 2, str(p.returncode))
        check("vazio: não lançou o claude", MARK not in p.stdout, p.stdout)


def test_without_value_refuses():
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


def test_flag_beats_the_env():
    with Repo() as r:
        (r.lib / "padrao.md").write_text("do env\n")
        (r.lib / "outro.md").write_text("da flag\n")
        a = args_of(r.run("--prompt", "outro", env={"CEPA_PROMPT": "padrao"}))
        check("flag vence o env", prompt_par(a)[1] == "da flag", a)


def test_without_prompt_nothing_changes():
    with Repo() as r:
        a = args_of(r.run("--resume"))
        check("sem --prompt: repassa só os args do usuário",
              from_user(a) == ["--resume"], a)


for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
    print(fn.__name__)
    fn()

print()
if failures:
    print(f"✗ {len(failures)} falha(s): {', '.join(failures)}")
    raise SystemExit(1)
print("✓ todos os contratos de --prompt passam")
