#!/usr/bin/env python3
"""CS-3 of docs/spec/perguntas-da-largada-legiveis.md: no route gets the fixed
phrase "done already?", and the legend under the question has one line per key
of the menu.

Before: a route with no written question got "done already? With yes, the task
closes and the item goes back to the queue." (L2, L3 of the spec), and the legend
was a single line ("yes = ...; no = ...; d = ...") that named three of the seven
keys and described "yes" a second way. Now the question stops describing what the
keys do, and the legend says it once, a line per key, in the same order as the
menu ("Decided without asking": "Task" and "item" never in the same sentence).

Its own file so the proof gate can run it alone:
`python3 tests/test_cepa_until_legend_per_key.py`, exit 1 on any failure.
"""
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import CEPA_UNTIL, build_repo, item  # noqa: E402
from test_cepa_until_decide import (  # noqa: E402
    ANSI, FAILURES, check, load_module, on_tty)

LEGEND_LINE = re.compile(r"^(s|n|t|d|e|Enter|q) = \S")


def _legend_keys(block_lines):
    """The keys the legend explains, one per line, in order."""
    keys = []
    for l in block_lines:
        m = LEGEND_LINE.match(l.lstrip("│ ").strip())
        if m:
            keys.append(m.group(1))
    return keys


def _menu_keys(block_lines):
    """The keys of the menu chips (`[s] yes · [n] no · ...`)."""
    keys = []
    for l in block_lines:
        if "[q] quit" in l or "[Enter] later" in l or "[s] yes" in l:
            keys += re.findall(r"\[(\w+)\]", l)
    return keys


def _blocks(plain, idents):
    """Splits the panel into one block of lines per item, by the card header."""
    out = {}
    lines = plain.splitlines()
    starts = [(i, ident) for i, l in enumerate(lines) for ident in idents
              if re.search(rf"\d+/\d+ · {re.escape(ident)}\b", l)]
    starts.sort()
    for n, (i, ident) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
        out[ident] = lines[i:end]
    return out


def test_decide_on_terminal_has_no_done_already_and_one_legend_line_per_key():
    """Red test of CS-3, as a process in a pseudo-terminal: `cepa-until decide fila`
    over an item with `human_pending` and no question does not contain "done
    already" nor "the task closes and the item goes back", and the legend has a line
    for each key of the menu. A delivered (`done`) route with no question, the other
    branch that said "done already?", is covered too."""
    with tempfile.TemporaryDirectory() as tmp:
        x1 = item("x1", status="pending", human_pending="valide o login real")
        d1 = item("d1", status="done", human_pending="crie o papel no portal")
        root = build_repo(tmp, [x1, d1])
        cmd = [sys.executable, str(CEPA_UNTIL), "decide", "fila", "--repo", str(root)]
        rc, out = on_tty(cmd, str(root), inputs=[
            ("[t] I write the answer", ""), ("[t] I write the answer", "")])
        plain = ANSI.sub("", out)
        flat = " ".join(plain.split())
        check("CS-3 pty: decide exits 0", rc == 0, plain[-1500:])
        check("CS-3 pty: both routes reached the screen",
              "valide o login real" in plain and "crie o papel no portal" in plain,
              plain)
        check("CS-3 pty: no 'done already'", "done already" not in flat.lower(), plain)
        check("CS-3 pty: no 'the task closes and the item goes back'",
              "the task closes and the item goes back" not in flat.lower(), plain)
        blocks = _blocks(plain, ["x1", "d1"])
        check("CS-3 pty: one card per item", set(blocks) == {"x1", "d1"}, plain)
        for ident, lines in blocks.items():
            menu = _menu_keys(lines)
            legend = _legend_keys(lines)
            check(f"CS-3 pty {ident}: the menu has its keys", len(menu) >= 6, lines)
            check(f"CS-3 pty {ident}: the legend has one line per menu key, in "
                  "the menu's order", legend == menu, (legend, menu, lines))
            check(f"CS-3 pty {ident}: the route without a question still gets a "
                  "question", any(l.lstrip("│ ").startswith("? ") for l in lines),
                  lines)
            check(f"CS-3 pty {ident}: 'task' and 'item' never in one legend line",
                  not any("task" in l.lower() and "item" in l.lower()
                          for l in lines if LEGEND_LINE.match(l.lstrip("│ ").strip())),
                  lines)


def test_decide_without_terminal_legend_is_one_line_per_key():
    """Outside a terminal the panel prints the legend too, one indented line per
    key, and the question no longer describes the keys. With the agent's
    `se_sim`/`se_nao`, the yes and no lines carry what each answer does to the
    work."""
    m = load_module()
    screen, prompts = [], []
    deferred = [
        {"id": "x1", "title": "t", "reason": "human_pending",
         "human_pending": "valide o login", "question": None, "evidence": "ev"},
        {"id": "w1", "title": "t", "reason": "blocked-before", "human_pending": None,
         "question": "Entrego com os 18 casos pendentes?", "evidence": "",
         "owner_summary": {"impede": "o sistema responde em branco",
                           "se_sim": "o trabalho vai para revisão",
                           "se_nao": "o trabalho espera o defeito"}},
        {"id": "d1", "title": "t", "reason": "pos-entrega",
         "human_pending": "crie o papel", "question": None, "evidence": ""},
    ]
    answers = iter(["", "", ""])

    def ask(p):
        prompts.append(p)
        return next(answers, "")
    m.decide(Path("/nao/existe"), "fila", None, {}, deferred, {},
             question=ask, output=screen.append,
             answer=lambda i, t, keep=False, drop=False: (0, "ok"))
    text = "\n".join(screen)
    check("CS-3 text: no 'done already'", "done already" not in text, text)
    check("CS-3 text: no 'the task closes and the item goes back'",
          "the task closes and the item goes back" not in text, text)
    for n, ident in enumerate(("x1", "w1", "d1")):
        block = text.split(f"] {ident}\n")[1].split("━━ [")[0].splitlines()
        menu = re.findall(r"\[(\w+)\]", prompts[n])
        check(f"CS-3 text {ident}: one legend line per menu key, in order",
              _legend_keys(block) == menu, (block, prompts[n]))
    w1 = text.split("] w1\n")[1]
    check("CS-3 text: the yes line says what yes does to the work",
          "s = o trabalho vai para revisão" in w1, w1)
    check("CS-3 text: the no line says what no does to the work",
          "n = o trabalho espera o defeito" in w1, w1)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            fn()
    print(f"\n{len(FAILURES)} FAIL" if FAILURES else "\ntudo verde")
    sys.exit(1 if FAILURES else 0)
