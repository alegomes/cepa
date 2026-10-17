#!/usr/bin/env python3
"""C1-5 (intencao-c1): /common:whereami, o fallback do /common:next e a linha
de abertura do /common:recap.

Os três comandos de barra rodam a MESMA leitura, `cepa-intencao estado`, e quem
classifica o estado (vazio / normal / cumprido / outra-sessao) é o código, não
o olho do agente. Aqui o comando escrito em cada .md é EXTRAÍDO do arquivo e
EXECUTADO contra o `cepa-intencao` real num repo temporário, em cada estado:
se alguém trocar o comando documentado, ou o classificador, o teste reprova.

Também prova que a pergunta de "outra sessão" é uma só: a que o hook
`session-mode.py` injeta é a que o `estado` imprime.

Sem deps de terceiros — rode com `python3 tests/test_whereami_intencao.py`.
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
BIN = '"${CLAUDE_PLUGIN_ROOT}/bin/cepa-intencao"'
sys.path.insert(0, str(PLUGIN_ROOT / "hooks"))
import _modos as M  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def comando_estado(md):
    """A linha `python3 ... cepa-intencao" estado` escrita no .md (a 1ª)."""
    txt = (CMDS / md).read_text(encoding="utf-8")
    m = re.search(r'^\s*(python3 "\$\{CLAUDE_PLUGIN_ROOT\}/bin/cepa-intencao" estado)\s*$',
                  txt, re.M)
    return m.group(1) if m else None, txt


def sh(cmd, cwd, sessao="sess-A", extra=None):
    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
           "CLAUDE_CODE_SESSION_ID": sessao}
    env.pop("CEPA_UNTIL_RUN", None)
    env.update(extra or {})
    return subprocess.run(cmd, shell=True, cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=60)


def repo(raiz, nome):
    r = Path(raiz) / nome
    r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
    return r


def grava(r, sessao="sess-A"):
    c = (f'python3 {BIN} gravar --proposito "criar o comando whereami" '
         '--para-quando "testes verdes e commit feito" '
         '--plano "levantar" "escrever" "testar" "fechar"')
    out = sh(c, r, sessao)
    assert out.returncode == 0, out.stderr


def main():
    cmds = {md: comando_estado(md) for md in ("whereami.md", "next.md", "recap.md")}
    for md, (c, _) in cmds.items():
        check(f"{md} documenta o comando `cepa-intencao estado`", c is not None)
    cmd = cmds["whereami.md"][0] or ""
    check("os três .md rodam o mesmo comando", len({c for c, _ in cmds.values()}) == 1)

    with tempfile.TemporaryDirectory() as t:
        # --- vazio -----------------------------------------------------
        r = repo(t, "vazio")
        out = sh(cmd, r)
        check("vazio: sai 0", out.returncode == 0, out.stderr)
        check("vazio: 1ª linha é o estado", out.stdout.splitlines()[0] == "estado: vazio", out.stdout)
        check("vazio: a frase do desenho",
              "Esta sessão não tem intenção gravada. Diga o propósito e eu proponho o plano."
              in out.stdout, out.stdout)
        check("vazio: não delega fora do cepa-until", "delegar" not in out.stdout)
        check("vazio: não cria o arquivo", not (r / ".claude" / "session-intent").exists())
        out = sh(cmd, r, extra={"CEPA_UNTIL_RUN": "2026-10-17-0711"})
        check("vazio na rodada do cepa-until: delega ao /common:next",
              out.stdout.splitlines()[:2] == ["estado: vazio", "delegar: /common:next"], out.stdout)

        # --- normal ----------------------------------------------------
        r = repo(t, "normal")
        grava(r)
        sh(f"python3 {BIN} --passo 2", r)
        antes = (r / ".claude" / "session-intent").read_bytes()
        out = sh(cmd, r)
        check("normal: sai 0", out.returncode == 0, out.stderr)
        linhas = out.stdout.splitlines()
        check("normal: 1ª linha é o estado", linhas[0] == "estado: normal", out.stdout)
        check("normal: propósito e para quando por extenso",
              "propósito: criar o comando whereami" in out.stdout
              and "para quando: testes verdes e commit feito" in out.stdout, out.stdout)
        check("normal: plano com o cursor marcado só no passo 2",
              "  > 2. escrever" in out.stdout and "    1. levantar" in out.stdout
              and out.stdout.count("  > ") == 1, out.stdout)
        check("normal: passo atual com a idade",
              re.search(r"passo atual: 2 de 4, há agora \(desde \d{4}-", out.stdout), out.stdout)
        check("normal: linha de abertura do recap",
              "abertura: criar o comando whereami / passo 2 de 4" in linhas, out.stdout)
        check("estado é só leitura: o arquivo não mudou",
              (r / ".claude" / "session-intent").read_bytes() == antes)
        out2 = sh(cmd + " --passo 3", r)
        check("estado recusa opções de escrita", out2.returncode == 2, out2.stderr)
        check("... e não mexe no cursor", (r / ".claude" / "session-intent").read_bytes() == antes)
        out = sh(cmd, r, extra={"CEPA_UNTIL_RUN": "x"})
        check("rodada do cepa-until ignora a intenção herdada e delega",
              "delegar: /common:next" in out.stdout and out.stdout.startswith("estado: vazio"),
              out.stdout)

        # --- cumprido --------------------------------------------------
        sh(f"python3 {BIN} --passo 5", r)
        out = sh(cmd, r)
        check("cumprido: 1ª linha é o estado", out.stdout.splitlines()[0] == "estado: cumprido", out.stdout)
        check("cumprido: a frase do desenho",
              "Os 4 passos estão feitos. Ponto de parada: testes verdes e commit feito. "
              "Próximo: `/common:wrap-up`." in out.stdout, out.stdout)
        check("cumprido: abertura diz plano cumprido",
              "abertura: criar o comando whereami / plano cumprido 4/4" in out.stdout, out.stdout)
        check("cumprido: sem cursor marcado", "  > " not in out.stdout)

        # --- outra sessão ---------------------------------------------
        r = repo(t, "outra")
        grava(r, "sess-A")
        out = sh(cmd, r, sessao="sess-B")
        check("outra-sessao: 1ª linha é o estado",
              out.stdout.splitlines()[0] == "estado: outra-sessao", out.stdout)
        check("outra-sessao: mostra a data e pergunta se continua",
              re.search(r"Intenção de \d{4}-\d\d-\d\d \d\d:\d\d UTC, gravada em outra sessão",
                        out.stdout) and "continuo ou abro nova?" in out.stdout, out.stdout)
        check("outra-sessao: sem linha de abertura (não é desta sessão)",
              "abertura:" not in out.stdout)
        # a pergunta é a do hook, não uma segunda cópia
        hook = subprocess.run(
            [sys.executable, str(HOOK)], cwd=r, capture_output=True, text=True,
            input=json.dumps({"cwd": str(r), "session_id": "sess-B", "prompt": "oi"}),
            env={**os.environ, "CEPA_MODO": "on", "CEPA_UNTIL_RUN": ""})
        ctx = json.loads(hook.stdout)["hookSpecificOutput"]["additionalContext"] if hook.stdout else ""
        frases = M.pergunta_outra_sessao(M.read_intent(r), "criar o comando whereami")
        check("a pergunta do estado é a mesma que o hook injeta",
              all(f in ctx and f in out.stdout for f in frases), f"{ctx!r}")
        sh("python3 " + BIN + " continuar", r, sessao="sess-B")
        out = sh(cmd, r, sessao="sess-B")
        check("depois de `continuar` o estado volta a normal",
              out.stdout.splitlines()[0] == "estado: normal", out.stdout)

        # --- arquivo parcial (sem plano) conta como vazio ---------------
        r = repo(t, "parcial")
        (r / ".claude").mkdir()
        (r / ".claude" / "session-intent").write_text('proposito: "x"\n')
        out = sh(cmd, r)
        check("arquivo sem plano é vazio", out.stdout.splitlines()[0] == "estado: vazio", out.stdout)

    with tempfile.TemporaryDirectory() as t:
        # --- fronteira do último passo (passo == M) ---------------------
        r = repo(t, "ultimo")
        grava(r)
        sh(f"python3 {BIN} --passo 4", r)
        out = sh(cmd, r)
        check("ultimo passo (M de M) é normal, não cumprido",
              out.stdout.splitlines()[0] == "estado: normal", out.stdout)
        check("ultimo passo: cursor > no passo 4 e só nele",
              "  > 4. fechar" in out.stdout and out.stdout.count("  > ") == 1, out.stdout)
        check("ultimo passo: abertura diz passo 4 de 4",
              "abertura: criar o comando whereami / passo 4 de 4" in out.stdout.splitlines(),
              out.stdout)
        check("ultimo passo: sem a frase de plano cumprido", "cumprido" not in out.stdout)

        # --- idade do cursor --------------------------------------------
        def com_idade(nome, delta):
            rr = repo(t, nome)
            grava(rr)
            f = rr / ".claude" / "session-intent"
            ts = (datetime.now(timezone.utc) - delta).strftime("%Y-%m-%dT%H:%M:%SZ")
            f.write_text(re.sub(r'(?m)^passo_desde: .*$', f'passo_desde: "{ts}"',
                                f.read_text(encoding="utf-8")), encoding="utf-8")
            return sh(cmd, rr).stdout

        o = com_idade("idade2h", timedelta(hours=2, minutes=5, seconds=30))
        check("idade: 2h05 min atrás vira `há 2h05`", "passo atual: 1 de 4, há 2h05 (desde" in o, o)
        o = com_idade("idade12", timedelta(minutes=12, seconds=30))
        check("idade: 12 min atrás vira `há 12 min`", "passo atual: 1 de 4, há 12 min (desde" in o, o)
        o = com_idade("idade59", timedelta(minutes=59, seconds=30))
        check("idade: 59 min ainda é em minutos", "há 59 min (desde" in o, o)
        o = com_idade("idade60", timedelta(minutes=60, seconds=30))
        check("idade: 60 min vira `há 1h00`", "há 1h00 (desde" in o, o)

        # --- passo escrito à mão fora do plano vira passo 1 --------------
        for nome, valor in (("p0", 0), ("p99", 99), ("pneg", -3)):
            rr = repo(t, nome)
            grava(rr)
            f = rr / ".claude" / "session-intent"
            f.write_text(re.sub(r'(?m)^passo: .*$', f'passo: {valor}',
                                f.read_text(encoding="utf-8")), encoding="utf-8")
            o = sh(cmd, rr).stdout
            check(f"passo {valor} à mão é tratado como passo 1",
                  o.splitlines()[0] == "estado: normal" and "  > 1. levantar" in o
                  and "abertura: criar o comando whereami / passo 1 de 4" in o, o)

        # --- item de plano chamado `estado` é recusado --------------------
        rr = repo(t, "itemestado")
        o = sh(f'python3 {BIN} gravar --proposito x --para-quando y --plano "a" "estado"', rr)
        check("gravar recusa item de plano chamado `estado`",
              o.returncode == 2 and not (rr / ".claude" / "session-intent").exists(),
              o.stderr)

    # iso_utc: timestamp sem fuso é lido como UTC
    d = M.iso_utc("2026-10-17T10:00:00")
    check("iso_utc: sem fuso vira UTC",
          d is not None and d.utcoffset() == timedelta(0), repr(d))
    check("iso_utc: Z e offset equivalem",
          M.iso_utc("2026-10-17T10:00:00Z") == M.iso_utc("2026-10-17T07:00:00-03:00"))
    check("iso_utc: lixo devolve None", M.iso_utc("lixo") is None and M.iso_utc(None) is None)

    # --- o texto dos .md ------------------------------------------------
    w = " ".join((CMDS / "whereami.md").read_text(encoding="utf-8").split())
    fm = (CMDS / "whereami.md").read_text(encoding="utf-8").split("---")[1]
    check("whereami: nome único, sem alias", "alias" not in fm.lower())
    for est in ("vazio", "normal", "cumprido", "outra-sessao"):
        check(f"whereami trata o estado {est}", f"**`{est}`**" in w)
    check("whereami delega ao /common:next na rodada do cepa-until",
          "delegar: /common:next" in w and "execute o `/common:next`" in w)
    check("whereami confronta o log e só propõe",
          "Avanço?" in w and "Você propõe; o dono decide" in w
          and "Nunca avança o cursor por conta própria" in w)
    check("whereami avança só por `cepa-intencao --passo N`", '--passo N' in w)
    check("whereami proíbe editar o YAML à mão", "Nunca edite" in w)

    nxt = cmds["next.md"][1]
    i_cmd, i_vazio = nxt.find("cepa-intencao\" estado"), nxt.find("and the intent is `vazio`")
    i_plano = nxt.find("### 1. Locate the plan")
    check("next: o fallback vem depois de procurar o plano e antes de declarar ausência",
          0 <= i_plano < i_cmd < i_vazio, f"{i_plano} {i_cmd} {i_vazio}")
    n = " ".join(nxt.split())
    check("next: cumprido aponta /common:wrap-up e plano achado responde primeiro",
          "`cumprido` → the next step is `/common:wrap-up`" in n
          and "a plan answers first" in n)
    check("next: sem intenção mantém o comportamento (não inventa ordem)",
          "Don't manufacture an order" in n)

    check("next: normal responde a partir da saída e diz que vem da intenção da sessão",
          "`normal` → answer from it" in n
          and "Say that the answer comes from the session intent" in n)
    check("next: outra-sessao mostra a pergunta e espera",
          "`outra-sessao` → show the question the output carries and wait" in n)

    rec = cmds["recap.md"][1]
    check("recap: a linha de abertura (passo 0) vem antes de carregar o log",
          0 <= rec.find("### 0. Opening line") < rec.find("cepa-intencao\" estado")
          < rec.find("### 1. Load the intent log"))
    rn = " ".join(rec.split())
    check("recap: abre com a linha `abertura:` e sem intenção não imprime nada",
          "`abertura:` line" in rn and "print **no line at all**" in rn)

    check("recap: abre com a linha e nunca lê/edita o arquivo à mão",
          "open the recap with that line" in rn
          and "Never read or edit `.claude/session-intent` by hand" in rn)
    check("whereami: outra-sessao não é tratada como desta sessão; nunca reclassifica",
          "Não trate a intenção como a desta sessão e não faça a conferência do passo 2" in w
          and "Nunca reclassifica o estado de olho" in w)

    check("recap: o contrato cobre as duas saídas de `abertura:`",
          "passo N de M" in rn and "plano cumprido M/M" in rn
          and "plano cumprido 3/3" in rn and "passo 2 de 3" in rn)

    if FAILURES:
        print(f"\n{len(FAILURES)} FAIL")
        sys.exit(1)
    print("\nOK")


if __name__ == "__main__":
    main()
