#!/usr/bin/env python3
"""Regression tests for the `--mode` gate in common/bin/cepa (`--modo` still works).

Every session declares in which of the seven work modes it operates
(docs/modos-de-trabalho.md). The mode is recorded in .claude/session-mode in the
directory where the session will actually run. Without a mode cepa does not start: a silent
default would rebuild exactly the leak between activities that the mode
exists to close.

Contracts guarded here:
  - a valid mode writes the file and passes the remaining args to claude;
  - an unknown mode is an error (rc=2), never becomes a question nor a guess;
  - without a mode and without tty → refuses to start, and does NOT write a file;
  - CEPA_MODO=off turns off the whole requirement (escape hatch);
  - an overhaul without a budget is refused — an overhaul without a closed scope does not end;
  - the detection of "there is a human to ask" looks at stdin, not only /dev/tty:
    /dev/tty stays readable with redirected stdin, and alone it would let a
    pipe-fed script stop at an interactive menu.

No third-party deps — run with `python3 tests/test_cepa_mode.py`.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# cepa reads CEPA_PROMPT/CEPA_PROMPT_MODO from the environment. Inherited from the shell of whoever
# runs the suite (cepa-until runs with them), they become a prompt the test did not
# ask for and break the "passes only the user's args". Whoever wants the prompt passes
# it in the env= of the case itself.
for _k in ("CEPA_PROMPT", "CEPA_PROMPT_MODO"):
    os.environ.pop(_k, None)

# The intent cases write the .claude/session-log.md that session-mode reads,
# and the scan of tests/test_isolated_telemetry.py treats whoever cites an
# emitting hook as an emitter. Isolating here costs nothing and keeps the real ledger clean.
# See tests/_isolated_telemetry.py.
from _isolated_telemetry import isolate  # noqa: E402

isolate()

REPO =Path(__file__).resolve().parent.parent
CEPA = REPO / "common" / "bin" / "cepa"

FAKE_CLAUDE = '#!/bin/sh\nprintf "CLAUDE_ARGS:%s\\n" "$*"\n'

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


class Repo:
    """A disposable git repo with a fake `claude` in place of the real one."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "repo"
        self.path.mkdir()
        subprocess.run(["git", "init", "-q", "."], cwd=self.path, check=True)
        subprocess.run(
            ["git", "commit", "-q", "--allow-empty", "-m", "init"],
            cwd=self.path, check=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
        )
        fake = Path(self.tmp.name) / "fakeclaude"
        fake.write_text(FAKE_CLAUDE)
        fake.chmod(0o755)
        self.fake = fake
        return self

    def __exit__(self, *a):
        self.tmp.cleanup()

    def run(self, *args, env=None):
        e = {**os.environ,
             "CLAUDE_WT_CLAUDE_BIN": str(self.fake),
             "CEPA_PREFLIGHT": "off"}
        e.update(env or {})
        return subprocess.run(
            [str(CEPA), *args], cwd=self.path, env=e,
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30,
        )

    @property
    def mode_file(self):
        return self.path / ".claude" / "session-mode"


# Flags that cepa ITSELF adds before yours: today only the permission one
# (every session is born in bypassPermissions). The contract tested here is "did not
# swallow what you typed", so they come out of the comparison.
CEPA_FLAGS = ("--dangerously-skip-permissions", "--permission-mode")


def claude_args(proc):
    """The user args that reached the fake claude."""
    line = ""
    for l in proc.stdout.splitlines():
        if l.startswith("CLAUDE_ARGS:"):
            line = l[len("CLAUDE_ARGS:"):]
    return [x for x in line.split() if x.split("=")[0] not in CEPA_FLAGS]


def test_valid_mode():
    with Repo() as r:
        p = r.run("--mode", "construction", "--resume")
        check("modo válido: rc=0", p.returncode == 0, p.stderr)
        check("modo válido: grava o arquivo", r.mode_file.exists())
        body = r.mode_file.read_text() if r.mode_file.exists() else ""
        check("modo válido: registra o modo", "mode: construction" in body, body)
        check("modo válido: repassa os args ao claude",
              claude_args(p) == ["--resume"], p.stdout)


def test_invalid_mode():
    with Repo() as r:
        p = r.run("--mode=xpto")
        check("modo inválido: rc=2", p.returncode == 2, str(p.returncode))
        check("modo inválido: não grava", not r.mode_file.exists())
        check("modo inválido: lista os válidos", "construction" in p.stderr, p.stderr)


def test_without_mode_without_tty():
    with Repo() as r:
        p = r.run()
        check("sem modo: recusa subir", p.returncode == 2, str(p.returncode))
        check("sem modo: não grava", not r.mode_file.exists())
        check("sem modo: não caiu no menu interativo",
              "Which mode does this session operate in" not in p.stderr, p.stderr)
        check("sem modo: ensina o escape", "CEPA_MODO=off" in p.stderr, p.stderr)


def test_kill_switch():
    with Repo() as r:
        p = r.run("--resume", env={"CEPA_MODO": "off"})
        check("CEPA_MODO=off: sobe", p.returncode == 0, p.stderr)
        check("CEPA_MODO=off: não grava", not r.mode_file.exists())
        check("CEPA_MODO=off: entrega ao claude",
              claude_args(p) == ["--resume"], p.stdout)


def test_overhaul_budget():
    with Repo() as r:
        p = r.run("--mode", "refactor")
        check("reforma sem orçamento: recusa", p.returncode == 2, str(p.returncode))
        check("reforma sem orçamento: não grava", not r.mode_file.exists())
    with Repo() as r:
        p = r.run("--mode", "refactor", "--budget", "só o módulo de auth")
        check("reforma com orçamento: rc=0", p.returncode == 0, p.stderr)
        body = r.mode_file.read_text() if r.mode_file.exists() else ""
        check("reforma com orçamento: registra o escopo",
              'budget: "só o módulo de auth"' in body, body)


# --- session-mode.py hook ---------------------------------------------------
HOOK = REPO / "common" / "hooks" / "session-mode.py"


def run_hook(cwd, env=None, **payload):
    """`payload` becomes fields of the hook JSON (session_id, prompt). The cepa-until
    mark comes out of the environment: the suite runs inside it, and with it the hook
    silences the intent — whoever wants to test that passes it in the env= of the case."""
    import json as _json
    e = {k: v for k, v in os.environ.items() if k != "CEPA_UNTIL_RUN"}
    e.update(env or {})
    return subprocess.run(
        [sys.executable, str(HOOK)], input=_json.dumps({"cwd": str(cwd), **payload}),
        capture_output=True, text=True, timeout=15, env=e,
    )


