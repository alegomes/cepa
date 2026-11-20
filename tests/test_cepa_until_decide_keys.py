#!/usr/bin/env python3
"""CS-2 of docs/spec/teclas-em-ingles.md: the route panel (`cepa-until decide`)
shows and accepts `y` (yes) and `w` (I write the answer). The chips read
`[y] yes (recommended)` and `[w] I write the answer`, the legend has one line
starting with `y = ` and another with `w = `, and the old `[s]`, `[t]`, `s = `,
`t = ` are gone from the screen. What is written to the queue stays Portuguese.

Run with `python3 tests/test_cepa_until_decide_keys.py`, exit 1 on any failure.
"""
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_cepa_until_decide as base  # noqa: E402
from test_cepa_until_decide import (  # noqa: E402
    check, FAILURES, build_repo, item, fake_claude, run_until, plan_of, items_of,
    on_tty, BLOCKS_WITH_QUESTION, CEPA_UNTIL)

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
QUESTION = "Fecho o card como medir depois do go-live?"
REVIEW = ('```json cepa-decisoes\n{"itens": [{"id": "a1", "pergunta": "%s", '
          '"recomendo": "sim", "porque": "nao trava a fila"}]}\n```\n' % QUESTION)
ANCHOR = "[Enter] later"


def _decide(inputs, with_analysis=True):
    """Builds a queue whose a1 stopped with an owner question, optionally writes the
    run's analysis (`recomendo: sim`), runs the real `cepa-until decide` in a pty
    with `inputs`. Returns (rc, screen without ANSI, item a1)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, BLOCKS_WITH_QUESTION)
        run_until(root, binv, plan_of(root), ["--for", "2h"])
        until = root / ".claude" / "programs" / "fila" / "until"
        run_id = sorted(until.glob("*.estado.json"))[-1].name.split(".")[0]
        if with_analysis:
            (until / f"{run_id}.review.md").write_text(REVIEW, encoding="utf-8")
        rc, out = on_tty([sys.executable, str(CEPA_UNTIL), "decide", f"fila/{run_id}",
                          "--repo", str(root)], str(root), inputs=inputs, timeout=90)
        return rc, ANSI.sub("", out), items_of(root)["a1"]


def test_cs2_panel_shows_y_and_w_and_none_of_the_old_keys():
    rc, out, a1 = _decide([(ANCHOR, "q")])
    check("cs2 chips: [y] yes (recommended)", "[y] yes (recommended)" in out, out[-1500:])
    check("cs2 chips: [w] I write the answer", "[w] I write the answer" in out, out[-1500:])
    lines = [l.strip().lstrip("│ ").strip() for l in out.splitlines()]
    check("cs2 legend: a line starting with `y = `",
          any(l.startswith("y = ") for l in lines), out[-1500:])
    check("cs2 legend: a line starting with `w = `",
          any(l.startswith("w = ") for l in lines), out[-1500:])
    for old in ("[s]", "[t]", "s = ", "t = "):
        check(f"cs2 screen: no `{old}`", old not in out, out[-1500:])


def test_cs2_y_returns_the_item_to_the_queue_with_sim_in_the_evidence():
    rc, out, a1 = _decide([(ANCHOR, "y"), ("Anything to add", "")])
    check("cs2 y: the item went back to the queue", rc == 0 and a1["status"] == "pending",
          (rc, a1, out[-1200:]))
    check("cs2 y: the evidence says `sim: ...`", f"sim: {QUESTION}" in a1["evidence"], a1)


def test_cs2_w_then_a_line_then_y_returns_the_item_with_that_line():
    rc, out, a1 = _decide([(ANCHOR, "w"), ("Your answer", "vira checklist"),
                           ("Send the item back to the queue", "y")])
    check("cs2 w: the item went back to the queue", rc == 0 and a1["status"] == "pending",
          (rc, a1, out[-1200:]))
    check("cs2 w: the evidence holds the line", "vira checklist" in a1["evidence"], a1)


def test_cs2_invalid_option_says_type_w_first():
    rc, out, a1 = _decide([(ANCHOR, "blah"), (ANCHOR, "q")])
    check("cs2 invalid: says `type w first`", "type w first" in out, out[-1200:])
    check("cs2 invalid: no `type t first`", "type t first" not in out, out[-1200:])


def test_cs2_plain_rendering_uses_y_and_w():
    m = base.load_module()
    deferred_ones = [{"id": "W-1", "title": "x", "reason": "blocked-before",
                      "question": "Destravo?", "human_pending": None, "evidence": "y"}]
    analysis = {"itens": {"W-1": {"recomendo": "sim", "porque": "p"}}}
    answers, screen, prompts = iter(["q"]), [], []

    def ask(p_):
        prompts.append(p_)
        return next(answers)
    m.decide(Path("/nao/existe"), "fila", "run1", {}, deferred_ones, analysis,
             question=ask, output=screen.append, answer=lambda *a, **k: (0, "ok"))
    text = "\n".join(screen) + "\n".join(prompts)
    check("cs2 plain: [y] yes (recommended) and [w] chips",
          "[y] yes (recommended)" in text and "[w] I write the answer" in text, text)
    check("cs2 plain: no old keys",
          not any(k in text for k in ("[s]", "[t]", "s = ", "t = ")), text)
    check("cs2 plain: legend lines y = and w =",
          any(l.strip().startswith("y = ") for l in text.splitlines())
          and any(l.strip().startswith("w = ") for l in text.splitlines()), text)


def test_cs3_old_keys_get_a_line_naming_the_new_key_and_record_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, BLOCKS_WITH_QUESTION)
        run_until(root, binv, plan_of(root), ["--for", "2h"])
        until = root / ".claude" / "programs" / "fila" / "until"
        run_id = sorted(until.glob("*.estado.json"))[-1].name.split(".")[0]
        (until / f"{run_id}.review.md").write_text(REVIEW, encoding="utf-8")
        before = plan_of(root).read_bytes()
        rc, out = on_tty([sys.executable, str(CEPA_UNTIL), "decide", f"fila/{run_id}",
                          "--repo", str(root)], str(root),
                         inputs=[(ANCHOR, "s"), (ANCHOR, "t"), (ANCHOR, "sim"),
                                 (ANCHOR, "q")], timeout=90)
        out = ANSI.sub("", out)
        check("cs3 s: the line says `s is now y`", "s is now y" in out, out[-1500:])
        check("cs3 t: the line says `t is now w`", "t is now w" in out, out[-1500:])
        check("cs3 sim: the invalid-option message says `type w first`",
              '"sim" is not one of the options' in out and "type w first" in out,
              out[-1500:])
        # on_tty consumes each anchor it answers; a prompt left unanswered would
        # show up as "no answer within", so rc 0 means the menu asked again each time.
        check("cs3: the menu asked again after each old key",
              rc == 0 and "no answer within" not in out, (rc, out[-1500:]))
        check("cs3: the queue did not change", plan_of(root).read_bytes() == before,
              items_of(root))
        check("cs3: no answer line was opened by `t`", "Your answer" not in out,
              out[-1500:])


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
