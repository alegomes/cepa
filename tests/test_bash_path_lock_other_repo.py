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
a `cd` that is not the first segment, inside a pipe, subshell or background
job, into a directory that does not exist, into a directory that is not a git
repository (/tmp), or into a worktree of the SAME repository (the
proof-reviewer's perturbation copy). And a line that cites A's root is never
bucket 3. Only a plain `cd <absolute path>` counts: `pushd -n` does not move,
a relative path may follow CDPATH, a flag changes the meaning, and `..` is
resolved logically by the shell (`cd <A>/link/..` with `link -> <B>/x` lands
back in A) — the last two were bypasses found in the pair review.

The decision recorded with this item: outside the session root the lock has
no jurisdiction, for the Write tool too, and B's `build-hex.yaml` is not read.
`check_write_in_sibling_repo` pins that with a real repo B whose config would
deny the file.

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


def run(hook, agent_type, command, cwd, proc_cwd=None, env_extra=None):
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "agent_type": agent_type,
        "cwd": str(cwd),
    }
    env = dict(os.environ)
    env.pop("CEPA_BASHLOCK_ENFORCE", None)
    env.update(env_extra or {})
    p = subprocess.run([sys.executable, str(hook)], input=json.dumps(payload),
                       capture_output=True, text=True, env=env, timeout=60,
                       cwd=str(proc_cwd) if proc_cwd else None)
    return p.returncode, p.stderr