def ctx(proc):
    """The text the model actually receives — decoded, not the raw JSON."""
    import json as _json
    if not proc.stdout.strip():
        return ""
    return _json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]


def write_mode(repo, body):
    d = repo.path / ".claude"
    d.mkdir(exist_ok=True)
    (d / "session-mode").write_text(body, encoding="utf-8")


def test_hook_injects_mode_and_exit():
    with Repo() as r:
        write_mode(r, "mode: construction\nrotina: null\norcamento: null\n")
        p = run_hook(r.path)
        check("hook: rc=0", p.returncode == 0, p.stderr)
        c = ctx(p)
        check("hook: nomeia o modo", "construction" in c, c)
        check("hook: dá a condição de saída",
              "completion-auditor" in c and "PROVEN" in c, c)
        check("hook: manda capturar o desvio", "off-mode-capture" in c, c)


def test_hook_overhaul_shows_budget():
    with Repo() as r:
        write_mode(r, 'mode: refactor\norcamento: "só o módulo de auth"\n')
        p = run_hook(r.path)
        c = ctx(p)
        check("hook reforma: mostra o orçamento", "só o módulo de auth" in c, c)
        check("hook reforma: cobra teste externo não editado",
              "external test edited" in c, c)


def test_hook_silent_without_mode():
    with Repo() as r:
        p = run_hook(r.path)
        check("hook: silencioso sem arquivo de modo", p.stdout.strip() == "",
              repr(p.stdout))
        check("hook: rc=0 sem arquivo", p.returncode == 0, p.stderr)


def test_hook_respects_kill_switch():
    with Repo() as r:
        write_mode(r, "mode: construction\n")
        p = run_hook(r.path, env={"CEPA_MODO": "off"})
        check("hook: CEPA_MODO=off silencia", p.stdout.strip() == "", repr(p.stdout))


def test_hook_never_breaks_the_turn():
    with Repo() as r:
        write_mode(r, "lixo que não é yaml\n:::\n")
        p = run_hook(r.path)
        check("hook: arquivo corrompido não quebra", p.returncode == 0, p.stderr)
        check("hook: arquivo corrompido não injeta nada",
              p.stdout.strip() == "", repr(p.stdout))


# --- session intent in the hook (.claude/session-intent) ----------------------
# Design: docs/estrategia-intencao-da-sessao.md. Three states, a ceiling of two
# lines each: empty (the first three prompts + request to record), intent
# of ANOTHER session (a question, never shown as current) and normal (step N/M, how many
# turns ago, next). A cepa-until round does not receive intent.

sys.path.insert(0, str(REPO / "common" / "hooks"))
import _modes as _M  # noqa: E402

PLAN_TEXT = ["levantar o que existe", "escrever o doc", "rodar advisors", "decidir"]
SID = "209286bf-1111-2222-3333-444455556666"


def write_intent(repo, **fields):
    d = {"purpose": "institucionalizar as quatro perguntas",
         "by_when": "doc decidido", "plan": PLAN_TEXT, "step": 2,
         "step_since": "2026-10-16T21:40:00Z", "session_id": SID[:8],
         "branch": "main", "opened_at": "2026-10-16T18:30:00Z"}
    d.update(fields)
    (repo.path / ".claude").mkdir(exist_ok=True)
    (repo.path / ".claude" / "session-intent").write_text(_M.render_intent(d), encoding="utf-8")


def write_log(repo, inputs):
    """entries: [("2026-10-16", "21:41:00", "prompt"), ...] in the session-log format."""
    out, day = ["# Session log", ""], None
    for d, h, t in inputs:
        if d != day:
            out += [f"## {d}", ""]
            day = d
        out += [f"### {h} UTC", "", t, ""]
    (repo.path / ".claude").mkdir(exist_ok=True)
    (repo.path / ".claude" / "session-log.md").write_text("\n".join(out), encoding="utf-8")


def register(repo, sid, started_at):
    d = repo.path / ".claude" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    import json as _json
    (d / f"{sid}.json").write_text(_json.dumps({"session_id": sid, "started_at": started_at}))


def intent_lines(c):
    """The intent lines of the context: the first starts with [intenção]; the
    mode one is always a single line and comes before."""
    ls = c.split("\n")
    for i, l in enumerate(ls):
        if l.startswith("[intenção]"):
            return ls[i:]
    return []


def test_empty_intent_brings_the_first_prompts():
    with Repo() as r:
        write_mode(r, "mode: exploration\n")
        register(r, SID, "2026-10-16T18:00:00+00:00")
        write_log(r, [("2026-10-15", "10:00:00", "prompt de outra sessão"),
                      ("2026-10-16", "18:01:00", "quero institucionalizar as perguntas"),
                      ("2026-10-16", "18:02:00", "primeiro levante o que existe"),
                      ("2026-10-16", "18:03:00", "x" * 300),
                      ("2026-10-16", "18:04:00", "quarto prompt")])
        p = run_hook(r.path, session_id=SID, prompt="quarto prompt")
        check("intenção vazia: rc=0", p.returncode == 0, p.stderr)
        c = ctx(p)
        il = intent_lines(c)
        check("intenção vazia: diz que não há intenção gravada",
              "ainda não tem intenção gravada" in c, c)
        check("intenção vazia: traz os três primeiros prompts da sessão",
              "quero institucionalizar" in c and "primeiro levante" in c and "xxx" in c, c)
        check("intenção vazia: prompt de sessão anterior fica de fora",
              "outra sessão" not in c, c)
        check("intenção vazia: o quarto prompt fica de fora", "quarto prompt" not in c, c)
        check("intenção vazia: prompt longo é cortado", "x" * 200 not in c and "…" in c, c)
        check("intenção vazia: pede para gravar com cepa-intent e ensina o whereami",
              "cepa-intent write" in c and "/common:whereami" in c, c)
        check("intenção vazia: manda não propor em prompt trivial", "trivial" in c, c)
        check("intenção vazia: teto de duas linhas", 1 <= len(il) <= 2, il)
        check("intenção vazia: o modo continua lá", "[modo]" in c, c)


