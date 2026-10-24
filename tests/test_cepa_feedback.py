#!/usr/bin/env python3
"""Tests for the harness feedback notebook — bin/cepa-feedback + feedback-nudge.

The behavior these cases exist to hold is not "the file is written".
It is the set of refusals that keeps the ledger from becoming a dead file:

  - an empty record or a one-word record is REFUSED — a one-word complaint cannot be
    reconstructed months later, and a ledger full of "bad" has the same value as an
    empty ledger, with the disadvantage of looking full;
  - the text goes in VERBATIM (the bin summarizes nothing);
  - repo, branch and mode go in by themselves — a record that depends on the owner remembering
    where they were is born useless;
  - triage without destination, of a nonexistent id, or a SECOND triage of the same id are
    refused: re-triage would silently erase the previous decision;
  - the open/triaged state is a replay of the append-only ledger, and a corrupted line in the
    middle does not bring down the rest;
  - the hook only speaks when there is a complaint shape AND a harness target, and only once per
    session; fails open on everything.

No third-party deps — run with `python3 tests/test_cepa_feedback.py`.
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
TODAY = datetime.now(timezone.utc).strftime("%Y%m%d")

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


class Box:
    """Isolated ledger + a disposable git repo to serve as context."""

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

    def lines(self):
        out = []
        for file in sorted(self.ledger.glob("feedback-*.jsonl")):
            out += [json.loads(x) for x in file.read_text(encoding="utf-8").splitlines() if x.strip()]
        return out

    def hook(self, prompt, session_id="s1", cwd=None, **extra):
        payload = {"prompt": prompt, "cwd": str(cwd or self.repo),
                   "session_id": session_id}
        return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                              env=self.env(**extra), capture_output=True, text=True)


# --------------------------------------------------------------- record

def test_add_writes_verbatim_with_context():
    with Box() as c:
        plain_text = "o gate barrou meu commit legítimo e eu tive que desligar o modo"
        p = c.cli("add", plain_text, "--target", "write-mode-gate", "--origin", "skill")
        check("add: rc=0", p.returncode == 0, p.stderr)
        evs = c.lines()
        check("add: uma linha no ledger", len(evs) == 1, evs)
        ev = evs[0]
        check("add: texto verbatim", ev["texto"] == plain_text, ev.get("texto"))
        check("add: alvo registrado", ev["alvo"] == "write-mode-gate", ev.get("alvo"))
        check("add: origem registrada", ev["origem"] == "skill", ev.get("origem"))
        check("add: repo capturado sozinho", ev["repo"] == "projeto-x", ev.get("repo"))
        check("add: branch capturado sozinho",
              ev["branch"] == "session/exemplo", ev.get("branch"))
        check("add: modo da sessão capturado", ev["modo"] == "construcao", ev.get("modo"))
        check("add: id do dia", ev["id"] == f"fb-{TODAY}-1", ev.get("id"))


def test_add_refuses_empty_and_short():
    with Box() as c:
        p = c.cli("add", "   ")
        check("add: vazio recusado (rc=2)", p.returncode == 2, p.returncode)
        p = c.cli("add", "ruim")
        check("add: uma palavra recusada (rc=2)", p.returncode == 2, p.returncode)
        check("add: recusa diz o mínimo", "mínimo 12" in p.stderr, p.stderr)
        check("add: recusa não grava nada", not c.ledger.exists() or c.lines() == [],
              c.lines() if c.ledger.exists() else "sem dir")


def test_sequential_ids_in_the_day():
    with Box() as c:
        for i in range(3):
            c.cli("add", f"queixa numero {i} sobre o relatório final")
        ids = [e["id"] for e in c.lines()]
        check("id: sequência no dia",
              ids == [f"fb-{TODAY}-{n}" for n in (1, 2, 3)], ids)


def test_outside_git_repo_does_not_break():
    with Box() as c:
        outside = Path(c.tmp.name) / "sem-git"
        outside.mkdir()
        p = c.cli("add", "reclamação feita de um diretório qualquer", cwd=outside)
        check("add: fora de git ainda grava", p.returncode == 0, p.stderr)
        ev = c.lines()[0]
        check("add: fora de git não inventa branch", ev["branch"] is None, ev.get("branch"))


# ---------------------------------------------------------------- triage

def test_triage_marks_and_refuses_repetition():
    with Box() as c:
        c.cli("add", "o comando pergunta três vezes a mesma coisa")
        fid = f"fb-{TODAY}-1"
        p = c.cli("triage", fid, "--destination", "BACKLOG.md § Atrito de decisão")
        check("triar: rc=0", p.returncode == 0, p.stderr)
        ev = c.lines()[-1]
        check("triar: grava linha de triagem", ev["tipo"] == "triagem", ev)
        check("triar: cita o id", ev["id"] == fid, ev)
        check("triar: registro original intacto",
              c.lines()[0]["texto"] == "o comando pergunta três vezes a mesma coisa",
              c.lines()[0])
        p = c.cli("triage", fid, "--destination", "outro lugar")
        check("triar: re-triagem recusada (rc=4)", p.returncode == 4, p.returncode)
        check("triar: recusa nomeia o destino anterior",
              "Atrito de decisão" in p.stderr, p.stderr)


PLAN_TEXT = """schema_version: 2
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


