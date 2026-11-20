#!/usr/bin/env python3
"""CS-10 of docs/spec/perguntas-da-largada-legiveis.md: in the pre-read's choice at
the launch, `y` or Enter accepts the agent's default, `n` asks for one line saying
what to do instead (an empty line goes back to the menu, nothing recorded), `w`
records a free answer. Loose text is no longer the whole choice. The owner's choice
is recorded in the `largada` event of the run's ledger, with `fonte` "dono".

Run with `python3 tests/test_cepa_until_preference_keys.py`, exit 1 on any failure.
"""
import contextlib
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_cepa_until_decide as base  # noqa: E402
from test_cepa_until_decide import check, FAILURES, _pref_launch  # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
QUESTION = "Posso usar o formato curto?"
DEFAULT = "usar o formato curto"
MENU = "Your choice, in one line"
INSTEAD = "What should the agent do instead"


def _largada_choice(events, ident="x1"):
    found = [e for e in events if e.get("evento") == "largada"]
    if len(found) != 1:
        return None
    return {c.get("id"): c for c in found[0].get("escolhas") or []}.get(ident)


def test_cs10_n_then_a_line_records_no_question_instead_in_largada():
    out, events, reqs = _pref_launch(tty_inputs=[(MENU, "n"),
                                                 (INSTEAD, "usar a data da guia")])
    want = f"não: {QUESTION}. Em vez disso: usar a data da guia"
    choice = _largada_choice(events)
    check("cs10 n: largada records the choice", choice is not None
          and choice.get("escolha") == want, str(choice) + out[-1500:])
    check("cs10 n: with fonte dono", (choice or {}).get("fonte") == "dono", str(choice))
    check("cs10 n: the item's agent receives it", want in reqs.get("x1", ""),
          str(reqs) + out[-800:])
    check("cs10 n: the item's agent is told it is the owner's answer",
          "the owner's answer at the launch" in reqs.get("x1", ""), str(reqs))


def test_cs10_n_with_an_empty_line_goes_back_to_the_menu_without_recording():
    out, events, reqs = _pref_launch(tty_inputs=[(MENU, "n"), (INSTEAD, ""),
                                                 (MENU, "")])
    check("cs10 n empty: the menu was asked again", out.count(MENU) >= 2, out[-1500:])
    choice = _largada_choice(events)
    check("cs10 n empty: nothing recorded as the owner's",
          choice is not None and choice.get("fonte") == "padrao"
          and choice.get("escolha") == DEFAULT, str(choice) + out[-1500:])
    check("cs10 n empty: the item runs with the default",
          f"Go with: {DEFAULT}" in reqs.get("x1", ""), str(reqs))


def test_cs10_w_records_a_free_answer():
    out, events, reqs = _pref_launch(tty_inputs=[(MENU, "w"),
                                                 ("Your answer, in one line", "mostrar a data por extenso")])
    choice = _largada_choice(events)
    check("cs10 w: the free answer is the choice", choice is not None
          and choice.get("escolha") == "mostrar a data por extenso"
          and choice.get("fonte") == "dono", str(choice) + out[-1500:])


def test_cs10_loose_text_is_not_the_choice():
    out, events, reqs = _pref_launch(tty_inputs=[(MENU, "mostrar a data por extenso"),
                                                 (MENU, "")])
    check("cs10 loose: the screen says it is not an option",
          "is not one of the options" in out, out[-1500:])
    choice = _largada_choice(events)
    check("cs10 loose: the loose text did not become the choice",
          choice is not None and choice.get("escolha") == DEFAULT
          and choice.get("fonte") == "padrao", str(choice))


def _in_process(answers, panel):
    m = base.load_module(color="sempre" if panel else "nunca")
    prefs = {"x1": {"texto": "T.", "pergunta": QUESTION, "padrao": DEFAULT,
                    "escolha": DEFAULT, "fonte": "padrao"}}
    feed, prompts = list(answers), []

    def question(prompt):
        prompts.append(ANSI.sub("", prompt))
        return feed.pop(0)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        m.ask_preferences(prefs, wait=600, question=question)
    return prefs["x1"], prompts, ANSI.sub("", buf.getvalue())


