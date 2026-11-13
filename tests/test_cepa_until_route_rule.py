#!/usr/bin/env python3
"""CS-12 of docs/spec/perguntas-da-largada-legiveis.md: the prompt `cepa-until` hands to
each item's agent teaches how to open a route the way `cepa-plan finish` now demands
(CS-1): `--route-kind` with its three values, a closed `--question`, and `--if-yes` /
`--if-no` saying what each answer does to the work.

Its own file so the proof gate can run it alone in seconds:
`python3 tests/test_cepa_until_route_rule.py`, exit 1 on any failure.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_cepa_until_decide as base  # noqa: E402
from test_cepa_until_decide import check, load_module, _pref_launch  # noqa: E402

KINDS = ("owner-task", "external-block", "open-question")


def _has_route_rule(request):
    low = request.lower()
    return (re.search(r"--route-kind\b", request) is not None
            and all(k in request for k in KINDS)
            and re.search(r"--question\b", request) is not None
            and "closed" in low and "?" in request
            and re.search(r"--if-yes\b", request) is not None
            and re.search(r"--if-no\b", request) is not None
            # proof survivor: the warning that a missing field gets the finish refused
            and "if any of them is missing" in low
            and "refuses and records nothing" in low)


def _kinds_match_cepa_plan(request):
    """The values taught are exactly the ones `cepa-plan finish` accepts."""
    src = (Path(__file__).resolve().parent.parent / "common/bin/cepa-plan").read_text()
    return all(f'"{k}"' in src or f"'{k}'" in src for k in KINDS)


def test_route_rule_every_item_request_carries_it():
    mod = load_module()
    plain = mod.build_command("fila", "until/b", False)[2]
    check("route unit: the request still starts with the drain-plan call",
          plain.startswith("/common:drain-plan fila --max 1 --na-branch until/b\n\n"), plain)
    check("route unit: the request carries --route-kind, its three values, a closed "
          "--question and --if-yes/--if-no", _has_route_rule(plain), plain)
    check("route unit: the three values are the ones cepa-plan finish accepts",
          _kinds_match_cepa_plan(plain), plain)
    bare = mod.build_command("fila", "", False)[2]
    check("route unit: without a run branch the request still carries the rule",
          _has_route_rule(bare), bare)
    pref = {"texto": "T.", "padrao": "P", "escolha": "R", "fonte": "padrao"}
    noted = mod.build_command("fila", "until/b", False,
                              note=mod.preference_note("x1", pref))[2]
    check("route unit: with a note the rule is still there, and so is the note",
          _has_route_rule(noted) and "Go with: R" in noted, noted)
    check("route unit: the rule never reads as one of drain-plan's own flags",
          not re.search(r"(?<!\S)--(max|offline|dry-run|na-branch)\b",
                        (plain.split("\n\n", 1) + [""])[1]), plain)
    out, _, reqs = _pref_launch()
    check("route run: every item's prompt carries the route rule",
          set(reqs) == {"x1", "y1"} and all(_has_route_rule(r) for r in reqs.values()),
          str(reqs) + out[-800:])


def main():
    print("cepa-until — o agente do item recebe a regra de abrir rota (CS-12)\n")
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
