#!/usr/bin/env python3
"""Contract tests: gate-advance evaluates the baseline of the repo that RECEIVES the commit/push.

No third-party dependency — run with
`python3 tests/test_gate_advance_target_repo.py`.

The defect, reproduced on 2026-10-10: a session opened in repo A
(`~/coding/al2.digital/kodez.cool`, with a STALE `.claude/last-build.json`) ran
`cd ~/coding/cepa && git commit ...`. The hook anchored the state at the root of the repo
of the SESSION (A) and blocked a commit that belonged to repo B. The same applies to
`git -C <other repo> commit/push`. The reverse is also a hole: the session's
`.claude/no-build` opt-out must not leak to a push in a red repo B.

The rule: the target is the directory of the LAST `cd` before the `git` segment (relative
to the payload's cwd, `~` expanded) or the argument of `git -C`; its repo root
(`_wtlib.session_root`) decides `no-build`, `last-build.json` and the build
manifest. Without an explicit target, the payload's cwd applies, as always.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from _telemetria_isolada import isola

isola()


REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "common" / "hooks"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def run_hook(script, payload, env=None):
    return subprocess.run(
        [sys.executable, str(HOOKS / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )


def git(args, cwd):
    return subprocess.run(["git"] + args, cwd=str(cwd),
                          capture_output=True, text=True)


def make_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    git(["init", "-q", "-b", "main"], path)
    git(["config", "user.email", "t@t"], path)
    git(["config", "user.name", "t"], path)
    (path / "pom.xml").write_text("<project/>", encoding="utf-8")
    (path / "README.md").write_text("x", encoding="utf-8")
    git(["add", "-A"], path)
    git(["commit", "-qm", "seed"], path)
    return path


def red(repo):
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude" / "last-build.json").write_text(json.dumps({
        "status": "FAILURE", "at": "2026-10-10T10:00:00+00:00",
        "command": "./mvnw verify", "kind": "maven",
    }), encoding="utf-8")


def no_build(repo):
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude" / "no-build").write_text("", encoding="utf-8")


def gate(command, cwd, env=None):
    return run_hook("gate-advance.py", {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(cwd),
    }, env=env)


def new_pair(tmp, name):
    a = make_repo(tmp / name / "A")
    b = make_repo(tmp / name / "B")
    return a, b


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp).resolve()

    print("\n# cd B && git commit — A vermelho, B com no-build")
    a, b = new_pair(tmp, "c1")
    red(a)
    no_build(b)
    r = gate(f"cd {b} && git commit -m x", a)
    check("commit em B liberado", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:200]}")

    print("\n# git -C B push — A vermelho, B com no-build")
    a, b = new_pair(tmp, "c2")
    red(a)
    no_build(b)
    r = gate(f"git -C {b} push origin main", a)
    check("push -C B liberado", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:200]}")

    print("\n# o no-build da sessão não vaza para B vermelho")
    a, b = new_pair(tmp, "c3")
    no_build(a)
    red(b)
    r = gate(f"cd {b} && git push origin main", a)
    check("push em B vermelho BARRADO", r.returncode == 2,
          f"exit={r.returncode} stderr={r.stderr[:200]}")

    print("\n# sem cd / sem -C — comportamento de hoje")
    a, b = new_pair(tmp, "c4")
    red(a)
    r = gate("git push origin main", a)
    check("push no repo da sessão vermelho BARRADO", r.returncode == 2,
          f"exit={r.returncode} stderr={r.stderr[:200]}")

    print("\n# cd para subdiretório de B")
    a, b = new_pair(tmp, "c5")
    red(a)
    no_build(b)
    (b / "sub").mkdir()
    r = gate(f"cd {b}/sub && git commit -m x", a)
    check("ancora na raiz de B", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:200]}")

    print("\n# cd relativo")
    a, b = new_pair(tmp, "c6")
    red(a)
    no_build(b)
    r = gate("cd ../B && git commit -m x", a)
    check("cd ../B resolvido contra o cwd", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:200]}")

    print("\n# extras")
    a, b = new_pair(tmp, "c7")
    red(a)
    no_build(b)
    r = gate("cd ../B; git push origin main", a)
    check("separador `;` também", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:200]}")
    r = gate("git -C ../B commit -m x", a)
    check("-C relativo resolvido contra o cwd", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:200]}")

    print("\n# git -C — o portão precisa enxergar a forma e julgar o repo alvo")
    a, b = new_pair(tmp, "c8")
    no_build(a)
    red(b)
    r = gate(f"git -C {b} push origin main", a)
    check("git -C B push (B vermelho, A no-build) BARRADO", r.returncode == 2,
          f"exit={r.returncode} stderr={r.stderr[:200]}")
    r = gate(f"git -C{b} push origin main", a)
    check("git -C<B> colado BARRADO", r.returncode == 2,
          f"exit={r.returncode} stderr={r.stderr[:200]}")
    r = gate(f"git -C {b} status", a)
    check("git -C B status segue isento", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:200]}")

    print("\n# dois cd na mesma linha — vale o ÚLTIMO")
    a, b = new_pair(tmp, "c11")
    c = make_repo(tmp / "c11" / "C")
    red(a)
    red(c)
    no_build(b)
    r = gate(f"cd {c} && cd {b} && git push origin main", a)
    check("último cd (B, no-build) vence o primeiro (C, vermelho)", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:200]}")
    a, b = new_pair(tmp, "c12")
    c = make_repo(tmp / "c12" / "C")
    no_build(c)
    red(b)
    r = gate(f"cd {c} && cd {b} && git commit -m x", a)
    check("último cd (B, vermelho) vence o primeiro (C, no-build)", r.returncode == 2,
          f"exit={r.returncode} stderr={r.stderr[:200]}")

    print("\n# git -C: commit, -c k=v e ~")
    a, b = new_pair(tmp, "c13")
    no_build(a)
    red(b)
    r = gate(f"git -C {b} commit -m x", a)
    check("git -C B commit BARRADO", r.returncode == 2,
          f"exit={r.returncode} stderr={r.stderr[:200]}")
    # `git -c k=v -C B push` is NOT tested end to end: classify() only accepts
    # `-C` between `git` and the subcommand (decision: do not widen to `-c`). The
    # alignment of -C after a `-c` is locked in segment_dirs, below.
    a, b = new_pair(tmp, "c14")
    no_build(a)
    red(b)
    r = gate("git -C ~/c14/B push origin main", a, env={**os.environ, "HOME": str(tmp)})
    check("git -C ~/B expande o HOME e BARRA", r.returncode == 2,
          f"exit={r.returncode} stderr={r.stderr[:200]}")

    print("\n# fail-open — problema de parse nunca derruba o hook")
    a, _b = new_pair(tmp, "c9")
    red(a)
    r = gate("cd 'B && git commit -m x", a)
    print(f"    (aspas abertas) exit={r.returncode}")
    check("aspas abertas: sem Traceback", "Traceback" not in r.stderr, r.stderr[:300])
    check("aspas abertas: exit 0 ou 2, nunca 1", r.returncode in (0, 2), r.returncode)
    check("aspas abertas: decide pelo estado de A (barrado)", r.returncode == 2,
          f"exit={r.returncode}")
    r = gate("cd /caminho/que/nao/existe && git push origin main", a)
    print(f"    (cd inexistente) exit={r.returncode}")
    check("cd inexistente: sem Traceback", "Traceback" not in r.stderr, r.stderr[:300])
    # A target that does not resolve to a directory (nonexistent) is a resolution failure, not
    # a repo without build: the hook goes back to the session's repo (A, red).
    check("cd inexistente: cai no estado de A (barrado)", r.returncode == 2,
          f"exit={r.returncode} stderr={r.stderr[:200]}")
    for label, cmd in (("cd $VAR", "cd $VAR && git push origin main"),
                        ("cd -", "cd - && git push origin main"),
                        ("cd inexistente;", "cd /nao/existe; git push origin main"),
                        ("cd inexistente/xyz", "cd /nao/existe/xyz && git push origin main")):
        r = gate(cmd, a)
        check(f"{label}: não resolve, cai no estado de A (barrado)",
              r.returncode == 2 and "Traceback" not in r.stderr,
              f"exit={r.returncode} stderr={r.stderr[:200]}")
    a2, _b2 = new_pair(tmp, "c10")
    no_build(a2)
    r = gate("git -C && git push origin main", a2)
    print(f"    (-C pendurado) exit={r.returncode}")
    check("-C pendurado: sem Traceback", "Traceback" not in r.stderr, r.stderr[:300])
    check("-C pendurado: exit 0 ou 2", r.returncode in (0, 2), r.returncode)

# The directory resolver also needs to get -C right, with no hook in between.
sys.path.insert(0, str(HOOKS))
import _shellscan as S  # noqa: E402

print("\n# segment_dirs — resolução de cd e -C")
d = S.segment_dirs("cd /c && cd /b && git push", "/a")
check("dois cd: o último vence", d and d[0][1] == "/b" and d[0][2], d)
try:
    d = S.segment_dirs("cd 'B && git commit -m x", "/a")
    check("aspas abertas: segment_dirs não levanta", isinstance(d, list), d)
except Exception as e:  # noqa: BLE001
    check("aspas abertas: segment_dirs não levanta", False, repr(e))
d = S.segment_dirs("cd /x/y && git -C ../z push", "/a")
check("-C relativo ao último cd", d and d[0][1] == "/x/z" and d[0][2], d)
d = S.segment_dirs("git -c user.name=x -C /b push", "/a")
check("-c k=v não desalinha o -C", d and d[0][1] == "/b" and d[0][2], d)
d = S.segment_dirs("git push", "/a")
check("sem alvo explícito", d and d[0][1] == "/a" and not d[0][2], d)
d = S.segment_dirs("git commit -m 'a && cd /q'", "/a")
check("cd dentro de aspas é ignorado", d and d[0][1] == "/a", d)

print()
if FAILURES:
    print(f"{len(FAILURES)} FALHA(S): {', '.join(FAILURES)}")
    sys.exit(1)
print("todos os casos verdes")