def test_cs10_in_process_each_key_on_both_screens():
    for panel in (True, False):
        tag = "panel" if panel else "plain"
        got, _, _ = _in_process(["y"], panel)
        check(f"cs10 {tag} y: the default, answered by the owner",
              got["escolha"] == DEFAULT and got["fonte"] == "dono", str(got))
        got, _, _ = _in_process(["yes"], panel)
        check(f"cs10 {tag} yes: same as y", got["fonte"] == "dono", str(got))
        got, _, _ = _in_process([""], panel)
        check(f"cs10 {tag} Enter: the default, fonte stays padrao",
              got["escolha"] == DEFAULT and got["fonte"] == "padrao", str(got))
        got, _, _ = _in_process(["N", "usar a data da guia"], panel)
        check(f"cs10 {tag} n: não + question + instead",
              got["escolha"] == f"não: {QUESTION}. Em vez disso: usar a data da guia"
              and got["fonte"] == "dono", str(got))
        got, prompts, _ = _in_process(["n", "  ", "w", "", "x", ""], panel)
        check(f"cs10 {tag} n/w empty and loose: back to the menu each time",
              got["fonte"] == "padrao" and got["escolha"] == DEFAULT
              and sum(MENU in p for p in prompts) == 4, str(got) + str(prompts))
        got, _, _ = _in_process(["w", "outra   coisa"], panel)
        check(f"cs10 {tag} w: the free line, spaces collapsed",
              got["escolha"] == "outra coisa" and got["fonte"] == "dono", str(got))
    _, _, screen = _in_process([""], True)
    check("cs10 panel: the menu shows y, n and w",
          all(k in screen for k in ("[y] ", "[n] ", "[w] ")), screen)
    check("cs10 panel: Enter still keeps the default (CS-9's chip)",
          "[Enter] keep the agent's default (recommended)" in screen, screen)


def test_cs1_the_launch_screen_shows_y_n_w_and_not_s_t():
    tty = [(MENU, "")]
    full, _, _ = _pref_launch(tty_inputs=tty)
    # Only the launch preference screen: later cards of the run are CS-2's scope.
    start = full.find("choice(s) the pre-read found")
    end = full.find("Enter keeps the default]", start)
    out = full[start:end + 30] if start >= 0 and end >= 0 else full
    check("cs1 screen: [y] chip", "[y] yes, go with the agent's default" in out, out[-1500:])
    check("cs1 screen: [w] chip", "[w] I write the answer" in out, out[-1500:])
    check("cs1 screen: the prompt", "[y/n/w, Enter keeps the default]" in out, out[-1500:])
    check("cs1 screen: no [s], [t] nor s/n/t",
          "[s]" not in out and "[t]" not in out and "s/n/t" not in out, out[-1500:])
    note = " ".join(re.sub(r"[│┃|]", " ", out).split())  # the note may wrap in the frame
    check("cs1 screen: the opening note names y and w",
          "y accepts the agent's default" in note and "w writes a free answer" in note, note[:600])
    check("cs1 screen: the opening note no longer names s or t",
          "s accepts" not in note and "t writes" not in note, note[:600])


def test_cs1_typing_y_records_the_default_with_fonte_dono():
    out, events, reqs = _pref_launch(tty_inputs=[(MENU, "y")])
    choice = _largada_choice(events)
    check("cs1 y: the choice is the agent's default, fonte dono", choice is not None
          and choice.get("escolha") == DEFAULT and choice.get("fonte") == "dono",
          str(choice) + out[-1500:])


def test_cs1_typing_w_and_a_line_records_that_line():
    out, events, reqs = _pref_launch(tty_inputs=[(MENU, "w"),
                                                 ("Your answer, in one line", "mostrar a data por extenso")])
    choice = _largada_choice(events)
    check("cs1 w: the line is the choice", choice is not None
          and choice.get("escolha") == "mostrar a data por extenso"
          and choice.get("fonte") == "dono", str(choice) + out[-1500:])
    check("cs1 w: no invalid-option message", "is not one of the options" not in out, out[-1500:])


def test_cs1_plain_screen_menu_line_uses_y_and_w():
    _, _, screen = _in_process([""], False)
    check("cs1 plain: menu line", "[y] yes, go with the default" in screen
          and "[w] I write the answer" in screen and "[s]" not in screen
          and "[t]" not in screen, screen)
    check("cs1 plain: the opening note names y and w",
          "y accepts the agent's default" in screen and "w writes a free answer" in screen, screen)
    check("cs1 plain: the opening note no longer names s or t",
          "s accepts" not in screen and "t writes" not in screen, screen)


def test_cs1_invalid_option_message_says_type_w_first():
    _, _, screen = _in_process(["blah", ""], False)
    check("cs1 invalid: type w first", "type w first" in screen and "type t first" not in screen, screen)


def test_cs10_without_question_n_uses_the_choice_text():
    m = base.load_module(color="nunca")
    prefs = {"x1": {"texto": "Qual formato?", "pergunta": None, "padrao": DEFAULT,
                    "escolha": DEFAULT, "fonte": "padrao"}}
    feed = ["n", "por extenso"]
    with contextlib.redirect_stdout(io.StringIO()):
        m.ask_preferences(prefs, wait=600, question=lambda p: feed.pop(0))
    check("cs10 no question: n names the choice text",
          prefs["x1"]["escolha"] == "não: Qual formato?. Em vez disso: por extenso",
          str(prefs))


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"{name}:")
            fn()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
