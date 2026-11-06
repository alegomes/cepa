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
