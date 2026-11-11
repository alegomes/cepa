#!/usr/bin/env python3
"""CS-12 of docs/spec/perguntar-antes-do-run.md: the prompt `cepa-until` hands to each
item's agent carries the cut rule — `cepa-plan finish --decision` for a behavior choice
already committed on the run branch, `--human-pending` kept for a proof waiver, moving a
card to Done and a task outside the repository.

Its own file (not inside test_cepa_until_decide.py, whose helpers it borrows) so the proof
gate can run it alone in seconds: `python3 tests/test_cepa_until_cut_rule.py`, exit 1 on
any failure.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_cepa_until_decide as base  # noqa: E402
from test_cepa_until_decide import check, load_module, _pref_launch  # noqa: E402


# ── CS-12: the item's agent receives the cut rule (--decision vs --human-pending) ──

def _has_cut_rule(request):
    low = request.lower()
    return ("--decision" in request and "--human-pending" in request
            and "already committed" in low and "proof waiver" in low
            and "done" in low and "outside the repository" in low)


def test_cut_rule_cs12_every_item_request_carries_it():
    mod = load_module()
    plain = mod.build_command("fila", "until/b", False)[2]
    check("cs12 unit: the request still starts with the drain-plan call",
          plain.startswith("/common:drain-plan fila --max 1 --na-branch until/b\n\n"), plain)
    check("cs12 unit: the request without a note carries the cut rule",
          _has_cut_rule(plain), plain)
    check("cs12 unit: the rule names the finish flags, not drain-plan's",
          "cepa-plan finish" in plain, plain)
    pref = {"texto": "T.", "padrao": "P", "escolha": "R", "fonte": "padrao"}
    noted = mod.build_command("fila", "until/b", False,
                              note=mod.preference_note("x1", pref))[2]
    check("cs12 unit: with a note the rule is still there, and so is the note",
          _has_cut_rule(noted) and "Go with: R" in noted, noted)
    check("cs12 unit: the rule never reads as one of drain-plan's own flags",
          not re.search(r"(?<!\S)--(max|offline|dry-run|na-branch)\b",
                        (plain.split("\n\n", 1) + [""])[1]), plain)
    # Through the real supervisor: what the fake `claude` received.
    out, _, reqs = _pref_launch()
    check("cs12 run: every item's prompt carries the cut rule",
          set(reqs) == {"x1", "y1"} and all(_has_cut_rule(r) for r in reqs.values()),
          str(reqs) + out[-800:])


def main():
    print("cepa-until — o agente do item recebe a regra do corte (CS-12)\n")
    for given_name, fn in sorted(globals().items()):
        if given_name.startswith("test_") and callable(fn):
            print(f"{given_name}:")
            fn()
    print()
    if base.FAILURES:
        print(f"✗ {len(base.FAILURES)} falha(s): {', '.join(base.FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
