#!/usr/bin/env python3
"""cepa-until decidir — the end of the run asks, instead of only telling.

On 30/09 the owner read at the end of a run "the queue ended, and 14 stayed deferred
(each with the reason, in the report)" and "It stays with you: WEGO-2336 (the reason
is on each one's line, in Items)", and asked what to do with that. The
landing appeared as a command to copy, and the question that blocked
WEGO-2336 was in the middle of 600 characters of evidence.

What these cases prove:

  - `cepa-plan finish --pergunta` records the item's closed question, and
    `queue` returns it together with the deferred item;
  - `cepa-plan responde` turns a `blocked` back into `pending` and closes the human
    route, with the owner's answer in the evidence, and ONLY in a terminal (a `claude -p`
    agent has no TTY and does not close the route in place of the human);
  - `decide` asks to land and each item that only the owner unblocks, applies
    each answer and leaves the rest for later with the command to come back;
  - the real run, in a terminal, ends by asking; without a terminal, it lists
    the pending items with the `cepa-until decidir` command.

Run with `python3 tests/test_cepa_until_decide.py`.
"""

import importlib.machinery
import importlib.util
import json
import os
import pty
import re
import select
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    CEPA_UNTIL, fake_claude, item, build_repo, run_until)

CEPA_PLAN = CEPA_UNTIL.parent / "cepa-plan"
FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def load_module(color="nunca"):
    """Loads cepa-until with the terminal decoration turned off: the in-process
    cases read the plain text, even when they run in a terminal. With
    `color="sempre"` it turns on, for the case that proves the decorated layout."""
    before = os.environ.get("CEPA_UNTIL_COR")
    os.environ["CEPA_UNTIL_COR"] = color
    try:
        loader = importlib.machinery.SourceFileLoader("cepa_until",
                                                      str(CEPA_UNTIL))
        spec = importlib.util.spec_from_loader("cepa_until", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
    finally:
        if before is None:
            del os.environ["CEPA_UNTIL_COR"]
        else:
            os.environ["CEPA_UNTIL_COR"] = before
    return mod


ANSI = re.compile(r"\x1b\[[0-9;]*m")


def test_decide_on_terminal_draws_one_card_per_question():
    """The owner (23/10): "the questions asked at the end of cepa-until are still
    with very poor formatting". In the terminal each question is a
    card: ruler `┌─ i/n · id`, left border `│`, labels in a column,
    the question marked with `?`, the recommendation with `✦`, the menu in chips that
    fit the width and the closing `└─`. The sentences the pty answers stay
    whole, with no color in the middle. Outside the terminal none of this shows up."""
    m = load_module(color="sempre")
    check("a decoração está ligada", m.SCREEN.enabled)
    deferred_ones = [
        {"id": "W-1", "title": "Reenviar o envelope quando o e-mail muda",
         "reason": "bloqueado-antes", "question": "Mantenho o reenvio?",
         "evidence": "o gateway devolve 409"},
        {"id": "W-2", "title": "Rotacionar o segredo", "reason": "human_pending",
         "question": None, "human_pending": "rotacionar no cofre",
         "evidence": ""},
        {"id": "W-3", "title": "outro", "reason": "reservado"},
    ]
    analysis = {"aterrissar": {"recomendo": "sim", "porque": "build verde"},
               "itens": {"W-1": {"recomendo": "não", "porque": "duplica",
                                 "contexto": "dois clientes pediram",
                                 "instrucao": "cancelar e recriar"}}}
    state_dict = {"estado": "fim", "acoes": [{"id": "aterrissar", "frase": "levar X"}]}
    prompts, screen = [], []

    def question_text(p):
        prompts.append(p)
        return {1: "s", 2: "n", 3: "", 4: ""}.get(len(prompts), "")
    m.decide(Path("/nao/existe"), "fila", "run1", state_dict, deferred_ones, analysis,
             question=question_text, output=screen.append,
             answer=lambda i, t, keep=False: (0, f"{i} voltou"),
             land=lambda: 0)
    raw = "\n".join(screen)
    plain_text = ANSI.sub("", raw)
    check("tem cor", "\x1b[" in raw)
    check("régua de abertura com a contagem",
          "── 3 question(s) for you ─" in plain_text, plain_text)
    check("cartão de aterrissar com a recomendação marcada",
          "┌─ aterrissar ─" in plain_text and "│  ✦ Recommend yes: build verde"
          in plain_text, plain_text)
    check("um cartão por item, com i/n e id na régua",
          "┌─ 1/2 · W-1 ─" in plain_text and "┌─ 2/2 · W-2 ─" in plain_text, plain_text)
    check("rótulos numa coluna, com o curto no lugar do longo",
          "│  Stopped because the agent marked" in plain_text
          and "│  Context         dois clientes" in plain_text
          and "│  Task            rotacionar no cofre" in plain_text, plain_text)
    check("a pergunta marcada e a instrução embaixo dela",
          "│  ? Mantenho o reenvio?" in plain_text
          and "│    If yes, the next run receives: cancelar e recriar" in plain_text,
          plain_text)
    check("recomendação do item com ✦", "│  ✦ Recommend no: duplica" in plain_text,
          plain_text)
    check("menu em chips dentro do cartão, com a recomendada marcada",
          "│  [s] yes · [n] no (recommended) · [t] I write the answer · "
          "[d] discard the item" in plain_text
          and "[e] technical detail" in plain_text, plain_text)
    check("o prompt fica dentro do cartão e o cartão fecha",
          ANSI.sub("", prompts[1]) == "│  ▸ " and plain_text.count("└─") == 3,
          (prompts, plain_text))
    check("o gravado aparece com ✓ no cartão", "│  ✓ W-1 voltou" in plain_text,
          plain_text)
    check("fecho com placar e o comando de volta",
          "── closing ─" in plain_text and "answered now 2" in plain_text
          and "for later 1" in plain_text
          and "cepa-until decide fila/run1" in plain_text, plain_text)
    triggers = ("Land now? [y/N/q] ", "[t] I write the answer",
                "Anything to add, in one line? [Enter skips] ")
    all_ = raw + "\n".join(prompts)
    check("as frases que o pty responde ficam inteiras, sem cor no meio",
          all(g in all_ for g in triggers), all_)
    check("a versão sem terminal não tem cartão",
          "┌─" not in "\n".join(_decide_pure(deferred_ones, analysis, state_dict)))


def _decide_pure(deferred_ones, analysis, state_dict):
    m = load_module()
    screen = []
    answers = iter(["s", "n", "", ""])
    m.decide(Path("/nao/existe"), "fila", "run1", state_dict, deferred_ones, analysis,
             question=lambda _p: next(answers, ""), output=screen.append,
             answer=lambda i, t, keep=False: (0, "ok"),
             land=lambda: 0)
    return screen


def on_tty(cmd, cwd, inputs=(), env=None, timeout=120):
    """Runs `cmd` in a pseudo-terminal and answers each question when it
    appears: `inputs` is a list of (excerpt the screen shows, answer)."""
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(cwd)
        os.execve(cmd[0], cmd, env or dict(os.environ))
    out_text, queue, end = "", list(inputs), time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.5)
        if r:
            try:
                datum = os.read(fd, 4096)
            except OSError:
                break
            if not datum:
                break
            out_text += datum.decode(errors="replace")
        while queue and queue[0][0] in out_text:
            trigger, reply = queue.pop(0)
            # Consumes the trigger so the next equal question does not match on it.
            out_text = out_text.replace(trigger, f"<{trigger}>", 1)
            if isinstance(reply, str):
                reply = reply.encode()
            os.write(fd, reply + b"\n")
    # Past the wait, the child may still sit at a prompt nobody answered (an
    # anchor in `inputs` that the screen never showed): kill it, or waitpid
    # blocks forever and the suite hangs instead of failing (2026-11-06: 10h).
    if time.time() >= end:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        out_text += f"\n<on_tty: no answer within {timeout}s; still waiting: " \
                    f"{[t for t, _ in queue]}>"
    _, st = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(st), out_text


def plan_of(root):
    return root / ".claude" / "programs" / "fila" / "plan.yaml"


def items_of(root):
    return {it["id"]: it for it in
            yaml.safe_load(plan_of(root).read_text())["items"]}


def test_finish_writes_the_question_and_queue_returns_it():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        p = subprocess.run(
            [sys.executable, str(CEPA_PLAN), "finish", "fila", "a1",
             "--status", "blocked", "--evidence", "não há produção para medir",
             "--impede", "ainda não há usuários reais para medir",
             "--pergunta", "Fecho o card como medir depois do go-live?",
             "--repo", str(root)], capture_output=True, text=True)
        check("finish com --pergunta sai 0", p.returncode == 0, p.stderr)
        check("...e grava owner_question",
              items_of(root)["a1"].get("owner_question")
              == "Fecho o card como medir depois do go-live?",
              items_of(root)["a1"])
        q = subprocess.run(
            [sys.executable, str(CEPA_PLAN), "queue", "fila", "--json",
             "--repo", str(root)], capture_output=True, text=True)
        deferred = json.loads(q.stdout)["deferred"][0]
        check("o queue devolve a pergunta junto com o adiado",
              deferred.get("question", "").startswith("Fecho o card"), deferred)
        check("...e a evidência inteira, não só o detalhe",
              deferred.get("evidence") == "não há produção para medir", deferred)


def test_answer_refuses_without_terminal():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1", status="blocked")])
        p = subprocess.run(
            [sys.executable, str(CEPA_PLAN), "responde", "fila", "a1",
             "--resposta", "pode seguir", "--repo", str(root)],
            capture_output=True, text=True, stdin=subprocess.DEVNULL)
        check("sem TTY, `responde` recusa", p.returncode == 2, p.stdout)
        check("...e diz que só o dono responde", "terminal" in p.stderr,
              p.stderr)
        check("...e o item continua `blocked`",
              items_of(root)["a1"]["status"] == "blocked")


def test_answer_on_terminal_unblocks_blocked_and_closes_route():
    with tempfile.TemporaryDirectory() as tmp:
        stuck = item("a1", status="blocked")
        stuck["evidence"] = "não há produção"
        stuck["owner_question"] = "Fecho o card?"
        route = item("a2", human_pending="valide o login real")
        root = build_repo(tmp, [stuck, route])
        rc, out = on_tty([sys.executable, str(CEPA_PLAN), "responde", "fila",
                          "a1", "--resposta", "vira item do checklist",
                          "--repo", str(root)], str(root))
        a1 = items_of(root)["a1"]
        check("no terminal, `responde` sai 0", rc == 0, out)
        check("o blocked volta para pending", a1["status"] == "pending", a1)
        check("...com a resposta do dono na evidência",
              "vira item do checklist" in a1["evidence"], a1["evidence"])
        check("...guardando a evidência anterior",
              "não há produção" in a1["evidence"], a1["evidence"])
        check("...e a pergunta respondida sai do item",
              "owner_question" not in a1, a1)
        rc, out = on_tty([sys.executable, str(CEPA_PLAN), "responde", "fila",
                          "a2", "--resposta", "login ok, trilha gravada",
                          "--repo", str(root)], str(root))
        a2 = items_of(root)["a2"]
        check("a rota humana fecha", a2.get("human_pending") is None, a2)
        check("...com a chave presente e nula, como o validador da fila exige",
              "human_pending" in a2 and a2["human_pending"] is None, a2)
        check("...e o texto da rota fica na evidência",
              "valide o login real" in a2["evidence"]
              and "trilha gravada" in a2["evidence"], a2["evidence"])


def test_answer_keep_writes_the_answer_without_unblocking():
    """WEGO 2026-09-30-2016: the owner answered "mantenha travado" to WEGO-2337
    and "não liguei" to WEGO-1933, and both went back to `pending` — the
    `responde` unblocked every `blocked` that got an answer, whatever
    it was. The next run would execute both."""
    with tempfile.TemporaryDirectory() as tmp:
        stuck = item("a1", status="blocked")
        stuck["evidence"] = "causa não determinada"
        stuck["owner_question"] = "Destravo?"
        route = item("a2", human_pending="ligue a flag")
        root = build_repo(tmp, [stuck, route])
        rc, out = on_tty([sys.executable, str(CEPA_PLAN), "responde", "fila",
                          "a1", "--resposta", "mantenha travado", "--mantem",
                          "--repo", str(root)], str(root))
        a1 = items_of(root)["a1"]
        check("`responde --mantem` sai 0", rc == 0, out)
        check("...e o blocked continua blocked", a1["status"] == "blocked", a1)
        check("...com a resposta do dono na evidência",
              "mantenha travado" in a1["evidence"]
              and "causa não determinada" in a1["evidence"], a1["evidence"])
        check("...sem dizer que voltou para pending",
              "voltou de `blocked`" not in a1["evidence"], a1["evidence"])
        check("...e a pergunta continua aberta para o próximo decidir",
              a1.get("owner_question") == "Destravo?", a1)
        rc, out = on_tty([sys.executable, str(CEPA_PLAN), "responde", "fila",
                          "a2", "--resposta", "não liguei", "--mantem",
                          "--repo", str(root)], str(root))
        a2 = items_of(root)["a2"]
        check("`--mantem` numa rota humana não fecha a rota",
              a2.get("human_pending") == "ligue a flag", a2)
        check("...mas grava a resposta", "não liguei" in a2["evidence"], a2)


def test_decide_offers_to_keep_stuck():
    m = load_module()
    deferred_ones = [
        {"id": "W-1", "title": "flaky", "reason": "bloqueado-antes",
         "question": "Destravo?", "human_pending": None, "evidence": "x"},
        {"id": "W-2", "title": "flag", "reason": "human_pending",
         "question": None, "human_pending": "ligue a flag", "evidence": None},
    ]
    answers = iter(["t", "mantenha", "", "t", "não liguei", ""])
    screen, answered, questions = [], [], []

    def question_text(p_):
        questions.append(p_)
        return next(answers)
    applied, after = m.decide(
        Path("/nao/existe"), "fila", "run1", {}, deferred_ones, {},
        question=question_text, output=screen.append,
        answer=lambda i, t, keep=False: (
            answered.append((i, t, keep)), (0, f"{i} ok"))[1])
    check("as opções oferecem [n] no e [t] escrevo",
          all("[n] no" in p_ and "[t] I write" in p_
              for p_ in questions if "[Enter]" in p_), questions)
    check("[t] + N no 'devolvo?' chama o responde com keep=True",
          answered == [("W-1", "mantenha", True),
                          ("W-2", "não liguei", True)], answered)
    check("...e conta como respondido", len(applied) == 2, applied)


