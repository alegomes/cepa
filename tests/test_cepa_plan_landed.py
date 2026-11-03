#!/usr/bin/env python3
"""`cepa-plan landed` lists the Review cards whose code already reached the
integration branch with PROVEN proof and complete acceptance (fb-20261103-1).

Origin: on 2026-11-03 eleven WEGO cards sat in Review after
`cepa-until aterrissar` merged the overnight branch into main; nothing moved
them, because the run's rule is "no Done" and the landing never speaks to Jira.

Against the real CLI in a real git repo with board-flow.yaml:

  - proven + complete + head on main          -> ready
  - head only on a side branch                -> held, says not on the ref
  - verdict needs-human                       -> held
  - no acceptance / invalid acceptance YAML   -> held, each with its reason
  - card not In Review on the board           -> ignored
  - --json carries `into`, `prontos`, `retidos`
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

CEPA_PLAN = Path(__file__).resolve().parent.parent / "common" / "bin" / "cepa-plan"
FAILURES = []


def check(name, cond, detail=""):
    print(f"  ok  {name}" if cond else f"FAIL  {name}  {detail}")
    if not cond:
        FAILURES.append(name)


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c",
                           "user.name=t", *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def commit(root, name):
    (root / f"{name}.txt").write_text(name)
    git(root, "add", "-A")
    git(root, "commit", "-qm", name)
    return git(root, "rev-parse", "--short", "HEAD")


def proof(root, key, verdict, head):
    d = root / "docs" / "proof"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.yaml").write_text(f"key: {key}\nverdict: {verdict}\nhead_commit: {head}\n")


def acceptance(root, key, text="status: complete\n"):
    d = root / ".claude" / "acceptance"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.yaml").write_text(f"key: {key}\n{text}")


def build(tmp):
    root = Path(tmp) / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main", ".")
    (root / "board-flow.yaml").write_text(
        "defaults:\n  status_map:\n    in_review: \"In Review\"\n    done: \"Done\"\n")
    on_main = commit(root, "a")
    git(root, "checkout", "-qb", "side")
    on_side = commit(root, "b")
    git(root, "checkout", "-q", "main")
    proof(root, "K-1", "proven", on_main); acceptance(root, "K-1")
    proof(root, "K-2", "proven", on_side); acceptance(root, "K-2")
    proof(root, "K-3", "needs-human", on_main); acceptance(root, "K-3")
    proof(root, "K-4", "proven", on_main)
    proof(root, "K-5", "proven", on_main)
    acceptance(root, "K-5", "status: complete\nnote: a: b: c\n")
    proof(root, "K-6", "proven", on_main); acceptance(root, "K-6")
    board = Path(tmp) / "board.json"
    board.write_text(json.dumps({"cards": [
        {"key": k, "status": "In Review"} for k in ("K-1", "K-2", "K-3", "K-4", "K-5")]
        + [{"key": "K-6", "status": "Done"}]}))
    return root, board


def run(root, board, *extra):
    return subprocess.run([sys.executable, str(CEPA_PLAN), "landed", "--board",
                           str(board), "--repo", str(root), *extra],
                          capture_output=True, text=True)


def test_landed_lists_only_cards_ready_for_done():
    with tempfile.TemporaryDirectory() as tmp:
        root, board = build(tmp)
        p = run(root, board, "--json")
        check("sai 0", p.returncode == 0, p.stderr)
        d = json.loads(p.stdout)
        ready = [r["key"] for r in d["prontos"]]
        held = {r["key"]: r["motivo"] for r in d["retidos"]}
        check("ref de integração é main", d["into"] == "main", d["into"])
        check("só K-1 está pronto", ready == ["K-1"], ready)
        check("K-2 retido: código fora da main", "ainda não está em main" in held.get("K-2", ""), held)
        check("K-3 retido: needs-human", "needs-human" in held.get("K-3", ""), held)
        check("K-4 retido: sem auditoria", held.get("K-4") == "sem auditoria de aceite", held)
        check("K-5 retido: YAML inválido", "ilegível" in held.get("K-5", ""), held)
        check("K-6 (já Done) ignorado", "K-6" not in ready and "K-6" not in held)


def test_side_branch_card_becomes_ready_after_landing():
    with tempfile.TemporaryDirectory() as tmp:
        root, board = build(tmp)
        git(root, "merge", "-q", "--no-ff", "side", "-m", "aterrissa")
        d = json.loads(run(root, board, "--json").stdout)
        check("depois do merge, K-2 fica pronto",
              [r["key"] for r in d["prontos"]] == ["K-1", "K-2"], d["prontos"])


def test_text_output_counts():
    with tempfile.TemporaryDirectory() as tmp:
        root, board = build(tmp)
        p = run(root, board)
        check("texto diz 5 em revisão e 1 pronto",
              "5 card(s) em revisão; 1 pronto(s)" in p.stdout, p.stdout)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            fn()
    print("\nall green" if not FAILURES else f"\n{len(FAILURES)} FAIL")
    sys.exit(1 if FAILURES else 0)