def test_empty_intent_first_turn_uses_the_current_prompt():
    with Repo() as r:
        write_mode(r, "mode: exploration\n")
        register(r, SID, "2026-10-16T18:00:00+00:00")
        p = run_hook(r.path, session_id=SID, prompt="  quero   um comando whereami ")
        c = ctx(p)
        check("intenção vazia, log vazio: o prompt do turno entra",
              '"quero um comando whereami"' in c, c)


def test_empty_intent_without_record_falls_back_to_today():
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with Repo() as r:
        write_mode(r, "mode: exploration\n")
        write_log(r, [("2020-01-01", "10:00:00", "prompt antigo"),
                      (today, "00:00:01", "prompt de hoje")])
        c = ctx(run_hook(r.path, session_id="sem-registro", prompt="prompt de hoje"))
        check("sem registro: usa os prompts de hoje",
              "prompt de hoje" in c and "prompt antigo" not in c, c)


def test_empty_intent_without_mode_is_silent():
    with Repo() as r:
        p = run_hook(r.path, session_id=SID, prompt="oi")
        check("intenção vazia sem modo: silêncio (sessão não aberta pelo cepa)",
              p.stdout.strip() == "", repr(p.stdout))


def test_intent_normal_step_age_next():
    with Repo() as r:
        write_mode(r, "mode: exploration\n")
        write_intent(r)
        write_log(r, [("2026-10-16", "21:30:00", "antes do cursor"),
                      ("2026-10-16", "21:41:00", "depois 1"),
                      ("2026-10-17", "09:00:00", "depois 2")])
        p = run_hook(r.path, session_id=SID, prompt="depois 2")
        c = ctx(p)
        il = intent_lines(c)
        check("intenção normal: propósito, passo N/M e nome do passo",
              "institucionalizar as quatro perguntas" in c
              and "Passo 2/4: escrever o doc" in c, c)
        check("intenção normal: há quantos turnos o cursor está parado",
              "(há 2 turnos)" in c, c)
        check("intenção normal: próximo passo", "Próximo: rodar advisors." in c, c)
        check("intenção normal: ensina a avançar o cursor",
              "Ao concluir o passo, rode `cepa-intent --step 3`." in c, c)
        check("intenção normal: não despeja o plano inteiro",
              "levantar o que existe" not in c and "decidir" not in c, c)
        check("intenção normal: teto de duas linhas", len(il) == 2, il)
        check("intenção normal: não pergunta sobre outra sessão", "outra sessão" not in c, c)


def test_intent_normal_one_turn_in_the_singular():
    with Repo() as r:
        write_intent(r)
        write_log(r, [("2026-10-16", "21:41:00", "depois 1")])
        c = ctx(run_hook(r.path, session_id=SID))
        check("intenção normal: '(há 1 turno)' no singular", "(há 1 turno)" in c, c)


def test_intent_cuts_long_purpose_and_step():
    with Repo() as r:
        write_intent(r, purpose="p" * 500, plan=["a" * 300, "b"], step=1)
        write_log(r, [])
        c = ctx(run_hook(r.path, session_id=SID))
        check("propósito longo é cortado no hook", "p" * 160 not in c and "p" * 150 in c, c)
        check("nome de passo longo é cortado no hook", "a" * 80 not in c and "a" * 70 in c, c)


def test_empty_intent_turn_prompt_and_partial_log():
    with Repo() as r:
        write_mode(r, "mode: exploration\n")
        register(r, SID, "2026-10-16T18:00:00+00:00")
        write_log(r, [("2026-10-16", "18:01:00", "primeiro do log")])
        c = ctx(run_hook(r.path, session_id=SID, prompt="segundo, o do turno"))
        check("log com 1 prompt + prompt do turno diferente: entram os dois, em ordem",
              '"primeiro do log" | "segundo, o do turno"' in c, c)
        c = ctx(run_hook(r.path, session_id=SID, prompt="primeiro do log"))
        check("prompt do turno já no log: não duplica",
              c.count("primeiro do log") == 1, c)
    with Repo() as r:
        write_mode(r, "mode: exploration\n")
        c = ctx(run_hook(r.path, session_id=SID, prompt=""))
        check("log vazio e prompt vazio: 'nenhum ainda'", "Primeiros prompts: nenhum ainda." in c, c)


def test_empty_intent_cut_at_120():
    with Repo() as r:
        write_mode(r, "mode: exploration\n")
        long_ = "".join(chr(97 + i % 26) for i in range(125))
        c = ctx(run_hook(r.path, session_id=SID, prompt=long_))
        check("prompt cortado em 120 caracteres (119 + …)",
              f'"{long_[:119]}…"' in c, c)
        short = "y" * 120
        c = ctx(run_hook(r.path, session_id=SID, prompt=short))
        check("prompt de exatos 120 caracteres não é cortado", f'"{short}"' in c, c)


def test_empty_intent_multiline_log_and_title():
    with Repo() as r:
        write_mode(r, "mode: exploration\n")
        register(r, SID, "2026-10-16T18:00:00+00:00")
        write_log(r, [("2026-10-16", "18:01:00", "linha um\n# meu título\nlinha dois")])
        c = ctx(run_hook(r.path, session_id=SID, prompt="linha um # meu título linha dois"))
        check("prompt de várias linhas vira uma, título markdown preservado",
              '"linha um # meu título linha dois"' in c and c.count("linha um") == 1, c)


def test_empty_intent_record_in_the_main_clone():
    """In a linked worktree, the log is the worktree's and the record is the main clone's."""
    with Repo() as r:
        wt = Path(r.tmp.name) / "wt"
        subprocess.run(["git", "worktree", "add", "-q", "--detach", str(wt)],
                       cwd=r.path, check=True)
        (wt / ".claude").mkdir()
        (wt / ".claude" / "session-mode").write_text("mode: exploration\n")
        register(r, SID, "2026-10-16T18:00:00+00:00")  # in the main clone
        (wt / ".claude" / "session-log.md").write_text(
            "# Session log\n\n## 2026-10-15\n\n### 10:00:00 UTC\n\nvelho\n\n"
            "## 2026-10-16\n\n### 18:01:00 UTC\n\nda sessão\n\n")
        # the turn's prompt is DIFFERENT: if the record is not found, the fallback
        # (today's prompts) sees nothing from the log, and only the turn's prompt remains
        c = ctx(run_hook(wt, session_id=SID, prompt="o do turno"))
        check("worktree ligada: acha o início no registro do clone principal",
              '"da sessão" | "o do turno"' in c and "velho" not in c, c)


