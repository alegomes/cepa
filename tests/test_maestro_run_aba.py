#!/usr/bin/env python3
"""Contract test: /maestro:run forka as filhas SEMPRE na aba do próprio comando,
nunca na aba que estiver em foco no momento do spawn.

## O defeito (reflexão 2026-08-24, onda WEGO-paralelo, wego-acesso-backend)

O passo de spawn não dizia em que aba forkar. Sem `--tab`/`--workspace`, o
`herdr agent start` dividia a aba que estivesse em FOCO no instante do fork —
e entre o intake e o spawn passam minutos, tempo de sobra para o dono clicar
em outra aba. No `herdr-server.log` da onda real: a aba do `/maestro:run`
(`wJ:t1`) não recebeu foco nenhuma vez entre 13:01 e 13:05; a aba
`portais_vs_operadoras` (`wJ:tC`) recebeu foco às 13:01:01 e ficou assim; os
cinco `pane.spawn.start` da onda (13:04:45–13:04:46) mostram largura caindo
pela metade a cada um (173 → 87 → 44 → 22 → 11 colunas) — a assinatura de
cinco divisões sucessivas da MESMA aba errada.

## Fato verificado ao vivo contra o herdr 0.9.1 instalado (não é mais o esboço
## do BACKLOG — `herdr agent start` não aceita mais `--cwd`/`--tab`/`--workspace`
## nem comando após `--`; ele só inicia agente numa pane já existente)

`herdr pane split <PANE_ID> --direction right ... --no-focus` cria o pane novo
NA ABA do pane apontado, independente de qual aba está em foco — por isso o
conserto é capturar o pane-lar (`herdr pane current`) no INÍCIO da rotina,
persisti-lo em disco (`maestro-wave-state set-home`) e dividir esse pane por
ID explícito no passo de spawn, nunca o foco corrente.

## O que este teste segura (mecânico, no molde de tests/test_worktree_create_verify.py)

- `run.md` captura o pane-lar (`herdr pane current`) ANTES do intake gate
  (`cepa-dor`) no texto — captar depois é captar o valor errado;
- o passo de spawn usa `herdr pane split` com id explícito de pane e
  `--no-focus`, seguido de `herdr pane run` — e NÃO contém mais a receita
  obsoleta `herdr agent start <PROG>-<slice> --cwd`;
- existe fallback para pane-lar morto: `herdr tab create` com `--label`,
  disparado quando o split devolve `pane_not_found`;
- `set-home` é persistido em `run.md` e lido em `resume.md`;
- roundtrip real de `maestro-wave-state`: `init` + `set-home` + `get` guardam e
  devolvem pane/tab/workspace, e um wave-state sem `home` (formato antigo)
  continua carregando.

Run: python3 tests/test_maestro_run_aba.py
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
    """Espaços colapsados: as checagens casam FRASE, não quebra de linha —
    senão uma re-quebra inocente vira falso-vermelho e ensina a afrouxar o
    guard, que é como um guard mecânico vira decoração."""
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


def test_captura_antes_do_intake():
    run = RUN.read_text(encoding="utf-8")
    i_captura = run.find("herdr pane current")
    i_intake = run.find("common/bin/cepa-dor")
    check("run.md chama `herdr pane current`", i_captura != -1)
    check("run.md roda o intake gate (`cepa-dor`)", i_intake != -1)
    check("a captura do pane-lar vem ANTES do intake gate no texto",
          i_captura != -1 and i_intake != -1 and i_captura < i_intake,
          f"captura em {i_captura}, intake em {i_intake}")
    fr = flat(run)
    check("run.md explica por que captura no início, não no fork "
          "(minutos passam / foco muda)",
          "minutos" in fr and "foco" in fr)
    check("run.md cita a evidência WEGO-paralelo (largura caindo pela metade)",
          "2026-08-24" in fr and ("pela metade" in fr or "173" in fr))
    check("captura sem herdr → aba nova previsível (`herdr tab create ... "
          "--label <PROG>`), nunca o foco corrente",
          "herdr tab create" in fr and "--label <PROG>" in fr)


def test_spawn_usa_split_por_pane_lar():
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
          "nunca" in fr and "pane que estiver em foco" in fr)
    check("prosa nomeia que `--no-focus` não escolhe onde o pane nasce",
          "não escolhe onde" in fr)
    # o wrapper normativo (pipefail + PIPESTATUS + MAESTRO-EXIT) tem de
    # sobreviver à troca de receita — é o que os outros testes pinam.
    check("o wrapper normativo continua presente (pipefail)",
          "pipefail" in fr)
    check("o wrapper normativo continua marcando MAESTRO-EXIT",
          "MAESTRO-EXIT" in fr)
    check("o wrapper normativo continua exigindo --strict-mcp-config",
          "--strict-mcp-config" in fr)


def _extrai_herdr_pane_run(run_text):
    """Acha o bloco de código do passo 6c e devolve o texto a partir de
    `herdr pane run <novo-pane>` até o fim do bloco (o `bash -c '...'` inteiro,
    com as continuações de linha originais). Falha (retorna None) se o
    comando não existir mais aí — sinal de que o passo mudou de forma e este
    teste precisa ser reancorado."""
    for bloco in re.findall(r"```\n(.*?)```", run_text, re.S):
        if "herdr pane run <novo-pane>" in bloco:
            i = bloco.find("herdr pane run <novo-pane>")
            return bloco[i:].rstrip("\n")
    return None


def test_maestro_exit_nao_expande_no_shell_do_maestro():
    """Defeito real: `herdr pane run <novo-pane> "bash -c '...'"` é digitado
    num shell duplo-aspeado da PRÓPRIA sessão do maestro. Sem escapar
    `${PIPESTATUS[0]}`, `$ec` e `$MAESTRO_LINGER` com `\\$`, essas três
    variáveis expandem AQUI (vazias, pois não existem neste shell) ANTES de o
    texto chegar à pane filha — o `resultado.txt` ganharia `MAESTRO-EXIT:` sem
    código e `sleep ""`, quebrando a sincronização por arquivo em silêncio.

    Checagem mecânica: troca `herdr pane run <novo-pane>` por `printf '%s'` e
    roda o resto do comando (as aspas e escapes originais, intactos) num bash
    de verdade, sem `MAESTRO_LINGER`/`ec` no ambiente — isso reproduz
    EXATAMENTE o que o shell do maestro produziria como argumento único de
    `herdr pane run`, ou seja, o texto que a pane filha receberia. Se as três
    variáveis ainda aparecem LITERALMENTE (não expandidas) na saída, a receita
    está correta; se sumiram/ficaram vazias, expandiu cedo demais."""
    run = RUN.read_text(encoding="utf-8")
    cmd = _extrai_herdr_pane_run(run)
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
          "proposital" in flat(run) and "sujeira" in flat(run))


def test_fallback_pane_lar_morto():
    fr = flat(RUN.read_text(encoding="utf-8"))
    check("existe fallback para pane-lar morto (`pane_not_found`)",
          "pane_not_found" in fr)
    check("o fallback usa `herdr tab create` com `--label`",
          "herdr tab create" in fr and "--label <PROG>" in fr)
    check("o fallback atualiza o pane-lar com `set-home` para as slices seguintes",
          "set-home" in fr)


def test_set_home_persistido_e_lido():
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

    # wave-state antigo, sem a chave `home`, continua carregando (init
    # compatível — set-home é opt-in, não obrigatório para o formato existir).
    old = yaml.safe_load(plan.read_text()) and None  # noop, só para linter
    ws_sem_home = {k: v for k, v in ws.items() if k != "home"}
    (pd / "wave-state.yaml").write_text(
        yaml.safe_dump(ws_sem_home, allow_unicode=True, sort_keys=False))
    r = sh([WAVE_STATE, "get", pd, "--json"])
    check("wave-state sem `home` (formato antigo) ainda carrega",
          r.returncode == 0 and "home" not in json.loads(r.stdout), r.stdout)


def main():
    test_captura_antes_do_intake()
    test_spawn_usa_split_por_pane_lar()
    test_maestro_exit_nao_expande_no_shell_do_maestro()
    test_fallback_pane_lar_morto()
    test_set_home_persistido_e_lido()
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