def test_decide_asks_and_applies_each_answer():
    m = load_module()
    deferred_ones = [
        {"id": "W-1", "title": "medir produção", "reason": "blocked-before",
         "question": None, "human_pending": None,
         "evidence": "não existe produção do wego-acessos"},
        {"id": "W-2", "title": "login real", "reason": "human_pending",
         "question": None, "human_pending": "rode o login do Bradesco",
         "evidence": None},
        {"id": "W-3", "title": "outra", "reason": "blocked-before",
         "question": "Largo o card?", "human_pending": None,
         "evidence": "a evidência longa"},
        {"id": "W-4", "title": "cascata", "reason": "depends-on-deferred"},
    ]
    analysis = m.analysis_decisions(
        "texto\n```json cepa-decisoes\n"
        '{"aterrissar": {"recomendo": "sim", "porque": "build verde"},'
        ' "itens": [{"id": "W-1", "pergunta": "Movo para o checklist?",'
        ' "recomendo": "sim", "porque": "não trava a fila"}]}\n```\n')
    check("o bloco da análise é lido",
          analysis["itens"]["W-1"]["pergunta"] == "Movo para o checklist?",
          analysis)
    state_dict = {"acoes": [{"id": "aterrissar", "frase": "leva 5 commits"}]}
    answers = iter(["s", "t", "vira checklist", "s", "", "e", "q"])
    screen, answered, landed = [], [], []
    applied, after = m.decide(
        Path("/nao/existe"), "fila", "run1", state_dict, deferred_ones, analysis,
        question=lambda _p: next(answers), output=screen.append,
        answer=lambda i, t: (answered.append((i, t)), (0, f"{i} ok"))[1],
        land=lambda: landed.append(1) or 0)
    plain_text = "\n".join(screen)
    check("pergunta aterrissar e aterrissa com s", landed == [1], plain_text)
    check("...mostrando a recomendação da análise",
          "Recommend yes: build verde" in plain_text, plain_text)
    check("a pergunta da análise aparece no lugar da evidência",
          "Movo para o checklist?" in plain_text, plain_text)
    check("a resposta digitada vai para o `responde`",
          answered == [("W-1", "vira checklist")], answered)
    check("rota humana mostra a rota verbatim",
          "rode o login do Bradesco" in plain_text, plain_text)
    check("[e] mostra a evidência inteira do item com pergunta",
          "a evidência longa" in plain_text, plain_text)
    check("q encerra e o que sobrou fica para depois",
          any(x.startswith("W-3") for x in after)
          and any(x.startswith("W-2") for x in after), after)
    check("cascata não vira pergunta, só aparece como não sendo do dono",
          "W-4 (depends on a deferred item" in plain_text, plain_text)
    check("o fecho diz como voltar",
          "cepa-until decide fila/run1" in plain_text, plain_text)
    check("aplicados listam aterrissar e W-1",
          applied == ["aterrissar", "W-1: W-1 ok"], applied)


def test_decide_s_and_n_answer_the_drafted_question():
    """Feedback of 15/10: the question was yes/no ("Fecho a rota...? Recomendo
    sim") and the menu had no yes. Now `s` returns the item to the queue with
    "sim: <question>" and `n` records "não: <question>" keeping the item."""
    m = load_module()
    deferred_ones = [
        {"id": "W-1", "title": "t" * 90, "reason": "human_pending",
         "question": "Fecho a rota como 'fica para depois'?",
         "human_pending": "rodar os 20 lotes", "evidence": "x"},
        {"id": "W-2", "title": "flag", "reason": "blocked-before",
         "question": "Destravo?", "human_pending": None, "evidence": "y"},
        {"id": "W-3", "title": "sem pergunta", "reason": "blocked-before",
         "question": None, "human_pending": None, "evidence": "sem produção"},
    ]
    analysis = {"itens": {"W-1": {"recomendo": "sim", "porque": "só após merge"}}}
    answers = iter(["sim", "", "n", "por enquanto não", "s", "ligue a flag"])
    screen, answered, questions = [], [], []

    def question_text(p_):
        questions.append(p_)
        return next(answers)
    applied, _ = m.decide(
        Path("/nao/existe"), "fila", "run1", {}, deferred_ones, analysis,
        question=question_text, output=screen.append,
        answer=lambda i, t, keep=False: (
            answered.append((i, t, keep)), (0, f"{i} ok"))[1])
    plain_text = "\n".join(screen)
    check("o título sai inteiro (cortado em 60, o dono respondia a uma "
          "pergunta que via pela metade; 15/10)", "t" * 90 in plain_text, plain_text)
    check("a recomendação marca a letra no menu",
          any("[s] yes (recommended)" in p_ for p_ in questions), questions)
    check("a legenda diz o que sim e não fazem",
          "yes = the item goes back to the queue" in plain_text, plain_text)
    check("sem pergunta redigida, o terminal faz a padrão",
          "unblock the item and send it back to the queue?" in plain_text
          and "The agent stopped because: sem produção" in plain_text, plain_text)
    check("sim/n/s viram respostas gravadas, com a pergunta dentro",
          answered == [
              ("W-1", "sim: Fecho a rota como 'fica para depois'?", False),
              ("W-2", "não: Destravo?. por enquanto não", True),
              ("W-3", "sim: unblock the item. ligue a flag", False)],
          answered)
    check("os três contam como respondidos", len(applied) == 3, applied)
    menus = [p_ for p_ in questions if "[Enter]" in p_]
    check("o menu completo, com evidência: s, n, t, e, Enter, q",
          menus and all("[s] yes" in p_ and "[n] no" in p_
                        and "[t] I write the answer" in p_
                        and "[e] technical detail" in p_
                        and "[Enter] later" in p_ and "[q] quit" in p_
                        for p_ in menus), menus)
    check("...e sem as teclas antigas [r]/[f]/[m]",
          not any(k in p_ for p_ in menus for k in ("[r]", "[f]", "[m]")),
          menus)
    # AC3, branch of the human route without a drafted question
    screen2, resp2 = [], iter(["", "q"])
    m.decide(Path("/nao/existe"), "fila", "run1", {},
             [{"id": "W-9", "title": "rota", "reason": "human_pending",
               "question": None, "human_pending": "valide o login real",
               "evidence": None}], {},
             question=lambda _p: next(resp2), output=screen2.append)
    text2 = "\n".join(screen2)
    check("rota humana sem pergunta: mostra a tarefa e pergunta 'já fez?'",
          "Task left for you: valide o login real" in text2
          and "Question: done already?" in text2, text2)
    check("...e sem evidência o menu não oferece [e]",
          not any("[e]" in p_ for p_ in screen2), screen2)


def test_decide_shows_context_instruction_and_warns_question_outside_the_rules():
    """Feedback of 15/10 (decidir WEGO 2026-10-15-1128): the analysis put 71
    words, branch and test class in the question, and it all came out in a single
    block. Now the analysis separates `contexto` (lay) and `instrucao` (technical,
    recorded with the yes), the terminal labels each part, and a question outside
    the rules gets the warning, without ceasing to be shown."""
    m = load_module()
    long_ = ("Fecho a rota humana B.14 e devolvo o item à fila com a "
             "instrução: retomar da lateral until/2026-10-15-1128-vermelho "
             "e dar tinta à página sem texto de PipelineSemVazamentoTest, "
             "como nas outras 4 fixtures? (a alternativa é deixar adiado)")
    deferred_ones = [
        {"id": "S5", "title": "Pipeline marca página em branco",
         "reason": "human_pending", "question": None,
         "human_pending": "rodar os 20 lotes", "evidence": "x"},
        {"id": "S6", "title": "outro", "reason": "human_pending",
         "question": None, "human_pending": "revisar a prova",
         "evidence": "y"},
    ]
    analysis = {"itens": {
        "S5": {"pergunta": "Deixo a rodada dos 20 lotes para depois do merge "
                           "e devolvo o item à fila?",
               "contexto": "O código está pronto numa branch lateral; "
                           "só um teste de fixture ficou vermelho.",
               "instrucao": "retomar de until/2026-10-15-1128-vermelho-S5 e "
                            "dar tinta à fixture de PipelineTest",
               "recomendo": "sim", "porque": "a rodada só é possível após "
                                             "o merge"},
        "S6": {"pergunta": long_, "recomendo": "sim", "porque": "p"}}}
    answers = iter(["s", "", "s", ""])
    screen, answered = [], []
    m.decide(Path("/nao/existe"), "fila", "run1", {}, deferred_ones, analysis,
             question=lambda _p: next(answers), output=screen.append,
             answer=lambda i, t, keep=False: (
                 answered.append((i, t, keep)), (0, "ok"))[1])
    plain_text = "\n".join(screen)
    block_s5 = plain_text.split("━━ [1/2] S5")[1].split("━━ [2/2] S6")[0]
    check("cada item abre com separador e id em linha própria",
          "━━ [1/2] S5\n" in plain_text and "━━ [2/2] S6\n" in plain_text, plain_text)
    check("o bloco tem Parou porque / Tarefa / Contexto / Pergunta / "
          "Se sim / Recomendo, nesta ordem",
          [block_s5.find(r) for r in (
              "Stopped because: a task only you can do was left",
              "Task left for you: rodar os 20 lotes",
              "Context: O código está pronto numa branch lateral",
              "Question: Deixo a rodada dos 20 lotes",
              "If yes, the next run receives: retomar de until/",
              "Recommend yes: a rodada só é possível")]
          == sorted(i for i in (block_s5.find(r) for r in (
              "Stopped because:", "Task left for you", "Context:",
              "Question:", "If yes,", "Recommend yes")))
          and all(r in block_s5 for r in (
              "Stopped because:", "Task left for you", "Context:",
              "Question:", "If yes,", "Recommend yes")), block_s5)
    check("linha em branco antes da pergunta e antes da legenda do menu",
          "\n\n       Question:" in block_s5
          and "\n\n       yes = the item goes back" in block_s5, block_s5)
    check("a pergunta dentro das regras não ganha aviso",
          "outside the rules" not in block_s5, block_s5)
    check("o sim grava a pergunta E a instrução, para o próximo run",
          answered[0] == ("S5", "sim: Deixo a rodada dos 20 lotes para "
                             "depois do merge e devolvo o item à fila? "
                             "Instrução: retomar de until/2026-10-15-1128-"
                             "vermelho-S5 e dar tinta à fixture de "
                             "PipelineTest", False), answered)
    block_s6 = " ".join(plain_text.split("━━ [2/2] S6")[1].split())
    check("a pergunta longa com branch e classe é mostrada E avisada",
          "Question: Fecho a rota humana B.14" in block_s6
          and "outside the rules: 37 palavras, o limite é 25; nome de branch, "
              "classe de teste ou arquivo" in block_s6, block_s6)
    check("pergunta_fora_das_regras: None dentro das regras",
          m.question_breaks_rules("Fecho o card como 'medir depois'?")
          is None, "")
    check("...e pega a alternativa entre parênteses",
          "classe" in (m.question_breaks_rules(
              "Fecho? (a alternativa é não)") or ""), "")


def test_analysis_without_block_or_broken_does_not_crash():
    m = load_module()
    check("sem bloco devolve vazio", m.analysis_decisions("só texto") == {})
    check("JSON quebrado devolve vazio",
          m.analysis_decisions("```json cepa-decisoes\n{quebrado\n```") == {})


BLOCKS_WITH_QUESTION = (
    "ident = primeiro_pendente()\n"
    "if ident == 'a1':\n"
    "    marca(ident, status='blocked', evidence='não há produção',\n"
    "          owner_question='Fecho o card como medir depois do go-live?')\n"
    "elif ident:\n"
    "    marca(ident, status='done')\n")


def test_run_without_terminal_lists_the_pending_and_the_command():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, BLOCKS_WITH_QUESTION)
        p, _ = run_until(root, binv, plan_of(root), ["--for", "2h"])
        check("o fim lista o que espera o dono",
              "waiting on you" in p.stdout, p.stdout[-1500:])
        check("...com a pergunta do item, não a evidência",
              "Fecho o card como medir depois do go-live?" in p.stdout,
              p.stdout[-1500:])
        check("...e o comando para responder",
              "cepa-until decide fila/" in p.stdout, p.stdout[-800:])


def test_run_on_terminal_ends_asking_and_applies():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, BLOCKS_WITH_QUESTION)
        env = dict(os.environ)
        env["PATH"] = f"{binv}:{env['PATH']}"
        env["FAKE_PLANO"] = str(plan_of(root))
        env.setdefault("CEPA_UNTIL_LEITOR", "off")  # the pre-read must not call the fake claude
        env["FAKE_CHAMADAS"] = str(Path(tmp) / "chamadas.jsonl")
        env["CEPA_WORKTREE_HOME"] = str(Path(tmp) / "worktrees")
        rc, out = on_tty(
            [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
             "--for", "2h", "--no-verify", "--no-analysis"], str(root),
            inputs=[("[t] I write the answer", "t"),
                      ("Your answer", "vira item do checklist"),
                      ("Send the item back to the queue", "s")], env=env)
        check("o run sai 0", rc == 0, out[-1500:])
        check("pergunta o item travado com a pergunta gravada",
              "Fecho o card como medir depois do go-live?" in out, out[-1500:])
        a1 = items_of(root)["a1"]
        check("a resposta volta o item para a fila",
              a1["status"] == "pending"
              and "vira item do checklist" in a1["evidence"], a1)


def test_run_on_terminal_without_answer_exits_after_the_wait():
    """Item until-processo-nao-sai: an overnight run ends with nobody at the
    keyboard. The end-of-run prompt had no limit and PID 84993 (run WEGO
    2026-10-07-2132) stayed alive 15 days blocked in `input()`. With no
    keystroke inside CEPA_UNTIL_ESPERA_RESPOSTA the run prints the
    `cepa-until decide` command and exits 0, applying nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, BLOCKS_WITH_QUESTION)
        env = env_do_run(tmp, root, binv)
        env["CEPA_UNTIL_ESPERA_RESPOSTA"] = "2"
        rc, out = on_tty(
            [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
             "--for", "2h", "--no-verify", "--no-analysis"], str(root),
            inputs=[], env=env, timeout=90)
        check("o run sai 0 sem resposta", rc == 0, out[-1500:])
        check("o menu foi mostrado",
              "Fecho o card como medir depois do go-live?" in out, out[-1500:])
        check("imprime o comando para responder depois",
              "cepa-until decide fila/" in out, out[-1500:])
        check("nada foi aplicado",
              items_of(root)["a1"]["status"] == "blocked", items_of(root)["a1"])


def test_read_line_raises_when_nobody_types():
    mod = load_module()
    r, w = os.pipe()
    saved = sys.stdin
    sys.stdin = os.fdopen(r)
    try:
        try:
            mod.read_line("? ", wait=0.2)
            raised = False
        except mod.NoAnswer:
            raised = True
    finally:
        sys.stdin.close()
        sys.stdin = saved
        os.close(w)
    check("read_line sem digitação levanta NoAnswer", raised)


def env_do_run(tmp, root, binv):
    env = dict(os.environ)
    env["PATH"] = f"{binv}:{env['PATH']}"
    env["FAKE_PLANO"] = str(plan_of(root))
    env.setdefault("CEPA_UNTIL_LEITOR", "off")  # the pre-read must not call the fake claude
    env["FAKE_CHAMADAS"] = str(Path(tmp) / "chamadas.jsonl")
    env["CEPA_WORKTREE_HOME"] = str(Path(tmp) / "worktrees")
    return env


def test_run_on_terminal_asks_to_land_and_lands_with_s():
    """AC1: `s` at the end-of-run prompt really lands."""
    from test_cepa_until_land import with_origin, state
    from test_cepa_until_run_branch import WORKS, VERIFY, git
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        with_origin(root)
        binv = fake_claude(tmp, WORKS)
        rc, out = on_tty(
            [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
             "--for", "2h", "--verify", VERIFY, "--no-analysis"], str(root),
            inputs=[("Land now?", "s")],
            env=env_do_run(tmp, root, binv), timeout=240)
        check("o run sai 0", rc == 0, out[-1500:])
        check("o fim pergunta se aterrissa", "Land now?" in out,
              out[-1500:])
        log = git(root, "log", "--format=%s", "HEAD").splitlines()
        check("com s, o commit do item chega à main", "a1" in log, str(log))
        check("...e o estado do run vira aterrissado",
              state(root).get("estado") == "aterrissado", str(state(root)))


def test_reserved_does_not_become_a_question():
    """AC3: another live session on the item is not the owner's business."""
    m = load_module()
    screen, questions = [], []
    m.decide(Path("/nao/existe"), "fila", "run1", {},
             [{"id": "W-9", "title": "em outra sessão", "reason": "reserved"},
              {"id": "W-8", "title": "cascata",
               "reason": "depends-on-deferred"}],
             {}, question=lambda p_: questions.append(p_) or "",
             output=screen.append)
    plain_text = "\n".join(screen)
    check("nenhuma pergunta é feita", questions == [], questions)
    check("...e o fecho diz que nada espera por você",
          "nothing is waiting on you" in plain_text, plain_text)