def test_intent_same_session_tolerant():
    with Repo() as r:
        write_intent(r)
        c = ctx(run_hook(r.path))  # payload without session_id
        check("payload sem session_id: não acusa outra sessão",
              "Passo 2/4" in c and "outra sessão" not in c, c)
    with Repo() as r:
        write_intent(r, session_id="")
        c = ctx(run_hook(r.path, session_id=SID))
        check("arquivo sem session_id: não acusa outra sessão",
              "Passo 2/4" in c and "outra sessão" not in c, c)
    with Repo() as r:
        write_intent(r, session_id=SID)
        c = ctx(run_hook(r.path, session_id=SID[:8]))
        check("id gravado mais longo que o atual: mesma sessão por prefixo",
              "Passo 2/4" in c and "outra sessão" not in c, c)


def test_intent_other_session_details():
    with Repo() as r:
        write_intent(r, session_id="aaaaaaaa")
        c = ctx(run_hook(r.path, session_id=SID))
        check("outra sessão: data com hora (aberto_em)", "2026-10-16 18:30 UTC" in c, c)
        check("outra sessão: manda não tratar como atual", "Não a trate como a desta sessão" in c, c)
        check("outra sessão: mostra o propósito gravado",
              '"institucionalizar as quatro perguntas"' in c, c)
    with Repo() as r:
        write_intent(r, session_id="aaaaaaaa", opened_at="")
        c = ctx(run_hook(r.path, session_id=SID))
        check("outra sessão sem aberto_em: 'data desconhecida'", "data desconhecida" in c, c)


def test_intent_step_outside_the_plan_falls_to_1():
    for value in ("0", "6"):
        with Repo() as r:
            write_intent(r)
            f = r.path / ".claude" / "session-intent"
            f.write_text(f.read_text().replace("step: 2", f"step: {value}"))
            c = ctx(run_hook(r.path, session_id=SID))
            check(f"passo {value} com plano de 4: cai no passo 1", "Passo 1/4" in c, c)
    with Repo() as r:
        write_intent(r)
        f = r.path / ".claude" / "session-intent"
        f.write_text(f.read_text().replace("step: 2", "step: 5"))
        c = ctx(run_hook(r.path, session_id=SID))
        check("passo M+1 (5 com plano de 4) é plano cumprido, não passo 1",
              "Plano cumprido (4/4)" in c, c)


def test_intent_age_edges():
    with Repo() as r:
        write_intent(r, step_since="2026-10-16T21:40:00Z")
        write_log(r, [("2026-10-16", "21:39:59", "antes"),
                      ("2026-10-16", "21:40:00", "no mesmo segundo")])
        c = ctx(run_hook(r.path, session_id=SID))
        check("prompt no mesmo segundo do passo_desde conta", "(há 1 turno)" in c, c)
    with Repo() as r:
        write_intent(r, step_since="2026-10-16T21:40:00Z")
        write_log(r, [("2026-10-16", "21:39:00", "antes")])
        c = ctx(run_hook(r.path, session_id=SID))
        check("nenhum prompt depois do cursor: '(há 0 turnos)'", "(há 0 turnos)" in c, c)
    with Repo() as r:
        write_intent(r, step_since="2026-10-16T21:40:00")  # no timezone: read as UTC
        write_log(r, [("2026-10-16", "21:41:00", "depois")])
        c = ctx(run_hook(r.path, session_id=SID))
        check("passo_desde sem fuso é lido como UTC", "(há 1 turno)" in c, c)


def test_intent_plan_fulfilled_stopping_point():
    with Repo() as r:
        write_intent(r, step=5, by_when="q" * 400)
        c = ctx(run_hook(r.path, session_id=SID))
        check("plano cumprido: rótulo 'ponto de parada:'", "; ponto de parada: q" in c, c)
        check("plano cumprido: ponto de parada cortado em 160",
              "q" * 160 not in c and "q" * 159 + "…" in c, c)
    with Repo() as r:
        write_intent(r, step=5, by_when="")
        c = ctx(run_hook(r.path, session_id=SID))
        check("plano cumprido sem ponto de parada: sem o rótulo",
              "ponto de parada" not in c and "Plano cumprido (4/4). Próximo" in c, c)


def test_intent_penultimate_step_points_to_the_last():
    with Repo() as r:
        write_intent(r, step=3)
        c = ctx(run_hook(r.path, session_id=SID))
        check("penúltimo passo: próximo é o último passo, não o wrap-up",
              "Passo 3/4: rodar advisors" in c and "Próximo: decidir." in c
              and "wrap-up" not in c, c)


def test_intent_age_ignores_empty_log_entry():
    with Repo() as r:
        write_intent(r, step_since="2026-10-16T21:40:00Z")
        write_log(r, [("2026-10-16", "21:41:00", "   "),
                      ("2026-10-16", "21:42:00", "de verdade")])
        c = ctx(run_hook(r.path, session_id=SID))
        check("entrada vazia do log não conta como turno", "(há 1 turno)" in c, c)


def test_intent_last_step_points_to_wrap_up():
    with Repo() as r:
        write_intent(r, step=4)
        c = ctx(run_hook(r.path, session_id=SID))
        check("último passo: próximo é o wrap-up",
              "Passo 4/4: decidir" in c and "plano cumprido: hora de /common:wrap-up" in c, c)


def test_intent_plan_fulfilled():
    with Repo() as r:
        write_intent(r, step=5)
        c = ctx(run_hook(r.path, session_id=SID))
        il = intent_lines(c)
        check("plano cumprido: diz que cumpriu M/M e aponta wrap-up",
              "Plano cumprido (4/4)" in c and "/common:wrap-up" in c, c)
        check("plano cumprido: mostra o ponto de parada", "doc decidido" in c, c)
        check("plano cumprido: uma linha", len(il) == 1, il)


def test_intent_without_mode_is_still_injected():
    with Repo() as r:
        write_intent(r)
        c = ctx(run_hook(r.path, session_id=SID))
        check("intenção sem modo: injetada", "Passo 2/4" in c and "[modo]" not in c, c)


