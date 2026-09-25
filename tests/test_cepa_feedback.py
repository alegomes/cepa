#!/usr/bin/env python3
"""Testes do caderno de feedback do harness — bin/cepa-feedback + feedback-nudge.

O comportamento que estes casos existem para segurar não é "o arquivo é escrito".
É o conjunto de recusas que impede o ledger de virar arquivo morto:

  - registro vazio ou de uma palavra é RECUSADO — queixa de uma palavra não se
    reconstrói meses depois, e um ledger cheio de "ruim" tem o mesmo valor de um
    ledger vazio, com a desvantagem de parecer cheio;
  - o texto entra VERBATIM (o bin não resume nada);
  - repo, branch e modo entram sozinhos — registro que depende do dono lembrar
    onde estava nasce inútil;
  - triagem sem destino, de id inexistente, ou SEGUNDA triagem do mesmo id são
    recusadas: a re-triagem apagaria em silêncio a decisão anterior;
  - o estado aberto/triado é replay do ledger append-only, e linha corrompida no
    meio não derruba o resto;
  - o hook só fala quando há forma de queixa E alvo do harness, e só uma vez por
    sessão; falha aberto em tudo.

Sem deps de terceiros — rode com `python3 tests/test_cepa_feedback.py`.
"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "common" / "bin" / "cepa-feedback"
HOOK = REPO / "common" / "hooks" / "feedback-nudge.py"
HOJE = datetime.now(timezone.utc).strftime("%Y%m%d")

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


class Caixa:
    """Ledger isolado + um git repo descartável para servir de contexto."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.ledger = base / "ledger"
        self.repo = base / "projeto-x"
        self.repo.mkdir()
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        subprocess.run(["git", "init", "-q", "-b", "session/exemplo", "."],
                       cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "init"],
                       cwd=self.repo, check=True, env=env)
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "session-mode").write_text(
            "modo: construcao\norcamento: null\n", encoding="utf-8")
        return self

    def __exit__(self, *a):
        self.tmp.cleanup()

    def env(self, **extra):
        return {**os.environ,
                "CEPA_FEEDBACK_DIR": str(self.ledger),
                "CEPA_TELEMETRY_DIR": str(Path(self.tmp.name) / "tel"),
                **extra}

    def cli(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(BIN), *args],
                              cwd=str(cwd or self.repo), env=self.env(),
                              capture_output=True, text=True)

    def linhas(self):
        out = []
        for arq in sorted(self.ledger.glob("feedback-*.jsonl")):
            out += [json.loads(x) for x in arq.read_text(encoding="utf-8").splitlines() if x.strip()]
        return out

    def hook(self, prompt, session_id="s1", cwd=None, **extra):
        payload = {"prompt": prompt, "cwd": str(cwd or self.repo),
                   "session_id": session_id}
        return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                              env=self.env(**extra), capture_output=True, text=True)


# --------------------------------------------------------------- registro

def test_add_grava_verbatim_com_contexto():
    with Caixa() as c:
        texto = "o gate barrou meu commit legítimo e eu tive que desligar o modo"
        p = c.cli("add", texto, "--alvo", "modo-escrita-gate", "--origem", "skill")
        check("add: rc=0", p.returncode == 0, p.stderr)
        evs = c.linhas()
        check("add: uma linha no ledger", len(evs) == 1, evs)
        ev = evs[0]
        check("add: texto verbatim", ev["texto"] == texto, ev.get("texto"))
        check("add: alvo registrado", ev["alvo"] == "modo-escrita-gate", ev.get("alvo"))
        check("add: origem registrada", ev["origem"] == "skill", ev.get("origem"))
        check("add: repo capturado sozinho", ev["repo"] == "projeto-x", ev.get("repo"))
        check("add: branch capturado sozinho",
              ev["branch"] == "session/exemplo", ev.get("branch"))
        check("add: modo da sessão capturado", ev["modo"] == "construcao", ev.get("modo"))
        check("add: id do dia", ev["id"] == f"fb-{HOJE}-1", ev.get("id"))


def test_add_recusa_vazio_e_curto():
    with Caixa() as c:
        p = c.cli("add", "   ")
        check("add: vazio recusado (rc=2)", p.returncode == 2, p.returncode)
        p = c.cli("add", "ruim")
        check("add: uma palavra recusada (rc=2)", p.returncode == 2, p.returncode)
        check("add: recusa diz o mínimo", "mínimo 12" in p.stderr, p.stderr)
        check("add: recusa não grava nada", not c.ledger.exists() or c.linhas() == [],
              c.linhas() if c.ledger.exists() else "sem dir")


def test_ids_sequenciais_no_dia():
    with Caixa() as c:
        for i in range(3):
            c.cli("add", f"queixa numero {i} sobre o relatório final")
        ids = [e["id"] for e in c.linhas()]
        check("id: sequência no dia",
              ids == [f"fb-{HOJE}-{n}" for n in (1, 2, 3)], ids)


