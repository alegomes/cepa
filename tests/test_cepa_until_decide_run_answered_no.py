#!/usr/bin/env python3
"""decide-de-run-nao-repete-nao-respondido: `cepa until decide <queue>/<run>` (the
questions of ONE run) does not ask again the routes the owner already answered "não"
and whose conditions did not change (the item's evidence still STARTS with that
"não", `last_owner_no`); one line per queue says how many, the latest date and that
`cepa-until decide <queue>` revisits them. `cepa-until decide <queue>` (no run) still
asks every route: it is the way to revisit them.

Origin: after answering 30 questions of run `all/2026-11-21-1244`, the run's decide
re-presented 3 routes answered "não" that had nothing to do with the run.

Run with `python3 tests/test_cepa_until_decide_run_answered_no.py`, exit 1 on any failure.
"""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_cepa_until as base  # noqa: E402
import test_cepa_until_all as al  # noqa: E402
import test_cepa_until_decide as dec  # noqa: E402

check = dec.check
FAILURES = dec.FAILURES
CEPA_UNTIL = al.CEPA_UNTIL
if os.environ.get("CEPA_UNTIL_SCRIPT"):
    CEPA_UNTIL = Path(os.environ["CEPA_UNTIL_SCRIPT"]).resolve()
    dec.CEPA_UNTIL = al.CEPA_UNTIL = CEPA_UNTIL
ANSI = dec.ANSI
RUN = "2026-11-21-1244"


def no_route(ident, text, day="2026-11-06"):
    it = base.item(ident, human_pending=text)
    it["evidence"] = dec._answered(day)
    return it


def open_route(ident, text):
    return base.item(ident, human_pending=text)


def with_run(root, queue):
    """A run state on disk, so `<queue>/<run>` resolves."""
    m = dec.load_module()
    folder = m.until_dir(root, queue)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{RUN}.estado.json").write_text("{}", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm",
                    "run"], cwd=root, check=True)


def single(tmp, items):
    root = base.build_repo(tmp, items)
    with_run(root, "fila")
    return root


def cmd(root, target):
    return [sys.executable, str(CEPA_UNTIL), "decide", target, "--repo", str(root)]


def text_out(root, target):
    p = subprocess.run(cmd(root, target), capture_output=True, text=True, timeout=120,
                       stdin=subprocess.DEVNULL)
    return p.returncode, p.stdout + p.stderr


def tty_out(root, target, n_answers):
    inputs = []
    for _ in range(n_answers):
        inputs += [("[w] I write the answer", "n"), ("Anything to add", "")]
    rc, out = dec.on_tty(cmd(root, target), str(root), inputs=inputs, timeout=25)
    return rc, ANSI.sub("", out)


def lines_with(out, needle):
    return [l for l in out.splitlines() if needle in l]


def test_run_decide_on_a_terminal_skips_the_answered_no_and_asks_the_open_one():
    with tempfile.TemporaryDirectory() as tmp:
        root = single(tmp, [no_route("a1", "old route text"),
                            open_route("a2", "fresh route text")])
        rc, out = tty_out(root, f"fila/{RUN}", 1)
    line = lines_with(out, "already answered")
    check("exits 0", rc == 0, out[-1500:])
    check("one line: count, date dd/mm and the command to revisit",
          len(line) == 1 and "1 route(s)" in line[0] and "06/11" in line[0]
          and "cepa-until decide fila" in line[0]
          and "cepa-until decide fila/" not in line[0], str(line) + out[-1000:])
    check("the open route is asked and the answered one is not",
          "1 question(s) for you" in out and "fresh route text" in out
          and "old route text" not in out, out[-1500:])


def test_run_decide_without_terminal_does_not_list_the_answered_no():
    with tempfile.TemporaryDirectory() as tmp:
        root = single(tmp, [no_route("a1", "old route text"),
                            open_route("a2", "fresh route text")])
        rc, out = text_out(root, f"fila/{RUN}")
    line = lines_with(out, "already answered")
    check("exits 0", rc == 0, out)
    check("the open route is listed, the answered one is not",
          "fresh route text" in out and "old route text" not in out
          and "waiting on you: 1" in out, out)
    check("the summary line is there with count, date and command",
          len(line) == 1 and "1 route(s)" in line[0] and "06/11" in line[0]
          and "cepa-until decide fila" in line[0], out)