def test_intent_from_another_session_becomes_a_question():
    with Repo() as r:
        write_mode(r, "mode: exploration\n")
        write_intent(r, session_id="aaaaaaaa")
        p = run_hook(r.path, session_id=SID)
        c = ctx(p)
        il = intent_lines(c)
        check("outra sessão: diz que foi gravada em outra sessão, com a data",
              "outra sessão" in c and "2026-10-16" in c, c)
        check("outra sessão: pergunta continuo ou abro nova",
              "continuo ou abro nova" in c, c)
        check("outra sessão: diz como responder (continue / write)",
              "cepa-intent continue" in c and "--reason" in c, c)
        check("outra sessão: NÃO exibe o passo como atual", "Passo 2/4" not in c, c)
        check("outra sessão: teto de duas linhas", len(il) == 2, il)


def test_intent_continue_resolves_the_question():
    """The writer's `continuar` is what makes the D1 question stop coming back."""
    with Repo() as r:
        write_intent(r, session_id="aaaaaaaa")
        e = {**os.environ, "CLAUDE_CODE_SESSION_ID": SID}
        w = subprocess.run([sys.executable, str(REPO / "common" / "bin" / "cepa-intent"),
                            "continue"], cwd=r.path, env=e, capture_output=True, text=True)
        c = ctx(run_hook(r.path, session_id=SID))
        check("continuar: o hook volta a exibir a intenção como atual",
              w.returncode == 0 and "Passo 2/4" in c and "outra sessão" not in c,
              (w.stderr, c))


def test_intent_silent_in_cepa_until():
    with Repo() as r:
        write_mode(r, "mode: construction\n")
        write_intent(r, session_id="aaaaaaaa")
        c = ctx(run_hook(r.path, env={"CEPA_UNTIL_RUN": "1"}, session_id=SID))
        check("cepa-until: sem intenção no contexto", "[intenção]" not in c, c)
        check("cepa-until: o modo segue", "[modo]" in c, c)
    with Repo() as r:
        write_intent(r)
        p = run_hook(r.path, env={"CEPA_UNTIL_RUN": "1"}, session_id=SID)
        check("cepa-until sem modo: silêncio total", p.stdout.strip() == "", repr(p.stdout))


def test_corrupted_intent_does_not_break():
    with Repo() as r:
        write_mode(r, "mode: exploration\n")
        (r.path / ".claude" / "session-intent").write_text("::: lixo\n\x00passo: x\n")
        p = run_hook(r.path, session_id=SID)
        c = ctx(p)
        check("intenção corrompida: rc=0", p.returncode == 0, p.stderr)
        check("intenção corrompida: tratada como vazia",
              "ainda não tem intenção gravada" in c, c)
    with Repo() as r:
        write_intent(r, step_since="ontem")
        f = r.path / ".claude" / "session-intent"
        f.write_text(f.read_text().replace("step: 2", "step: abc"))
        p = run_hook(r.path, session_id=SID)
        c = ctx(p)
        check("passo e passo_desde inválidos: rc=0, cai no passo 1 sem idade",
              p.returncode == 0 and "Passo 1/4" in c and "(há" not in c, (p.stderr, c))


def test_intent_respects_kill_switch():
    with Repo() as r:
        write_intent(r)
        p = run_hook(r.path, env={"CEPA_MODO": "off"}, session_id=SID)
        check("CEPA_MODO=off: cala a intenção também", p.stdout.strip() == "", repr(p.stdout))


# --- help of the mode menu --------------------------------------------------
# The `cepa` menu listed the seven names and nothing else. Whoever does not remember what
# "reforma" covers chose by the name — and the mode, which is a boundary, became a label.
# The help shows the purpose of each mode read from _modes.py (single source), without
# opening the 307-line doc.

def test_help_non_interactive():
    """`cepa --modo ajuda` prints the purposes and does NOT start any session."""
    with Repo() as r:
        p = r.run("--mode", "help")
        output = p.stdout + p.stderr
        check("ajuda: rc=0", p.returncode == 0, str(p.returncode) + output)
        check("ajuda: não lança o claude", "CLAUDE_ARGS" not in p.stdout, p.stdout)
        check("ajuda: não grava modo", not r.mode_file.exists())
        check("ajuda: nomeia os sete modos",
              all(m in output for m in
                  ("exploration", "discovery", "design", "construction",
                   "refactor", "reflection", "documentation")), output)
        check("ajuda: diz o propósito, não só o nome",
              "without changing anything visible from outside" in output,
              output)


def _pty_run(repo, keyboard):
    """Runs cepa with a real terminal and types `keyboard` into it.

    `cepa` reads from /dev/tty, so a pipe is not enough: the process needs its
    own controlling terminal (setsid + TIOCSCTTY), otherwise /dev/tty would point
    to the terminal of whoever runs the tests.
    """
    import fcntl, pty, termios, time
    master, slave = pty.openpty()

    def ctty():
        os.setsid()
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)

    proc = subprocess.Popen(
        [str(CEPA), "--resume"], cwd=repo.path,
        env={**os.environ, "CLAUDE_WT_CLAUDE_BIN": str(repo.fake),
             "CEPA_PREFLIGHT": "off"},
        stdin=slave, stdout=slave, stderr=slave,
        preexec_fn=ctty, close_fds=True,
    )
    os.close(slave)
    for key in keyboard:
        time.sleep(0.4)
        os.write(master, key.encode())
    buf = b""
    end = time.time() + 20
    while time.time() < end:
        try:
            piece = os.read(master, 65536)
        except OSError:
            break
        if not piece:
            break
        buf += piece
        if proc.poll() is not None and b"CLAUDE_ARGS" in buf:
            break
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    os.close(master)
    return proc.returncode, buf.decode("utf-8", "replace")


def test_help_in_the_menu_and_re_presents():
    """In the menu, `?` shows the purposes and the menu comes back — it is not an invalid choice."""
    with Repo() as r:
        rc, output = _pty_run(r, ["?\n", "construction\n"])
        check("menu: oferece a ajuda", "?) help" in output, output)
        check("menu ?: mostra o propósito",
              "without changing anything visible from outside" in output,
              output)
        check("menu ?: não trata como modo desconhecido",
              "modo desconhecido" not in output, output)
        check("menu ?: pergunta de novo", output.count("mode? [") >= 2, output)
        check("menu ?: a escolha seguinte vale", rc == 0, str(rc) + output)
        body = r.mode_file.read_text() if r.mode_file.exists() else ""
        check("menu ?: grava o modo escolhido", "mode: construction" in body, body)


