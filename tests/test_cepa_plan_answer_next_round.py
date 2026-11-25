#!/usr/bin/env python3
"""CS-4 of docs/spec/resposta-do-decide-vira-trabalho.md: the next run finds the
work the owner's answer created.

Origin (2026-11-18, kairos-etapa-1 queue of wego-digitacao-backend): the queue
had only `done` items and one open owner question. The owner answered "sim" to
"Ponho na fila um item para ...?", and the next run found an empty batch: the
promised item never existed, so nothing could pick it up.

The scenario of that print, against the real CLIs, in a real git repo:
  - before the answer, `cepa-queue queue fila --max 1` returns an empty batch
    and stops at `end-of-queue` (the state the owner saw);
  - after `cepa-queue answer ... --answer "sim: ..."` (in a PTY: `answer` only
    runs on a TTY), the same `queue --max 1` returns the created item, and only
    it, in the batch;
  - the two ways a run looks for work see it: `cepa-queue ready --json` (what a
    `cepa-until --all` run reads) lists it among the ready items, and a
    single-queue `cepa-until fila --dry-run` names it as the 1st item;
  - an item declared "precisa do dono" is NOT handed to the run: it is deferred
    with reason `human_pending`, and the batch stays empty.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import item, build_repo, fake_claude, run_until  # noqa: E402
from test_cepa_until_decide import CEPA_PLAN, on_tty  # noqa: E402

FAILURES = []

ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
for v in ("CEPA_RUN", "CEPA_UNTIL_RUN", "CEPA_AUTONOMOUS_RUN_ID", "CLAUDE_AUTONOMOUS_RUN_ID"):
    ENV.pop(v, None)

QUESTION = "Ponho na fila um item para calibrar X?"


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def print_scenario(needs_owner=False):
    """Only `done` items, and one of them with an open owner question whose "sim"
    declares the item "calibrar X"."""
    routed = item("a2", status="done", human_pending="decidir se calibra X")
    routed["route_kind"] = "open-question"
    routed["owner_question"] = QUESTION
    routed["owner_summary"] = {
        "se_sim": "um item novo calibra X", "se_nao": "X fica como está",
        "item_se_sim": {"titulo": "calibrar X", "precisa_do_dono": needs_owner},
        "item_se_nao": "nenhum"}
    return [item("a1", status="done"), routed, item("a3", status="done")]


def queue(root, max_items=1):
    p = subprocess.run([sys.executable, str(CEPA_PLAN), "queue", "fila",
                        "--max", str(max_items), "--repo", str(root), "--json"],
                       capture_output=True, text=True, env=ENV)
    return p.returncode, json.loads(p.stdout or "{}"), p.stderr


def answer(root, ident, text):
    return on_tty([sys.executable, str(CEPA_PLAN), "answer", "fila", ident,
                   "--answer", text, "--repo", str(root), "--no-commit"],
                  str(root), env=ENV)


def created_id(root):
    _rc, data, _err = queue(root, 10 ** 6)
    ids = [b["id"] for b in data.get("batch") or []]
    ids += [d["id"] for d in data.get("deferred") or []]
    return ids[0] if len(ids) == 1 else None


def commit_all(root):
    """The run launch refuses a dirty tree; `--no-commit` left the answer unstaged."""
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, env=ENV)
    subprocess.run(["git", "commit", "-qm", "answer"], cwd=root, check=True, env=ENV)


def test_red_test_next_round_finds_the_created_item():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, print_scenario())
        rc, before, err = queue(root)
        check("antes da resposta: `queue` sai 0", rc == 0, err)
        check("antes da resposta: lote vazio (o print do dono)",
              before.get("batch") == [], before.get("batch"))
        check("antes da resposta: o lote para em `end-of-queue`",
              (before.get("stop") or {}).get("reason") == "end-of-queue",
              before.get("stop"))

        arc, out = answer(root, "a2", "sim: pode calibrar")
        check("answer sai 0", arc == 0, out)
        new = created_id(root)
        check("a resposta criou exatamente um item para rodar", new is not None, out)

        rc, after, err = queue(root)
        batch = after.get("batch") or []
        check("depois da resposta: `queue --max 1` sai 0", rc == 0, err)
        check("depois da resposta: o lote tem só o item criado",
              [b["id"] for b in batch] == [new], batch)
        check("o item do lote tem o título declarado",
              batch and batch[0].get("title") == "calibrar X", batch)
        check("o item criado não fica entre os adiados",
              new not in [d["id"] for d in after.get("deferred") or []],
              after.get("deferred"))

        p = subprocess.run([sys.executable, str(CEPA_PLAN), "ready", "--repo",
                            str(root), "--json"], capture_output=True, text=True,
                           env=ENV)
        check("`ready` sai 0", p.returncode == 0, p.stderr)
        ready = [r["id"] for q in json.loads(p.stdout or "{}").get("filas") or []
                 for r in q.get("prontos") or []]
        check("`ready` (o que um run --all lê) lista o item criado",
              ready == [new], ready)

        commit_all(root)
        binv = fake_claude(tmp, "pass")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        up, calls = run_until(root, binv, plan, ["--for", "2h", "--dry-run"])
        first = [l for l in up.stdout.splitlines() if "1st item:" in l]
        check("`cepa-until fila --dry-run` sai 0", up.returncode == 0,
              (up.stderr or up.stdout)[-800:])
        check("`cepa-until` nomeia o item criado como o 1º da rodada",
              len(first) == 1 and str(new) in first[0], first or up.stdout[:800])
        check("--dry-run não disparou nada", not calls, calls)


def test_item_that_needs_the_owner_is_not_handed_to_the_run():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, print_scenario(needs_owner=True))
        arc, out = answer(root, "a2", "sim: pode calibrar")
        check("precisa do dono: answer sai 0", arc == 0, out)
        new = created_id(root)
        rc, after, err = queue(root)
        check("precisa do dono: `queue` sai 0", rc == 0, err)
        check("precisa do dono: o lote continua vazio",
              after.get("batch") == [], after.get("batch"))
        deferred = {d["id"]: d.get("reason") for d in after.get("deferred") or []}
        check("precisa do dono: o item criado aparece adiado por `human_pending`",
              new is not None and deferred.get(new) == "human_pending", deferred)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            fn()
    print(f"\n{len(FAILURES)} falha(s)")
    sys.exit(1 if FAILURES else 0)