def test_triage_with_plan_appends_to_the_queue():
    with Box() as c:
        (c.repo / ".claude" / "programs" / "WEGO").mkdir(parents=True)
        (c.repo / ".claude" / "programs" / "WEGO" / "plan.yaml").write_text(
            PLAN_TEXT, encoding="utf-8")
        plain_text = "o relatório final do drain não nomeia o card que travou, custou 20min"
        c.cli("add", plain_text)
        fid = f"fb-{TODAY}-1"
        p = c.cli("triage", fid, "--destination", "fila WEGO", "--queue", "WEGO",
                  "--why", "achado real de sessão")
        check("triar --plano: rc=0", p.returncode == 0, p.stderr)
        check("triar --plano: confirma a entrada na fila",
              "também entrou na fila" in p.stdout, p.stdout)
        queue = (c.repo / ".claude" / "programs" / "WEGO" / "plan.yaml").read_text(
            encoding="utf-8")
        check("triar --plano: item novo no plan.yaml", fid in queue, queue)
        check("triar --plano: título é o começo do texto do feedback",
              plain_text[:60] in queue, queue)


def test_triage_with_plan_already_in_queue_is_not_an_error():
    with Box() as c:
        (c.repo / ".claude" / "programs" / "WEGO").mkdir(parents=True)
        plan_with_item = PLAN_TEXT.replace("id: WEGO-1", f"id: fb-{TODAY}-1")
        (c.repo / ".claude" / "programs" / "WEGO" / "plan.yaml").write_text(
            plan_with_item, encoding="utf-8")
        c.cli("add", "queixa qualquer que já tem item homônimo na fila")
        fid = f"fb-{TODAY}-1"
        p = c.cli("triage", fid, "--destination", "fila WEGO", "--queue", "WEGO")
        check("triar --plano: id já na fila não é erro (rc=0)",
              p.returncode == 0, p.stderr)
        check("triar --plano: avisa sem alarde", "já estava na fila" in p.stdout,
              p.stdout)


def test_triage_with_plan_real_error_does_not_undo_the_triage():
    """`add` failing for a REAL reason (not the "already there" of exit 4) must not
    erase the triage that was already recorded — writing the triage event
    and trying to enter the queue are two steps, and the first has already
    happened when the second fails. The proof stays in the ledger FILE, not
    only in the process output: a `write()` that only runs conditioned on the success
    of `add` would go unnoticed if the assertion looked only at stdout."""
    with Box() as c:
        # `mode: waves` is a WAVES plan (/maestro:program-plan) — the
        # `cepa-plan add` refuses with a real error (exit 3), different from the
        # exit 4 of "id already in the queue".
        wave_plan = PLAN_TEXT.replace("mode: single-track", "mode: waves")
        (c.repo / ".claude" / "programs" / "WEGO").mkdir(parents=True)
        (c.repo / ".claude" / "programs" / "WEGO" / "plan.yaml").write_text(
            wave_plan, encoding="utf-8")
        c.cli("add", "queixa que precisa sobreviver a um erro real do add")
        fid = f"fb-{TODAY}-1"
        p = c.cli("triage", fid, "--destination", "fila WEGO", "--queue", "WEGO")
        check("triar com erro real do add: rc=0 (a triagem em si teve sucesso)",
              p.returncode == 0, p.stderr)
        check("triar com erro real do add: avisa que NÃO entrou na fila",
              "NÃO entrou na fila" in p.stderr, p.stderr)
        # The proof that the triage survived is in the FILE, not in stdout.
        events = c.lines()
        triages = [e for e in events if e.get("tipo") == "triagem" and e.get("id") == fid]
        check("triar com erro real do add: evento de triagem GRAVADO no ledger",
              len(triages) == 1 and triages[0]["destino"] == "fila WEGO",
              events)


