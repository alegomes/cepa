#!/usr/bin/env python3
"""Contract test: /maestro:run forks the daughters ALWAYS in the tab of its own command,
never in whichever tab is in focus at the moment of the spawn.

## The defect (reflection 2026-08-24, WEGO-paralelo wave, wego-acesso-backend)

The spawn step did not say which tab to fork in. Without `--tab`/`--workspace`, `herdr
agent start` split whichever tab was in FOCUS at the instant of the fork —
and between the intake and the spawn minutes pass, plenty of time for the owner to click
another tab. In the real wave's `herdr-server.log`: the `/maestro:run` tab
(`wJ:t1`) received no focus at all between 13:01 and 13:05; the tab
`portais_vs_operadoras` (`wJ:tC`) received focus at 13:01:01 and stayed that way; the
five `pane.spawn.start` of the wave (13:04:45–13:04:46) show the width halving
at each one (173 → 87 → 44 → 22 → 11 columns) — the signature of
five successive splits of the SAME wrong tab.

## Fact verified live against the installed herdr 0.9.1 (no longer the BACKLOG
## sketch — `herdr agent start` no longer accepts `--cwd`/`--tab`/`--workspace`
## nor a command after `--`; it only starts an agent in an already existing pane)

`herdr pane split <PANE_ID> --direction right ... --no-focus` creates the new pane
IN THE TAB of the pointed pane, regardless of which tab is in focus — so the
fix is to capture the home pane (`herdr pane current`) at the START of the routine,
persist it on disk (`maestro-wave-state set-home`) and split that pane by
explicit ID in the spawn step, never the current focus.

## What this test holds (mechanical, in the mold of tests/test_worktree_create_verify.py)

- `run.md` captures the home pane (`herdr pane current`) BEFORE the intake gate
  (`cepa-dor`) in the text — capturing after is capturing the wrong value;
- the spawn step uses `herdr pane split` with an explicit pane id and
  `--no-focus`, followed by `herdr pane run` — and NO longer contains the
  obsolete recipe `herdr agent start <PROG>-<slice> --cwd`;
- there is a fallback for a dead home pane: `herdr tab create` with `--label`,
  fired when the split returns `pane_not_found`;
- `set-home` is persisted in `run.md` and read in `resume.md`;
- a real roundtrip of `maestro-wave-state`: `init` + `set-home` + `get` store and
  return pane/tab/workspace, and a wave-state without `home` (old format)
  still loads.

Run: python3 tests/test_maestro_run_tab.py
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
RUN = REPO / "maestro" / "commands" / "run.md"
RESUME = REPO / "maestro" / "commands" / "resume.md"
WAVE_STATE = REPO / "maestro" / "bin" / "maestro-wave-state"

FAILURES = []


def check(label, cond, extra=""):
    if cond:
        print(f"✓ {label}")
    else:
        print(f"✗ {label}" + (f" — {extra}" if extra else ""))
        FAILURES.append(label)


def flat(txt):
    """Collapsed whitespace: the checks match a PHRASE, not a line break —
    otherwise an innocent re-wrap becomes a false red and teaches loosening the
    guard, which is how a mechanical guard becomes decoration.
    """
    return " ".join(txt.split())


PLAN = """\
schema_version: 1
program: t
waves:
  - id: 1
    slices: [S1]
    status: pending
slices:
  S1:
    demanda: A
    surface: ["src/a.py"]
