#!/usr/bin/env python3
"""Tests for the safe-exit-gate Stop hook and the shared definition of dirt
(common/hooks/_dirt.py). fb-20261105-3: wrap-up said "Safe to exit" with the
main clone dirty and `cepa-until` refused to start right after.

Run: python3 tests/test_safe_exit_gate.py
"""

import importlib.machinery
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "safe-exit-gate.py"
CEPA_UNTIL = REPO / "common" / "bin" / "cepa-until"
FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def git(repo, *args):
    return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                           *args], cwd=str(repo), capture_output=True, text=True)


def make_repo(tmp):
    root = Path(tmp) / "main"
    q = root / ".claude" / "queues" / "f"
    q.mkdir(parents=True)
    (q / "queue.yaml").write_text("items: []\n", encoding="utf-8")
    (root / "README.md").write_text("base\n", encoding="utf-8")
    git(root, "init", "-q", "-b", "main", ".")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    return root


def transcript(tmp, text):
    p = Path(tmp) / "t.jsonl"
    row = {"type": "assistant",
           "message": {"content": [{"type": "text", "text": text}]}}
    p.write_text(json.dumps(row) + "\n", encoding="utf-8")
    return p


SAFE = "Landed. Safe to `exit`."


def run_hook(tmp, cwd, text=SAFE, **extra):
    payload = {"hook_event_name": "Stop", "transcript_path": str(transcript(tmp, text)),
               "cwd": str(cwd), "session_id": "t", **extra}
    import os
    env = dict(os.environ, CEPA_TELEMETRY_DIR=str(Path(tmp) / "telemetry"))
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       capture_output=True, text=True, timeout=60, env=env)
    return p.stdout, p.returncode