def test_run_decide_with_only_answered_no_routes_prints_the_line_and_asks_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        root = single(tmp, [no_route("a1", "old one", "2026-11-06"),
                            no_route("a2", "old two", "2026-11-11")])
        rc, out = text_out(root, f"fila/{RUN}")
    line = lines_with(out, "already answered")
    check("exits 0", rc == 0, out)
    check("no listing", "waiting on you" not in out and "old one" not in out
          and "old two" not in out, out)
    check("one line: 2 routes, the latest date",
          len(line) == 1 and "2 route(s)" in line[0] and "11/11" in line[0], out)


def test_queue_decide_without_run_still_asks_the_answered_no():
    with tempfile.TemporaryDirectory() as tmp:
        root = single(tmp, [no_route("a1", "old route text"),
                            open_route("a2", "fresh route text")])
        rc, out = tty_out(root, "fila", 2)
        rc2, out2 = text_out(root, "fila")
    check("the terminal asks both", rc == 0 and "2 question(s) for you" in out
          and "old route text" in out and "fresh route text" in out, out[-1500:])
    check("no summary line", "already answered" not in out, out[-1500:])
    check("the text listing has both and no summary line",
          "old route text" in out2 and "fresh route text" in out2
          and "already answered" not in out2, out2)


def test_a_no_that_is_not_at_the_start_of_the_evidence_is_asked_in_the_run():
    stale = open_route("a1", "rerun route text")
    stale["evidence"] = "Agent run 2026-11-20 finished again. " + dec._answered("2026-11-06")
    with tempfile.TemporaryDirectory() as tmp:
        root = single(tmp, [stale])
        rc, out = text_out(root, f"fila/{RUN}")
    check("asked, with no summary line", "rerun route text" in out
          and "already answered" not in out, out)


def test_a_last_answer_sim_is_asked_in_the_run():
    sim = open_route("a1", "sim route text")
    sim["evidence"] = dec._answered("2026-11-08", "sim: ok", old=dec._answered("2026-11-02"))
    with tempfile.TemporaryDirectory() as tmp:
        root = single(tmp, [sim])
        rc, out = text_out(root, f"fila/{RUN}")
    check("asked, with no summary line", "sim route text" in out
          and "already answered" not in out, out)


def test_all_run_has_one_line_per_queue_and_does_not_ask_the_answered_no():
    def route(ident, q, day=None):
        it = al._owner_item(ident, f"route of {ident}", q) \
            if hasattr(al, "_owner_item") else None
        if it is None:
            it = base.item(ident, human_pending=f"route of {ident}")
            it["owner_question"] = q
        if day:
            it["evidence"] = dec._answered(day)
        return it
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = al._repo(tmp, {
            "a": [route("a1", "Old A question?", "2026-11-06"),
                  route("a2", "Fresh A question?")],
            "b": [route("b1", "Old B question?", "2026-11-11"),
                  route("b2", "Old B2 question?", "2026-11-09")]})
        with_run(root, "all")
        rc, out = text_out(root, f"all/{RUN}")
        rc2, tty = tty_out(root, f"all/{RUN}", 1)
    for label, text in (("text", out), ("terminal", tty)):
        check(f"{label}: only the open route is asked",
              "Fresh A question?" in text and "Old A question?" not in text
              and "Old B question?" not in text and "Old B2 question?" not in text,
              text[-1500:])
        la = lines_with(text, "queue `a`")
        lb = lines_with(text, "queue `b`")
        check(f"{label}: a line for queue a", len(la) == 1 and "1 route(s)" in la[0]
              and "06/11" in la[0] and "cepa-until decide a" in la[0], text[-1500:])
        check(f"{label}: a line for queue b with its count and latest date",
              len(lb) == 1 and "2 route(s)" in lb[0] and "11/11" in lb[0]
              and "cepa-until decide b" in lb[0], text[-1500:])


