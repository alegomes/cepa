#!/usr/bin/env python3
"""bash-path-lock: a `cd` into ANOTHER repository leaves the session root for good.

No dependencies — run with `python3 tests/test_bash_path_lock_other_repo.py`.
Exits non-zero on failure.

## The incident (fb-20261110-6, 2026-11-10)

The session was opened in wego-faturamento-backend (repo A). Its workers wrote
in the worktree of wego-digitacao-backend (repo B, C1-20), a sibling directory
outside A. A qa-engineer ran, in a single Bash call:

    cd <B>/bootstrap/src/test/java/.../cli && cat > Base.java <<'EOF'
    ...
    EOF
    cat > MultimodalTest.java <<'EOF'
    ...

and was denied "escrita fora da sua pista" naming `MultimodalTest.java`. The
second `cat` comes after a newline, and with `;`/newline the lock assumes the
`cd` may have failed: it resolved the relative target against A's root too,
and judged it by A's lanes. The file was in B, in the qa-engineer's lane.

A `cd` to a directory that exists now, in another git repository, as the FIRST
segment of the line, cannot fail: nothing before it in the line could have
removed the directory. From there on the line runs in B, which is outside the
jurisdiction of A's lock (bucket 3), exactly as with `&&`.

What stays conservative, on purpose (the owner's design for the `cd`, approved
2026-08-15, and the existing tests in test_bash_path_lock_exec.py):
a `cd` that is not the first segment, inside a pipe or subshell, into a
directory that does not exist, into a directory that is not a git repository
(/tmp), or into a worktree of the SAME repository (the proof-reviewer's
perturbation copy). And a line that cites A's root is never bucket 3.

The cases run against every generated copy of the hook, as a subprocess.

## Perturbation

In `common/hooks/_templates/bash-path-lock.py.tmpl`, make `_cd_cannot_fail`
return False, regenerate with `python3 bin/gen-locks.py --write` and run: the
"libera" cases turn red in every copy.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from _isolated_telemetry import isolate

isolate()

REPO = Path(__file__).resolve().parent.parent
HOOKS = sorted(REPO.glob("*/hooks/bash-path-lock.py"))

AGENTS = {
    "build-hex": "qa-engineer",
    "build-team": "qa-engineer",
    "design": "ux-architect",
    "discovery": "user-researcher",
    "docs-topology": "doc-author",
    "marketing": "copywriter",
}

FAILURES = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok  {label}")
    else:
        FAILURES.append(label)
        print(f"FAIL  {label}  {detail}")


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


def make_repo(prefix):
    root = Path(tempfile.mkdtemp(prefix=prefix)).resolve()
    git("init", "-q", cwd=root)
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
        "--allow-empty", "-m", "init", cwd=root)
    return root


def plugin_of(hook: Path) -> str:
    return json.loads((hook.parent.parent / ".claude-plugin" / "plugin.json")
                      .read_text(encoding="utf-8"))["name"]


def run(hook, agent_type, command, cwd):
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "agent_type": agent_type,
        "cwd": str(cwd),
    }
    env = dict(os.environ)
    env.pop("CEPA_BASHLOCK_ENFORCE", None)
    p = subprocess.run([sys.executable, str(hook)], input=json.dumps(payload),
                       capture_output=True, text=True, env=env, timeout=60)
    return p.returncode, p.stderr


def main():
    if not HOOKS:
        print("FAIL: no */hooks/bash-path-lock.py found")
        return 1

    a = make_repo("bpl-repo-a-")          # the session's repo
    b = make_repo("bpl-repo-b-")          # the sibling repo the worker writes in
    b_dir = b / "bootstrap" / "src" / "test" / "java"
    b_dir.mkdir(parents=True)
    # A worktree of A itself, outside A's root: the perturbation copy.
    same = Path(tempfile.mkdtemp(prefix="bpl-wt-")).resolve() / "red"
    git("worktree", "add", "-q", "--detach", str(same), "HEAD", cwd=a)
    tmp = Path(tempfile.mkdtemp(prefix="bpl-tmp-")).resolve()   # not a repo

    heredocs = ("cat > Base.java <<'EOF'\nclass Base {}\nEOF\n"
                "cat > MultimodalTest.java <<'EOF'\nclass MultimodalTest {}\nEOF")

    allow = [
        ("incidente: cd no repo vizinho && heredoc, outro heredoc na linha seguinte",
         f"cd {b_dir} && {heredocs}"),
        ("cd no repo vizinho; escrita relativa", f"cd {b_dir}; cat > Y.java <<'EOF'\nx\nEOF"),
        ("cd no repo vizinho, interpretador na linha seguinte",
         f"cd {b} && D=x\npython3 - <<'EOF'\nprint(1)\nEOF"),
        ("cd na raiz do repo vizinho || escrita", f"cd {b} || cat > Y.java <<'EOF'\nx\nEOF"),
    ]
    deny = [
        ("cd não é o primeiro segmento", f"true && cd {b}; cat > Y.java <<'EOF'\nx\nEOF"),
        ("cd dentro de pipe não muda o diretório", f"cd {b} | true; python3 -c 1"),
        ("cd em subshell não muda o diretório", f"(cd {b}); python3 -c 1"),
        ("diretório que não existe pode falhar", f"cd {b}/nao-existe; python3 -c 1"),
        ("diretório fora de git (/tmp) segue conservador", f"cd {tmp}; python3 -c 1"),
        ("worktree do MESMO repo (cópia de perturbação) segue conservador",
         f"cd {same}; python3 -c 1"),
        ("linha que cita a raiz da sessão nunca é balde 3",
         f"cd {b}; python3 -c \"open('{a}/src/main/X.java','w')\""),
    ]

    for hook in HOOKS:
        top = hook.parent.parent.name
        agent_type = f"{plugin_of(hook)}:{AGENTS[top]}"
        for want, cases in ((0, allow), (2, deny)):
            for label, cmd in cases:
                rc, err = run(hook, agent_type, cmd, a)
                verb = "libera" if want == 0 else "nega"
                check(f"[{top:13}] {verb}: {label}",
                      rc == want and "erro interno" not in err,
                      f"exit={rc} (esperado {want}) stderr={err.strip()[:300]!r}")

    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
