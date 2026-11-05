#!/usr/bin/env python3
"""Tests of DUR-2 (docs/estrategia-durabilidade.md O1 item 1, 2026-11-05):
`cepa-plan finish` refuses an item already terminal, a caller that is not the
holder, and `done` with an uncommitted tree; `done` records `head_commit`;
every refusal is kept in `finish_recusado`; `--supervisor` bypasses the first two.

Run with `python3 tests/test_cepa_plan_finish_owner.py`. Subprocess against the
real CLI in temporary git repos. The session registry is empty in a fresh
repo, so `CLAUDE_SESSION_ID` is what identifies the caller.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    print("✗ precisa de PyYAML (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

REPO = Path(__file__).resolve().parent.parent
CEPA_PLAN = REPO / "common" / "bin" / "cepa-plan"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def run(repo, *args, session=None):
    env = dict(os.environ)
    env.pop("CLAUDE_WT_CLAIM", None)
    env.pop("CEPA_UNTIL_RUN", None)
    if session:
        env["CLAUDE_SESSION_ID"] = session
    else:
        env.pop("CLAUDE_SESSION_ID", None)
    return subprocess.run([sys.executable, str(CEPA_PLAN)] + list(args),
                          capture_output=True, text=True, cwd=str(repo), env=env)


def git(d, *args):
    return subprocess.run(["git", "-C", str(d), *args], capture_output=True,
                          text=True, check=True).stdout.strip()


def make_repo(base, given_name, items):
    """Git repo with a queue, committed (so the tree starts clean)."""
    d = Path(base) / given_name
    d.mkdir(parents=True)
    git(d, "init", "-q")
    git(d, "config", "user.email", "t@t")
    git(d, "config", "user.name", "t")
    (d / "code.py").write_text("x = 1\n")
    p = d / "itens.json"
    p.write_text(json.dumps(items), encoding="utf-8")
    r = run(d, "write", "fila", "--items", str(p), "--source", "teste",
            "--when", "2026-11-05", "--repo", ".")
    assert r.returncode == 0, r.stderr
    p.unlink()
    git(d, "add", "-A")
    git(d, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "init")
    return d


def item(ident):
    return {"id": ident, "title": f"item {ident}", "why": f"porque {ident}",
            "status": "pending", "blocked_by": [], "human_pending": None}


def plan_item(d, ident="A"):
    plan = yaml.safe_load((d / ".claude/queues/fila/queue.yaml")
                          .read_text(encoding="utf-8"))
    return {i["id"]: i for i in plan["items"]}[ident]


def start(d, session="s1", ident="A"):
    r = run(d, "start", "fila", ident, "--repo", ".", session=session)
    assert r.returncode == 0, r.stderr


def finish(d, status, evidence="feito", *extra, session="s1", ident="A"):
    return run(d, "finish", "fila", ident, "--status", status, "--evidence",
               evidence, "--repo", ".", *extra, session=session)


def test_two_finishes_keep_the_first_evidence(base):
    d = make_repo(base, "dois", [item("A")])
    start(d)
    r1 = finish(d, "done", "primeira evidência\nsegunda linha")
    check("o primeiro finish done é aceito", r1.returncode == 0, r1.stderr)
    r2 = finish(d, "done", "evidência que apagaria a primeira")
    check("o segundo finish é recusado (exit 2)", r2.returncode == 2, r2.stderr)
    check("a recusa nomeia o status e a primeira linha da evidência",
          "`done`" in r2.stderr and "primeira evidência" in r2.stderr, r2.stderr)
    it = plan_item(d)
    check("a evidence do primeiro continua igual",
          it["evidence"] == "primeira evidência\nsegunda linha", it.get("evidence"))
    check("finish_recusado tem 1 entrada", len(it.get("finish_recusado") or []) == 1,
          it.get("finish_recusado"))
    entry = (it.get("finish_recusado") or [{}])[0]
    check("a entrada traz quando, quem, status_pedido e motivo",
          all(entry.get(k) for k in ("quando", "quem", "status_pedido", "motivo")),
          entry)
    check("o status segue done", it["status"] == "done")


def test_refusals_keep_only_the_last_five(base):
    d = make_repo(base, "cinco", [item("A")])
    start(d)
    finish(d, "done")
    for _ in range(7):
        finish(d, "done", "outra")
    check("finish_recusado guarda só as 5 últimas",
          len(plan_item(d)["finish_recusado"]) == 5)


def test_done_with_modified_file_is_refused(base):
    d = make_repo(base, "suja", [item("A")])
    start(d)
    (d / "code.py").write_text("x = 2\n")
    r = finish(d, "done")
    check("done com arquivo modificado sem commit: recusado", r.returncode == 2, r.stderr)
    check("a recusa lista o arquivo", "code.py" in r.stderr, r.stderr)
    it = plan_item(d)
    check("o item continua in_progress", it["status"] == "in_progress", it)
    check("evidence ausente", not it.get("evidence"), it.get("evidence"))
    check("a recusa ficou registrada", len(it.get("finish_recusado") or []) == 1)
    check("o claimed_by não mudou", (it.get("claimed_by") or {}).get("session_id") == "s1")
    check("sem head_commit", "head_commit" not in it)


def test_done_with_clean_tree_records_head(base):
    d = make_repo(base, "limpa", [item("A")])
    start(d)  # leaves the queue modified, without commit, on purpose
    (d / ".claude/queues/fila/queue.yaml.bak").write_text("bak\n")
    r = finish(d, "done")
    check("done com árvore limpa (só a fila modificada): aceito", r.returncode == 0,
          r.stderr)
    it = plan_item(d)
    check("grava head_commit igual a git rev-parse HEAD",
          it.get("head_commit") == git(d, "rev-parse", "HEAD"), it.get("head_commit"))
    check("sem finish_recusado", not it.get("finish_recusado"))


def test_done_with_untracked_file_is_refused(base):
    d = make_repo(base, "nova", [item("A")])
    start(d)
    (d / "novo.py").write_text("y = 1\n")
    r = finish(d, "done")
    check("done com arquivo novo não rastreado: recusado", r.returncode == 2, r.stderr)
    check("a recusa lista o arquivo novo", "novo.py" in r.stderr, r.stderr)
    check("o item continua in_progress", plan_item(d)["status"] == "in_progress")


def test_done_outside_git_is_refused(base):
    d = make_repo(base, "semgit", [item("A")])
    start(d)
    # A directory that is not a git repo cannot record the SHA.
    outside = Path(base) / "fora"
    outside.mkdir()
    r = run(d, "finish", "fila", "A", "--status", "done", "--evidence", "x",
            "--repo", str(outside), session="s1")
    check("done sem repo git é recusado", r.returncode == 2, r.stderr)
    check("a recusa diz que o SHA não pode ser gravado",
          "SHA" in r.stderr or "git" in r.stderr, r.stderr)


def test_blocked_with_dirty_tree_is_accepted(base):
    d = make_repo(base, "bloqueia", [item("A")])
    start(d)
    (d / "code.py").write_text("x = 3\n")
    r = run(d, "finish", "fila", "A", "--status", "blocked", "--evidence", "travou",
            "--impede", "o servidor caiu", "--repo", ".", session="s1")
    check("blocked com árvore suja: aceito", r.returncode == 0, r.stderr)
    it = plan_item(d)
    check("status blocked, sem head_commit",
          it["status"] == "blocked" and "head_commit" not in it, it)


def test_other_caller_is_refused_and_supervisor_passes(base):
    d = make_repo(base, "outro", [item("A")])
    start(d, "s1")
    r = finish(d, "done", "intruso", session="s2")
    check("chamador diferente: recusado", r.returncode == 2, r.stderr)
    check("a recusa nomeia o dono s1", "s1" in r.stderr, r.stderr)
    it = plan_item(d)
    check("o item segue in_progress com dono s1",
          it["status"] == "in_progress" and it["claimed_by"]["session_id"] == "s1", it)
    check("a recusa registra quem tentou (s2)",
          it["finish_recusado"][0]["quem"]["session_id"] == "s2", it["finish_recusado"])
    r = finish(d, "done", "supervisor fecha", "--supervisor", session="s2")
    check("com --supervisor: aceito", r.returncode == 0, r.stderr)
    check("o status mudou", plan_item(d)["status"] == "done")


def test_unregistered_caller_compares_host_and_tree(base):
    d = make_repo(base, "semsessao", [item("A")])
    start(d, session=None)
    r = finish(d, "done", session=None)
    check("sem sessão registrada, mesma árvore: aceito", r.returncode == 0, r.stderr)
    d2 = make_repo(base, "semsessao2", [item("A")])
    start(d2, session=None)
    other = Path(base) / "semsessao-outra-arvore"
    subprocess.run(["git", "-C", str(d2), "worktree", "add", "-q", "-b", "w", str(other)],
                   check=True, capture_output=True)
    r = run(d2, "finish", "fila", "A", "--status", "done", "--evidence", "x",
            "--repo", str(other))
    check("sem sessão registrada, outra árvore: recusado", r.returncode == 2, r.stderr)
    check("ainda in_progress", plan_item(d2)["status"] == "in_progress")


def test_supervisor_reopens_a_done_item(base):
    d = make_repo(base, "reabre", [item("A")])
    start(d)
    finish(d, "done", "agente fechou")
    r = finish(d, "pending", "build vermelho, voltou", "--supervisor", session="outra")
    check("--supervisor sobre item done: aceito", r.returncode == 0, r.stderr)
    it = plan_item(d)
    check("o status mudou e a evidence foi trocada",
          it["status"] == "pending" and it["evidence"] == "build vermelho, voltou", it)
    check("head_commit antigo sai quando o item reabre", "head_commit" not in it)


def test_owner_can_finish_from_a_subdirectory(base):
    d = make_repo(base, "subdir", [item("A")])
    start(d)
    sub = d / "sub"
    sub.mkdir()
    r = finish(sub, "done")
    check("start na raiz, finish done a partir de sub/ (--repo .): aceito",
          r.returncode == 0, r.stderr)
    check("grava head_commit",
          plan_item(d).get("head_commit") == git(d, "rev-parse", "HEAD"))


def test_never_started_item_can_be_blocked(base):
    d = make_repo(base, "nunca", [item("A")])
    r = run(d, "finish", "fila", "A", "--status", "blocked", "--evidence", "x",
            "--impede", "fora do ar", "--repo", ".", session="qualquer")
    check("item sem claimed_by, blocked: aceito como antes", r.returncode == 0, r.stderr)


def main():
    with tempfile.TemporaryDirectory() as base:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                print(name)
                fn(base)
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\ntodos passaram")


if __name__ == "__main__":
    main()