# --- old names (item interface-in-english) ----------------------------------
# The pt-BR names of the modes, flags and keys remain valid on READING;
# what `cepa` writes is always the new name.

def test_old_cepa_names():
    with Repo() as r:
        p = r.run("--modo", "construcao", "--resume")
        body = r.mode_file.read_text() if r.mode_file.exists() else ""
        check("antigo: `--modo construcao` sobe", p.returncode == 0, p.stderr)
        check("antigo: grava SÓ o nome novo (`mode: construction`, chaves novas)",
              "mode: construction" in body and "routine: null" in body and "budget: null" in body
              and "opened_at:" in body and "modo:" not in body and "orcamento" not in body
              and "aberto_em" not in body, body)
    with Repo() as r:
        p = r.run("--modo=reforma", "--orcamento", "só o módulo de auth")
        body = r.mode_file.read_text() if r.mode_file.exists() else ""
        check("antigo: `--modo=reforma --orcamento X` sobe como refactor",
              p.returncode == 0 and "mode: refactor" in body
              and 'budget: "só o módulo de auth"' in body, (p.stderr, body))
    with Repo() as r:
        p = r.run("--modo", "reforma")
        check("antigo: `--modo reforma` sem orçamento recusa", p.returncode == 2 and not r.mode_file.exists(),
              p.stderr)
    with Repo() as r:
        p = r.run("--mode=exploracao", "--resume")
        body = r.mode_file.read_text() if r.mode_file.exists() else ""
        check("antigo: `--mode exploracao` (nome antigo, flag nova) vira exploration",
              p.returncode == 0 and "mode: exploration" in body, (p.stderr, body))
    with Repo() as r:
        p = r.run("--modo", "ajuda")
        check("antigo: `--modo ajuda` ainda mostra os propósitos e não sobe",
              p.returncode == 0 and "exploration" in p.stdout + p.stderr and not r.mode_file.exists(),
              p.stderr)


def test_hook_reads_old_session_mode_and_intent():
    with Repo() as r:
        write_mode(r, "modo: construcao\nrotina: null\norcamento: null\naberto_em: 2026-08-18T19:40:00Z\n")
        (r.path / ".claude" / "session-intent").write_text(
            'proposito: "institucionalizar as quatro perguntas"\npara_quando: "doc decidido"\n'
            'plano:\n  - "levantar"\n  - "escrever"\n  - "decidir"\npasso: 2\n'
            f'passo_desde: "2026-10-16T21:40:00Z"\nsession_id: "{SID[:8]}"\nbranch: "main"\n'
            'aberto_em: "2026-10-16T18:30:00Z"\n')
        c = ctx(run_hook(r.path, session_id=SID))
        check("antigo: `modo: construcao` é lido como construction no hook",
              "**construction**" in c and "completion-auditor COMPLETE" in c, c)
        check("antigo: session-intent com chaves pt-BR é lido (Passo 2/3, próximo, comando novo)",
              "Passo 2/3: escrever" in c and "Próximo: decidir" in c and "cepa-intent --step 3" in c, c)
    with Repo() as r:
        write_mode(r, 'modo: reforma\norcamento: "só o módulo de auth"\n')
        c = ctx(run_hook(r.path, session_id=SID))
        check("antigo: `orcamento:` aparece como orçamento no hook",
              "**refactor**" in c and "só o módulo de auth" in c, c)


CEPA_MODES = REPO / "common" / "bin" / "cepa-modes"


def fake_home(tmp, plugins=("discovery",), name="home"):
    """A throwaway HOME whose Claude install has `plugins` installed AND enabled,
    seen the way cepa-doctor sees it (known_marketplaces + cache + enabledPlugins).
    The manifests are read from this very repo; the real machine's plugins never count."""
    home = Path(tmp) / name
    claude = home / ".claude"
    (claude / "plugins").mkdir(parents=True)
    (claude / "plugins" / "known_marketplaces.json").write_text(
        json.dumps({"cepa": {"installLocation": str(REPO)}}))
    for plugin in plugins:
        (claude / "plugins" / "cache" / "cepa" / plugin / "99.0.0").mkdir(parents=True)
    (claude / "settings.json").write_text(
        json.dumps({"enabledPlugins": {f"{n}@cepa": True for n in plugins}}))
    return home


def run_menu(repo, mode, home):
    env = {**os.environ, "HOME": str(home)}
    return subprocess.run([sys.executable, str(CEPA_MODES), "--menu", mode, "--no-color"],
                          cwd=repo.path, env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=30)


def test_menu_discovery():
    """CS-1: `cepa-modes --menu discovery` prints the numbered menu from `actions`."""
    print("menu: discovery, no board-flow.yaml, discovery plugin installed")
    with Repo() as r:
        p = run_menu(r, "discovery", fake_home(r.tmp.name))
        check("--menu discovery rc 0", p.returncode == 0, p.stderr[-200:])
        out = p.stdout
        want = ["1) Detail an idea until it becomes a build-ready specification",
                "/common:spec", "/common:spec --continuar", "/common:epic",
                "/discovery:capture", "/common:queue"]
        pos, ordered = 0, True
        for w in want:
            i = out.find(w, pos)
            if i < 0:
                ordered = False
                break
            pos = i + len(w) if w.startswith("1)") else i
        check("menu has the lines in order", ordered, out)
        check("board-flow action hidden without board-flow.yaml", "/board-flow:" not in out, out)
        bare = run_menu(r, "discovery", fake_home(r.tmp.name, plugins=(), name="bare"))
        check("capture hidden without the discovery plugin",
              "/discovery:capture" not in bare.stdout, bare.stdout)


def test_menu_empty_and_unknown():
    with Repo() as r:
        home = fake_home(r.tmp.name)
        p = run_menu(r, "design", home)
        check("--menu design: rc 0 and empty", p.returncode == 0 and p.stdout == "", repr(p.stdout))
        q = run_menu(r, "nope", home)
        check("--menu unknown mode: rc 2", q.returncode == 2)


def set_topology(repo, topology, board_flow=False):
    claude = Path(repo.path) / ".claude"
    claude.mkdir(exist_ok=True)
    (claude / "topology").write_text(topology + "\n")
    if board_flow:
        (Path(repo.path) / "board-flow.yaml").write_text("project: X\n")