def test_decidir_as_process_with_and_without_terminal():
    """AC5: `cepa-until decidir <queue>/<run>` after the run, and AC2 at the end:
    the human route closes by answering inside decide."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        body = ("ident = primeiro_pendente()\n"
                 "if ident == 'a1':\n"
                 "    marca(ident, status='blocked', evidence='sem produção',\n"
                 "          owner_question='Fecho o card?')\n"
                 "elif ident == 'a2':\n"
                 "    marca(ident, status='pending', evidence='feito',\n"
                 "          human_pending='valide o login real')\n")
        binv = fake_claude(tmp, body)
        run_until(root, binv, plan_of(root), ["--for", "2h"])
        run_id = sorted((root / ".claude" / "programs" / "fila" / "until")
                        .glob("*.estado.json"))[-1].name.split(".")[0]
        cmd = [sys.executable, str(CEPA_UNTIL), "decide", f"fila/{run_id}",
               "--repo", str(root)]
        p = subprocess.run(cmd, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        check("sem terminal, decidir sai 0 e lista", p.returncode == 0
              and "Fecho o card?" in p.stdout
              and "valide o login real" in p.stdout, p.stdout + p.stderr)
        check("...sem mexer na fila",
              items_of(root)["a1"]["status"] == "blocked")
        rc, out = on_tty(cmd, str(root), inputs=[
            ("[t] I write the answer", "t"), ("Your answer", "vira checklist"),
            ("Send the item back to the queue", "s"),
            ("[t] I write the answer", "s"), ("Anything to add", "login ok")])
        a1, a2 = items_of(root)["a1"], items_of(root)["a2"]
        check("no terminal, decidir aplica o blocked",
              rc == 0 and a1["status"] == "pending"
              and "vira checklist" in a1["evidence"], out[-1200:])
        check("...e fecha a rota humana com a resposta",
              a2.get("human_pending") is None
              and "login ok" in a2["evidence"], a2)


def test_agent_instructions_ask_for_the_question():
    """AC6: without these lines, the agent goes back to blocking an item without a question and the
    analysis goes back to not recording the block the terminal reads."""
    commands = CEPA_UNTIL.parent.parent / "commands"
    review = (commands / "until-review.md").read_text(encoding="utf-8")
    drain = (commands / "drain-plan.md").read_text(encoding="utf-8")
    check("until-review manda gravar o bloco cepa-decisoes",
          "```json cepa-decisoes" in review, "")
    check("...cobrindo todos os adiados da fila, pelo queue",
          "deferred" in review and "cepa-plan queue" in review, "")
    check("...e diz que as ações vêm da lista fechada",
          "closed list" in review, "")
    check("drain-plan manda gravar --question ao travar",
          "--question" in drain, "")
    p = subprocess.run([sys.executable, str(CEPA_UNTIL.parent / "cepa-plan"),
                        "finish", "--help"], capture_output=True, text=True,
                       timeout=30)
    help_ = " ".join(p.stdout.split())
    for given_name, plain_text in (("until-review", review), ("drain-plan", drain),
                        ("cepa-plan finish --help", help_)):
        plain_text = " ".join(plain_text.replace("**", "").split())
        # The commands and cepa-plan's help were translated to English.
        sentences = {
            "drain-plan": ("Up to 25 words", "without a branch name",
                           "the item goes back to the queue"),
            # the terminal menu is printed in pt-BR by cepa-until and the
            # command quotes it literally.
            "until-review": ("Up to 25 words", "no branch name",
                             "volta para a fila"),
        }.get(given_name, ("25 words", "no branch, class or file name",
                           "the item returns to the queue"))
        check(f"{given_name}: pergunta de até 25 palavras",
              sentences[0] in plain_text, plain_text[-600:])
        check(f"{given_name}: sem nome de branch, classe ou arquivo",
              sentences[1] in plain_text, plain_text[-600:])
        check(f"{given_name}: sim = o item volta para a fila",
              sentences[2] in plain_text, plain_text[-600:])
    r = " ".join(review.replace("`", "").split())
    check("until-review: o bloco tem contexto (leigo) e instrucao (técnica)",
          '"contexto"' in r and '"instrucao"' in r
          and "contexto is" in r and "instrucao is" in r, r[-1500:])


REVIEW_WITH_BLOCK = (
    "if ARGS and ARGS[1].startswith('/common:until-review'):\n"
    "    print('RELATORIO')\n"
    "    print('```json cepa-decisoes')\n"
    "    print(json.dumps({'itens': [{'id': 'a1', 'pergunta': "
    "'Movo a medição para o checklist?', 'recomendo': 'sim', "
    "'porque': 'não trava a fila'}]}))\n"
    "    print('```')\n"
    "    sys.exit(0)\n")


def test_end_with_analysis_asks_with_the_block_wording():
    """Exit path 3 (with analysis): the question comes from the analysis block
    when the agent recorded none."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        body = REVIEW_WITH_BLOCK + (
            "marca(primeiro_pendente(), status='blocked', "
            "evidence='evidência crua longa')\n")
        binv = fake_claude(tmp, body)
        p, _ = run_until(root, binv, plan_of(root), ["--for", "2h", "--com-analise"])
        end = p.stdout.split("── waiting on you")[-1]
        check("com análise, o fim lista o que espera o dono",
              "── waiting on you" in p.stdout, p.stdout[-1200:])
        check("...com a pergunta redigida pela análise",
              "Movo a medição para o checklist?" in end, end)


def test_end_stopped_by_quota_also_asks():
    """Exit path 2 (quota): the analysis does not run, but the questions do."""
    with tempfile.TemporaryDirectory() as tmp:
        stuck = item("a1", status="blocked")
        stuck["evidence"] = "sem produção"
        stuck["owner_question"] = "Fecho o card?"
        root = build_repo(tmp, [stuck, item("a2")])
        body = ("if ARGS and ARGS[1].startswith('/common:until-review'):\n"
                 "    sys.exit(0)\n"
                 "print(json.dumps({'type': 'result', 'result': "
                 "\"You've hit your session limit\"}))\n")
        binv = fake_claude(tmp, body)
        p, _ = run_until(root, binv, plan_of(root), ["--for", "2h", "--com-analise"])
        from test_cepa_until import ledger_of
        end = [e for e in ledger_of(root) if e["evento"] == "run_end"][0]
        check("o run parou pela cota", end["motivo"] == "limite-de-uso", str(end))
        check("...e mesmo assim termina perguntando",
              "── waiting on you" in p.stdout
              and "Fecho o card?" in p.stdout, p.stdout[-1200:])


def test_list_without_terminal_filters_what_is_not_the_owners():
    m = load_module()
    screen = []
    m.pending_as_text(
        "fila", "run1", {"acoes": [{"id": "aterrissar", "frase": "leva 3"}]},
        [{"id": "W-1", "reason": "human_pending",
          "human_pending": "rode o login real"},
         {"id": "W-2", "reason": "reservado", "detail": "sessão viva"},
         {"id": "W-3", "reason": "depende-de-adiado", "detail": "de W-1"}],
        {}, output=screen.append)
    plain_text = "\n".join(screen)
    check("sem terminal, lista aterrissar", "aterrissar: leva 3" in plain_text,
          plain_text)
    check("...e a rota humana verbatim", "rode o login real" in plain_text, plain_text)
    check("...contando 2, sem reservado nem cascata",
          "waiting on you: 2" in plain_text and "W-2" not in plain_text
          and "W-3" not in plain_text, plain_text)


def test_block_that_is_not_an_object_is_ignored():
    m = load_module()
    check("lista no lugar de objeto devolve vazio",
          m.analysis_decisions("```json cepa-decisoes\n[1, 2]\n```") == {})


def test_question_leaves_when_the_item_moves_again_and_reservation_vanishes_in_answer():
    with tempfile.TemporaryDirectory() as tmp:
        stuck = item("a1", status="blocked")
        stuck["owner_question"] = "Fecho?"
        other_one = item("a2", status="blocked")
        other_one["evidence"] = "x"
        other_one["claimed_by"] = {"session": "morta"}
        root = build_repo(tmp, [stuck, other_one])
        subprocess.run(
            [sys.executable, str(CEPA_PLAN), "finish", "fila", "a1",
             "--status", "pending", "--evidence", "destravou", "--supervisor",
             "--repo", str(root)], capture_output=True, text=True, check=True)
        check("finish pending sem --pergunta tira a pergunta velha",
              "owner_question" not in items_of(root)["a1"], items_of(root)["a1"])
        on_tty([sys.executable, str(CEPA_PLAN), "responde", "fila", "a2",
                "--resposta", "segue", "--repo", str(root)], str(root))
        check("responde limpa a reserva do item",
              "claimed_by" not in items_of(root)["a2"], items_of(root)["a2"])


def test_hostile_input_does_not_corrupt_the_queue_nor_leave_the_folder():
    """Adversarial level: the answer is free text from the owner and goes into the queue
    YAML; the `decidir` target becomes a path on disk."""
    hostile = "a: b\n- c # x 'q' \"z\" {{}} [1] ---\n!!python/object:os.system"
    with tempfile.TemporaryDirectory() as tmp:
        stuck = item("a1", status="blocked")
        root = build_repo(tmp, [stuck])
        rc, out = on_tty([sys.executable, str(CEPA_PLAN), "responde", "fila",
                          "a1", "--resposta", hostile, "--repo", str(root)],
                         str(root))
        check("resposta com sintaxe de YAML é aceita", rc == 0, out)
        v = subprocess.run([sys.executable, str(CEPA_PLAN), "validate",
                            str(plan_of(root))], capture_output=True, text=True)
        check("...a fila continua válida", v.returncode == 0, v.stdout + v.stderr)
        ev = items_of(root)["a1"]["evidence"]
        check("...e o texto fica como texto, numa linha",
              "!!python/object:os.system" in ev and "\n" not in ev, ev)
        empty = on_tty([sys.executable, str(CEPA_PLAN), "responde", "fila",
                        "a1", "--resposta", "   ", "--repo", str(root)],
                       str(root))
        check("resposta só de espaços é recusada", empty[0] == 2, empty[1])
        # A real state outside the run folder: without it, the target with `..`
        # was refused only because the file did not exist (finding of the proof, 30/09).
        outside = root / ".claude" / "programs" / "x.estado.json"
        outside.write_text('{"acoes": []}')
        # `until/..` only resolves if the run folder exists, as it does after
        # the first run.
        (root / ".claude" / "programs" / "fila" / "until").mkdir()
        for target in ("../../etc/passwd", "semBarra", "fila/../../x",
                     "fila/../x", "../fila/x"):
            p_ = subprocess.run([sys.executable, str(CEPA_UNTIL), "decide",
                                 target, "--repo", str(root)],
                                capture_output=True, text=True,
                                stdin=subprocess.DEVNULL, timeout=60)
            check(f"alvo {target!r} recusa com 2, sem traceback",
                  p_.returncode == 2 and "Traceback" not in p_.stderr
                  and "waiting on you" not in p_.stdout,
                  p_.stdout + p_.stderr)


def test_already_landed_run_does_not_ask_again():
    """In WEGO run 2026-09-29-2059 the owner landed at 07:15 and `decidir`
    still listed the landing: the action stays in the state as a record."""
    m = load_module()
    state_dict = {"estado": "aterrissado",
           "acoes": [{"id": "aterrissar", "frase": "leva 5"}]}
    screen, questions = [], []
    m.decide(Path("/nao/existe"), "fila", "run1", state_dict, [], {},
             question=lambda p_: questions.append(p_) or "", output=screen.append)
    check("run aterrissado não pergunta aterrissar", questions == [], questions)
    screen2 = []
    m.pending_as_text("fila", "run1", state_dict, [], {}, output=screen2.append)
    check("...nem lista sem terminal", screen2 == [], screen2)


def test_decidir_s_and_n_on_terminal_reach_the_plan():
    """AC2 at the end: `n` and `s` typed in a real terminal go through the real
    `cepa-plan responde` and record "não: <question>" (item as it is)
    and "sim: <question>" (item back to the queue)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        body = ("ident = primeiro_pendente()\n"
                 "if ident == 'a1':\n"
                 "    marca(ident, status='blocked', evidence='sem produção',\n"
                 "          owner_question='Fecho o card?')\n"
                 "elif ident == 'a2':\n"
                 "    marca(ident, status='pending', evidence='feito',\n"
                 "          human_pending='valide o login real')\n")
        binv = fake_claude(tmp, body)
        run_until(root, binv, plan_of(root), ["--for", "2h"])
        run_id = sorted((root / ".claude" / "programs" / "fila" / "until")
                        .glob("*.estado.json"))[-1].name.split(".")[0]
        cmd = [sys.executable, str(CEPA_UNTIL), "decide", f"fila/{run_id}",
               "--repo", str(root)]
        rc, out = on_tty(cmd, str(root), inputs=[
            ("[t] I write the answer", "n"), ("Anything to add", ""),
            ("[t] I write the answer", "s"), ("Anything to add", "vi ok")])
        a1, a2 = items_of(root)["a1"], items_of(root)["a2"]
        check("n no terminal: o blocked continua blocked",
              rc == 0 and a1["status"] == "blocked", (rc, a1, out[-1200:]))
        check("...com 'não: <pergunta>' na evidência",
              "não: Fecho o card?" in a1["evidence"], a1)
        check("s na rota sem pergunta: a rota fecha",
              a2.get("human_pending") is None, a2)
        check("...com 'sim: <rota>. <acréscimo>' na evidência",
              "sim: valide o login real. vi ok" in a2["evidence"], a2)
        rc, out = on_tty(cmd, str(root), inputs=[
            ("[t] I write the answer", "s"),
            ("Anything to add", "mas só depois do deploy")])
        a1 = items_of(root)["a1"]
        check("s no blocked com pergunta: volta para pending, com o comentário",
              rc == 0 and a1["status"] == "pending"
              and "sim: Fecho o card?. mas só depois do deploy" in a1["evidence"],
              (a1, out[-800:]))


def test_invalid_byte_on_terminal_does_not_crash_decide():
    """In decidir WEGO 2026-09-29-2059 the owner typed `não` and the terminal
    delivered `n\\xcb...` (the tilde of the dead key, half erased): `input()`
    blew up with UnicodeDecodeError and the questions died with a
    traceback. The unreadable line has to be asked for again."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, BLOCKS_WITH_QUESTION)
        run_until(root, binv, plan_of(root), ["--for", "2h"])
        run_id = sorted((root / ".claude" / "programs" / "fila" / "until")
                        .glob("*.estado.json"))[-1].name.split(".")[0]
        rc, out = on_tty(
            [sys.executable, str(CEPA_UNTIL), "decide", f"fila/{run_id}",
             "--repo", str(root)], str(root), inputs=[
                ("[t] I write the answer", b"n\xcb\xc3\xa3o"),
                ("could not read that line", "t"),
                ("Your answer", "vira checklist"),
                ("Send the item back to the queue", "s")])
        check("sem traceback", "Traceback" not in out, out[-1500:])
        check("...avisa que não leu e pede de novo",
              "could not read that line" in out, out[-1500:])
        a1 = items_of(root)["a1"]
        check("...e a resposta seguinte ainda é aplicada",
              rc == 0 and a1["status"] == "pending"
              and "vira checklist" in a1["evidence"], a1)


