#!/usr/bin/env python3
"""C1-5 (intencao-c1): /common:whereami, the fallback of /common:next and the opening line
of /common:recap.

The three slash commands run the SAME read, `cepa-intent estado`, and what
classifies the state (empty / normal / fulfilled / other-session) is the code, not
the agent's eye. Here the command written in each .md is EXTRACTED from the file and
EXECUTED against the real `cepa-intent` in a temporary repo, in each state:
if someone swaps the documented command, or the classifier, the test fails.

It also proves that the "other session" question is a single one: the one the
`session-mode.py` hook injects is the one `state` prints.

No third-party deps — run with `python3 tests/test_whereami_intent.py`.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from _telemetria_isolada import isola
isola()

REPO = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO / "common"
CMDS = PLUGIN_ROOT / "commands"
HOOK = PLUGIN_ROOT / "hooks" / "session-mode.py"
BIN = '"${CLAUDE_PLUGIN_ROOT}/bin/cepa-intent"'
sys.path.insert(0, str(PLUGIN_ROOT / "hooks"))
import _modes as M  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def state_command(md):
    """The line `python3 ... cepa-intent" state` written in the .md (the 1st)."""
    txt = (CMDS / md).read_text(encoding="utf-8")
    m = re.search(r'^\s*(python3 "\$\{CLAUDE_PLUGIN_ROOT\}/bin/cepa-intent" state)\s*$',
                  txt, re.M)
    return m.group(1) if m else None, txt


def sh(cmd, cwd, session="sess-A", extra=None):
    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
           "CLAUDE_CODE_SESSION_ID": session}
    env.pop("CEPA_UNTIL_RUN", None)
    env.update(extra or {})
    return subprocess.run(cmd, shell=True, cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=60)


def repo(root, name):
    r = Path(root) / name
    r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
    return r


def write_intent(r, session="sess-A"):
    c = (f'python3 {BIN} write --purpose "criar o comando whereami" '
         '--by-when "testes verdes e commit feito" '
         '--plan "levantar" "escrever" "testar" "fechar"')
    out = sh(c, r, session)
    assert out.returncode == 0, out.stderr


def main():
    cmds = {md: state_command(md) for md in ("whereami.md", "next.md", "recap.md")}
    for md, (c, _) in cmds.items():
        check(f"{md} documenta o comando `cepa-intent estado`", c is not None)
    cmd = cmds["whereami.md"][0] or ""
    check("os três .md rodam o mesmo comando", len({c for c, _ in cmds.values()}) == 1)

    with tempfile.TemporaryDirectory() as t:
        # --- empty -----------------------------------------------------
        r = repo(t, "vazio")
        out = sh(cmd, r)
        check("empty: sai 0", out.returncode == 0, out.stderr)
        check("empty: 1ª linha é o estado", out.stdout.splitlines()[0] == "state: empty", out.stdout)
        check("empty: a frase do desenho",
              "Esta sessão não tem intenção gravada. Diga o propósito e eu proponho o plano."
              in out.stdout, out.stdout)
        check("empty: não delega fora do cepa-until", "delegate" not in out.stdout)
        check("empty: não cria o arquivo", not (r / ".claude" / "session-intent").exists())
        out = sh(cmd, r, extra={"CEPA_UNTIL_RUN": "2026-10-17-0711"})
        check("vazio na rodada do cepa-until: delega ao /common:next",
              out.stdout.splitlines()[:2] == ["state: empty", "delegate: /common:next"], out.stdout)

        # --- normal ----------------------------------------------------
        r = repo(t, "normal")
        write_intent(r)
        sh(f"python3 {BIN} --step 2", r)
        before = (r / ".claude" / "session-intent").read_bytes()
        out = sh(cmd, r)
        check("normal: sai 0", out.returncode == 0, out.stderr)
        lines = out.stdout.splitlines()
        check("normal: 1ª linha é o estado", lines[0] == "state: normal", out.stdout)
        check("normal: propósito e para quando por extenso",
              "propósito: criar o comando whereami" in out.stdout
              and "para quando: testes verdes e commit feito" in out.stdout, out.stdout)
        check("normal: plano com o cursor marcado só no passo 2",
              "  > 2. escrever" in out.stdout and "    1. levantar" in out.stdout
              and out.stdout.count("  > ") == 1, out.stdout)
        check("normal: passo atual com a idade",
              re.search(r"passo atual: 2 de 4, há agora \(desde \d{4}-", out.stdout), out.stdout)
        check("normal: linha de abertura do recap",
              "opening: criar o comando whereami / passo 2 de 4" in lines, out.stdout)
        check("estado é só leitura: o arquivo não mudou",
              (r / ".claude" / "session-intent").read_bytes() == before)
        out2 = sh(cmd + " --step 3", r)
        check("estado recusa opções de escrita", out2.returncode == 2, out2.stderr)
        check("... e não mexe no cursor", (r / ".claude" / "session-intent").read_bytes() == before)
        out = sh(cmd, r, extra={"CEPA_UNTIL_RUN": "x"})
        check("rodada do cepa-until ignora a intenção herdada e delega",
              "delegate: /common:next" in out.stdout and out.stdout.startswith("state: empty"),
              out.stdout)

        # --- fulfilled -------------------------------------------------
        sh(f"python3 {BIN} --step 5", r)
        out = sh(cmd, r)
        check("cumprido: 1ª linha é o estado", out.stdout.splitlines()[0] == "state: fulfilled", out.stdout)
        check("cumprido: a frase do desenho",
              "Os 4 passos estão feitos. Ponto de parada: testes verdes e commit feito. "
              "Próximo: `/common:wrap-up`." in out.stdout, out.stdout)
        check("cumprido: abertura diz plano cumprido",
              "opening: criar o comando whereami / plano cumprido 4/4" in out.stdout, out.stdout)
        check("cumprido: sem cursor marcado", "  > " not in out.stdout)

        # --- other session --------------------------------------------
        r = repo(t, "outra")
        write_intent(r, "sess-A")
        out = sh(cmd, r, session="sess-B")
        check("other-session: 1ª linha é o estado",
              out.stdout.splitlines()[0] == "state: other-session", out.stdout)
        check("other-session: mostra a data e pergunta se continua",
              re.search(r"Intenção de \d{4}-\d\d-\d\d \d\d:\d\d UTC, gravada em outra sessão",
                        out.stdout) and "continuo ou abro nova?" in out.stdout, out.stdout)
        check("other-session: sem linha de abertura (não é desta sessão)",
              "opening:" not in out.stdout)
        # the question is the hook's, not a second copy
        hook = subprocess.run(
            [sys.executable, str(HOOK)], cwd=r, capture_output=True, text=True,
            input=json.dumps({"cwd": str(r), "session_id": "sess-B", "prompt": "oi"}),
            env={**os.environ, "CEPA_MODO": "on", "CEPA_UNTIL_RUN": ""})
        ctx = json.loads(hook.stdout)["hookSpecificOutput"]["additionalContext"] if hook.stdout else ""
        phrases = M.other_session_question(M.read_intent(r), "criar o comando whereami")
        check("a pergunta do estado é a mesma que o hook injeta",
              all(f in ctx and f in out.stdout for f in phrases), f"{ctx!r}")
        sh("python3 " + BIN + " continue", r, session="sess-B")
        out = sh(cmd, r, session="sess-B")
        check("depois de `continuar` o estado volta a normal",
              out.stdout.splitlines()[0] == "state: normal", out.stdout)

        # --- partial file (without a plan) counts as empty ---------------
        r = repo(t, "parcial")
        (r / ".claude").mkdir()
        (r / ".claude" / "session-intent").write_text('proposito: "x"\n')
        out = sh(cmd, r)
        check("arquivo sem plano é vazio", out.stdout.splitlines()[0] == "state: empty", out.stdout)

    with tempfile.TemporaryDirectory() as t:
        # --- boundary of the last step (step == M) ----------------------
        r = repo(t, "ultimo")
        write_intent(r)
        sh(f"python3 {BIN} --step 4", r)
        out = sh(cmd, r)
        check("ultimo passo (M de M) é normal, não cumprido",
              out.stdout.splitlines()[0] == "state: normal", out.stdout)
        check("ultimo passo: cursor > no passo 4 e só nele",
              "  > 4. fechar" in out.stdout and out.stdout.count("  > ") == 1, out.stdout)
        check("ultimo passo: abertura diz passo 4 de 4",
              "opening: criar o comando whereami / passo 4 de 4" in out.stdout.splitlines(),
              out.stdout)
        check("ultimo passo: sem a frase de plano cumprido", "cumprido" not in out.stdout)

        # --- age of the cursor ------------------------------------------
        def with_age(name, delta):
            rr = repo(t, name)
            write_intent(rr)
            f = rr / ".claude" / "session-intent"
            ts = (datetime.now(timezone.utc) - delta).strftime("%Y-%m-%dT%H:%M:%SZ")
            f.write_text(re.sub(r'(?m)^step_since: .*$', f'step_since: "{ts}"',
                                f.read_text(encoding="utf-8")), encoding="utf-8")
            return sh(cmd, rr).stdout

        o = with_age("idade2h", timedelta(hours=2, minutes=5, seconds=30))
        check("idade: 2h05 min atrás vira `há 2h05`", "passo atual: 1 de 4, há 2h05 (desde" in o, o)
        o = with_age("idade12", timedelta(minutes=12, seconds=30))
        check("idade: 12 min atrás vira `há 12 min`", "passo atual: 1 de 4, há 12 min (desde" in o, o)
        o = with_age("idade59", timedelta(minutes=59, seconds=30))
        check("idade: 59 min ainda é em minutos", "há 59 min (desde" in o, o)
        o = with_age("idade60", timedelta(minutes=60, seconds=30))
        check("idade: 60 min vira `há 1h00`", "há 1h00 (desde" in o, o)

        # --- a step written by hand outside the plan becomes step 1 ------
        for name, value in (("p0", 0), ("p99", 99), ("pneg", -3)):
            rr = repo(t, name)
            write_intent(rr)
            f = rr / ".claude" / "session-intent"
            f.write_text(re.sub(r'(?m)^step: .*$', f'step: {value}',
                                f.read_text(encoding="utf-8")), encoding="utf-8")
            o = sh(cmd, rr).stdout
            check(f"passo {value} à mão é tratado como passo 1",
                  o.splitlines()[0] == "state: normal" and "  > 1. levantar" in o
                  and "opening: criar o comando whereami / passo 1 de 4" in o, o)

        # --- a plan item called `state` is refused -----------------------
        rr = repo(t, "itemestado")
        o = sh(f'python3 {BIN} write --purpose x --by-when y --plan "a" "state"', rr)
        check("gravar recusa item de plano chamado `state`",
              o.returncode == 2 and not (rr / ".claude" / "session-intent").exists(),
              o.stderr)

    # iso_utc: a timestamp without a timezone is read as UTC
    d = M.iso_utc("2026-10-17T10:00:00")
    check("iso_utc: sem fuso vira UTC",
          d is not None and d.utcoffset() == timedelta(0), repr(d))
    check("iso_utc: Z e offset equivalem",
          M.iso_utc("2026-10-17T10:00:00Z") == M.iso_utc("2026-10-17T07:00:00-03:00"))
    check("iso_utc: lixo devolve None", M.iso_utc("lixo") is None and M.iso_utc(None) is None)

    # --- the text of the .md files --------------------------------------
    w = " ".join((CMDS / "whereami.md").read_text(encoding="utf-8").split())
    fm = (CMDS / "whereami.md").read_text(encoding="utf-8").split("---")[1]
    check("whereami: nome único, sem alias", "alias" not in fm.lower())
    for est in ("empty", "normal", "fulfilled", "other-session"):
        check(f"whereami trata o estado {est}", f"**`{est}`**" in w)
    check("whereami delega ao /common:next na rodada do cepa-until",
          "delegate: /common:next" in w and "run `/common:next`" in w)
    check("whereami confronta o log e só propõe",
          "Avanço?" in w and "You propose; the owner decides" in w
          and "Never advances the cursor on its own" in w)
    check("whereami avança só por `cepa-intent --step N`", '--step N' in w)
    check("whereami proíbe editar o YAML à mão", "Never edit `.claude/session-intent` by hand" in w)

    nxt = cmds["next.md"][1]
    i_cmd, i_empty = nxt.find("cepa-intent\" state"), nxt.find("and the intent is `empty`")
    i_plan = nxt.find("### 1. Locate the plan")
    check("next: o fallback vem depois de procurar o plano e antes de declarar ausência",
          0 <= i_plan < i_cmd < i_empty, f"{i_plan} {i_cmd} {i_empty}")
    n = " ".join(nxt.split())
    check("next: cumprido aponta /common:wrap-up e plano achado responde primeiro",
          "`fulfilled` → the next step is `/common:wrap-up`" in n
          and "a plan answers first" in n)
    check("next: sem intenção mantém o comportamento (não inventa ordem)",
          "Don't manufacture an order" in n)

    check("next: normal responde a partir da saída e diz que vem da intenção da sessão",
          "`normal` → answer from it" in n
          and "Say that the answer comes from the session intent" in n)
    check("next: outra-sessao mostra a pergunta e espera",
          "`other-session` → show the question the output carries and wait" in n)

    rec = cmds["recap.md"][1]
    check("recap: a linha de abertura (passo 0) vem antes de carregar o log",
          0 <= rec.find("### 0. Opening line") < rec.find("cepa-intent\" state")
          < rec.find("### 1. Load the intent log"))
    rn = " ".join(rec.split())
    check("recap: abre com a linha `opening:` e sem intenção não imprime nada",
          "`opening:` line" in rn and "print **no line at all**" in rn)

    check("recap: abre com a linha e nunca lê/edita o arquivo à mão",
          "open the recap with that line" in rn
          and "Never read or edit `.claude/session-intent` by hand" in rn)
    check("whereami: outra-sessao não é tratada como desta sessão; nunca reclassifica",
          "Do not treat the intent as this session's and do not do the step 2 check" in w
          and "Never reclassifies the state by eye" in w)

    check("recap: o contrato cobre as duas saídas de `opening:`",
          "passo N de M" in rn and "plano cumprido M/M" in rn
          and "plano cumprido 3/3" in rn and "passo 2 de 3" in rn)

    # --- old names ----------------------------------------------------------
    # `cepa-intencao estado` (shortcut + old action) prints the same as
    # `cepa-intent state`, and a session-intent in the OLD format is classified
    with tempfile.TemporaryDirectory() as t:
        r = repo(t, "antigo")
        (r / ".claude").mkdir()
        (r / ".claude" / "session-intent").write_text(
            'proposito: "criar o comando whereami"\npara_quando: "q"\nplano:\n  - "a"\n  - "b"\n'
            'passo: 2\npasso_desde: "2020-01-01T00:00:00Z"\nsession_id: "sess-A"\nbranch: "main"\n')
        new = sh(cmd, r)
        old = sh('python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-intencao" estado', r)
        check("antigo: arquivo com chaves pt-BR é classificado como normal",
              new.stdout.splitlines()[0] == "state: normal"
              and "opening: criar o comando whereami / passo 2 de 2" in new.stdout, new.stdout)
        check("antigo: `cepa-intencao estado` imprime o mesmo que `cepa-intent state`",
              old.returncode == 0 and old.stdout == new.stdout, (old.stdout, new.stdout))

    if FAILURES:
        print(f"\n{len(FAILURES)} FAIL")
        sys.exit(1)
    print("\nOK")


if __name__ == "__main__":
    main()
