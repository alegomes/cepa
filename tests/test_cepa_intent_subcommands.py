#!/usr/bin/env python3
"""`cepa intent` says the action by subcommand (CS-7 of reforma-de-nomes).

No external dependency: run with `python3 tests/test_cepa_intent_subcommands.py`.
Exits with code != 0 if anything fails.

What it proves, each against the real CLI in a temporary git repo:
  * `cepa intent step N` does what `--step N` does (cursor, refusals, telemetry);
  * `cepa intent edit --purpose/--plan` does what the action-less flags did, and
    `edit` with neither is a usage error;
  * `cepa intent <action> --help` / `<action> help` prints the help of THAT action
    only, for every action, with only the options that apply to it;
  * the flag forms keep working, and the plan-item guard knows the new names.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from _isolated_telemetry import isolate
isolate()

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "common" / "bin" / "cepa-intent"
LAUNCHER = REPO / "common" / "bin" / "cepa"
sys.path.insert(0, str(REPO / "common" / "hooks"))
import _modes as M  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


TMP = Path(tempfile.mkdtemp(prefix="cepa-intent-sub-test-"))
TEL = TMP / "tel"
ENV = {**os.environ, "CEPA_TELEMETRY_DIR": str(TEL), "CLAUDE_CODE_SESSION_ID": "sess-1",
       "NO_COLOR": "1"}


def new_repo(name):
    r = TMP / name
    r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
    p = cepa(r, "write", "--purpose", "entregar o doc", "--by-when", "hoje",
             "--plan", "levantar", "escrever", "decidir")
    assert p.returncode == 0, p.stderr
    return r


def cepa(repo, *args):
    return subprocess.run([sys.executable, str(BIN), *args], cwd=repo, env=ENV,
                          capture_output=True, text=True)


def intent_file(repo):
    return (repo / ".claude" / "session-intent").read_text()


def events(name):
    out = []
    for f in sorted(TEL.glob("events-*.jsonl")):
        out += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return [e for e in out if e["event"] == name]


# --- 1. `step N` -------------------------------------------------------------
r = new_repo("step")
p = cepa(r, "step", "3")
d = M.read_intent(r)
check("`step 3` sai 0 e move o cursor para o passo 3", p.returncode == 0 and d["step"] == 3,
      p.stderr + str(d.get("step")))
check("`step 3` imprime o resumo do passo 3", p.stdout.startswith("passo 3/3"), p.stdout)
ev = events("intent.cursor_advanced")
check("`step 3` emite intent.cursor_advanced de=1 para=3",
      len(ev) == 1 and ev[0]["de"] == 1 and ev[0]["para"] == 3 and ev[0]["passos"] == 3, ev)

p = cepa(r, "step", "4")
check("`step 4` (M+1) = plano cumprido",
      p.returncode == 0 and p.stdout.startswith("plano cumprido 3/3"), p.stdout + p.stderr)
before = intent_file(r)
for bad in ("0", "5", "abc"):
    p = cepa(r, "step", bad)
    check(f"`step {bad}` recusa com 2 e não escreve",
          p.returncode == 2 and intent_file(r) == before, p.stdout + p.stderr)
p = cepa(r, "step")
check("`step` sem número recusa com 2", p.returncode == 2, p.stderr)
p = cepa(r, "step", "2", "--purpose", "x", "--reason", "y")
check("`step 2 --purpose` recusa com 2 (como --step)", p.returncode == 2
      and intent_file(r) == before, p.stderr)
p = cepa(r, "step", "2", "--step", "3")
check("`step 2 --step 3` recusa com 2", p.returncode == 2, p.stderr)

# same result as the flag form, on a twin repo
ra, rb = new_repo("twin-a"), new_repo("twin-b")
pa, pb = cepa(ra, "step", "2"), cepa(rb, "--step", "2")
check("`step 2` e `--step 2` imprimem o mesmo", pa.stdout == pb.stdout and pa.returncode == pb.returncode)
check("a flag `--step 3` segue aceita", cepa(rb, "--step", "3").returncode == 0
      and M.read_intent(rb)["step"] == 3)
check("o apelido `--passo 1` segue aceito", cepa(rb, "--passo", "1").returncode == 0
      and M.read_intent(rb)["step"] == 1)
rn = TMP / "no-intent"
rn.mkdir()
subprocess.run(["git", "init", "-q", "-b", "main", str(rn)], check=True)
check("`step 2` sem intenção sai 3 (como --step)", cepa(rn, "step", "2").returncode == 3)

# --- 3. `edit` ---------------------------------------------------------------
r = new_repo("edit")
p = cepa(r, "edit", "--purpose", "novo propósito", "--reason", "o dono reformulou")
d = M.read_intent(r)
check("`edit --purpose --reason` troca o propósito",
      p.returncode == 0 and d["purpose"] == "novo propósito", p.stderr)
check("`edit --purpose` guarda o anterior no histórico",
      d["history"][-1]["purpose"] == "entregar o doc"
      and d["history"][-1]["change_reason"] == "o dono reformulou", d["history"])
before = intent_file(r)
p = cepa(r, "edit", "--purpose", "outro")
check("`edit --purpose` sem --reason recusa com 2 e não escreve",
      p.returncode == 2 and intent_file(r) == before, p.stderr)
p = cepa(r, "edit", "--plan", "a", "b", "--reason", "encolheu")
d = M.read_intent(r)
check("`edit --plan a b` troca o plano e volta ao passo 1",
      p.returncode == 0 and d["plan"] == ["a", "b"] and d["step"] == 1, p.stderr)
check("`edit --plan` guarda o plano anterior",
      d["history"][-1]["previous_plan"] == "levantar | escrever | decidir"
      and d["history"][-1]["change_reason"] == "encolheu", d["history"])
p = cepa(r, "edit", "--plan", "c")
check("`edit --plan c` sem --reason funciona (motivo padrão)",
      p.returncode == 0 and M.read_intent(r)["plan"] == ["c"], p.stderr)
before = intent_file(r)
p = cepa(r, "edit")
check("`edit` sem --purpose nem --plan é erro de uso (2)",
      p.returncode == 2 and intent_file(r) == before, p.stdout + p.stderr)
p = cepa(r, "edit", "--step", "1")
check("`edit --step 1` recusa com 2", p.returncode == 2, p.stderr)
check("`edit` com plano com ':' recusa com 2", cepa(r, "edit", "--plan", "a:b").returncode == 2)
check("`edit` sem intenção sai 3", cepa(rn, "edit", "--plan", "a").returncode == 3)
ev = [e for e in events("intent.written") if e.get("acao") in ("proposito", "plano")]
check("`edit` emite intent.written (proposito e plano)",
      {e["acao"] for e in ev} == {"proposito", "plano"}, ev)

# the action-less flags still do the same
r = new_repo("flags")
check("`--purpose X --reason Y` sem ação segue aceito",
      cepa(r, "--purpose", "via flag", "--reason", "r").returncode == 0
      and M.read_intent(r)["purpose"] == "via flag")
check("`--plan a b` sem ação segue aceito",
      cepa(r, "--plan", "a", "b").returncode == 0 and M.read_intent(r)["plan"] == ["a", "b"])

# --- the plan-item guard knows the new actions -------------------------------
r = new_repo("guard")
before = intent_file(r)
for word in ("step", "edit", "write", "state"):
    p = cepa(r, "edit", "--plan", "a", word)
    check(f"item de plano `{word}` é recusado (2)",
          p.returncode == 2 and intent_file(r) == before, p.stderr)

# --- 2. per-action help ------------------------------------------------------
ACTIONS = ("write", "show", "continue", "state", "close", "remind", "reminders", "step", "edit")
APPLY = {  # the options each action's help must list (and no other)
    "write": {"--purpose", "--by-when", "--plan", "--reason"},
    "edit": {"--purpose", "--plan", "--reason"},
    "close": {"--landed"},
    "remind": {"--context", "--at"},
}
ALL_OPTS = {"--purpose", "--by-when", "--plan", "--reason", "--landed", "--context", "--at",
            "--step"}
for act in ACTIONS:
    outs = {}
    # `remind help` is a reminder text, not a help request (tested below)
    for form in (["--help"], ["-h"], ["help"]):
        p = cepa(TMP, act, *form)  # outside any git repo: help never needs one
        outs[form[0]] = p
    if act == "remind":
        outs["help"] = outs["--help"]
    p = outs["--help"]
    check(f"`{act} --help` sai 0", p.returncode == 0, p.stderr)
    check(f"`{act} --help`, `-h` e `help` imprimem o mesmo",
          p.stdout == outs["-h"].stdout == outs["help"].stdout)
    first = p.stdout.splitlines()[0]
    check(f"`{act} --help` abre com `usage: cepa intent {act}`",
          first.startswith(f"usage: cepa intent {act}"), first)
    listed = {tok for tok in ALL_OPTS if f"  {tok} " in p.stdout or f"  {tok}\n" in p.stdout}
    check(f"`{act} --help` lista só as opções que valem para `{act}`",
          listed == APPLY.get(act, set()), f"{listed} vs {APPLY.get(act, set())}")
    check(f"`{act} --help` tem exemplos com `cepa intent {act}`",
          f"cepa intent {act}" in p.stdout.split("examples:")[-1], p.stdout)
    others = [x for x in ACTIONS if x != act and f"cepa intent {x} " in
              p.stdout.split("examples:")[-1].split("exit codes:")[0]]
    check(f"`{act} --help` não lista os exemplos de outras ações", not others, others)
    check(f"`{act} --help` não traz a lista de ações", "ACTION is one of" not in p.stdout)

# `remind help` is a reminder whose text is "help"; only --help / -h ask for help
r = new_repo("remind-help")
for word in ("help", "ajuda"):
    p = cepa(r, "remind", word, "--context", "x")
    check(f"`remind {word} --context x` grava um lembrete com o texto {word!r}",
          p.returncode == 0 and p.stdout.startswith("lembrete gravado")
          and f": {word}" in p.stdout, p.stdout + p.stderr)
check("os dois lembretes ficaram gravados", len(M.read_reminders(r)) == 2)
p = cepa(r, "remind", "--help")
check("`remind --help` segue imprimindo a ajuda do remind",
      p.returncode == 0 and p.stdout.startswith("usage: cepa intent remind"), p.stdout)

# a help request never writes, even next to other args
r = new_repo("help-nowrite")
before = intent_file(r)
p = cepa(r, "write", "--purpose", "x", "--help")
check("`write --purpose x --help` imprime a ajuda e não escreve",
      p.returncode == 0 and p.stdout.startswith("usage: cepa intent write")
      and intent_file(r) == before)
p = cepa(r, "--help")
check("`cepa intent --help` segue listando as ações, com `step` e `edit`",
      p.returncode == 0 and "ACTION is one of" in p.stdout and "step N" in p.stdout
      and "edit " in p.stdout and "cepa intent step 2" in p.stdout
      and "still\naccepted" in p.stdout.replace("  ", " ").replace("\n ", "\n"), p.stdout)
p = cepa(r, "gravar", "--help")
check("o nome antigo `gravar --help` mostra a ajuda do write",
      p.returncode == 0 and p.stdout.startswith("usage: cepa intent write"))

# through the launcher, as the owner types it
p = subprocess.run([str(LAUNCHER), "intent", "write", "--help"], cwd=TMP, env=ENV,
                   capture_output=True, text=True)
check("`cepa intent write --help` pelo lançador", p.returncode == 0
      and p.stdout.startswith("usage: cepa intent write"), p.stdout + p.stderr)
r = new_repo("launcher")
p = subprocess.run([str(LAUNCHER), "intent", "step", "2"], cwd=r, env=ENV,
                   capture_output=True, text=True)
check("`cepa intent step 2` pelo lançador move o cursor",
      p.returncode == 0 and M.read_intent(r)["step"] == 2, p.stdout + p.stderr)

# --- proof survivors: edit + --step, and the pinned text of each action help --
r = new_repo("edit-step")
before = intent_file(r)
p = cepa(r, "edit", "--purpose", "X", "--reason", "Y", "--step", "2")
check("`edit --purpose X --reason Y --step 2` sai 2 e não escreve",
      p.returncode == 2 and intent_file(r) == before and "edit não aceita --step" in p.stderr,
      p.stdout + p.stderr)
p = cepa(r, "edit", "--plan", "a", "b", "--step", "2")
check("`edit --plan a b --step 2` sai 2 e não escreve",
      p.returncode == 2 and intent_file(r) == before, p.stderr)

p = cepa(r, "write", "texto", "--purpose", "a", "--by-when", "b", "--plan", "c")
check("texto posicional fora de `remind` é recusado com a mensagem certa",
      p.returncode == 2 and "o texto posicional só vale com `remind` (e o número com `step`)"
      in p.stderr and intent_file(r) == before, p.stderr)
p = cepa(r, "bogus")
check("ação inválida lista todas as ações aceitas",
      p.returncode == 2 and "choose from write, show, continue, state, close, remind, "
      "reminders, step, edit" in p.stderr, p.stderr)

OK, USAGE = "ok", "invalid usage, not a git repo, or a writer rule refused (nothing written)"
NONE = "no intent recorded in this worktree"
HELP_SPEC = {  # action: (summary line, positional or None, {exit code: meaning})
    "write": ("Records a new intent: purpose, stopping point and plan.", None,
              {"0": OK, "2": USAGE, "4": "an intent exists and --reason is missing"}),
    "show": ("Prints the current intent (the default with no action)", None,
             {"0": OK, "3": NONE}),
    "continue": ("Adopts, in this session, the intent recorded by another session.", None,
                 {"0": OK, "2": USAGE, "3": NONE}),
    "state": ("Read-only: classifies the intent and prints the ready-made answer.", None,
              {"0": "ok, in every state", "2": USAGE}),
    "close": ("What /common:wrap-up runs: end-of-session telemetry.", None,
              {"0": "ok, always", "2": USAGE}),
    "step": ("Moves the cursor: step N is now in progress.",
             ("N", "the step in progress, 1-based; M+1 = plan fulfilled"),
             {"0": OK, "2": "invalid usage, or N outside the plan (nothing written)",
              "3": NONE}),
    "edit": ("Changes the purpose or the plan of the existing intent.", None,
             {"0": OK, "2": USAGE, "3": NONE}),
    "remind": ("Records an owner reminder with its date and a context sentence.",
               ("TEXT", "the reminder, in the owner's words"),
               {"0": OK, "2": USAGE}),
    "reminders": ("Read-only: lists the owner's reminders, with date and context.", None,
                  {"0": OK, "2": USAGE}),
}


def section(text, title):
    """Lines of `title:` up to the next blank line."""
    lines = text.splitlines()
    if f"{title}:" not in lines:
        return None
    out = []
    for l in lines[lines.index(f"{title}:") + 1:]:
        if not l.strip():
            break
        out.append(l.strip())
    return out


for act, (summary, positional, exits) in HELP_SPEC.items():
    out = cepa(TMP, act, "--help").stdout
    lines = out.splitlines()
    check(f"ajuda de `{act}`: resumo", summary in lines, out)
    args = section(out, "arguments")
    if positional:
        check(f"ajuda de `{act}`: posicional {positional[0]}",
              args is not None and len(args) == 1 and args[0].split()[0] == positional[0]
              and positional[1] in " ".join(args[0].split()), args)
    else:
        check(f"ajuda de `{act}`: sem posicional", args is None, args)
    got = {}
    for l in section(out, "exit codes") or []:
        code, _, meaning = l.partition("  ")
        got[code] = meaning.strip()
    check(f"ajuda de `{act}`: códigos de saída", got == exits, f"{got} vs {exits}")
    check(f"ajuda de `{act}`: seção de exemplos", bool(section(out, "examples")), out)

main_help = cepa(TMP, "--help").stdout
for frag in ("  step N     moves the cursor: step N is in progress (M+1 = plan fulfilled)",
             "  edit       changes the purpose (--purpose, needs --reason) or the plan (--plan)",
             "  show       prints the current intent", "  write      records a new intent",
             "  remind     records an owner reminder", "  reminders  read-only: lists"):
    check(f"`cepa intent --help` lista: {frag.strip()[:30]}", frag in main_help, main_help)
check("`cepa intent --help` cita as ações step e edit no argumento ACTION",
      "write, show, step, edit, continue, state, close, remind or reminders" in
      " ".join(main_help.split()), main_help)

if FAILURES:
    print(f"\n{len(FAILURES)} falha(s): {FAILURES}")
    sys.exit(1)
print("\ntudo ok")