def test_menu_construction_build_solo_without_board_flow():
    """CS-2: no board-flow.yaml hides every board-flow line; topology picks the build-solo variants."""
    print("menu: construction, build-solo, no board-flow.yaml")
    with Repo() as r:
        set_topology(r, "build-solo")
        p = run_menu(r, "construction", fake_home(r.tmp.name))
        out = p.stdout
        check("--menu construction rc 0", p.returncode == 0, p.stderr[-200:])
        check("no /board-flow: line", "/board-flow:" not in out, out)
        check("build-solo fix variant shows", "/build-solo:reproduce-fix-verify" in out, out)
        check("build-solo build variant shows", "/build-solo:plan-build-validate" in out, out)
        check("red-test action without command shows",
              "Write the red test of the criterion (no command yet)" in out, out)
        check("build-hex variants hidden", "/build-hex:" not in out, out)


def test_menu_construction_with_board_flow():
    """CS-2: with board-flow.yaml the menu is capped at 5, one line per label, sequences joined by ', then '."""
    print("menu: construction, build-solo, with board-flow.yaml")
    with Repo() as r:
        set_topology(r, "build-solo", board_flow=True)
        p = run_menu(r, "construction", fake_home(r.tmp.name))
        out = p.stdout
        lines = [l for l in out.splitlines() if l.strip()]
        check("exactly 5 numbered actions",
              len(lines) == 5 and all(l.startswith(f"{i}) ") for i, l in enumerate(lines, 1)), out)
        check("/board-flow:execute shows", "/board-flow:execute" in out, out)
        check("'Fix a bug' appears exactly once", out.count("Fix a bug") == 1, out)
        check("sequence joined by ', then '",
              "/board-flow:capture Bug: <description>, then /board-flow:fix <created key>" in out, out)
        check("later variant of the same label dropped", "/build-solo:reproduce-fix-verify" not in out, out)
        check("prove-drain cut by the cap", "/board-flow:prove-drain" not in out, out)


def test_need_met_unknown_type_is_not_met():
    """An unknown requirement type never lets an action show."""
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("cepa_modes_under_test", str(CEPA_MODES))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    with tempfile.TemporaryDirectory() as d:
        check("unknown type `bogus:x` is not met", mod.need_met("bogus:x", d, set()) is False)
        check("known type still works (plugin)", mod.need_met("plugin:x", d, {"x"}) is True)


# A fake claude that records each argument it got, one JSON list per call,
# so a multi-line prompt survives intact (FAKE_CLAUDE joins them with spaces).
RECORDING_CLAUDE = (
    '#!/bin/sh\n'
    'python3 -c \'import json,os,sys; '
    'open(os.environ["FAKE_ARGS_FILE"],"a").write(json.dumps(sys.argv[1:])+"\\n")\' "$@"\n'
)


def recorded_args(repo, *cepa_args, env=None):
    """Runs cepa with the recording claude; returns (proc, owner args of the last call)."""
    fake = Path(repo.tmp.name) / "recclaude"
    fake.write_text(RECORDING_CLAUDE)
    fake.chmod(0o755)
    out = Path(repo.tmp.name) / "args.jsonl"
    if out.exists():
        out.unlink()
    home = Path(repo.tmp.name) / "rechome"
    if not home.exists():
        fake_home(repo.tmp.name, name="rechome")
    e = {"CLAUDE_WT_CLAUDE_BIN": str(fake), "FAKE_ARGS_FILE": str(out), "HOME": str(home),
         "CEPA_ENCADEAR": "off"}
    e.update(env or {})
    for k in ("CEPA_UNTIL_RUN", "CEPA_MENU"):
        if k not in e:
            e[k] = ""
    p = repo.run(*cepa_args, env=e)
    lines = out.read_text().splitlines() if out.exists() else []
    args = json.loads(lines[-1]) if lines else None
    if args is not None:
        args = [a for a in args if a.split("=")[0] not in CEPA_FLAGS]
    return p, args


def test_opening_prompt_carries_the_menu():
    """CS-3: `cepa --mode discovery` with no request sends the menu as the opening prompt;
    with a request, only the owner's args reach claude."""
    print("cepa --mode: opening prompt with the menu")
    with Repo() as r:
        p, args = recorded_args(r, "--mode", "discovery")
        check("no request: claude was called", args is not None, p.stderr[-300:])
        opening = (args or [None])[-1] or ""
        check("no request: exactly one prompt argument", args is not None and len(args) == 1, args)
        check("no request: prompt starts with [menu do modo]",
              opening.startswith("[menu do modo]"), repr(opening[:200]))
        check("no request: prompt carries /common:spec", "/common:spec" in opening, repr(opening))
        check("no request: prompt ends with the reply line",
              opening.rstrip().endswith(
                  "Reply with the number, the command, or write what you want to do."),
              repr(opening[-200:]))
        check("no request: prompt carries the numbered menu",
              "1) Detail an idea until it becomes a build-ready specification" in opening,
              repr(opening))

        p, args = recorded_args(r, "--mode", "discovery", "arruma o teste X")
        check("with request: only the owner's args", args == ["arruma o teste X"], args)

        for extra, label in ((["--resume"], "--resume"), (["-c"], "-c"),
                             (["--continue"], "--continue"), (["-p", "x"], "-p"),
                             (["--print"], "--print"), (["-r"], "-r"),
                             (["--resume=abc"], "--resume=abc")):
            p, args = recorded_args(r, "--mode", "discovery", *extra)
            check(f"{label}: no opening prompt", args == extra, args)

        p, args = recorded_args(r, "--mode", "design")
        check("mode with an empty menu: no opening prompt", args == [], args)
        p, args = recorded_args(r, "--mode", "discovery", env={"CEPA_MENU": "off"})
        check("CEPA_MENU=off: no opening prompt", args == [], args)
        p, args = recorded_args(r, "--mode", "discovery", env={"CEPA_UNTIL_RUN": "1"})
        check("inside cepa-until: no opening prompt", args == [], args)
        p, args = recorded_args(r, "--mode", "discovery", env={"CEPA_MODO": "off"})
        check("CEPA_MODO=off: no opening prompt", args == [], args)

        p, args = recorded_args(r, "--mode", "discovery", "--model=opus")
        check("a flag=value alone still gets the menu",
              args is not None and len(args) == 2 and args[0] == "--model=opus"
              and args[1].startswith("[menu do modo]"), args)

        p, args = recorded_args(r, "--mode", "discovery", "--model", "opus")
        check("a flag with a separate value counts as a request (safe side)",
              args == ["--model", "opus"], args)

        p, args = recorded_args(r, "--mode", "discovery", "--prompt", "nope-missing")
        check("system prompt error still exits 2 (no launch)", p.returncode == 2 and args is None,
              (p.returncode, args))