def test_loose_text_at_options_prompt_does_not_vanish():
    """In the same decidir the owner wrote the answer straight into the options
    prompt (`eu não faço ideia...`, `não`): it was not r/f/e/q, the item went
    to later and the text vanished without warning. It has to warn and ask
    again."""
    m = load_module()
    answers = iter(["eu não faço ideia de como resolver isso", "t",
                      "não sei", "s"])
    screen, answered = [], []
    m.decide(Path("/nao/existe"), "fila", "run1", {},
             [{"id": "W-1", "title": "t", "reason": "blocked-before",
               "question": "Ligou a flag?"}], {},
             question=lambda _p: next(answers), output=screen.append,
             answer=lambda i, t: (answered.append((i, t)), (0, "ok"))[1])
    plain_text = "\n".join(screen)
    check("avisa que o texto não é uma opção",
          "is not one of the options" in plain_text, plain_text)
    check("...e a resposta dada depois do r é gravada",
          answered == [("W-1", "não sei")], answered)


def test_loose_text_on_terminal_warns_and_still_writes():
    """The same case as the test above, through `cepa-until decidir` in a real
    terminal: the loose text is refused with a warning and the answer given
    after the r reaches plan.yaml."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, BLOCKS_WITH_QUESTION)
        run_until(root, binv, plan_of(root), ["--for", "2h"])
        run_id = sorted((root / ".claude" / "programs" / "fila" / "until")
                        .glob("*.estado.json"))[-1].name.split(".")[0]
        rc, out = on_tty(
            [sys.executable, str(CEPA_UNTIL), "decide", f"fila/{run_id}",
             "--repo", str(root)], str(root), inputs=[
                ("[t] I write the answer", "eu não faço ideia"),
                ("type t first", "t"),
                ("Your answer", "não sei ainda"),
                ("Send the item back to the queue", "s")])
        check("avisa que o texto solto não é opção",
              "is not one of the options" in out and "type t first" in out,
              out[-1500:])
        a1 = items_of(root)["a1"]
        check("...e a resposta dada depois do r chega ao plano",
              rc == 0 and a1["status"] == "pending"
              and "não sei ainda" in a1["evidence"], a1)


def _finish(root, *args):
    return subprocess.run(
        [sys.executable, str(CEPA_PLAN), "finish", "fila", "a1", *args,
         "--repo", str(root)], capture_output=True, text=True)


def test_finish_keeps_agent_and_human_sections_apart():
    """The owner (2026-11-01), on WEGO-2381: "Sua escrita é enigmática, cheia
    de códigos e pressupostos de entendimento." The screen said "travou por
    algo de fora do código" and the reason was in the sixth sentence of a log.
    Now `evidence` is the agents' section (codes allowed) and `owner_summary`
    is the human one: required on `blocked`, refused with codes."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        log = ("Matriz 154 = 136 cobertos + 18 bloqueados (WEGO-2490). "
               "completion-auditor INCOMPLETE, proof-reviewer PROVEN, "
               "commits 2a86075d..99818a34")
        p = _finish(root, "--status", "blocked", "--evidence", log)
        check("blocked sem --impede é recusado", p.returncode == 2, p.stderr)
        check("...dizendo que o dono lê a seção humana",
              "--blocker" in p.stderr and "seção humana" in p.stderr, p.stderr)
        check("...e nada muda no disco",
              items_of(root)["a1"]["status"] == "pending", items_of(root)["a1"])

        p = _finish(root, "--status", "blocked", "--evidence", log,
                    "--impede", "o bug WEGO-2490 deixa o 403 sem corpo")
        check("código de card na seção humana é recusado",
              p.returncode == 2 and "--blocker: código de card ou de commit"
              in p.stderr, p.stderr)
        p = _finish(root, "--status", "blocked", "--evidence", log,
                    "--impede", "o sistema responde em branco",
                    "--pergunta", "Aceito o INCOMPLETE do completion-auditor?")
        check("verificador e veredito na pergunta são recusados",
              p.returncode == 2
              and "--question: nome de verificador ou veredito interno"
              in p.stderr, p.stderr)
        p = _finish(root, "--status", "blocked", "--evidence", log,
                    "--impede", "palavra " * 31)
        check("campo humano acima de 30 palavras é recusado",
              p.returncode == 2 and "31 palavras, o limite é 30" in p.stderr,
              p.stderr)

        p = _finish(root, "--status", "blocked", "--evidence", log,
                    "--pedido", "testar a parte que controla quem entra no "
                                "sistema",
                    "--pronto", "136 de 154 casos testados e passando",
                    "--impede", "o sistema responde em branco quando nega um "
                                "acesso, e 18 testes dependem dessa resposta",
                    "--se-sim", "o trabalho vai para revisão com os 18 casos "
                                "marcados como pendentes do defeito",
                    "--se-nao", "o trabalho espera o defeito ser corrigido",
                    "--pergunta", "Entrego com os 18 casos pendentes do "
                                  "defeito?")
        check("com a seção humana leiga, blocked fecha", p.returncode == 0,
              p.stderr)
        it = items_of(root)["a1"]
        check("...a seção dos agentes guarda os códigos",
              it["evidence"] == log, it)
        check("...e a seção humana fica em owner_summary",
              it.get("owner_summary", {}).get("impede", "").startswith(
                  "o sistema responde em branco")
              and set(it["owner_summary"]) == {"pedido", "pronto", "impede",
                                               "se_sim", "se_nao"}, it)
        q = subprocess.run(
            [sys.executable, str(CEPA_PLAN), "queue", "fila", "--json",
             "--repo", str(root)], capture_output=True, text=True)
        deferred = json.loads(q.stdout)["deferred"][0]
        check("o queue devolve a seção humana junto com o adiado",
              deferred.get("owner_summary") == it["owner_summary"], deferred)
        st = subprocess.run(
            [sys.executable, str(CEPA_PLAN), "status", "fila",
             "--repo", str(root)], capture_output=True, text=True,
            env={**os.environ, "NO_COLOR": "1"})
        check("o status mostra o motivo leigo, não a 1ª frase do log",
              "o sistema responde em branco" in st.stdout
              and "Matriz 154" not in st.stdout, st.stdout)
        # DUR-2: the item is already `blocked`; reopening it is the supervisor's act.
        p = _finish(root, "--status", "pending", "--evidence", "voltou",
                    "--supervisor")
        check("pending limpa a seção humana, que era do travamento",
              "owner_summary" not in items_of(root)["a1"], items_of(root)["a1"])


def test_decide_shows_human_section_and_what_each_answer_does():
    """The screen opens with the human section (why it stopped, what was
    asked, what is ready), and the menu legend says what sim and não do to
    the WORK. The codes only show on [e], under "Technical detail"."""
    m = load_module()
    deferred_ones = [{
        "id": "WEGO-2381", "title": "Ampliar cobertura de testes",
        "reason": "blocked-before", "human_pending": None,
        "question": "Entrego com os 18 casos pendentes do defeito?",
        "evidence": "completion-auditor INCOMPLETE; WEGO-2490 criado",
        "owner_summary": {
            "pedido": "testar a parte que controla quem entra no sistema",
            "pronto": "136 de 154 casos testados e passando",
            "impede": "o sistema responde em branco quando nega um acesso",
            "se_sim": "o trabalho vai para revisão",
            "se_nao": "o trabalho espera o defeito ser corrigido"}}]
    answers = iter(["e", "", "q"])
    screen = []
    m.decide(Path("/nao/existe"), "fila", "run1", {}, deferred_ones, {},
             question=lambda _p: next(answers), output=screen.append,
             answer=lambda *a, **k: (0, "ok"))
    text = "\n".join(screen)
    flat = " ".join(text.split())
    order = [flat.find(x) for x in (
        "Stopped because: o sistema responde em branco",
        "Was meant to: testar a parte",
        "Already done: 136 de 154",
        "Question: Entrego com os 18 casos",
        "yes = o trabalho vai para revisão. The item goes back to the queue",
        "no = o trabalho espera o defeito ser corrigido")]
    check("motivo, pedido, pronto, pergunta e legenda, nesta ordem",
          -1 not in order and order == sorted(order), text)
    check("a etiqueta genérica some quando há motivo leigo",
          "the agent marked the item as stuck" not in text
          and "travou por algo de fora do código" not in text, text)
    before_e = text.split("Technical detail")[0]
    check("os códigos só aparecem no detalhe técnico, no [e]",
          "WEGO-2490" not in before_e
          and "Technical detail (for agents): completion-auditor" in text, text)


def test_old_blocked_item_gets_a_true_generic_reason():
    """An item blocked before the human section existed: the screen no longer
    claims "algo de fora do código", which was false on WEGO-2381."""
    m = load_module()
    screen = []
    m.decide(Path("/nao/existe"), "fila", "run1", {},
             [{"id": "a1", "title": "t", "reason": "blocked-before",
               "human_pending": None, "question": None, "evidence": "x"}],
             {}, question=lambda _p: "q", output=screen.append,
             answer=lambda *a, **k: (0, "ok"))
    text = "\n".join(screen)
    check("item antigo mostra o motivo genérico verdadeiro",
          "Stopped because: the agent marked the item as stuck." in text
          and "fora do código" not in text, text)


def test_supervisor_block_writes_a_lay_reason():
    """`block_item` is the supervisor closing an item nobody explained; it
    passes `cepa-plan`'s new rule with its own lay reason."""
    m = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        err = m.block_item("fila", root, "a1", 3)
        it = items_of(root)["a1"]
        check("block_item fecha blocked sob a regra nova", err is None, err)
        check("...com o motivo leigo na seção humana",
              (it.get("owner_summary") or {}).get("impede", "").startswith(
                  "the executor tried 3 times in a row"), it)


def test_finish_item_reopens_an_item_the_agent_closed_done():
    """DUR-2: `cepa-plan finish` refuses a second finish on a terminal item;
    the supervisor's `finish_item` must pass `--supervisor` (red full build puts
    the agent's `done` back to `pending`)."""
    m = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        done = item("a1", status="done")
        done["evidence"] = "o agente fechou"
        root = build_repo(tmp, [done])
        err = m.finish_item("fila", root, "a1", "pending", "build vermelho")
        check("finish_item reabre item done (devolve None)", err is None, err)
        it = items_of(root)["a1"]
        check("...o status virou pending e a evidence foi trocada",
              it["status"] == "pending" and it["evidence"] == "build vermelho", it)


def _launch_events(root):
    """item_start/ids of every run ledger the queue has."""
    out = []
    for f in sorted((root / ".claude" / "programs" / "fila" / "until").glob("*.jsonl")):
        out += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return out