def test_fora_de_repo_git_nao_quebra():
    with Caixa() as c:
        fora = Path(c.tmp.name) / "sem-git"
        fora.mkdir()
        p = c.cli("add", "reclamação feita de um diretório qualquer", cwd=fora)
        check("add: fora de git ainda grava", p.returncode == 0, p.stderr)
        ev = c.linhas()[0]
        check("add: fora de git não inventa branch", ev["branch"] is None, ev.get("branch"))


# ---------------------------------------------------------------- triagem

def test_triar_marca_e_recusa_repeticao():
    with Caixa() as c:
        c.cli("add", "o comando pergunta três vezes a mesma coisa")
        fid = f"fb-{HOJE}-1"
        p = c.cli("triar", fid, "--destino", "BACKLOG.md § Atrito de decisão")
        check("triar: rc=0", p.returncode == 0, p.stderr)
        ev = c.linhas()[-1]
        check("triar: grava linha de triagem", ev["tipo"] == "triagem", ev)
        check("triar: cita o id", ev["id"] == fid, ev)
        check("triar: registro original intacto",
              c.linhas()[0]["texto"] == "o comando pergunta três vezes a mesma coisa",
              c.linhas()[0])
        p = c.cli("triar", fid, "--destino", "outro lugar")
        check("triar: re-triagem recusada (rc=4)", p.returncode == 4, p.returncode)
        check("triar: recusa nomeia o destino anterior",
              "Atrito de decisão" in p.stderr, p.stderr)


PLANO = """schema_version: 2
mode: single-track
program: WEGO
source: teste
items:
- id: WEGO-1
  title: primeiro
  why: porque
  status: pending
  blocked_by: []
  human_pending: null
  evidence: null
"""


def test_triar_com_plano_acrescenta_a_fila():
    with Caixa() as c:
        (c.repo / ".claude" / "programs" / "WEGO").mkdir(parents=True)
        (c.repo / ".claude" / "programs" / "WEGO" / "plan.yaml").write_text(
            PLANO, encoding="utf-8")
        texto = "o relatório final do drain não nomeia o card que travou, custou 20min"
        c.cli("add", texto)
        fid = f"fb-{HOJE}-1"
        p = c.cli("triar", fid, "--destino", "fila WEGO", "--plano", "WEGO",
                  "--why", "achado real de sessão")
        check("triar --plano: rc=0", p.returncode == 0, p.stderr)
        check("triar --plano: confirma a entrada na fila",
              "também entrou na fila" in p.stdout, p.stdout)
        fila = (c.repo / ".claude" / "programs" / "WEGO" / "plan.yaml").read_text(
            encoding="utf-8")
        check("triar --plano: item novo no plan.yaml", fid in fila, fila)
        check("triar --plano: título é o começo do texto do feedback",
              texto[:60] in fila, fila)


def test_triar_com_plano_ja_na_fila_nao_e_erro():
    with Caixa() as c:
        (c.repo / ".claude" / "programs" / "WEGO").mkdir(parents=True)
        plano_com_item = PLANO.replace("id: WEGO-1", f"id: fb-{HOJE}-1")
        (c.repo / ".claude" / "programs" / "WEGO" / "plan.yaml").write_text(
            plano_com_item, encoding="utf-8")
        c.cli("add", "queixa qualquer que já tem item homônimo na fila")
        fid = f"fb-{HOJE}-1"
        p = c.cli("triar", fid, "--destino", "fila WEGO", "--plano", "WEGO")
        check("triar --plano: id já na fila não é erro (rc=0)",
              p.returncode == 0, p.stderr)
        check("triar --plano: avisa sem alarde", "já estava na fila" in p.stdout,
              p.stdout)


def test_triar_sem_plano_nao_toca_em_fila_nenhuma():
    with Caixa() as c:
        (c.repo / ".claude" / "programs" / "WEGO").mkdir(parents=True)
        (c.repo / ".claude" / "programs" / "WEGO" / "plan.yaml").write_text(
            PLANO, encoding="utf-8")
        c.cli("add", "queixa comum, sem pedir fila nenhuma desta vez")
        fid = f"fb-{HOJE}-1"
        p = c.cli("triar", fid, "--destino", "BACKLOG.md § X")
        check("triar sem --plano: rc=0", p.returncode == 0, p.stderr)
        fila = (c.repo / ".claude" / "programs" / "WEGO" / "plan.yaml").read_text(
            encoding="utf-8")
        check("triar sem --plano: fila intocada", fid not in fila, fila)


def test_triar_recusa_id_inexistente_e_destino_vazio():
    with Caixa() as c:
        c.cli("add", "alguma queixa suficientemente longa aqui")
        p = c.cli("triar", "fb-19700101-9", "--destino", "x")
        check("triar: id inexistente (rc=3)", p.returncode == 3, p.returncode)
        p = c.cli("triar", f"fb-{HOJE}-1", "--destino", "   ")
        check("triar: destino vazio (rc=2)", p.returncode == 2, p.returncode)


# ------------------------------------------------------------------ lista