def check_write_in_sibling_repo(a):
    """Write tool, session in A, file in a real sibling repo B: out of A's
    jurisdiction, and B's committed build-hex.yaml is NOT applied (the item's
    recorded decision). The file is outside the qa-engineer's lanes in both
    repos, so exit 0 proves neither rule set decided."""
    b = make_repo("bpl-repo-b-cfg-")
    (b / "build-hex.yaml").write_text("schema_version: 1\nroles:\n  domain: core\n",
                                      encoding="utf-8")
    git("add", "build-hex.yaml", cwd=b)
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "cfg", cwd=b)
    hook = REPO / "build-hex" / "hooks" / "path-lock.py"
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(b / "core" / "src" / "main" / "X.java")},
        "agent_type": "build-hex:qa-engineer",
        "cwd": str(a),
    }
    p = subprocess.run([sys.executable, str(hook)], input=json.dumps(payload),
                       capture_output=True, text=True, timeout=60)
    check("[build-hex    ] Write num repo vizinho com build-hex.yaml: fora da jurisdição",
          p.returncode == 0, f"exit={p.returncode} stderr={p.stderr.strip()[:300]!r}")
    # control: the same file inside A's root IS judged (qa-engineer, src/main)
    payload["tool_input"]["file_path"] = str(a / "domain" / "src" / "main" / "X.java")
    p = subprocess.run([sys.executable, str(hook)], input=json.dumps(payload),
                       capture_output=True, text=True, timeout=60)
    check("[build-hex    ] controle: o mesmo Write dentro de A é julgado e negado",
          p.returncode == 2, f"exit={p.returncode}")


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
    (b / "x").mkdir()
    (a / "link").symlink_to(b / "x")   # logical `..` through it lands in A
    (b / "toA").symlink_to(a)          # a relative path in B that reaches A
    # A session root nested inside another repo P (root = P/N).
    p_repo = make_repo("bpl-repo-p-")
    n_root = p_repo / "N"
    n_root.mkdir()
    git("init", "-q", cwd=n_root)
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
        "--allow-empty", "-m", "init", cwd=n_root)
    plain = Path(tempfile.mkdtemp(prefix="bpl-plain-")).resolve()   # root outside git

    heredocs = ("cat > Base.java <<'EOF'\nclass Base {}\nEOF\n"
                "cat > MultimodalTest.java <<'EOF'\nclass MultimodalTest {}\nEOF")

    allow = [
        ("incidente: cd no repo vizinho && heredoc, outro heredoc na linha seguinte",
         f"cd {b_dir} && {heredocs}"),
        ("cd no repo vizinho; escrita relativa", f"cd {b_dir}; cat > Y.java <<'EOF'\nx\nEOF"),
        ("cd no repo vizinho, interpretador na linha seguinte",
         f"cd {b} && D=x\npython3 - <<'EOF'\nprint(1)\nEOF"),
        ("cd na raiz do repo vizinho || escrita", f"cd {b} || cat > Y.java <<'EOF'\nx\nEOF"),
        ("cd no repo vizinho dentro de $(...)", f"x=$(cd {b}; python3 -c 1)"),
    ]
    deny = [
        ("cd não é o primeiro segmento", f"true && cd {b}; cat > Y.java <<'EOF'\nx\nEOF"),
        ("cd dentro de pipe não muda o diretório", f"cd {b} | true; python3 -c 1"),
        ("cd em subshell não muda o diretório", f"(cd {b}); python3 -c 1"),
        ("diretório que não existe pode falhar", f"cd {b}/nao-existe; python3 -c 1"),
        ("diretório fora de git (/tmp) segue conservador", f"cd {tmp}; python3 -c 1"),
        ("worktree do MESMO repo (cópia de perturbação) segue conservador",
         f"cd {same}; python3 -c 1"),
        ("pushd -n não muda o diretório",
         f"pushd -n {b}\ncat > rel.txt <<'EOF'\nx\nEOF"),
        ("`..` lógico por um link de A volta para A",
         f"cd {a}/link/..\ncat > rel.txt <<'EOF'\nx\nEOF"),
        ("cd relativo pode seguir o CDPATH", f"cd ../{b.name}; python3 -c 1"),
        ("cd com flag não conta como certo", f"cd -P {b}; python3 -c 1"),
        ("cd | escrita: o pipe não herda o cd", f"cd {b} | cat > Y.java <<'EOF'\nx\nEOF"),
        ("cd em segundo plano não muda o diretório",
         f"cd {b} &\ncat > Y.java <<'EOF'\nx\nEOF"),
        ("cd & escrita na mesma linha", f"cd {b} & cat > Y.java <<'EOF'\nx\nEOF"),
        ("cd $OLDPWD volta para a raiz",
         f"cd {b}\ncd $OLDPWD\ncat > evil.txt <<'E'\nx\nE"),
        ("link em B que aponta para A, depois de ;",
         f"cd {b}\ncat > toA/evil.txt <<'E'\nx\nE"),
        ("link em B que aponta para A, depois de &&",
         f"cd {b} && cat > toA/evil.txt <<'E'\nx\nE"),
        ("cd ~- volta para a raiz", f"cd {b}; cd ~-; touch x"),
        ("~-/x é a raiz", f"cd {b}; touch ~-/x"),
        ("~+ é o diretório atual: ~+/toA alcança a raiz por link",
         f"cd {b}; touch ~+/toA/evil.txt"),
        ("valor de flag --out= por um link para A",
         f"cd {b}; python3 tool.py --out=toA/evil.txt"),
        ("cd dentro de $(...) não move a linha",
         f"echo $(cd {b}); cat > Y.java <<'E'\nx\nE"),
        ("linha que cita a raiz da sessão nunca é balde 3",
         f"cd {b}; python3 -c \"open('{a}/src/main/X.java','w')\""),
    ]

    # (label, command, session root, hook process cwd)
    deny_other_roots = [
        ("raiz aninhada no destino: cd no repo pai, escrita relativa",
         f"cd {p_repo}\ncat > N/evil.txt <<'E'\nx\nE", n_root, None),
        ("raiz aninhada no destino: cd no repo pai nunca é certo",
         f"cd {p_repo}; python3 -c 1", n_root, None),
        ("raiz fora de git: na dúvida, conservador", f"cd {b}; python3 -c 1", plain, None),
        ("cd relativo sem .. pode seguir o CDPATH",
         f"cd {b.name}; python3 -c 1", a, b.parent),
    ]

    for hook in HOOKS:
        top = hook.parent.parent.name
        agent_type = f"{plugin_of(hook)}:{AGENTS[top]}"
        cases = [(0, label, cmd, a, None, None) for label, cmd in allow]
        cases += [(2, label, cmd, a, None, None) for label, cmd in deny]
        cases += [(2, label, cmd, root, pc, None) for label, cmd, root, pc in deny_other_roots]
        # the hook's environment may carry an OLDPWD pointing at B: it must not
        # be taken as the line's previous directory
        cases.append((2, "cd $OLDPWD com OLDPWD=<B> no ambiente do hook",
                      f"cd {b}\ncd $OLDPWD\ncat > evil.txt <<'E'\nx\nE", a, None,
                      {"OLDPWD": str(b)}))
        for want, label, cmd, root, pc, env_extra in cases:
            rc, err = run(hook, agent_type, cmd, root, pc, env_extra)
            verb = "libera" if want == 0 else "nega"
            check(f"[{top:13}] {verb}: {label}",
                  rc == want and "erro interno" not in err,
                  f"exit={rc} (esperado {want}) stderr={err.strip()[:300]!r}")

    check_write_in_sibling_repo(a)

    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
