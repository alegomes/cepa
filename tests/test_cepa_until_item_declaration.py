#!/usr/bin/env python3
"""CS-1 of docs/spec/resposta-do-decide-vira-trabalho.md, the cepa-until and `_ownertext`
side of the item declarations (`item_se_sim` / `item_se_nao`), in small fast cases:

  - `_ownertext`: "nenhuma"/"none" count as none; `item_flags` forwards titles and the
    needs-owner marker;
  - `finish_item` (the supervisor's re-finish) forwards the stored declarations;
  - `open_precondition_route` defaults the "no" to `nenhum` only when the item declares
    nothing, and keeps the item's own declaration otherwise;
  - the decide screen (`owner_summary_of`) never shows the raw `item_*` declarations;
  - `parse_route` drops a title with control characters.

`check` raises, so it is red under pytest too. Run: `python3 tests/test_cepa_until_item_declaration.py`.
"""
import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "common" / "hooks"))
import _ownertext  # noqa: E402
import test_cepa_plan_route_item_declaration as plan_t  # noqa: E402
from test_cepa_plan_route_item_declaration import (  # noqa: E402
    make_repo, item_a, run, queue_file, QUESTION, ROUTE)

CEPA_UNTIL = HERE.parent / "common" / "bin" / "cepa-run"
FAILURES = []


def check(label, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    if not ok:
        FAILURES.append(label)
        print(f"       {detail}")
        raise AssertionError(f"{label}: {detail}")


def load_until():
    before = os.environ.get("CEPA_UNTIL_COR")
    os.environ["CEPA_UNTIL_COR"] = "nunca"
    try:
        loader = importlib.machinery.SourceFileLoader("cepa_until_decl", str(CEPA_UNTIL))
        spec = importlib.util.spec_from_loader("cepa_until_decl", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
    finally:
        if before is None:
            del os.environ["CEPA_UNTIL_COR"]
        else:
            os.environ["CEPA_UNTIL_COR"] = before
    return mod


def open_route(d, *extra):
    r = run(d, "finish", "fila", "A", "--status", "pending", "--human-pending", ROUTE,
            "--evidence", "x", "--repo", ".", "--route-kind", "open-question",
            "--question", QUESTION, "--if-yes", "o limite é calibrado",
            "--if-no", "o limite fica como está", *extra)
    check("route opened", r.returncode == 0, r.stderr)


def test_none_words_and_item_flags():
    for word in ("nenhum", "Nenhuma", "NONE"):
        check(f"{word!r} is none",
              _ownertext.item_declaration("item_se_nao", word) == ("nenhum", None))
    check("item_flags: 'nenhuma' becomes `nenhum`",
          _ownertext.item_flags({"item_se_nao": "Nenhuma"}) == ["--if-no-item", "nenhum"])
    flags = _ownertext.item_flags({
        "item_se_sim": {"titulo": "Calibrar o limite", "precisa_do_dono": True},
        "item_se_nao": {"titulo": "Registrar o limite", "precisa_do_dono": False}})
    check("item_flags forwards titles and the needs-owner marker only where set",
          flags == ["--if-yes-item", "Calibrar o limite", "--if-yes-item-needs-owner",
                    "--if-no-item", "Registrar o limite"], str(flags))
    check("item_flags of nothing is empty",
          _ownertext.item_flags({}) == [] and _ownertext.item_flags(None) == [])


def test_supervisor_re_finish_keeps_the_declaration():
    m = load_until()
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "u1")
        open_route(d, "--if-no-item", "Registrar o limite", "--if-no-item-needs-owner")
        summary = item_a(d)["owner_summary"]
        err = m.finish_item("fila", d, "A", "pending", "build vermelho", owner=summary)
        check("finish_item succeeds", err is None, err)
        kept = item_a(d)["owner_summary"].get("item_se_nao")
        check("the stored declaration survives the supervisor's re-finish",
              kept == {"titulo": "Registrar o limite", "precisa_do_dono": True}, str(kept))


def test_precondition_route_default_and_own_declaration():
    m = load_until()
    row = {"id": "A", "texto": ROUTE, "pergunta": QUESTION}
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "u6")
        err = m.open_precondition_route("fila", d, row)
        check("route opened without a declaration", err is None, err)
        check("the \"no\" defaults to `nenhum`",
              item_a(d)["owner_summary"].get("item_se_nao") == "nenhum",
              str(item_a(d).get("owner_summary")))
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "u7")
        open_route(d, "--if-no-item", "Registrar o limite", "--if-no-item-needs-owner")
        err = m.open_precondition_route("fila", d, row)
        check("route reopened with a declaration", err is None, err)
        check("the item's own declaration is kept, not overwritten by `nenhum`",
              item_a(d)["owner_summary"].get("item_se_nao")
              == {"titulo": "Registrar o limite", "precisa_do_dono": True},
              str(item_a(d).get("owner_summary")))


def test_decide_screen_hides_raw_declarations():
    m = load_until()
    ad = {"owner_summary": {"se_sim": "volta para a fila", "se_nao": "fica esperando",
                            "item_se_sim": "nenhum",
                            "item_se_nao": {"titulo": "Registrar", "precisa_do_dono": True}}}
    out = m.owner_summary_of(ad, {})
    check("the screen keeps the text fields",
          out.get("se_sim") == "volta para a fila" and out.get("se_nao") == "fica esperando",
          str(out))
    check("no item_* key reaches the screen",
          not any(k.startswith("item_") for k in out), str(out))


def test_parse_route_rejects_control_characters_in_the_title():
    m = load_until()

    def route(title):
        return m.parse_route(json.dumps({
            "route_kind": "external-block", "question": "Já liberou o acesso?",
            "if_yes": "volta para a fila", "if_no": "continua esperando",
            "item_se_nao": {"titulo": title, "precisa_do_dono": False}}))

    good = route("Registrar o acesso pendente")
    check("a clean title is kept",
          good and good.get("item_se_nao", {}).get("titulo") == "Registrar o acesso pendente",
          str(good))
    for bad in ("Registrar\x07 o acesso", "Registrar​ o acesso", "Registrar\x00 acesso"):
        r = route(bad)
        check(f"title {bad!r}: the route stays valid but the declaration is dropped",
              r is not None and "item_se_nao" not in r, str(r))


def main():
    print("cepa-until: declarações de item (CS-1)\n")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"{name}:")
            try:
                fn()
            except AssertionError:
                pass
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