def test_triage_without_plan_touches_no_queue():
    with Box() as c:
        (c.repo / ".claude" / "programs" / "WEGO").mkdir(parents=True)
        (c.repo / ".claude" / "programs" / "WEGO" / "plan.yaml").write_text(
            PLAN_TEXT, encoding="utf-8")
        c.cli("add", "queixa comum, sem pedir fila nenhuma desta vez")
        fid = f"fb-{TODAY}-1"
        p = c.cli("triage", fid, "--destination", "BACKLOG.md § X")
        check("triar sem --plano: rc=0", p.returncode == 0, p.stderr)
        queue = (c.repo / ".claude" / "programs" / "WEGO" / "plan.yaml").read_text(
            encoding="utf-8")
        check("triar sem --plano: fila intocada", fid not in queue, queue)


def test_triage_refuses_unknown_id_and_empty_destination():
    with Box() as c:
        c.cli("add", "alguma queixa suficientemente longa aqui")
        p = c.cli("triage", "fb-19700101-9", "--destination", "x")
        check("triar: id inexistente (rc=3)", p.returncode == 3, p.returncode)
        p = c.cli("triage", f"fb-{TODAY}-1", "--destination", "   ")
        check("triar: destino vazio (rc=2)", p.returncode == 2, p.returncode)


# ------------------------------------------------------------------ list

def test_list_replay_of_the_ledger():
    with Box() as c:
        c.cli("add", "primeira queixa longa o suficiente para passar")
        c.cli("add", "segunda queixa longa o suficiente para passar")
        c.cli("triage", f"fb-{TODAY}-1", "--destination", "BACKLOG.md § X")
        p = c.cli("list", "--json")
        open_ones = json.loads(p.stdout)
        check("list: default só os abertos", [r["id"] for r in open_ones] == [f"fb-{TODAY}-2"],
              [r["id"] for r in open_ones])
        p = c.cli("list", "--status", "todos", "--json")
        all_ = json.loads(p.stdout)
        check("list: --todos traz os dois", len(all_) == 2, len(all_))
        triaged = [r for r in all_ if r["id"] == f"fb-{TODAY}-1"][0]
        check("list: triado carrega o destino",
              triaged["triagem"]["destino"] == "BACKLOG.md § X", triaged.get("triagem"))
        p = c.cli("list", "--status", "todos", "--repo", "outro-repo", "--json")
        check("list: filtro por repo", json.loads(p.stdout) == [], p.stdout)


def test_corrupted_line_does_not_bring_down_the_rest():
    with Box() as c:
        c.cli("add", "queixa que precisa sobreviver à linha quebrada")
        file = next(c.ledger.glob("feedback-*.jsonl"))
        with open(file, "a", encoding="utf-8") as fh:
            fh.write("{isso não é json\n\n")
        p = c.cli("list", "--json")
        check("ledger: linha corrompida é pulada", p.returncode == 0, p.stderr)
        check("ledger: o registro bom sobrevive", len(json.loads(p.stdout)) == 1, p.stdout)


def test_list_with_nothing_recorded():
    with Box() as c:
        p = c.cli("list", "--no-color")
        check("list: ledger vazio não é erro", p.returncode == 0, p.stderr)
        check("list: ledger vazio diz que está vazio",
              "Nenhum feedback" in p.stdout, p.stdout)


# -------------------------------------------------------------------- hook

def test_hook_injects_on_complaint_about_the_harness():
    with Box() as c:
        p = c.hook("esse gate me irrita, barrou um commit legítimo")
        check("hook: queixa + alvo injeta", "feedback-capture" in p.stdout, p.stdout)
        check("hook: nunca bloqueia", p.returncode == 0, p.returncode)


def test_hook_silent_without_one_of_the_two_conditions():
    with Box() as c:
        p = c.hook("implemente o endpoint de assinatura", session_id="a")
        check("hook: prompt normal é silêncio", p.stdout.strip() == "", p.stdout)
        p = c.hook("essa API do fornecedor está errada e me irrita", session_id="b")
        check("hook: queixa sem alvo do harness é silêncio",
              p.stdout.strip() == "", p.stdout)
        p = c.hook("rode o /board-flow:drain nos cards de hoje", session_id="c")
        check("hook: alvo sem queixa é silêncio", p.stdout.strip() == "", p.stdout)