def test_list_replay_do_ledger():
    with Caixa() as c:
        c.cli("add", "primeira queixa longa o suficiente para passar")
        c.cli("add", "segunda queixa longa o suficiente para passar")
        c.cli("triar", f"fb-{HOJE}-1", "--destino", "BACKLOG.md § X")
        p = c.cli("list", "--json")
        abertos = json.loads(p.stdout)
        check("list: default só os abertos", [r["id"] for r in abertos] == [f"fb-{HOJE}-2"],
              [r["id"] for r in abertos])
        p = c.cli("list", "--status", "todos", "--json")
        todos = json.loads(p.stdout)
        check("list: --todos traz os dois", len(todos) == 2, len(todos))
        triado = [r for r in todos if r["id"] == f"fb-{HOJE}-1"][0]
        check("list: triado carrega o destino",
              triado["triagem"]["destino"] == "BACKLOG.md § X", triado.get("triagem"))
        p = c.cli("list", "--status", "todos", "--repo", "outro-repo", "--json")
        check("list: filtro por repo", json.loads(p.stdout) == [], p.stdout)


def test_linha_corrompida_nao_derruba_o_resto():
    with Caixa() as c:
        c.cli("add", "queixa que precisa sobreviver à linha quebrada")
        arq = next(c.ledger.glob("feedback-*.jsonl"))
        with open(arq, "a", encoding="utf-8") as fh:
            fh.write("{isso não é json\n\n")
        p = c.cli("list", "--json")
        check("ledger: linha corrompida é pulada", p.returncode == 0, p.stderr)
        check("ledger: o registro bom sobrevive", len(json.loads(p.stdout)) == 1, p.stdout)


def test_list_sem_nada_registrado():
    with Caixa() as c:
        p = c.cli("list", "--sem-cor")
        check("list: ledger vazio não é erro", p.returncode == 0, p.stderr)
        check("list: ledger vazio diz que está vazio",
              "Nenhum feedback" in p.stdout, p.stdout)


# -------------------------------------------------------------------- hook

def test_hook_injeta_em_queixa_sobre_o_harness():
    with Caixa() as c:
        p = c.hook("esse gate me irrita, barrou um commit legítimo")
        check("hook: queixa + alvo injeta", "feedback-capture" in p.stdout, p.stdout)
        check("hook: nunca bloqueia", p.returncode == 0, p.returncode)


def test_hook_calado_sem_uma_das_duas_condicoes():
    with Caixa() as c:
        p = c.hook("implemente o endpoint de assinatura", session_id="a")
        check("hook: prompt normal é silêncio", p.stdout.strip() == "", p.stdout)
        p = c.hook("essa API do fornecedor está errada e me irrita", session_id="b")
        check("hook: queixa sem alvo do harness é silêncio",
              p.stdout.strip() == "", p.stdout)
        p = c.hook("rode o /board-flow:drain nos cards de hoje", session_id="c")
        check("hook: alvo sem queixa é silêncio", p.stdout.strip() == "", p.stdout)


def test_hook_uma_vez_por_sessao():
    with Caixa() as c:
        p1 = c.hook("o comando de novo? isso me irrita", session_id="s9")
        p2 = c.hook("e o hook continua chato pra caramba", session_id="s9")
        p3 = c.hook("e o hook continua chato pra caramba", session_id="s10")
        check("hook: primeira vez fala", "feedback" in p1.stdout, p1.stdout)
        check("hook: segunda vez na MESMA sessão cala", p2.stdout.strip() == "", p2.stdout)
        check("hook: sessão nova volta a falar", "feedback" in p3.stdout, p3.stdout)


def test_hook_kill_switch_e_falha_aberta():
    with Caixa() as c:
        p = c.hook("esse gate me irrita demais", CEPA_FEEDBACK_NUDGE="off")
        check("hook: kill switch silencia", p.stdout.strip() == "", p.stdout)
        p = subprocess.run([sys.executable, str(HOOK)], input="isso não é json",
                           env=c.env(), capture_output=True, text=True)
        check("hook: payload inválido não quebra o turno", p.returncode == 0, p.stderr)
        check("hook: payload inválido não injeta", p.stdout.strip() == "", p.stdout)


def main():
    print("test_cepa_feedback")
    for fn in (test_add_grava_verbatim_com_contexto, test_add_recusa_vazio_e_curto,
               test_ids_sequenciais_no_dia, test_fora_de_repo_git_nao_quebra,
               test_triar_marca_e_recusa_repeticao,
               test_triar_com_plano_acrescenta_a_fila,
               test_triar_com_plano_ja_na_fila_nao_e_erro,
               test_triar_sem_plano_nao_toca_em_fila_nenhuma,
               test_triar_recusa_id_inexistente_e_destino_vazio,
               test_list_replay_do_ledger, test_linha_corrompida_nao_derruba_o_resto,
               test_list_sem_nada_registrado,
               test_hook_injeta_em_queixa_sobre_o_harness,
               test_hook_calado_sem_uma_das_duas_condicoes,
               test_hook_uma_vez_por_sessao, test_hook_kill_switch_e_falha_aberta):
        fn()
    if failures:
        print(f"\n{len(failures)} falha(s): {', '.join(failures)}")
        return 1
    print("\ntudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
