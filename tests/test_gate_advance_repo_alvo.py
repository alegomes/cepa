#!/usr/bin/env python3
"""Contract tests: gate-advance avalia a baseline do repo que RECEBE o commit/push.

Sem dependência de terceiros — rode com
`python3 tests/test_gate_advance_repo_alvo.py`.

O defeito, reproduzido em 2026-10-10: uma sessão aberta no repo A
(`~/coding/al2.digital/kodez.cool`, com `.claude/last-build.json` STALE) rodou
`cd ~/coding/cepa && git commit ...`. O hook ancorava o estado na raiz do repo
da SESSÃO (A) e barrou um commit que pertencia ao repo B. O mesmo vale para
`git -C <outro repo> commit/push`. O contrário também é um furo: o opt-out
`.claude/no-build` da sessão não pode vazar para um push num repo B vermelho.

A regra: o alvo é o diretório do ÚLTIMO `cd` antes do segmento `git` (relativo
ao cwd do payload, `~` expandido) ou o argumento de `git -C`; sua raiz de repo
(`_wtlib.session_root`) decide `no-build`, `last-build.json` e o manifesto de
build. Sem alvo explícito, vale o cwd do payload, como sempre.
"""

import json
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


def run_hook(script, payload):
    return subprocess.run(
        [sys.executable, str(HOOKS / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
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


def vermelho(repo):
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude" / "last-build.json").write_text(json.dumps({
        "status": "FAILURE", "at": "2026-10-10T10:00:00+00:00",
        "command": "./mvnw verify", "kind": "maven",
    }), encoding="utf-8")


def sem_build(repo):
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude" / "no-build").write_text("", encoding="utf-8")


def gate(command, cwd):
    return run_hook("gate-advance.py", {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(cwd),
    })


def novo_par(tmp, nome):
    a = make_repo(tmp / nome / "A")
    b = make_repo(tmp / nome / "B")
    return a, b


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp).resolve()

    print("\n# cd B && git commit — A vermelho, B com no-build")
    a, b = novo_par(tmp, "c1")
    vermelho(a)
    sem_build(b)
    r = gate(f"cd {b} && git commit -m x", a)
    check("commit em B liberado", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:200]}")

    print("\n# git -C B push — A vermelho, B com no-build")
    a, b = novo_par(tmp, "c2")
    vermelho(a)
    sem_build(b)
    r = gate(f"git -C {b} push origin main", a)
    check("push -C B liberado", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:200]}")

    print("\n# o no-build da sessão não vaza para B vermelho")
    a, b = novo_par(tmp, "c3")
    sem_build(a)
    vermelho(b)
    r = gate(f"cd {b} && git push origin main", a)
    check("push em B vermelho BARRADO", r.returncode == 2,
          f"exit={r.returncode} stderr={r.stderr[:200]}")

    print("\n# sem cd / sem -C — comportamento de hoje")
    a, b = novo_par(tmp, "c4")
    vermelho(a)
    r = gate("git push origin main", a)
    check("push no repo da sessão vermelho BARRADO", r.returncode == 2,
          f"exit={r.returncode} stderr={r.stderr[:200]}")

    print("\n# cd para subdiretório de B")
    a, b = novo_par(tmp, "c5")
    vermelho(a)
    sem_build(b)
    (b / "sub").mkdir()
    r = gate(f"cd {b}/sub && git commit -m x", a)
    check("ancora na raiz de B", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:200]}")

    print("\n# cd relativo")
    a, b = novo_par(tmp, "c6")
    vermelho(a)
    sem_build(b)
    r = gate("cd ../B && git commit -m x", a)
    check("cd ../B resolvido contra o cwd", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:200]}")

    print("\n# extras")
    a, b = novo_par(tmp, "c7")
    vermelho(a)
    sem_build(b)
    r = gate("cd ../B; git push origin main", a)
    check("separador `;` também", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:200]}")
    r = gate("git -C ../B commit -m x", a)
    check("-C relativo resolvido contra o cwd", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:200]}")

    print("\n# git -C — o portão precisa enxergar a forma e julgar o repo alvo")
    a, b = novo_par(tmp, "c8")
    sem_build(a)
    vermelho(b)
    r = gate(f"git -C {b} push origin main", a)
    check("git -C B push (B vermelho, A no-build) BARRADO", r.returncode == 2,
          f"exit={r.returncode} stderr={r.stderr[:200]}")
    r = gate(f"git -C{b} push origin main", a)
    check("git -C<B> colado BARRADO", r.returncode == 2,
          f"exit={r.returncode} stderr={r.stderr[:200]}")
    r = gate(f"git -C {b} status", a)
    check("git -C B status segue isento", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:200]}")

# O resolvedor de diretório também precisa acertar o -C, sem hook no meio.
sys.path.insert(0, str(HOOKS))
import _shellscan as S  # noqa: E402

print("\n# segment_dirs — resolução de cd e -C")
d = S.segment_dirs("cd /x/y && git -C ../z push", "/a")
check("-C relativo ao último cd", d and d[0][1] == "/x/z" and d[0][2], d)
d = S.segment_dirs("git push", "/a")
check("sem alvo explícito", d and d[0][1] == "/a" and not d[0][2], d)
d = S.segment_dirs("git commit -m 'a && cd /q'", "/a")
check("cd dentro de aspas é ignorado", d and d[0][1] == "/a", d)

print()
if FAILURES:
    print(f"{len(FAILURES)} FALHA(S): {', '.join(FAILURES)}")
    sys.exit(1)
print("todos os casos verdes")