def test_end_of_run_report_does_not_hand_back_the_answered_no():
    m = dec.load_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = single(tmp, [no_route("a1", "old route text"),
                            open_route("a2", "fresh route text")])
        report = {}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            m.close_with_owner(root, "fila", RUN, {}, interactive=False, report=report)
        whole = {}
        with contextlib.redirect_stdout(io.StringIO()):
            m.close_with_owner(root, "fila", None, {}, interactive=False, report=whole)
    ids = [str(ad.get("id")) for ad in report.get("deferred") or []]
    check("only the open route is handed back", ids == ["a2"], str(ids))
    check("nothing is printed by close_with_owner on the report path",
          buf.getvalue() == "", buf.getvalue())
    check("the report carries the count and latest date of the left-out routes",
          report.get("answered_no") == {"fila": ["2026-11-06"]}, str(report))
    check("without a run, the report keeps every route",
          sorted(str(ad.get("id")) for ad in whole.get("deferred") or [])
          == ["a1", "a2"], str(whole))


def test_end_of_run_report_after_the_questions_leaves_the_answered_no_out():
    """The interactive end of a run reads the queue AGAIN after the questions: that
    second read is split too (a route answered "no" in the panel itself included)."""
    m = dec.load_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = single(tmp, [no_route("a1", "old route text"),
                            open_route("a2", "open route text")])
        seen = []
        real = m.decide
        m.decide = lambda *a, **k: seen.append([str(ad.get("id")) for ad in a[4]])
        try:
            report = {}
            with contextlib.redirect_stdout(io.StringIO()):
                m.close_with_owner(root, "fila", RUN, {}, interactive=True,
                                   ask_land=False, report=report)
        finally:
            m.decide = real
    check("the panel was handed only the open route", seen == [["a2"]], str(seen))
    ids = [str(ad.get("id")) for ad in report.get("deferred") or []]
    check("after the questions, only the open route is handed back",
          ids == ["a2"], str(ids))
    check("after the questions, the left-out route is counted",
          report.get("answered_no") == {"fila": ["2026-11-06"]}, str(report))


def _row_text(row):
    return "".join(str(part[1]) for part in row)


def test_next_panel_counts_the_answered_no_and_does_not_say_nothing_left():
    m = dec.load_module()
    st = {"estado": "encerrado"}
    rows = [_row_text(r) for r in m.next_rows(
        Path("/nao/existe"), "fila", RUN, st, "/nao/existe",
        {"deferred": [], "asked": [],
         "answered_no": {"fila": ["2026-11-06", "2026-11-21"], "b": ["2026-11-11"]}})]
    line = [r for r in rows if "already answered" in r]
    check("one row per queue", len(line) == 2, str(rows))
    check("the row has the count, the latest date and the way to revisit",
          line and "2 route(s)" in line[0] and "21/11" in line[0]
          and line[0].endswith("cepa-until decide fila"), str(line))
    check("the other queue's row names that queue",
          len(line) == 2 and "1 route(s)" in line[1] and "11/11" in line[1]
          and line[1].endswith("cepa-until decide b"), str(line))
    check("a route answered no is not 'nothing left for you'",
          not any("nothing left for you" in r for r in rows), str(rows))
    check("the row is not a numbered question",
          not any(r.lstrip()[:2] in ("1.", "2.") for r in line), str(line))
    none = [_row_text(r) for r in m.next_rows(
        Path("/nao/existe"), "fila", RUN, st, "/nao/existe",
        {"deferred": [], "asked": [], "answered_no": {}})]
    check("with none, the panel still says nothing left",
          none == ["nothing left for you"], str(none))


def test_help_text_says_it():
    p = subprocess.run([sys.executable, str(CEPA_UNTIL), "decide", "--help"],
                       capture_output=True, text=True, timeout=60)
    check("the help says a run's decide leaves out the routes answered no",
          "already answered" in " ".join(p.stdout.split()), p.stdout)


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