def _launch_on_tty(answers, wait="600", items=None, extra=(), timeout=90):
    """Queue with only A (unless `items`), which has an open `human_pending`; real
    `cepa-until` on a pty (drained continuously by `on_tty`, or the supervisor blocks in
    `print`). `extra` are added arguments (e.g. `--dry-run`)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, items if items is not None else
                          [item("a1", human_pending="provision the Keycloak role")])
        binv = fake_claude(tmp, "pass")
        env = env_do_run(tmp, root, binv)
        env["CEPA_UNTIL_ESPERA_RESPOSTA"] = wait
        rc, out = on_tty(
            [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
             "--for", "2h", "--no-verify", "--no-analysis", *extra], str(root),
            inputs=answers, env=env, timeout=timeout)
        return rc, out, _launch_events(root), items_of(root)


def test_launch_on_terminal_asks_and_yes_runs_the_item_in_the_same_run():
    """CS-2 (spec perguntar-antes-do-run): the route of an open item is asked BEFORE
    the first item and "y" makes the item run in this very run."""
    rc, out, events, _ = _launch_on_tty(
        [("[t] I write the answer", "y"), ("Anything to add", "")], wait="2")
    starts = [e for e in events if e.get("evento") == "item_start"]
    check("the run exits 0", rc == 0, out[-1500:])
    check("the question shows up at the launch", "provision the Keycloak role" in out, out[:1500])
    check("item_start of a1 is recorded", any(e.get("id") == "a1" for e in starts), str(events) + out[-1500:])


def test_launch_on_terminal_no_or_enter_leaves_the_item_without_item_start():
    for reply in ("n", ""):
        trig = [("[t] I write the answer", reply)] + (
            [("Anything to add", "")] if reply else [])
        rc, out, events, items = _launch_on_tty(trig)
        check(f"answer {reply!r}: no item_start", not any(
            "item_start" in json.dumps(e) for e in events), str(events) + out[-1000:])
        check(f"answer {reply!r}: run exits 0", rc == 0, out[-1000:])
        check(f"answer {reply!r}: the question was asked", "[t] I write the answer" in out,
              out[-1000:])
        check(f"answer {reply!r}: a1 keeps its open route",
              items["a1"].get("human_pending"), str(items["a1"]))


def test_launch_on_terminal_without_answer_carries_on_after_the_wait():
    """Nobody reads the terminal: the launch panel must not hang; one line, then the run
    goes on as today (a1 stays deferred, so no item_start, and the process exits)."""
    rc, out, events, _ = _launch_on_tty([], wait="2")
    check("the run exits 0 instead of hanging", rc == 0, out[-1500:])
    check("it says nobody answered, in one line", "nobody answered" in out, out[-1500:])
    check("no item_start", not any("item_start" in json.dumps(e) for e in events), str(events))


def test_launch_without_terminal_keeps_ending_with_no_item_start():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1", human_pending="provision the Keycloak role")])
        binv = fake_claude(tmp, "pass")
        # stdin explicitly NOT a terminal (DEVNULL), so the test never depends on
        # the runner's stdin and pins the isatty guard in front of ask_at_launch.
        env = dict(os.environ)
        env["PATH"] = f"{binv}:{env['PATH']}"
        env["FAKE_PLANO"] = str(plan_of(root))
        env.setdefault("CEPA_UNTIL_LEITOR", "off")  # the pre-read must not call the fake claude
        env.setdefault("CEPA_WORKTREE_HOME", str(Path(root).parent / "worktrees"))
        calls_f = Path(root).parent / "chamadas.jsonl"
        env["FAKE_CHAMADAS"] = str(calls_f)
        p = subprocess.run(
            [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
             "--for", "2h", "--no-verify", "--no-analysis"],
            capture_output=True, text=True, env=env, timeout=120,
            stdin=subprocess.DEVNULL)
        calls = ([json.loads(l) for l in calls_f.read_text().splitlines() if l.strip()]
                 if calls_f.exists() else [])
        check("no terminal: nothing to do, as today",
              "nothing to do" in p.stdout, p.stdout[-1000:])
        check("no terminal: the launch panel did not appear", not any(
            m in p.stdout for m in ("[t] I write the answer", "question(s) for you",
                                    "questions interrupted")), p.stdout[-1000:])
        check("no terminal: no item_start", not any(
            "item_start" in json.dumps(e) for e in _launch_events(root)))
        check("no terminal: the agent was not called", not calls, str(calls))


def test_launch_dry_run_on_terminal_does_not_ask():
    """CS-2: `--dry-run` shows the header and exits; the launch question is not asked."""
    rc, out, events, items = _launch_on_tty([], wait="2", extra=("--dry-run",))
    check("dry-run exits 0", rc == 0, out[-1500:])
    check("dry-run: no question panel", "question(s) for you" not in out
          and "[t] I write the answer" not in out, out[-1500:])
    check("dry-run: says nothing was executed", "nothing was executed" in out, out[-1500:])
    check("dry-run: a1 keeps its open route", items["a1"].get("human_pending"), str(items))


def test_launch_asks_only_owner_items_not_those_deferred_for_another_reason():
    """CS-2: a3 depends on a2 (deferred, as in the CS-1 header test), reason `depends-on-deferred`: not a question
    and not handed to `decide` (which would list it under "Not on you")."""
    a3 = item("a3")
    a3["blocked_by"] = ["a2"]
    a3["title"] = "item a3 dependent"
    rc, out, events, items = _launch_on_tty(
        [("[t] I write the answer", "n"), ("Anything to add", "")], wait="5",
        items=[item("a1"), item("a2", human_pending="provision the Keycloak role"), a3])
    check("the run exits 0", rc == 0, out[-1500:])
    check("the panel says 1 question", "1 question(s) for you" in out, out[-1500:])
    check("a3 is not asked as a question", "item a3 dependent" not in out, out[-1500:])
    check("a3 is not handed to decide (no 'Not on you' line)", "Not on you" not in out,
          out[-1500:])
    check("only one route was asked", out.count("I write the answer") <= 2, out[-1500:])


def test_launch_does_not_ask_about_delivered_items():
    """CS-2: a `done` item with an open `human_pending` is not part of the launch
    panel (`delivered_leftovers` is not added): total 1, its route text absent."""
    done = item("d1", status="done", human_pending="delivered leftover route text")
    rc, out, events, items = _launch_on_tty(
        [("[t] I write the answer", "n")], wait="5",
        items=[done, item("a1", human_pending="provision the Keycloak role")])
    check("the run exits 0", rc == 0, out[-1500:])
    check("the panel says 1 question", "1 question(s) for you" in out, out[-1500:])
    check("the open item was asked", "provision the Keycloak role" in out, out[-1500:])
    check("the delivered item's route is absent", "delivered leftover route text" not in out,
          out[-1500:])


def _before_first_item(out):
    """The launch output up to the line of the first item (`<id>   item 1`), ANSI
    stripped; that line is printed right where the ledger records `item_start`."""
    plain = ANSI.sub("", out)
    cut = re.search(r"^\[\d\d:\d\d\] \S+.*? {3}item 1 ", plain, re.M)
    return plain[:cut.start()] if cut else None


def test_launch_cs3_delivered_route_is_not_asked_before_the_first_item():
    """CS-3 (spec perguntar-antes-do-run), the declared scenario: a `done` item with
    an open `human_pending` and a `pending` item. The pending item starts, and the
    delivered item's route is not in the launch output before its `item_start`."""
    done = item("d1", status="done", human_pending="delivered leftover route text")
    rc, out, events, _ = _launch_on_tty([], wait="2", items=[done, item("a2")])
    starts = [e.get("id") for e in events if e.get("evento") == "item_start"]
    before = _before_first_item(out)
    check("the run exits 0", rc == 0, out[-1500:])
    check("the pending item starts", starts[:1] == ["a2"], str(events))
    check("the first item's line is in the output", before is not None, out[-2000:])
    check("the delivered route is absent before the first item",
          "delivered leftover route text" not in (before or ""), (before or "")[-1500:])
    check("no launch panel for a delivered route alone",
          "question(s) for you" not in (before or ""), (before or "")[-1500:])


def test_launch_cs3_panel_before_the_first_item_leaves_the_delivered_route_out():
    """CS-3 with a panel to compare: next to the delivered route, an open item with a
    route. The panel comes before the first `item_start`, asks the open route only,
    and the delivered one never shows up before the pending item starts."""
    done = item("d1", status="done", human_pending="delivered leftover route text")
    rc, out, events, _ = _launch_on_tty(
        [("[t] I write the answer", "n"), ("Anything to add", "")], wait="5",
        items=[done, item("a1", human_pending="provision the Keycloak role"), item("a2")])
    starts = [e.get("id") for e in events if e.get("evento") == "item_start"]
    before = _before_first_item(out) or ""
    check("the run exits 0", rc == 0, out[-1500:])
    check("the pending item starts", starts[:1] == ["a2"], str(events))
    check("the launch panel is before the first item, with 1 question",
          "1 question(s) for you" in before, before[-1500:])
    check("the open route is asked before the first item",
          "provision the Keycloak role" in before, before[-1500:])
    check("the delivered route is absent before the first item",
          "delivered leftover route text" not in before, before[-1500:])


def _answered(day, answer="não: Fecho o card?", old=""):
    """Evidence as `cepa-plan answer --keep` leaves it: the answer prepended."""
    return (f"Resposta do dono em {day}: {answer}. O dono manteve o item como estava "
            f"(`pending`, rota humana aberta). Evidência anterior: {old or 'x'}")


def _no_routes(day="2026-11-02"):
    a1 = item("a1", human_pending="first route text")
    a2 = item("a2", human_pending="second route text")
    a1["evidence"] = a2["evidence"] = _answered(day)
    return [a1, a2]


def test_last_owner_no_reads_only_the_first_answer():
    m = load_module()
    check("não at the start gives the date",
          m.last_owner_no(_answered("2026-11-02")) == "2026-11-02")
    check("nao without accent and upper case count",
          m.last_owner_no("Resposta do dono em 2026-11-03: NAO: x") == "2026-11-03")
    check("a later sim wins over the older não",
          m.last_owner_no(_answered("2026-11-05", "sim: ok",
                                    old=_answered("2026-11-02"))) is None)
    check("free text is not a não",
          m.last_owner_no(_answered("2026-11-05", "nada a ver")) is None)
    check("empty and None", m.last_owner_no("") is None and m.last_owner_no(None) is None)


def test_last_owner_no_tolerates_leading_whitespace():
    m = load_module()
    check("leading spaces and a newline before the answer still count",
          m.last_owner_no("  \n" + _answered("2026-11-02")) == "2026-11-02")


def test_launch_cs4_summary_line_shows_the_most_recent_of_several_dates():
    """Two routes answered "não" on different days: the line names the latest (09/11),
    not the oldest, and with the year turning the ISO comparison still picks the latest."""
    import contextlib, io
    m = load_module()
    for days, expected in ((("2026-11-02", "2026-11-09"), "09/11"),
                           (("2026-11-09", "2026-11-02"), "09/11"),
                           (("2026-12-30", "2027-01-02"), "02/01")):
        deferred = [{"id": f"a{i}", "reason": "human_pending",
                     "human_pending": f"route {i}", "evidence": _answered(d)}
                    for i, d in enumerate(days, 1)]
        m.query_queue = lambda *a, **k: ({"deferred": deferred}, None)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            got = m.ask_at_launch(Path("/nao/existe"), "fila", {"batch": []})
        out = buf.getvalue()
        line = [l for l in out.splitlines() if "already answered" in l]
        check(f"{days}: one line with 2 and {expected}",
              len(line) == 1 and "2 route(s)" in line[0]
              and f"last on {expected}" in line[0], out)
        check(f"{days}: nothing asked, data returned as is",
              got == {"batch": []} and "question(s) for you" not in out, out)


def test_launch_cs4_answered_no_routes_become_one_line_not_questions():
    """CS-4 declared scenario: two routes whose last answer was "não" on 2026-11-02."""
    rc, out, events, _ = _launch_on_tty([], wait="2", items=_no_routes() + [item("a3")])
    before = _before_first_item(out)
    check("the run exits 0", rc == 0, out[-1500:])
    check("the first item's line is in the output", before is not None, out[-2000:])
    line = [l for l in (before or "").splitlines() if "already answered" in l]
    check("one summary line with the count and the date",
          len(line) == 1 and "2 route(s)" in line[0] and "02/11" in line[0], before)
    check("neither route is asked",
          "[t] I write the answer" not in (before or "")
          and "question(s) for you" not in (before or "")
          and "first route text" not in (before or ""), (before or "")[-1500:])


