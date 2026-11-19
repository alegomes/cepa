#!/usr/bin/env python3
"""CS-1 of docs/spec/resposta-do-decide-vira-trabalho.md: the contract the agents read.
`common/commands/until-review.md` must document `item_se_sim`, `item_se_nao` and
`nenhum` as mandatory in the `cepa-decisoes` block, under the same definition of an
answer without return (yes on a `done` item, no on any route), with an example that
parses and carries `item_se_nao`; `drain-plan.md` must mention `--if-no-item`.

Fast and standalone: `python3 tests/test_until_review_item_declaration.py`.
"""
import json
import re
import sys
from pathlib import Path

COMMANDS = Path(__file__).resolve().parent.parent / "common" / "commands"
FAILURES = []


def check(label, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    if not ok:
        FAILURES.append(label)
        print(f"       {detail}")
        raise AssertionError(f"{label}: {detail}")


def _flat(text):
    return " ".join(text.replace("**", "").replace("`", "").split())


def test_until_review_documents_the_item_declaration():
    review = (COMMANDS / "until-review.md").read_text(encoding="utf-8")
    flat = _flat(review)
    for word in ("item_se_sim", "item_se_nao", "nenhum"):
        check(f"until-review mentions {word}", word in flat, "")
    check("until-review calls the declaration mandatory",
          "item_se_sim and item_se_nao declare" in flat and "mandatory" in flat, "")
    check("...for the no of every item",
          "the item_se_nao of every item" in flat, "")
    check("...and the yes of a delivered `done` item",
          "item_se_sim of an item that was delivered" in flat
          and "pos-entrega" in flat and "status done" in flat, "")
    check("...a yes on a blocked/pending item returns to the queue and needs none",
          "returns it to the queue and needs none" in flat, "")
    check("...accepts nenhum or {titulo, precisa_do_dono}",
          '"nenhum"' in review and "precisa_do_dono" in review, "")
    check("...says a question that promises work must declare it",
          "promises work" in flat and "MUST declare" in flat, "")
    check("...points to the cepa-plan flags",
          "--if-yes-item" in review and "--if-no-item" in review, "")


def test_until_review_example_block_parses_and_declares_item_se_nao():
    review = (COMMANDS / "until-review.md").read_text(encoding="utf-8")
    m = re.search(r"```json cepa-decisoes\n(.*?)\n```", review, re.S)
    check("until-review has an example cepa-decisoes block", m is not None, "")
    if not m:
        return
    try:
        block = json.loads(m.group(1))
    except ValueError as e:
        check("the example block is valid JSON", False, str(e))
        return
    check("the example block is valid JSON", True)
    items = block.get("itens") or []
    check("the example has at least one item", bool(items), block)
    for it in items:
        check(f"example item {it.get('id')} carries item_se_nao", "item_se_nao" in it, it)
        declared = it.get("item_se_nao")
        ok = declared == "nenhum" or (isinstance(declared, dict)
                                      and declared.get("titulo")
                                      and isinstance(declared.get("precisa_do_dono"), bool))
        check(f"example item {it.get('id')}: item_se_nao is nenhum or titulo+precisa_do_dono",
              bool(ok), declared)


def test_drain_plan_mentions_if_no_item():
    drain = (COMMANDS / "drain-plan.md").read_text(encoding="utf-8")
    check("drain-plan mentions --if-no-item", "--if-no-item" in drain, "")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            fn()
    print(f"\n{len(FAILURES)} FAIL" if FAILURES else "\ntudo verde")
    sys.exit(1 if FAILURES else 0)