"""


def sh(argv):
    return subprocess.run([sys.executable] + [str(x) for x in argv],
                          capture_output=True, text=True)


def test_capture_before_the_intake():
    run = RUN.read_text(encoding="utf-8")
    i_capture = run.find("herdr pane current")
    i_intake = run.find("common/bin/cepa-dor")
    check("run.md chama `herdr pane current`", i_capture != -1)
    check("run.md roda o intake gate (`cepa-dor`)", i_intake != -1)
    check("a captura do pane-lar vem ANTES do intake gate no texto",
          i_capture != -1 and i_intake != -1 and i_capture < i_intake,
          f"captura em {i_capture}, intake em {i_intake}")
    fr = flat(run)
    check("run.md explica por que captura no início, não no fork "
          "(minutos passam / foco muda)",
          "minutes go by" in fr and "the focus changes" in fr)
    check("run.md cita a evidência WEGO-paralelo (largura caindo pela metade)",
          "2026-08-24" in fr and ("pela metade" in fr or "173" in fr))
    check("captura sem herdr → aba nova previsível (`herdr tab create ... "
          "--label <PROG>`), nunca o foco corrente",
          "herdr tab create" in fr and "--label <PROG>" in fr)


def test_spawn_uses_split_by_home_pane():
    run = RUN.read_text(encoding="utf-8")
    fr = flat(run)
    check("spawn usa `herdr pane split`", "herdr pane split" in fr)
    check("o split leva `--no-focus`", "--no-focus" in fr)
    check("o split é seguido de `herdr pane run` (envio do wrapper)",
          "herdr pane run" in fr)
    check("run.md NÃO tem mais a receita obsoleta "
          "`herdr agent start <PROG>-<slice> --cwd`",
          "herdr agent start <PROG>-<slice> --cwd" not in fr)
    check("run.md nomeia que `herdr agent start` 0.9 perdeu --cwd/--tab/"
          "--workspace/comando (motivo da mudança de receita)",
          "0.9" in fr and "agent start" in fr)
    check("prosa proíbe dividir o pane em foco / omitir o id do pane-lar",
          "Never split the pane that is in focus" in fr)
    check("prosa nomeia que `--no-focus` não escolhe onde o pane nasce",
          "it does not choose where" in fr)
    # the normative wrapper (pipefail + PIPESTATUS + MAESTRO-EXIT) must
    # survive the swap of recipe — it is what the other tests pin.
    check("o wrapper normativo continua presente (pipefail)",
          "pipefail" in fr)
    check("o wrapper normativo continua marcando MAESTRO-EXIT",
          "MAESTRO-EXIT" in fr)
    check("o wrapper normativo continua exigindo --strict-mcp-config",
          "--strict-mcp-config" in fr)


def _extract_herdr_pane_run(run_text):
    """Finds the code block of step 6c and returns the text from
    `herdr pane run <new-pane>` to the end of the block (the whole `bash -c '...'`,
    with the original line continuations). Fails (returns None) if the
    command no longer exists there — a sign that the step changed shape and this
    test needs to be re-anchored.
    """
    for block in re.findall(r"```\n(.*?)```", run_text, re.S):
        if "herdr pane run <novo-pane>" in block:
            i = block.find("herdr pane run <novo-pane>")
            return block[i:].rstrip("\n")
    return None


def test_maestro_exit_does_not_expand_in_the_maestro_shell():
    """Real defect: `herdr pane run <new-pane> "bash -c '...'"` is typed
    in a double-quoted shell of the maestro's OWN session. Without escaping
    `${PIPESTATUS[0]}`, `$ec` and `$MAESTRO_LINGER` with `\$`, those three
    variables expand HERE (empty, since they do not exist in this shell) BEFORE the
    text reaches the daughter pane — the `resultado.txt` would get `MAESTRO-EXIT:` without a
    code and `sleep ""`, silently breaking the file synchronization.

    Mechanical check: swaps `herdr pane run <new-pane>` for `printf '%s'` and
    runs the rest of the command (the original quotes and escapes, intact) in a real
    bash, without `MAESTRO_LINGER`/`ec` in the environment — that reproduces
    EXACTLY what the maestro's shell would produce as the single argument of
    `herdr pane run`, that is, the text the daughter pane would receive. If the three
    variables still appear LITERALLY (unexpanded) in the output, the recipe
    is correct; if they vanished/became empty, it expanded too early.
    """
    run = RUN.read_text(encoding="utf-8")
    cmd = _extract_herdr_pane_run(run)
    check("o passo 6c ainda tem o `herdr pane run <novo-pane> ...` (reancore "
          "este teste antes de seguir se mudou de forma)", bool(cmd))
    if not cmd:
        return

    script = cmd.replace("herdr pane run <novo-pane>", "printf '%s'", 1)
    env = dict(os.environ)
    env.pop("MAESTRO_LINGER", None)
    env.pop("ec", None)
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                       env=env)
    check("o comando simulado roda sem erro de shell",
          r.returncode == 0, r.stderr)
    out = r.stdout
    check("o texto que chegaria à pane filha ainda tem `${PIPESTATUS[0]}` "
          "literal (não expandido no shell do maestro)",
          "${PIPESTATUS[0]}" in out, out)
    check("...e `$ec` literal",
          "$ec" in out, out)
    check("...e `$MAESTRO_LINGER` literal",
          "$MAESTRO_LINGER" in out, out)
    check("run.md explica por que o `\\$` está ali (não é sujeira de escape)",
          "deliberate" in flat(run) and "not escaping debris" in flat(run))


def test_fallback_dead_home_pane():
    fr = flat(RUN.read_text(encoding="utf-8"))
    check("existe fallback para pane-lar morto (`pane_not_found`)",
          "pane_not_found" in fr)
    check("o fallback usa `herdr tab create` com `--label`",
          "herdr tab create" in fr and "--label <PROG>" in fr)
    check("o fallback atualiza o pane-lar com `set-home` para as slices seguintes",
          "set-home" in fr)


def test_set_home_persisted_and_read():
    fr_run = flat(RUN.read_text(encoding="utf-8"))
    fr_resume = flat(RESUME.read_text(encoding="utf-8"))
    check("run.md persiste com `maestro-wave-state set-home`",
          "maestro-wave-state set-home" in fr_run
          or "wave-state set-home" in fr_run)
    check("resume.md lê o pane-lar do wave-state (`home.pane`) para re-spawn",
          "home.pane" in fr_resume or "home" in fr_resume)
    check("resume.md confere liveness por `herdr pane get`, não por "
          "`herdr agent get` (removido do herdr 0.9)",
          "herdr pane get" in fr_resume and "herdr agent get" not in fr_resume)


def test_wave_state_roundtrip(tmp):
    pd = Path(tmp) / "prog"
    pd.mkdir()
    plan = pd / "plan.yaml"
    plan.write_text(PLAN)

    r = sh([WAVE_STATE, "init", pd, "--plan", plan, "--wave", "1"])
    check("wave-state init roda ok", r.returncode == 0, r.stderr)

    r = sh([WAVE_STATE, "set-home", pd,
            "--pane", "w9:p1", "--tab", "w9:t1", "--workspace", "w9"])
    check("set-home roda ok", r.returncode == 0, r.stderr)

    r = sh([WAVE_STATE, "get", pd, "--json"])
    ws = json.loads(r.stdout)
    check("get expõe home.pane/tab/workspace gravados",
          ws.get("home") == {"pane": "w9:p1", "tab": "w9:t1", "workspace": "w9"},
          ws.get("home"))

    # old wave-state, without the `home` key, still loads (compatible
    # init — set-home is opt-in, not required for the format to exist).
    old = yaml.safe_load(plan.read_text()) and None  # noop, only for the linter
    ws_without_home = {k: v for k, v in ws.items() if k != "home"}
    (pd / "wave-state.yaml").write_text(
        yaml.safe_dump(ws_without_home, allow_unicode=True, sort_keys=False))
    r = sh([WAVE_STATE, "get", pd, "--json"])
    check("wave-state sem `home` (formato antigo) ainda carrega",
          r.returncode == 0 and "home" not in json.loads(r.stdout), r.stdout)


def main():
    test_capture_before_the_intake()
    test_spawn_uses_split_by_home_pane()
    test_maestro_exit_does_not_expand_in_the_maestro_shell()
    test_fallback_dead_home_pane()
    test_set_home_persisted_and_read()
    with tempfile.TemporaryDirectory() as tmp:
        test_wave_state_roundtrip(tmp)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