def _cs10_check(label, items, answers, count):
    """CS-10: no item runs after the panel, so the run does not start: no branch, no
    worktree, no ledger; the output says so and points at `decide`."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, items)
        binv = fake_claude(tmp, "pass")
        env = env_do_run(tmp, root, binv)
        env["CEPA_UNTIL_ESPERA_RESPOSTA"] = "2"
        rc, out = on_tty(
            [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
             "--for", "2h", "--no-verify", "--no-analysis"], str(root),
            inputs=answers, env=env, timeout=90)
        branches = subprocess.run(["git", "-C", str(root), "branch", "--list", "until/*"],
                                  capture_output=True, text=True).stdout.strip()
        wts = subprocess.run(["git", "-C", str(root), "worktree", "list"],
                             capture_output=True, text=True).stdout.strip().splitlines()
        check(f"{label}: exits 0", rc == 0, out[-1500:])
        check(f"{label}: says no item runs and the run does not start",
              "nothing to do: no item runs, so the run does not start" in out, out[-1500:])
        check(f"{label}: the message names this run's branch, not a placeholder",
              re.search(r"no `until/\d{4}-\d{2}-\d{2}-\d{4}` branch", out) is not None
              and "<run_id>" not in out, out[-1500:])
        check(f"{label}: no until/* branch", branches == "", branches)
        check(f"{label}: worktree list has only the clone", len(wts) == 1, str(wts))
        check(f"{label}: no ledger events", _launch_events(root) == [], out[-800:])
        check(f"{label}: wait-for-you line with count {count}",
              f"{count} item(s) wait for you: cepa-until decide fila" in out, out[-1500:])


def test_launch_cs10_only_answered_no_routes_the_run_does_not_start():
    _cs10_check("cs10 answered no", _no_routes(), [], 2)


def test_launch_cs10_route_answered_no_in_the_panel_the_run_does_not_start():
    _cs10_check("cs10 panel n", [item("a1", human_pending="provision the Keycloak role")],
                [("[t] I write the answer", "n")], 1)


def test_launch_cs4_decide_on_the_queue_still_asks_both():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, _no_routes())
        cmd = [sys.executable, str(CEPA_UNTIL), "decide", "fila", "--repo", str(root)]
        rc, out = on_tty(cmd, str(root), inputs=[
            ("[t] I write the answer", "n"), ("Anything to add", ""),
            ("[t] I write the answer", "n"), ("Anything to add", "")])
        check("decide exits 0", rc == 0, out[-1500:])
        check("decide says 2 questions", "2 question(s) for you" in out, out[-1500:])
        check("both routes are asked",
              "first route text" in out and "second route text" in out, out[-1500:])


def test_launch_cs4_mixed_asks_only_the_unanswered_route():
    no = item("a1", human_pending="first route text")
    no["evidence"] = _answered("2026-11-02")
    rc, out, events, _ = _launch_on_tty(
        [("[t] I write the answer", "n"), ("Anything to add", "")], wait="5",
        items=[no, item("a2", human_pending="second route text"), item("a3")])
    before = _before_first_item(out) or ""
    line = [l for l in before.splitlines() if "already answered" in l]
    check("the run exits 0", rc == 0, out[-1500:])
    check("the line says 1 and 02/11",
          len(line) == 1 and "1 route(s)" in line[0] and "02/11" in line[0], before)
    check("the panel asks only the other one",
          "1 question(s) for you" in before and "second route text" in before
          and "first route text" not in before, before[-1500:])


def test_launch_cs4_latest_answer_wins_over_an_older_no():
    a1 = item("a1", human_pending="first route text")
    a1["evidence"] = _answered("2026-11-05", "sim: Fecho o card?",
                               old=_answered("2026-11-02"))
    rc, out, events, _ = _launch_on_tty(
        [("[t] I write the answer", "n"), ("Anything to add", "")], wait="5",
        items=[a1, item("a2")])
    before = _before_first_item(out) or ""
    check("the run exits 0", rc == 0, out[-1500:])
    check("no summary line", "already answered" not in before, before)
    check("the route is asked", "1 question(s) for you" in before
          and "first route text" in before, before[-1500:])


def test_launch_asks_every_owner_item_not_only_the_first():
    """CS-2: the read is uncapped: 2 owner-route items behind 2 runnable ones, 2 questions,
    "y" to both."""
    rc, out, events, _ = _launch_on_tty(
        [("[t] I write the answer", "y"), ("Anything to add", ""),
         ("[t] I write the answer", "y"), ("Anything to add", "")], wait="2",
        # p1 and p2 run: a read capped at `--max 1` stops at the cap (p2 is next)
        # and never reaches a1 and a2, which only the uncapped read sees.
        items=[item("p1"), item("p2"),
               item("a1", human_pending="first route text"),
               item("a2", human_pending="second route text")])
    check("the panel says 2 questions", "2 question(s) for you" in out, out[-1500:])
    check("both routes were asked", "first route text" in out and "second route text" in out,
          out[-1500:])
    check("both answers were taken (nothing left waiting at a prompt)",
          "no answer within" not in out and "2/2 · a2" in out, out[-1500:])
    check("the run exits 0", rc == 0, out[-1500:])


def test_launch_interrupt_at_the_question_prints_one_line_and_carries_on():
    for name, byte in (("Ctrl-C", "\x03"), ("EOF", "\x04")):
        rc, out, events, items = _launch_on_tty([("[t] I write the answer", byte)])
        check(f"{name}: exits 0", rc == 0, out[-1500:])
        check(f"{name}: prints the interrupted line", "questions interrupted" in out,
              out[-1500:])
        check(f"{name}: no traceback", "Traceback" not in out, out[-1500:])
        check(f"{name}: no item_start", not any(
            "item_start" in json.dumps(e) for e in events), str(events))


def test_launch_guard_needs_both_stdin_and_stdout_on_a_terminal():
    """CS-2: stdin on a pty with stdout on a pipe, and stdin DEVNULL with stdout on a
    pty: the panel does not appear in either."""
    markers = ("question(s) for you", "[t] I write the answer", "questions interrupted",
               "nobody answered")
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1", human_pending="provision the Keycloak role")])
        binv = fake_claude(tmp, "pass")
        env = env_do_run(tmp, root, binv)
        env["CEPA_UNTIL_ESPERA_RESPOSTA"] = "2"
        cmd = [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
               "--for", "2h", "--no-verify", "--no-analysis"]
        # a) stdin = pty, stdout = pipe
        master, slave = pty.openpty()
        try:
            p = subprocess.run(cmd, stdin=slave, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, env=env,
                               timeout=60, cwd=str(root))
            out = p.stdout
        except subprocess.TimeoutExpired as e:
            out = f"<timeout> {e.stdout}"
        finally:
            os.close(master)
            os.close(slave)
        check("stdin tty, stdout pipe: no panel", not any(m in out for m in markers)
              and "nothing to do" in out, out[-1500:])
        # b) stdin = DEVNULL, stdout = pty
        master, slave = pty.openpty()
        chunks = b""
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=slave,
                                stderr=slave, env=env, cwd=str(root))
        os.close(slave)
        end = time.time() + 60
        try:
            while time.time() < end:
                r, _, _ = select.select([master], [], [], 0.5)
                if r:
                    try:
                        d = os.read(master, 4096)
                    except OSError:
                        break
                    if not d:
                        break
                    chunks += d
                elif proc.poll() is not None:
                    break
            if proc.poll() is None:
                proc.kill()
            proc.wait()
        finally:
            os.close(master)
        out = chunks.decode(errors="replace")
        check("stdin devnull, stdout tty: no panel", not any(m in out for m in markers)
              and "nothing to do" in out, out[-1500:])


# ── CS-5: the pre-read defers an item with a missing pre-condition ──────────

def _fake_reader(tmp, mode):
    """A fake reader script (the closed JSON on stdout) and the file where it records
    the ids it was asked about. `mode` is what it prints for item x1."""
    script = Path(tmp) / "leitor.py"
    log = Path(tmp) / "leitor-chamadas.txt"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        "it = json.load(sys.stdin)\n"
        f"open({str(log)!r}, 'a').write(it['id'] + '\\n')\n"
        f"mode = {mode!r}\n"
        "if it['id'] != 'x1' or mode == 'null':\n"
        "    print(json.dumps({'tipo': None}))\n"
        "elif mode == 'pre':\n"
        "    print(json.dumps({'tipo': 'pre-condicao',\n"
        "        'texto': 'Falta o token de acesso do ambiente de homologação.',\n"
        "        'pergunta': 'Você já providenciou o token de acesso?'}))\n"
        "elif mode == 'longq':\n"
        "    print(json.dumps({'tipo': 'pre-condicao',\n"
        "        'texto': 'Falta o token de acesso do ambiente de homologação.',\n"
        "        'pergunta': ' '.join(['Você já providenciou o token de acesso']*10) + '?'}))\n"
        "elif mode == 'pref':\n"
        "    print(json.dumps({'tipo': 'preferencia', 'padrao': 'usar o formato curto',\n"
        "        'texto': 'Há duas formas de mostrar a data.',\n"
        "        'pergunta': 'Posso usar o formato curto?'}))\n"
        "elif mode == 'prefnodefault':\n"
        "    print(json.dumps({'tipo': 'preferencia', 'padrao': '  ',\n"
        "        'texto': 'Há duas formas de mostrar a data.',\n"
        "        'pergunta': 'Posso usar o formato curto?'}))\n"
        "elif mode == 'emptytext':\n"
        "    print(json.dumps({'tipo': 'pre-condicao', 'texto': '  ',\n"
        "        'pergunta': 'Você já providenciou o token de acesso?'}))\n"
        "elif mode == 'garbage':\n"
        "    print('this is not json')\n"
        "elif mode == 'fail':\n"
        "    sys.exit(3)\n")
    script.chmod(0o755)
    return script, log


def _pre_read_launch(mode, leitor=None, extra=(), x_item=None):
    """No terminal (stdin DEVNULL): queue with x1 and y1, the fake reader plugged
    through CEPA_UNTIL_LEITOR (or `leitor` as given). Returns (stdout, events, items,
    reader_calls)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [x_item or item("x1"), item("y1")])
        binv = fake_claude(tmp, "pass")
        script, log = _fake_reader(tmp, mode)
        env = env_do_run(tmp, root, binv)
        env["CEPA_UNTIL_LEITOR"] = leitor if leitor is not None else str(script)
        p = subprocess.run(
            [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
             "--for", "2h", "--no-verify", "--no-analysis", *extra],
            capture_output=True, text=True, env=env, timeout=120,
            stdin=subprocess.DEVNULL)
        calls = log.read_text().split() if log.exists() else []
        return p.stdout + p.stderr, _launch_events(root), items_of(root), calls


def _started(events):
    return [e.get("item") or e.get("id") for e in events if e.get("evento") == "item_start"]


def test_pre_read_cs5_precondition_defers_the_item_without_spending_the_run_on_it():
    out, events, items, calls = _pre_read_launch("pre")
    reads = [e for e in events if e.get("evento") == "leitura_previa"]
    check("cs5: one leitura_previa event", len(reads) == 1, out[-1500:])
    rows = {r["id"]: r for r in (reads[0]["itens"] if reads else [])}
    check("cs5: the event lists every item read", set(rows) == {"x1", "y1"}, str(rows))
    check("cs5: x1 is the pre-condition, y1 has no finding",
          rows.get("x1", {}).get("tipo") == "pre-condicao"
          and rows.get("y1", {}).get("tipo") is None, str(rows))
    check("cs5: the route was opened", rows.get("x1", {}).get("rota_aberta") is True
          and not rows["x1"].get("erro"), str(rows))
    check("cs5: no item_start of x1", "x1" not in _started(events), str(events))
    check("cs5: y1 still runs", "y1" in _started(events), str(events))
    check("cs5: queue.yaml has the open route on x1",
          "token" in str(items["x1"].get("human_pending")), str(items["x1"]))
    check("cs5: x1 stays pending (not blocked, not done)",
          items["x1"].get("status") == "pending", str(items["x1"]))
    check("cs5: the question is recorded", "token" in str(items["x1"].get("owner_question")),
          str(items["x1"]))
    check("cs5: leitura_previa comes right after run_start",
          [e.get("evento") for e in events][:2] == ["run_start", "leitura_previa"],
          str([e.get("evento") for e in events]))


def test_pre_read_cs5_route_keeps_the_previous_evidence_and_summary():
    old = "Red build: work left on branch side/x1 (commits abc123, def456)."
    x = dict(item("x1"), evidence=old, owner_summary={"impede": "o build ficou vermelho"})
    out, events, items, calls = _pre_read_launch("pre", x_item=x)
    check("cs5 evidence: the route opened", items["x1"].get("human_pending"), str(items["x1"]))
    check("cs5 evidence: the old text is still inside evidence",
          old in str(items["x1"].get("evidence")), str(items["x1"]))
    check("cs5 evidence: the finding comes first",
          str(items["x1"].get("evidence")).startswith("Pre-read at launch"),
          str(items["x1"]))
    check("cs5 evidence: owner_summary carried over",
          (items["x1"].get("owner_summary") or {}).get("impede") == "o build ficou vermelho",
          str(items["x1"]))
    check("cs5 evidence: x1 has no item_start", "x1" not in _started(events), out[-800:])


def test_pre_read_cs5_question_refused_by_cepa_plan_still_opens_the_route():
    out, events, items, calls = _pre_read_launch("longq")
    check("cs5 long question: the route opened without the question",
          "token" in str(items["x1"].get("human_pending")), str(items["x1"]))
    check("cs5 long question: x1 has no item_start", "x1" not in _started(events), out[-800:])
    reads = [e for e in events if e.get("evento") == "leitura_previa"]
    check("cs5 long question: event says rota_aberta without error",
          reads and reads[0]["itens"][0]["rota_aberta"] is True
          and not reads[0]["itens"][0]["erro"], str(reads))


def test_pre_read_cs5_preference_does_not_open_a_route_and_the_item_runs():
    out, events, items, calls = _pre_read_launch("pref")
    check("cs5 pref: x1 runs", "x1" in _started(events), out[-800:])
    check("cs5 pref: no route on x1", not items["x1"].get("human_pending"), str(items["x1"]))
    reads = [e for e in events if e.get("evento") == "leitura_previa"]
    row = {r["id"]: r for r in (reads[0]["itens"] if reads else [])}.get("x1", {})
    check("cs5 pref: the event records the preference, route not opened",
          row.get("tipo") == "preferencia" and row.get("rota_aberta") is False
          and row.get("padrao") == "usar o formato curto", str(row))


def test_pre_read_cs5_precondition_with_empty_text_is_no_finding():
    out, events, items, calls = _pre_read_launch("emptytext")
    check("cs5 empty text: x1 runs", "x1" in _started(events), out[-800:])
    check("cs5 empty text: no route on x1", not items["x1"].get("human_pending"),
          str(items["x1"]))
    reads = [e for e in events if e.get("evento") == "leitura_previa"]
    check("cs5 empty text: the event has tipo null",
          reads and all(r["tipo"] is None for r in reads[0]["itens"]), str(reads))


def test_pre_read_cs5_cepa_plan_refusing_both_attempts_runs_the_item_with_the_error():
    # The previous owner_summary is carried over to `finish` and fails its plain-text
    # validation (file name and commit code), with or without the question.
    x = dict(item("x1"), owner_summary={"impede": "quebrou em src/Foo.java no commit 3f9a2c1"})
    out, events, items, calls = _pre_read_launch("pre", x_item=x)
    reads = [e for e in events if e.get("evento") == "leitura_previa"]
    row = {r["id"]: r for r in (reads[0]["itens"] if reads else [])}.get("x1", {})
    check("cs5 refused: the event says rota_aberta false with an erro",
          row.get("tipo") == "pre-condicao" and row.get("rota_aberta") is False
          and row.get("erro"), str(row))
    check("cs5 refused: no route on x1", not items["x1"].get("human_pending"), str(items["x1"]))
    check("cs5 refused: x1 runs as today", "x1" in _started(events), out[-800:])
    check("cs5 refused: one line says the route could not be opened",
          "could not open the route of x1" in out, out[-800:])


def test_pre_read_cs5_orphan_reservation_needs_the_supervisor_flag():
    # `cepa-plan queue` returns an `in_progress` item with an orphan reservation as
    # executable; without `--supervisor`, `finish` refuses a claim that is not the
    # caller's (finish_gate), so the route would never open.
    x = dict(item("x1", status="in_progress"),
             claimed_by={"session_id": "morta", "pid": 1, "hostname": "outra-maquina",
                         "cwd": "/nao/existe", "branch": "until/old",
                         "started_at": "2026-01-01T00:00:00+00:00"})
    out, events, items, calls = _pre_read_launch("pre", x_item=x)
    check("cs5 orphan: the route opened", "token" in str(items["x1"].get("human_pending")),
          str(items["x1"]))
    check("cs5 orphan: x1 has no item_start", "x1" not in _started(events), out[-800:])


def test_pre_read_cs5_route_opened_by_the_pre_read_shows_in_the_launch_panel():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("x1"), item("y1")])
        binv = fake_claude(tmp, "pass")
        script, log = _fake_reader(tmp, "pre")
        env = env_do_run(tmp, root, binv)
        env["CEPA_UNTIL_LEITOR"] = str(script)
        env["CEPA_UNTIL_ESPERA_RESPOSTA"] = "2"
        rc, out = on_tty(
            [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
             "--for", "2h", "--no-verify", "--no-analysis"], str(root),
            inputs=[], env=env, timeout=90)
    panel = out.find("Falta o token de acesso")
    first = out.find("item_start")
    check("cs5 panel: the pre-read route text is in the launch panel",
          panel >= 0 and "question(s) for you" in out, out[-1500:])
    check("cs5 panel: it appears before the first item runs",
          panel >= 0 and (first < 0 or panel < first)
          and out.find("1st item") < panel, out[-1500:])


def test_pre_read_cs5_nothing_left_after_the_pre_read_means_no_run():
    # The queue is read again after a route is opened: with only x1 and its route
    # open, the batch is empty, so the run does not start (no run_start, no ledger).
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("x1")])
        binv = fake_claude(tmp, "pass")
        script, log = _fake_reader(tmp, "pre")
        env = env_do_run(tmp, root, binv)
        env["CEPA_UNTIL_LEITOR"] = str(script)
        p = subprocess.run(
            [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
             "--for", "2h", "--no-verify", "--no-analysis"],
            capture_output=True, text=True, env=env, timeout=120,
            stdin=subprocess.DEVNULL)
        events = _launch_events(root)
        check("cs5 empty batch: says nothing to do", "nothing to do" in p.stdout,
              p.stdout[-800:])
        check("cs5 empty batch: no run was started", not events, str(events))
        check("cs5 empty batch: the route is open", items_of(root)["x1"].get("human_pending"),
              str(items_of(root)["x1"]))


def test_pre_read_cs5_no_finding_garbage_or_failure_runs_the_item_as_today():
    for mode in ("null", "garbage", "fail"):
        out, events, items, calls = _pre_read_launch(mode)
        check(f"cs5 {mode}: x1 runs", "x1" in _started(events), out[-1500:])
        check(f"cs5 {mode}: no route on x1", not items["x1"].get("human_pending"),
              str(items["x1"]))
        reads = [e for e in events if e.get("evento") == "leitura_previa"]
        check(f"cs5 {mode}: the event says no finding",
              len(reads) == 1 and all(r["tipo"] is None for r in reads[0]["itens"]),
              str(reads))


def test_pre_read_cs5_dry_run_does_not_read():
    out, events, items, calls = _pre_read_launch("pre", extra=("--dry-run",))
    check("cs5 dry-run: the reader was not called", not calls, str(calls))
    check("cs5 dry-run: x1 keeps no route", not items["x1"].get("human_pending"),
          str(items["x1"]))


def test_pre_read_cs5_off_disables_it():
    out, events, items, calls = _pre_read_launch("pre", leitor="off")
    check("cs5 off: no leitura_previa event", not any(
        e.get("evento") == "leitura_previa" for e in events), out[-1500:])
    check("cs5 off: x1 runs", "x1" in _started(events), out[-1500:])


