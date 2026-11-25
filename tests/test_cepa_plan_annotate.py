#!/usr/bin/env python3
"""The evidence of a closed item can be corrected without being erased
(feedback fb-20261110-3, 2026-11-10).

The case: C1-17 of wego-digitacao-backend closed `done` with the evidence
"sem merge e sem push". Then merge eb31cd5 landed it. `finish` refuses to
touch a done item (it would erase the closer's evidence) and no subcommand
could add a note, so the stale text made another agent state that C1-17 was
not merged.

Red test (BACKLOG.md § `cepa queue finish` não deixa corrigir a evidência de um
item done que ficou falsa):

  - `cepa-queue annotate <fila> <id> --note TEXT` on a `done` (or `dropped`)
    item appends `{texto, em, autor}` to the item's `anotacoes`, and never
    touches `evidence`, `status` nor `head_commit` (the record only grows);
  - a second note is appended, the first stays;
  - the author is the calling session (CLAUDE_SESSION_ID), or `--author`;
  - `show <fila> <id>` prints the notes, with date and author, BEFORE the
    original evidence, which is still printed; `show --json` and
    `status --json` carry `anotacoes`; the text `status` flags the done item;
  - refused (exit 2, nothing written): an open item (its evidence is
    `finish`'s), an unknown id, an empty note;
  - the refusal of a second `finish` on a done item names `annotate`.

Run: python3 tests/test_cepa_plan_annotate.py
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import build_repo, item  # noqa: E402
from test_cepa_until_decide import CEPA_PLAN  # noqa: E402

FAILURES = []
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t", NO_COLOR="1",
           CLAUDE_SESSION_ID="sessao-que-anota")
for v in ("CEPA_RUN", "CEPA_UNTIL_RUN", "CEPA_AUTONOMOUS_RUN_ID", "CLAUDE_AUTONOMOUS_RUN_ID", "CLAUDE_CODE_SESSION_ID"):
    ENV.pop(v, None)

OLD = "C1-17 no branch until/x: sem merge e sem push"
NOTE1 = "mesclado na main pelo merge eb31cd5; a frase sem merge ficou falsa"
NOTE2 = "push feito em 2026-11-12"


def check(name, cond, detail=""):
    print(f"  ok  {name}" if cond else f"FAIL  {name}  {detail}")
    if not cond:
        FAILURES.append(name)


def cli(root, *args):
    return subprocess.run([sys.executable, str(CEPA_PLAN), *args, "--repo", str(root)],
                          capture_output=True, text=True, cwd=root, env=ENV,
                          timeout=60)


def plan_file(root):
    return Path(root) / ".claude" / "programs" / "fila" / "plan.yaml"


def item_of(root, ident="d1"):
    return {i["id"]: i for i in yaml.safe_load(plan_file(root).read_text())["items"]}[ident]


def fixture(tmp):
    done = dict(item("d1", status="done"), evidence=OLD, head_commit="a" * 40)
    dropped = dict(item("x1", status="dropped"), evidence="não será feito")
    return build_repo(tmp, [done, dropped, item("p1")])


def test_note_is_appended_and_evidence_kept():
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        p = cli(root, "annotate", "fila", "d1", "--note", f"  {NOTE1}  ")
        check("annotate on done exits 0", p.returncode == 0, p.stderr)
        it = item_of(root)
        check("evidence untouched", it.get("evidence") == OLD, str(it.get("evidence")))
        check("status untouched", it.get("status") == "done")
        check("head_commit untouched", it.get("head_commit") == "a" * 40)
        notes = it.get("anotacoes") or []
        check("one note recorded", len(notes) == 1, str(notes))
        if notes:
            n = notes[0]
            check("note text normalized", n.get("texto") == NOTE1, str(n))
            today = datetime.now(timezone.utc).date().isoformat()
            check("note dated", str(n.get("em") or "").startswith(today), str(n))
            check("author is the session", n.get("autor") == "sessao-que-anota", str(n))

        p = cli(root, "annotate", "fila", "d1", "--note", NOTE2, "--author", "dono")
        check("second annotate exits 0", p.returncode == 0, p.stderr)
        notes = item_of(root).get("anotacoes") or []
        check("second note appended, first kept",
              [n.get("texto") for n in notes] == [NOTE1, NOTE2], str(notes))
        check("--author wins", len(notes) == 2 and notes[1].get("autor") == "dono",
              str(notes))
        check("evidence still untouched", item_of(root).get("evidence") == OLD)

        p = cli(root, "annotate", "fila", "x1", "--note", "o motivo mudou")
        check("annotate on dropped exits 0", p.returncode == 0, p.stderr)

        show = cli(root, "show", "fila", "d1")
        out = show.stdout
        check("show exits 0", show.returncode == 0, show.stderr)
        check("show prints both notes and the old evidence",
              NOTE1 in out and NOTE2 in out and OLD in out, out)
        check("show prints the notes before the evidence",
              NOTE1 in out and OLD in out and out.index(NOTE1) < out.index(OLD), out)
        check("show prints author of each note",
              "sessao-que-anota" in out and "dono" in out, out)

        sj = cli(root, "show", "fila", "d1", "--json")
        data = json.loads(sj.stdout) if sj.returncode == 0 else {}
        check("show --json carries anotacoes",
              [n.get("texto") for n in data.get("item", {}).get("anotacoes") or []]
              == [NOTE1, NOTE2], sj.stdout + sj.stderr)

        st = cli(root, "status", "fila", "--json")
        rows = {i["id"]: i for i in json.loads(st.stdout)["items"]} if st.returncode == 0 else {}
        check("status --json carries anotacoes",
              len((rows.get("d1") or {}).get("anotacoes") or []) == 2, st.stdout + st.stderr)
        check("status --json item without notes has empty list",
              (rows.get("p1") or {}).get("anotacoes") == [], str(rows.get("p1")))

        txt = cli(root, "status", "fila").stdout
        line = [l for l in txt.splitlines() if "anotaç" in l]
        check("text status flags the annotated done item", bool(line), txt)
        check("text status counts the notes of d1",
              any(l.strip().startswith("2 anotaç") and "fila d1" in l for l in line),
              txt)


def test_note_whitespace_is_collapsed():
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        p = cli(root, "annotate", "fila", "d1", "--note", "mesclado\n  pelo\teb31cd5")
        check("multi-line note accepted", p.returncode == 0, p.stderr)
        notes = item_of(root).get("anotacoes") or []
        check("internal whitespace and newlines collapsed",
              [n.get("texto") for n in notes] == ["mesclado pelo eb31cd5"], str(notes))


def test_malformed_notes_are_hidden():
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        plan = yaml.safe_load(plan_file(root).read_text())
        for it in plan["items"]:
            if it["id"] == "d1":
                it["anotacoes"] = ["texto solto", {"texto": "   ", "em": "x"},
                                   {"texto": NOTE1, "em": "2026-11-12", "autor": "a"}]
        plan_file(root).write_text(yaml.safe_dump(plan, allow_unicode=True))
        sj = cli(root, "show", "fila", "d1", "--json")
        data = json.loads(sj.stdout) if sj.returncode == 0 else {}
        check("show --json keeps only well-formed notes",
              [n.get("texto") for n in data.get("item", {}).get("anotacoes") or []]
              == [NOTE1], sj.stdout + sj.stderr)
        out = cli(root, "show", "fila", "d1").stdout
        check("show text hides the malformed notes",
              "texto solto" not in out and NOTE1 in out, out)
        txt = cli(root, "status", "fila").stdout
        check("text status counts only well-formed notes",
              any(l.strip().startswith("1 anotaç") for l in txt.splitlines()), txt)


def test_refusals_write_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        before = plan_file(root).read_bytes()
        p = cli(root, "annotate", "fila", "p1", "--note", "qualquer")
        check("open item refused with exit 2", p.returncode == 2, p.stdout + p.stderr)
        check("open item refusal points at finish", "finish" in p.stderr, p.stderr)
        p = cli(root, "annotate", "fila", "nao-existe", "--note", "qualquer")
        check("unknown id refused with exit 2", p.returncode == 2, p.stdout + p.stderr)
        p = cli(root, "annotate", "fila", "d1", "--note", "   ")
        check("empty note refused with exit 2", p.returncode == 2, p.stdout + p.stderr)
        check("nothing written by the refusals", plan_file(root).read_bytes() == before)

        p = cli(root, "finish", "fila", "d1", "--status", "done", "--evidence", "outra")
        check("second finish on done still refused", p.returncode != 0, p.stdout)
        check("second finish refusal names annotate",
              "annotate" in (p.stdout + p.stderr), p.stdout + p.stderr)


def main():
    for t in (test_note_is_appended_and_evidence_kept, test_refusals_write_nothing,
              test_note_whitespace_is_collapsed, test_malformed_notes_are_hidden):
        print(t.__name__)
        t()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        return 1
    print("\nok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