def test_hook_once_per_session():
    with Box() as c:
        p1 = c.hook("o comando de novo? isso me irrita", session_id="s9")
        p2 = c.hook("e o hook continua chato pra caramba", session_id="s9")
        p3 = c.hook("e o hook continua chato pra caramba", session_id="s10")
        check("hook: primeira vez fala", "feedback" in p1.stdout, p1.stdout)
        check("hook: segunda vez na MESMA sessão cala", p2.stdout.strip() == "", p2.stdout)
        check("hook: sessão nova volta a falar", "feedback" in p3.stdout, p3.stdout)


def test_hook_kill_switch_and_fail_open():
    with Box() as c:
        p = c.hook("esse gate me irrita demais", CEPA_FEEDBACK_NUDGE="off")
        check("hook: kill switch silencia", p.stdout.strip() == "", p.stdout)
        p = subprocess.run([sys.executable, str(HOOK)], input="isso não é json",
                           env=c.env(), capture_output=True, text=True)
        check("hook: payload inválido não quebra o turno", p.returncode == 0, p.stderr)
        check("hook: payload inválido não injeta", p.stdout.strip() == "", p.stdout)


# Format checked in .claude/session-log.md (the prompt that UserPromptSubmit
# received in 2026-09): the end-of-task warning comes alone in the prompt.
WARNING = ("<task-notification>\n<task-id>a1b2c3d4</task-id>\n"
         "<status>completed</status>\n<summary>Agent \"completion-auditor\" "
         "completed</summary>\n<result>Veredito COMPLETE. O gate não funciona "
         "fora do git e o hook está errado no caso X.</result>\n"
         "</task-notification>")


def test_hook_ignores_subagent_warning():
    with Box() as c:
        p = c.hook(WARNING, session_id="n1")
        check("hook: aviso de subagente sozinho é silêncio",
              p.stdout.strip() == "", p.stdout)
        p = c.hook(WARNING, session_id="n1")
        p = c.hook("esse gate me irrita, barrou um commit legítimo", session_id="n1")
        check("hook: aviso não gasta o aviso único da sessão",
              "feedback-capture" in p.stdout, p.stdout)
        p = c.hook(WARNING + "\nesse gate me irrita demais", session_id="n2")
        check("hook: queixa do dono junto do aviso ainda conta",
              "feedback-capture" in p.stdout, p.stdout)
        p = c.hook(WARNING + "\nrode o próximo item", session_id="n3")
        check("hook: fala neutra do dono junto do aviso é silêncio",
              p.stdout.strip() == "", p.stdout)
        cut = WARNING.replace("</task-notification>", "")
        p = c.hook(cut, session_id="n4")
        check("hook: aviso sem fechamento é silêncio", p.stdout.strip() == "", p.stdout)
        p = c.hook(WARNING + "\n" + WARNING, session_id="n5")
        check("hook: dois avisos seguidos são silêncio", p.stdout.strip() == "", p.stdout)
        long_ = WARNING.replace("Veredito", "x" * 5000 + " Veredito")
        p = c.hook(long_ + "\nesse gate me irrita demais", session_id="n6")
        check("hook: aviso longo não esconde a queixa curta do dono",
              "feedback-capture" in p.stdout, p.stdout)


def main():
    print("test_cepa_feedback")
    for fn in (test_add_writes_verbatim_with_context, test_add_refuses_empty_and_short,
               test_sequential_ids_in_the_day, test_outside_git_repo_does_not_break,
               test_triage_marks_and_refuses_repetition,
               test_triage_with_plan_appends_to_the_queue,
               test_triage_with_plan_already_in_queue_is_not_an_error,
               test_triage_with_plan_real_error_does_not_undo_the_triage,
               test_triage_without_plan_touches_no_queue,
               test_triage_refuses_unknown_id_and_empty_destination,
               test_list_replay_of_the_ledger, test_corrupted_line_does_not_bring_down_the_rest,
               test_list_with_nothing_recorded,
               test_hook_injects_on_complaint_about_the_harness,
               test_hook_silent_without_one_of_the_two_conditions,
               test_hook_once_per_session, test_hook_kill_switch_and_fail_open,
               test_hook_ignores_subagent_warning):
        fn()
    if failures:
        print(f"\n{len(failures)} falha(s): {', '.join(failures)}")
        return 1
    print("\ntudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