def load_until():
    loader = importlib.machinery.SourceFileLoader("cepa_until_gate", str(CEPA_UNTIL))
    spec = importlib.util.spec_from_loader("cepa_until_gate", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


CU = load_until()


def until_dirty(repo):
    return CU.dirty_tree(repo, live_run_ok=True)


def blocks(out):
    return '"decision": "block"' in out


def touch(root, rel, text="x\n"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_a_tracked_modified_blocks():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        touch(root, ".claude/queues/f/queue.yaml", "items: [1]\n")
        out, rc = run_hook(tmp, root)
        check("a: bloqueia", blocks(out), out)
        check("a: nomeia queue.yaml", "queue.yaml" in out, out)
        check("a: instrui add -u", "add -u" in out, out)
        check("a: until recusa também", bool(until_dirty(root)))
        check("a: exit 0", rc == 0)


def test_b_clean_silent():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        out, _ = run_hook(tmp, root)
        check("b: limpo sem saída", out == "", out)
        check("b: until não recusa", not until_dirty(root))


def test_c_run_record_and_bak_do_not_count():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        touch(root, ".claude/queues/f/until/x.jsonl")
        touch(root, ".claude/queues/f/queue.yaml.bak")
        out, _ = run_hook(tmp, root)
        check("c: não bloqueia", out == "", out)
        check("c: until não recusa", not until_dirty(root))


def test_d_no_safe_exit_phrase():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        touch(root, ".claude/queues/f/queue.yaml", "items: [1]\n")
        out, _ = run_hook(tmp, root, text="Feito. Ainda falta commitar.")
        check("d: sem a frase, não bloqueia", out == "", out)


def test_e_stop_hook_active():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        touch(root, ".claude/queues/f/queue.yaml", "items: [1]\n")
        out, _ = run_hook(tmp, root, stop_hook_active=True)
        check("e: stop_hook_active deixa passar", out == "", out)


def test_f_linked_worktree_checks_main_clone():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        wt = Path(tmp) / "wt"
        git(root, "worktree", "add", "-q", "-b", "session/x", str(wt))
        touch(root, ".claude/queues/f/queue.yaml", "items: [1]\n")
        out, _ = run_hook(tmp, wt)
        check("f: worktree limpa, main suja → bloqueia", blocks(out), out)
        check("f: cita o clone principal", str(root.resolve()) in out
              or str(root) in out, out)
        check("f: until recusa no main", bool(until_dirty(root)))
        check("f: until não recusa na worktree", not until_dirty(wt))


def test_g_exclude():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        touch(root, ".claude/sessions/s.json")
        touch(root, ".claude/last-build.json")
        p = subprocess.run([sys.executable, str(HOOK), "--exclude", str(root)],
                           capture_output=True, text=True)
        ex = (root / ".git" / "info" / "exclude").read_text()
        check("g: sessions/ no exclude", ".claude/sessions/" in ex, ex)
        check("g: last-build.json no exclude", ".claude/last-build.json" in ex, ex)
        check("g: --exclude sai 0", p.returncode == 0, p.stdout)
        check("g: status vazio", git(root, "status", "--porcelain").stdout == "")
        p2 = subprocess.run([sys.executable, str(HOOK), "--exclude", str(root)],
                            capture_output=True, text=True)
        check("g: idempotente", (root / ".git/info/exclude").read_text() == ex, p2.stdout)

    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        touch(root, ".claude/last-build.json", "{}\n")
        git(root, "add", "-A")
        git(root, "commit", "-qm", "oops tracked")
        touch(root, ".claude/last-build.json", '{"a":1}\n')
        p = subprocess.run([sys.executable, str(HOOK), "--exclude", str(root)],
                           capture_output=True, text=True)
        exf = root / ".git" / "info" / "exclude"
        ex = exf.read_text() if exf.exists() else ""
        check("g: tracked não vai pro exclude", "last-build.json" not in ex, ex)
        check("g: tracked segue como sujeira", p.returncode == 1
              and ".claude/last-build.json" in p.stdout, p.stdout)


def test_g2_exclude_from_linked_worktree():
    """`--exclude` run from a linked worktree writes the MAIN clone's info/exclude."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        wt = Path(tmp) / "wt"
        git(root, "worktree", "add", "-q", "-b", "session/y", str(wt))
        touch(wt, ".claude/sessions/s.json")
        touch(wt, ".claude/last-build.json")
        p = subprocess.run([sys.executable, str(HOOK), "--exclude", str(wt)],
                           capture_output=True, text=True)
        ex = (root / ".git" / "info" / "exclude").read_text()
        check("g2: exclude do clone principal recebe sessions/", ".claude/sessions/" in ex, ex)
        check("g2: ...e last-build.json", ".claude/last-build.json" in ex, ex)
        check("g2: nada escrito dentro da worktree", not (wt / ".git" / "info").exists())
        check("g2: --exclude sai 0", p.returncode == 0, p.stdout)
        check("g2: status da worktree vazio", git(wt, "status", "--porcelain").stdout == "")


def test_h_parity_with_cepa_until():
    """The acceptance: the gate is silent exactly when cepa-until would start,
    and blocks exactly when it would refuse. Scenarios beyond a..f, including
    the one the completion-auditor found (an unversioned `.claude/` holding
    only a run record, which a collapsed `?? .claude/` used to hide)."""
    def scenario(label, setup, expect_dirty):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "main"
            root.mkdir()
            (root / "README.md").write_text("base\n", encoding="utf-8")
            git(root, "init", "-q", "-b", "main", ".")
            git(root, "add", "-A")
            git(root, "commit", "-qm", "base")
            setup(root)
            out, _ = run_hook(tmp, root)
            until = bool(until_dirty(root))
            check(f"h: {label} — hook {'bloqueia' if expect_dirty else 'cala'}",
                  blocks(out) == expect_dirty, out[-300:])
            check(f"h: {label} — until {'recusa' if expect_dirty else 'larga'}",
                  until == expect_dirty)
            check(f"h: {label} — hook e until concordam", blocks(out) == until)
            return root, tmp

    scenario(".claude/ sem versão só com registro de run",
             lambda r: touch(r, ".claude/queues/g/until/r.jsonl", "{}\n"), False)
    scenario("arquivo novo solto", lambda r: touch(r, "novo.txt"), True)
    scenario(".claude/ sem versão só com runtime dos hooks",
             lambda r: touch(r, ".claude/sessions/s.json"), True)
    scenario("registro de run + runtime dos hooks",
             lambda r: (touch(r, ".claude/queues/g/until/r.jsonl"),
                        touch(r, ".claude/last-build.json")), True)

    # and after `--exclude`, both sides agree again on "clean"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "main"
        root.mkdir()
        (root / "README.md").write_text("base\n", encoding="utf-8")
        git(root, "init", "-q", "-b", "main", ".")
        git(root, "add", "-A")
        git(root, "commit", "-qm", "base")
        touch(root, ".claude/queues/g/until/r.jsonl")
        touch(root, ".claude/sessions/s.json")
        out, _ = run_hook(tmp, root)
        check("h: antes do --exclude o hook manda excluir", blocks(out) and "--exclude" in out, out[-300:])
        subprocess.run([sys.executable, str(HOOK), "--exclude", str(root)],
                       capture_output=True, text=True)
        out, _ = run_hook(tmp, root)
        check("h: depois do --exclude o hook cala", not blocks(out), out[-300:])
        check("h: ...e o until larga", not until_dirty(root))


def test_i_check_exit_code():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        p = subprocess.run([sys.executable, str(HOOK), "--check", str(root)],
                           capture_output=True, text=True)
        check("i: limpo → 0", p.returncode == 0 and "limpo" in p.stdout, p.stdout)
        touch(root, ".claude/queues/f/queue.yaml", "items: [1]\n")
        p = subprocess.run([sys.executable, str(HOOK), "--check", str(root)],
                           capture_output=True, text=True)
        check("i: sujo → 1", p.returncode == 1 and "queue.yaml" in p.stdout, p.stdout)


def test_j_plugin_registration():
    d = json.loads((REPO / "common/.claude-plugin/plugin.json").read_text())
    cmds = [h["command"] for g in d["hooks"]["Stop"] for h in g["hooks"]]
    check("j: registrado em Stop", any("safe-exit-gate.py" in c for c in cmds), cmds)
    check("j: versão 3.5.0", d["version"] == "3.5.0", d["version"])


def test_k_prose():
    s = (REPO / "common/commands/wrap-up.md").read_text()
    check("k: regra velha removida", "Don't block on unrelated dirt" not in s)
    check("k: cita safe-exit-gate.py", "safe-exit-gate.py" in s)
    check("k: cita --exclude", "--exclude" in s)


for name, fn in list(globals().items()):
    if name.startswith("test_"):
        print(name)
        fn()

if FAILURES:
    print(f"\n{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("\nall ok")