def test_pre_read_cs5_ceiling_kills_a_slow_reader_and_the_item_runs():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("x1")])
        binv = fake_claude(tmp, "pass")
        env = env_do_run(tmp, root, binv)
        env["CEPA_UNTIL_LEITOR"] = f"{sys.executable} -c 'import time; time.sleep(60)'"
        env["CEPA_UNTIL_TETO_LEITURA"] = "1"
        t0 = time.time()
        p = subprocess.run(
            [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
             "--for", "2h", "--no-verify", "--no-analysis"],
            capture_output=True, text=True, env=env, timeout=120,
            stdin=subprocess.DEVNULL)
        events = _launch_events(root)
        check("cs5 ceiling: the launch did not wait for the slow reader",
              time.time() - t0 < 40, f"{time.time() - t0:.0f}s")
        check("cs5 ceiling: x1 runs as today", "x1" in _started(events), p.stdout[-1500:])


# ── CS-7: the pre-read stops at the ceiling and the unread item runs as today ──

def _cs7_launch(items, reader, ceiling="1", body="pass"):
    """Real launch with `reader` as CEPA_UNTIL_LEITOR; returns (out, events)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, items)
        binv = fake_claude(tmp, body)
        env = env_do_run(tmp, root, binv)
        env["CEPA_UNTIL_LEITOR"] = reader(tmp) if callable(reader) else reader
        env["CEPA_UNTIL_TETO_LEITURA"] = ceiling
        p = subprocess.run(
            [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
             "--for", "2h", "--no-verify", "--no-analysis"],
            capture_output=True, text=True, env=env, timeout=120,
            stdin=subprocess.DEVNULL)
        return p.stdout + p.stderr, _launch_events(root)


def _cs7_reads(events):
    return [e for e in events if e.get("evento") == "leitura_previa"]


def test_pre_read_cs7_ceiling_marks_the_item_as_not_read_and_it_runs():
    out, events = _cs7_launch(
        [item("x1")], f"{sys.executable} -c 'import time; time.sleep(5)'")
    reads = _cs7_reads(events)
    ev = reads[0] if reads else {}
    row = next((r for r in ev.get("itens", []) if r.get("id") == "x1"), {})
    check("cs7 ceiling: one leitura_previa event", len(reads) == 1, str(reads))
    check("cs7 ceiling: the launch did not wait the reader's 5 s",
          ev.get("segundos", 99) < 5, str(ev.get("segundos")))
    check("cs7 ceiling: x1 is marked not read (teto)",
          row.get("lido") is False and row.get("nao_lido") == "teto", str(row))
    check("cs7 ceiling: listed in nao_lidos, lidos is 0",
          ev.get("nao_lidos") == ["x1"] and ev.get("lidos") == 0, str(ev))
    check("cs7 ceiling: x1 gets item_start", "x1" in _started(events), out[-1500:])
    check("cs7 ceiling: the screen says it was not read",
          "not read within the 1s ceiling: x1" in out, out[-1500:])


def test_pre_read_cs7_mixed_queue_only_the_slow_item_is_unread():
    def reader(tmp):
        script = Path(tmp) / "leitor_misto.py"
        script.write_text(
            "import sys, time\n"
            "if 'y1' in sys.stdin.read() + ' '.join(sys.argv):\n"
            "    time.sleep(5)\n"
            "print('null')\n")
        return f"{sys.executable} {script}"
    out, events = _cs7_launch([item("x1"), item("y1")], reader)
    ev = (_cs7_reads(events) or [{}])[0]
    rows = {r.get("id"): r for r in ev.get("itens", [])}
    check("cs7 mixed: x1 read", rows.get("x1", {}).get("lido") is True
          and rows["x1"].get("nao_lido") is None, str(rows))
    check("cs7 mixed: y1 not read (teto)", rows.get("y1", {}).get("lido") is False
          and rows["y1"].get("nao_lido") == "teto", str(rows))
    check("cs7 mixed: lidos 1, nao_lidos [y1]",
          ev.get("lidos") == 1 and ev.get("nao_lidos") == ["y1"], str(ev))
    check("cs7 mixed: both run", {"x1", "y1"} <= set(_started(events)), out[-1500:])


def test_pre_read_cs7_failing_reader_is_falha_not_teto():
    out, events = _cs7_launch(
        [item("x1")], f"{sys.executable} -c 'import sys; sys.exit(3)'")
    ev = (_cs7_reads(events) or [{}])[0]
    row = next((r for r in ev.get("itens", []) if r.get("id") == "x1"), {})
    check("cs7 falha: lido False, nao_lido falha",
          row.get("lido") is False and row.get("nao_lido") == "falha", str(row))
    check("cs7 falha: not in nao_lidos, lidos 0",
          ev.get("nao_lidos") == [] and ev.get("lidos") == 0, str(ev))
    check("cs7 falha: x1 runs", "x1" in _started(events), out[-1500:])


def test_pre_read_cs7_items_waiting_for_a_free_reader_past_the_ceiling_are_teto():
    ids = [f"w{n}" for n in range(1, 10)]  # 9 items > 8 reader workers
    out, events = _cs7_launch(
        [item(i) for i in ids], f"{sys.executable} -c 'import time; time.sleep(5)'",
        body="marca(primeiro_pendente(), status='done')")  # each item really finishes
    ev = (_cs7_reads(events) or [{}])[0]
    rows = {r.get("id"): r for r in ev.get("itens", [])}
    check("cs7 waiting: all 9 rows are teto and not read",
          len(rows) == 9 and all(r.get("lido") is False and r.get("nao_lido") == "teto"
                                 for r in rows.values()), str(rows))
    check("cs7 waiting: all 9 in nao_lidos, lidos 0",
          sorted(ev.get("nao_lidos", [])) == sorted(ids) and ev.get("lidos") == 0, str(ev))
    check("cs7 waiting: the 9th row, never launched, is teto",
          rows.get("w9", {}).get("nao_lido") == "teto", str(rows.get("w9")))
    check("cs7 waiting: the 9th item gets item_start", "w9" in _started(events),
          out[-1500:])



# ── CS-6: a preference runs with the agent's default, or with the owner's answer ──

def _requests(tmp):
    """The `-p` request of each fake `claude` call, in order (one per item attempt)."""
    f = Path(tmp) / "chamadas.jsonl"
    calls = [json.loads(l) for l in f.read_text().splitlines() if l.strip()] \
        if f.exists() else []
    return [c[c.index("-p") + 1] if "-p" in c else "" for c in calls]


def _pref_launch(mode="pref", tty_inputs=None, wait="5"):
    """Queue x1, y1 with the fake reader. `tty_inputs` None = no terminal; a list =
    on a pty with those answers. Returns (out, events, requests_by_item)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("x1"), item("y1")])
        binv = fake_claude(tmp, "pass")
        script, _ = _fake_reader(tmp, mode)
        env = env_do_run(tmp, root, binv)
        env["CEPA_UNTIL_LEITOR"] = str(script)
        env["CEPA_UNTIL_ESPERA_RESPOSTA"] = wait
        cmd = [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
               "--for", "2h", "--no-verify", "--no-analysis"]
        if tty_inputs is None:
            p = subprocess.run(cmd, capture_output=True, text=True, env=env,
                               timeout=120, stdin=subprocess.DEVNULL)
            out = p.stdout + p.stderr
        else:
            _, out = on_tty(cmd, str(root), inputs=tty_inputs, env=env, timeout=90)
        events = _launch_events(root)
        started = _started(events)
        reqs = _requests(tmp)
        return ANSI.sub("", out), events, dict(zip(started, reqs))


def test_pre_read_cs6_without_answer_the_prompt_carries_the_default_and_the_summary_lists_it():
    out, events, reqs = _pref_launch()
    check("cs6 default: x1 and y1 ran", set(reqs) == {"x1", "y1"}, str(reqs) + out[-800:])
    check("cs6 default: x1's prompt carries the default",
          "usar o formato curto" in reqs.get("x1", ""), str(reqs))
    check("cs6 default: the prompt says it was the agent's default",
          "the owner did not answer" in reqs.get("x1", ""), str(reqs))
    check("cs6 default: the prompt still starts with the drain-plan request",
          reqs.get("x1", "").startswith("/common:drain-plan fila --max 1"), str(reqs))
    check("cs6 default: y1's prompt has no note", "pre-read" not in reqs.get("y1", "x"),
          str(reqs))
    tail = out[out.find("ended at"):]
    check("cs6 default: the end summary lists the choice",
          "Choices the pre-read found (1)" in tail
          and "x1: usar o formato curto (the agent's default" in tail, tail[-1500:])
    check("cs6 default: the summary line carries what the choice was about",
          "Há duas formas de mostrar a data." in tail, tail[-1500:])
    start = [e for e in events if e.get("evento") == "item_start" and e.get("id") == "x1"]
    check("cs6 default: item_start of x1 records the choice and its source",
          start and start[0].get("preferencia") == {"escolha": "usar o formato curto",
                                                    "fonte": "padrao"}, str(start))
    reads = [e for e in events if e.get("evento") == "leitura_previa"]
    row = {r["id"]: r for r in (reads[0]["itens"] if reads else [])}.get("x1", {})
    check("cs6 default: leitura_previa records escolha and fonte",
          row.get("escolha") == "usar o formato curto" and row.get("fonte") == "padrao",
          str(row))


def test_pre_read_cs6_answer_typed_in_the_launch_panel_goes_into_the_prompt():
    out, events, reqs = _pref_launch(
        tty_inputs=[("Your choice, in one line", "mostrar a data por extenso")])
    check("cs6 answer: the panel showed the question and the default",
          "Posso usar o formato curto?" in out
          and "the agent goes with: usar o formato curto" in out, out[-1500:])
    check("cs6 answer: x1's prompt carries the owner's answer",
          "mostrar a data por extenso" in reqs.get("x1", ""), str(reqs) + out[-800:])
    check("cs6 answer: and not the default as the choice",
          "Go with: usar o formato curto" not in reqs.get("x1", ""), str(reqs))
    check("cs6 answer: the prompt says it was the owner's answer",
          "the owner's answer at the launch" in reqs.get("x1", ""), str(reqs))
    tail = out[out.find("ended at"):]
    check("cs6 answer: the summary says it was the owner's answer",
          "x1: mostrar a data por extenso (your answer at the launch)" in tail,
          tail[-1500:])
    start = [e for e in events if e.get("evento") == "item_start" and e.get("id") == "x1"]
    check("cs6 answer: item_start records fonte dono",
          start and (start[0].get("preferencia") or {}).get("fonte") == "dono", str(start))


def test_pre_read_cs6_enter_or_silence_in_the_panel_keeps_the_default():
    for label, inputs in (("enter", [("Your choice, in one line", "")]),
                          ("silence", [])):
        out, events, reqs = _pref_launch(tty_inputs=inputs, wait="2")
        check(f"cs6 {label}: x1 ran with the default",
              "Go with: usar o formato curto" in reqs.get("x1", ""), str(reqs) + out[-800:])
        check(f"cs6 {label}: y1 ran too", "y1" in reqs, str(reqs))
        if label == "silence":
            check("cs6 silence: one line says nobody answered",
                  "the remaining choice(s) run with the agent's default" in out,
                  out[-1500:])


def test_pre_read_cs6_preference_without_default_is_no_finding():
    out, events, reqs = _pref_launch(mode="prefnodefault")
    check("cs6 no default: x1 ran", "x1" in reqs, str(reqs) + out[-800:])
    check("cs6 no default: no note in x1's prompt", "pre-read" not in reqs.get("x1", "x"),
          str(reqs))
    reads = [e for e in events if e.get("evento") == "leitura_previa"]
    check("cs6 no default: the event says no finding",
          reads and all(r["tipo"] is None for r in reads[0]["itens"]), str(reads))
    check("cs6 no default: the summary has no choices block",
          "Choices the pre-read found" not in out, out[-800:])


def test_pre_read_cs6_note_and_command_units():
    mod = load_module()
    check("cs6 unit: no preference, no note", mod.preference_note("x1", None) == "")
    plain = mod.build_command("fila", "until/b", False)
    check("cs6 unit: without a note the request is unchanged",
          plain[2] == "/common:drain-plan fila --max 1 --na-branch until/b", str(plain))
    pref = {"texto": "T.", "padrao": "P", "escolha": "R", "fonte": "dono"}
    with_note = mod.build_command("fila", "until/b", False, note=mod.preference_note("x1", pref))
    check("cs6 unit: the note follows the request in its own paragraph",
          with_note[2].startswith("/common:drain-plan fila --max 1 --na-branch until/b\n\n")
          and "Go with: R" in with_note[2] and "item you reserve is x1" in with_note[2],
          str(with_note))
    sneaky = dict(pref, escolha="--offline --max 9 usar a-b")
    note = mod.preference_note("x1", sneaky)
    check("cs6 unit: no flag-looking word survives in the note",
          not re.search(r"(?<!\S)--?\w", note) and "usar a-b" in note, note)
    parsed = mod.parse_finding('{"tipo": "preferencia", "texto": "t", "padrao": " a  b "}')
    check("cs6 unit: the default is normalised", parsed and parsed["padrao"] == "a b",
          str(parsed))
    check("cs6 unit: the reader prompt asks for a preference with a default",
          "preferencia" in mod.READER_PROMPT and '"padrao"' in mod.READER_PROMPT)


# ── CS-8: the queue's questions come before the pre-read ends; its own go at the end ──

def _slow_reader(tmp, mode="pre", delay=2):
    """The CS-5 fake reader behind a `delay`-second sleep; it also writes, when it
    returns, a line to `leitor-fim.txt`, so the test knows the reading was not over
    yet when the queue's question was on the screen."""
    script, log = _fake_reader(tmp, mode)
    done = Path(tmp) / "leitor-fim.txt"
    slow = Path(tmp) / "leitor-lento.py"
    slow.write_text(
        f"#!{sys.executable}\n"
        "import subprocess, sys, time\n"
        f"time.sleep({delay})\n"
        f"p = subprocess.run([{str(script)!r}], input=sys.stdin.read(), text=True,\n"
        "                   capture_output=True)\n"
        "sys.stdout.write(p.stdout)\n"
        f"open({str(done)!r}, 'a').write('fim\\n')\n")
    slow.chmod(0o755)
    return slow, done