def opening_turn(repo, mode, home):
    """The real opening prompt `cepa --mode <mode>` sends, then the hook's context for it."""
    p, args = recorded_args(repo, "--mode", mode)
    opening = (args or [""])[-1]
    check(f"{mode}: launcher sent an opening prompt", opening.startswith("[menu do modo]"),
          repr(opening[:200]))
    h = run_hook(repo.path, env={"HOME": str(home)}, prompt=opening, session_id="s-open")
    check(f"{mode}: hook rc 0", h.returncode == 0, h.stderr)
    return ctx(h)


def test_hook_opening_turn_carries_the_menu_rules():
    """CS-5: on the opening turn the hook tells the agent how to show the menu and how to
    treat the next reply (number/command fires, ask first, no command = conversation,
    free text = normal request)."""
    print("hook: opening turn of the mode menu")
    with Repo() as r:
        home = fake_home(r.tmp.name, name="hookhome")
        c = opening_turn(r, "discovery", home)
        check("display rule: translate the phrases",
              "traduzid" in c and "língua do dono" in c, c)
        check("display rule: keep order, numbering and commands",
              "ordem" in c and "numeração" in c and "comandos" in c, c)
        check("action 1 asks its one-line question first",
              "Ação 1" in c and '"What is the idea?"' in c and "/common:spec <the idea>" in c, c)
        check("number or command fires the action", "número ou comando" in c, c)
        check("free-text rule", "texto livre" in c and "pedido normal" in c, c)
        check("discovery has no sequence rule", "chave de um card" not in c, c)
        check("the number is bound to its own action (1 = the idea, 2 = the slug)",
              'Ação 1 pede argumento: antes de rodar, pergunte em uma linha "What is the idea?"' in c
              and 'Ação 2 pede argumento: antes de rodar, pergunte em uma linha '
                  '"Which specification (slug)?"' in c, c)

        set_topology(r, "build-solo", board_flow=True)
        c = opening_turn(r, "construction", home)
        check("Fix a bug: a card key runs only /board-flow:fix",
              "chave de um card" in c and "só `/board-flow:fix <created key>`" in c, c)
        check("Fix a bug: a description runs capture then fix on the created key",
              "`/board-flow:capture Bug: <description>`" in c and "chave criada" in c, c)
        check("Fix a bug is action 4",
              'Ação 4 pede argumento: antes de rodar, pergunte em uma linha '
              '"What is the card key or the bug description?"' in c, c)

        (Path(r.path) / "board-flow.yaml").unlink()
        c = opening_turn(r, "construction", home)
        check("no-command action is led in conversation",
              "sem comando" in c and "conversa" in c, c)

        h = run_hook(r.path, env={"HOME": str(home)}, prompt="quero especificar X",
                     session_id="s-open")
        check("an ordinary turn carries no menu rule", "[menu]" not in ctx(h), ctx(h))
        h = run_hook(r.path, env={"HOME": str(home)},
                     prompt="olha isso: [menu do modo] discovery", session_id="s-open")
        check("marker mid-prompt is not the opening turn", "[menu]" not in ctx(h), ctx(h))
        h = run_hook(r.path, env={"HOME": str(home)},
                     prompt="abcdefghijklmn discovery\nveja: [menu do modo]", session_id="s-open")
        check("marker mid-prompt with a valid mode where the name would be: still not",
              "[menu]" not in ctx(h), ctx(h))
        h = run_hook(r.path, env={"HOME": str(home)}, prompt="[menu do modo] design\n\n",
                     session_id="s-open")
        check("mode with an empty menu: no menu rule", "[menu]" not in ctx(h), ctx(h))
        h = run_hook(r.path, env={"HOME": str(home)}, prompt="[menu do modo] nope\n\n",
                     session_id="s-open")
        check("unknown mode in the marker: hook still rc 0, no menu rule",
              h.returncode == 0 and "[menu]" not in ctx(h), (h.returncode, ctx(h)))


def main():
    print("test_cepa_mode")
    for fn in (test_menu_discovery, test_menu_empty_and_unknown,
               test_opening_prompt_carries_the_menu,
               test_hook_opening_turn_carries_the_menu_rules,
               test_menu_construction_build_solo_without_board_flow,
               test_menu_construction_with_board_flow,
               test_need_met_unknown_type_is_not_met, test_valid_mode, test_invalid_mode, test_without_mode_without_tty,
               test_old_cepa_names, test_hook_reads_old_session_mode_and_intent,
               test_kill_switch, test_overhaul_budget,
               test_help_non_interactive, test_help_in_the_menu_and_re_presents,
               test_hook_injects_mode_and_exit, test_hook_overhaul_shows_budget,
               test_hook_silent_without_mode, test_hook_respects_kill_switch,
               test_hook_never_breaks_the_turn,
               test_empty_intent_brings_the_first_prompts,
               test_empty_intent_first_turn_uses_the_current_prompt,
               test_empty_intent_without_record_falls_back_to_today,
               test_empty_intent_without_mode_is_silent,
               test_intent_normal_step_age_next,
               test_intent_normal_one_turn_in_the_singular,
               test_intent_cuts_long_purpose_and_step,
               test_empty_intent_turn_prompt_and_partial_log,
               test_empty_intent_cut_at_120, test_empty_intent_multiline_log_and_title,
               test_empty_intent_record_in_the_main_clone,
               test_intent_same_session_tolerant, test_intent_other_session_details,
               test_intent_step_outside_the_plan_falls_to_1, test_intent_age_edges,
               test_intent_plan_fulfilled_stopping_point,
               test_intent_penultimate_step_points_to_the_last,
               test_intent_age_ignores_empty_log_entry,
               test_intent_last_step_points_to_wrap_up, test_intent_plan_fulfilled,
               test_intent_without_mode_is_still_injected,
               test_intent_from_another_session_becomes_a_question,
               test_intent_continue_resolves_the_question,
               test_intent_silent_in_cepa_until, test_corrupted_intent_does_not_break,
               test_intent_respects_kill_switch):
        fn()
    if failures:
        print(f"\n{len(failures)} falha(s): {', '.join(failures)}")
        return 1
    print("\ntudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