def _cs8_launch(items, mode="pre", inputs=None, wait="5", delay=2):
    """Real launch on a pty with the slow fake reader. Returns (out, events, items,
    reader_done_when_the_first_question_was_answered)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, items)
        binv = fake_claude(tmp, "pass")
        reader, done = _slow_reader(tmp, mode, delay)
        env = env_do_run(tmp, root, binv)
        env["CEPA_UNTIL_LEITOR"] = str(reader)
        env["CEPA_UNTIL_ESPERA_RESPOSTA"] = wait
        seen = {}

        def first_answer():
            # Read at the moment the first question is answered: the reader must
            # still be sleeping (the queue's panel did not wait for it).
            seen["reader_done"] = done.exists()
            return b""
        replies = inputs if inputs is not None else [
            ("[t] I write the answer", first_answer),
            ("[t] I write the answer", b"")]
        rc, out = on_tty_calls(
            [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
             "--for", "2h", "--no-verify", "--no-analysis"], str(root),
            inputs=replies, env=env, timeout=90)
        return ANSI.sub("", out), _launch_events(root), items_of(root), seen


def on_tty_calls(cmd, cwd, inputs=(), env=None, timeout=120):
    """`on_tty` where a reply may be a function, called when its trigger shows."""
    wrapped = []
    for trigger, reply in inputs:
        wrapped.append((trigger, reply))
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(cwd)
        os.execve(cmd[0], cmd, env or dict(os.environ))
    out_text, queue, end = "", list(wrapped), time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.5)
        if r:
            try:
                datum = os.read(fd, 4096)
            except OSError:
                break
            if not datum:
                break
            out_text += datum.decode(errors="replace")
        while queue and queue[0][0] in out_text:
            trigger, reply = queue.pop(0)
            out_text = out_text.replace(trigger, f"<{trigger}>", 1)
            if callable(reply):
                reply = reply()
            if isinstance(reply, str):
                reply = reply.encode()
            os.write(fd, reply + b"\n")
    if time.time() >= end:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        out_text += f"\n<on_tty: no answer within {timeout}s>"
    _, st = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(st), out_text


def test_launch_cs8_queue_route_comes_before_the_pre_read_question_and_the_total_sums_both():
    """CS-8 declared scenario: a reader that takes 2 seconds and a queue with one open
    route. The route's question is on the screen before the reading ends, the
    pre-read's question comes after it in the same list, and the total sums both."""
    out, events, items, seen = _cs8_launch(
        [item("r1", human_pending="provision the Keycloak role"), item("x1"),
         item("y1")])
    route = out.find("provision the Keycloak role")
    found = out.find("Falta o token de acesso")
    check("cs8: the queue's route is asked", route >= 0, out[-2500:])
    check("cs8: the pre-read's question is asked", found >= 0, out[-2500:])
    check("cs8: the route comes before the pre-read's question",
          0 <= route < found, out[-2500:])
    check("cs8: the route was on the screen before the reading ended",
          seen.get("reader_done") is False, str(seen))
    check("cs8: the panel says the pre-read is still reading",
          "the pre-read is still reading" in out[:route if route >= 0 else None],
          out[:2500])
    check("cs8: the pre-read's question is numbered after the queue's (2/2)",
          "[2/2] x1" in out or "2/2 · x1" in out, out[-2500:])
    check("cs8: the panel total sums both (2 question(s) in total)",
          "2 question(s) in total" in out, out[-2500:])
    check("cs8: the list opens once (one header before 2/2 · x1)",
          out[:out.find("2/2 · x1")].count("question(s) for you") == 1
          and out[:out.find("── closing")].count("question(s) for you") == 1,
          out[-2500:])
    check("cs8: the list closes once",
          out.count("Answered now:") + out.count("answered now ") == 1, out[-2500:])
    check("cs8: y1 still runs", "y1" in _started(events), out[-1500:])
    check("cs8: x1 is deferred by its open route",
          "x1" not in _started(events) and "token" in str(items["x1"].get("human_pending")),
          str(items["x1"]))


def test_launch_cs8_without_queue_routes_the_pre_read_opens_the_panel_itself():
    """No route in the queue: the pre-read's question opens a normal panel (1/1)."""
    out, events, items, _ = _cs8_launch(
        [item("x1"), item("y1")], inputs=[("[t] I write the answer", "")])
    check("cs8 alone: one question for you", "1 question(s) for you" in out, out[-2500:])
    check("cs8 alone: not announced as still reading",
          "the pre-read is still reading" not in out, out[-2500:])
    check("cs8 alone: numbered 1/1", "[1/1] x1" in out or "1/1 · x1" in out, out[-2500:])


def test_launch_cs8_preference_counts_in_the_total_after_the_queue_route():
    """A preference found by the pre-read comes after the queue's route and counts in
    the total; Enter keeps the default and the item runs."""
    out, events, items, _ = _cs8_launch(
        [item("r1", human_pending="provision the Keycloak role"), item("x1")],
        mode="pref", inputs=[("[t] I write the answer", ""),
                             ("Your choice, in one line", "")])
    route = out.find("provision the Keycloak role")
    pref = out.find("Posso usar o formato curto?")
    check("cs8 pref: the route comes before the preference", 0 <= route < pref,
          out[-2500:])
    check("cs8 pref: the total sums both", "2 question(s) in total" in out, out[-2500:])
    check("cs8 pref: the preference is numbered 2/2", "2/2 · x1" in out, out[-2500:])
    check("cs8 pref: x1 runs", "x1" in _started(events), out[-1500:])


def test_launch_cs8_route_just_opened_is_asked_even_over_an_old_no():
    """A route the pre-read opened on an item whose evidence starts with an old "não"
    is still asked: it is counted in the total, so it must be shown."""
    import contextlib, io
    m = load_module()
    deferred = [{"id": "x1", "reason": "human_pending", "human_pending": "token",
                 "evidence": _answered("2026-11-02")}]
    m.query_queue = lambda *a, **k: ({"deferred": deferred}, None)
    asked = []
    m.decide = lambda *a, **k: (asked.append([d["id"] for d in a[4]]), ([], []))[1]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        m.ask_at_launch(Path("/nao/existe"), "fila", {"batch": []}, only={"x1"},
                        tally={"shown": 1, "of": 2})
    check("cs8 old no: the just-opened route is asked", asked == [["x1"]], str(asked))
    check("cs8 old no: no CS-4 summary line in the pre-read part",
          "already answered" not in buf.getvalue(), buf.getvalue())


def test_launch_cs8_empty_queue_route_and_preference_from_the_pre_read_share_one_count():
    """No route in the queue; the pre-read opens a route on x1 and finds a preference
    on y1: one header with 2, numbered 1/2 (the route) and 2/2 (the preference)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("x1"), item("y1")])
        binv = fake_claude(tmp, "pass")
        reader = Path(tmp) / "leitor-misto.py"
        reader.write_text(
            f"#!{sys.executable}\n"
            "import json, sys\n"
            "it = json.load(sys.stdin)\n"
            "if it['id'] == 'x1':\n"
            "    print(json.dumps({'tipo': 'pre-condicao',\n"
            "        'texto': 'Falta o token de acesso do ambiente de homologação.',\n"
            "        'pergunta': 'Você já providenciou o token de acesso?'}))\n"
            "else:\n"
            "    print(json.dumps({'tipo': 'preferencia', 'padrao': 'usar o formato curto',\n"
            "        'texto': 'Há duas formas de mostrar a data.',\n"
            "        'pergunta': 'Posso usar o formato curto?'}))\n")
        reader.chmod(0o755)
        env = env_do_run(tmp, root, binv)
        env["CEPA_UNTIL_LEITOR"] = str(reader)
        env["CEPA_UNTIL_ESPERA_RESPOSTA"] = "5"
        _, out = on_tty(
            [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
             "--for", "2h", "--no-verify", "--no-analysis"], str(root),
            inputs=[("[t] I write the answer", ""), ("Your choice, in one line", "")],
            env=env, timeout=90)
        out = ANSI.sub("", out)
    launch = out[:out.find("── closing")]
    check("cs8 mixed: one header with the sum", "2 question(s) for you" in launch
          and launch.count("question(s) for you") == 1, launch[-2500:])
    check("cs8 mixed: the route is 1/2", "1/2 · x1" in out, out[-2500:])
    check("cs8 mixed: the preference is 2/2", "2/2 · y1" in out, out[-2500:])



# ── CS-9: an option skips the pre-read and the panel; no terminal reads without one ──

def _mixed_reader(tmp):
    """Fake reader: x1 has a missing pre-condition, y1 a preference, the rest nothing.
    Records each id it was asked about."""
    script = Path(tmp) / "leitor-misto.py"
    log = Path(tmp) / "leitor-chamadas.txt"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        "it = json.load(sys.stdin)\n"
        f"open({str(log)!r}, 'a').write(it['id'] + '\\n')\n"
        "if it['id'] == 'x1':\n"
        "    print(json.dumps({'tipo': 'pre-condicao',\n"
        "        'texto': 'Falta o token de acesso do ambiente de homologação.',\n"
        "        'pergunta': 'Você já providenciou o token de acesso?'}))\n"
        "elif it['id'] == 'y1':\n"
        "    print(json.dumps({'tipo': 'preferencia', 'padrao': 'usar o formato curto',\n"
        "        'texto': 'Há duas formas de mostrar a data.',\n"
        "        'pergunta': 'Posso usar o formato curto?'}))\n"
        "else:\n"
        "    print(json.dumps({'tipo': None}))\n")
    script.chmod(0o755)
    return script, log


def _cs9_items():
    return [item("r1", human_pending="provision the Keycloak role"), item("x1"),
            item("y1")]


def test_launch_cs9_option_on_terminal_skips_the_pre_read_and_the_panel():
    """CS-9 declared scenario, first half: with the option, the ledger has no
    `leitura_previa`, nothing is asked at the launch, and the CS-1 line is there."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, _cs9_items())
        binv = fake_claude(tmp, "pass")
        reader, log = _mixed_reader(tmp)
        env = env_do_run(tmp, root, binv)
        env["CEPA_UNTIL_LEITOR"] = str(reader)
        env["CEPA_UNTIL_ESPERA_RESPOSTA"] = "2"
        rc, out = on_tty(
            [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
             "--for", "2h", "--no-verify", "--no-analysis", "--no-pre-read"],
            str(root), inputs=[], env=env, timeout=90)
        events = _launch_events(root)
        calls = log.read_text().split() if log.exists() else []
        launch = _before_first_item(out)
    plain = ANSI.sub("", out)
    check("cs9 option: the option is accepted (exit 0)", rc == 0, plain[-1500:])
    check("cs9 option: no leitura_previa in the ledger",
          not any(e.get("evento") == "leitura_previa" for e in events),
          str([e.get("evento") for e in events]))
    check("cs9 option: the reader was not called", not calls, str(calls))
    check("cs9 option: the launch reaches the first item", launch is not None,
          plain[-2500:])
    check("cs9 option: nothing is asked before the first item",
          launch is not None and not any(m in launch for m in (
              "[t] I write the answer", "question(s) for you", "Your choice",
              "pre-read")), (launch or plain)[-2500:])
    check("cs9 option: the CS-1 forecast line is there",
          "start: 2 run, 1 wait for the owner" in plain, plain[:2500])
    check("cs9 option: x1 and y1 run as today", {"x1", "y1"} <= set(_started(events)),
          str(_started(events)))


def test_launch_cs9_option_has_a_portuguese_alias_and_is_in_the_help():
    p = subprocess.run([sys.executable, str(CEPA_UNTIL), "--help"],
                       capture_output=True, text=True, timeout=60)
    check("cs9 help: --no-pre-read is documented", "--no-pre-read" in p.stdout,
          p.stdout[-2000:])
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, _cs9_items())
        binv = fake_claude(tmp, "pass")
        reader, log = _mixed_reader(tmp)
        env = env_do_run(tmp, root, binv)
        env["CEPA_UNTIL_LEITOR"] = str(reader)
        q = subprocess.run(
            [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
             "--for", "2h", "--no-verify", "--no-analysis", "--sem-leitura"],
            capture_output=True, text=True, env=env, timeout=120,
            stdin=subprocess.DEVNULL)
        events = _launch_events(root)
        check("cs9 alias: --sem-leitura accepted", q.returncode == 0, q.stderr[-800:])
        check("cs9 alias: no terminal + option: no leitura_previa, reader not called",
              not any(e.get("evento") == "leitura_previa" for e in events)
              and not log.exists(), str(events))
        check("cs9 alias: x1 runs (nothing deferred it)", "x1" in _started(events),
              str(_started(events)))


def test_launch_cs9_without_terminal_reads_and_lists_the_questions_as_text():
    """CS-9 declared scenario, second half: no terminal and no option. stdin is a pipe
    whose write end stays open the whole run, so any read of input would hang until
    the timeout instead of getting EOF."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, _cs9_items())
        binv = fake_claude(tmp, "pass")
        reader, log = _mixed_reader(tmp)
        env = env_do_run(tmp, root, binv)
        env["CEPA_UNTIL_LEITOR"] = str(reader)
        env["CEPA_UNTIL_ESPERA_RESPOSTA"] = "600"
        rfd, wfd = os.pipe()
        try:
            proc = subprocess.Popen(
                [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
                 "--for", "2h", "--no-verify", "--no-analysis"],
                stdin=rfd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, env=env)
            os.close(rfd)
            try:
                out, _ = proc.communicate(timeout=120)
                hung = False
            except subprocess.TimeoutExpired:
                proc.kill()
                out, _ = proc.communicate()
                hung = True
        finally:
            os.close(wfd)
        events = _launch_events(root)
        items = items_of(root)
    check("cs9 no terminal: the run ends without waiting for input",
          not hung and proc.returncode == 0, out[-1500:])
    reads = [e for e in events if e.get("evento") == "leitura_previa"]
    check("cs9 no terminal: leitura_previa is in the ledger", len(reads) == 1,
          str([e.get("evento") for e in events]))
    check("cs9 no terminal: the pre-read's questions are listed as text",
          "the pre-read's questions (2)" in out
          and "Você já providenciou o token de acesso?" in out
          and "Posso usar o formato curto?" in out, out[-2500:])
    check("cs9 no terminal: the preference line names the default",
          "runs with the agent's default: usar o formato curto" in out, out[-2500:])
    check("cs9 no terminal: the listing says where to answer",
          "cepa-until decide fila" in out, out[-2500:])
    check("cs9 no terminal: no panel prompt",
          not any(m in out for m in ("[t] I write the answer", "question(s) for you",
                                     "Your choice", "nobody answered in")), out[-2500:])
    check("cs9 no terminal: x1 deferred by the route, y1 runs",
          "x1" not in _started(events) and "y1" in _started(events)
          and "token" in str(items["x1"].get("human_pending")), str(_started(events)))


def test_pre_read_as_text_unit():
    m = load_module()
    lines = []
    m.pre_read_as_text("fila", [{"id": "a", "tipo": None, "rota_aberta": False}], {},
                       output=lines.append)
    check("cs9 unit: no finding prints nothing", lines == [], str(lines))
    lines = []
    m.pre_read_as_text("fila", [{"id": "a", "tipo": "pre-condicao", "rota_aberta": False,
                                 "texto": "t", "pergunta": "q?"}], {},
                       output=lines.append)
    check("cs9 unit: a route that failed to open is not listed as deferred",
          lines == [], str(lines))
    lines = []
    m.pre_read_as_text("fila", [], {"b": {"texto": "t", "pergunta": None, "padrao": "P"}},
                       output=lines.append)
    joined = "\n".join(lines)
    check("cs9 unit: a preference alone is listed, without the decide line",
          "b (runs with the agent's default: P): t" in joined
          and "cepa-until decide" not in joined, joined)


def main():
    print("cepa-until decidir — o fim do run pergunta\n")
    for given_name, fn in sorted(globals().items()):
        if given_name.startswith("test_") and callable(fn):
            print(f"{given_name}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
