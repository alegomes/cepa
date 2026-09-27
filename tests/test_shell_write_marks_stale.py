#!/usr/bin/env python3
"""Edição por shell suja a baseline de build tanto quanto edição por Edit/Write.

Sem dependências — rode com `python3 tests/test_shell_write_marks_stale.py`.

O defeito (BACKLOG, "Modo automático edita por `sed` e três hooks só escutam
`Edit|Write`", 2026-08-25): o modo automático manda preferir `sed`, heredoc e
script curto a `Edit`/`Write`, e o `mark-build-stale.py` só era registrado em
`Edit|Write|MultiEdit`. O código mudava, a `.claude/last-build.json` seguia
SUCCESS, e o `gate-advance` liberava um verde que descrevia código que já não
existia. O `session-activity.py` tinha a mesma porta: a sessão que editava por
`sed` parecia parada.

O teste cobre as duas metades do conserto, porque qualquer uma sozinha é um
hook que nunca dispara:

- o hook entende o payload de Bash (`sed -i`, heredoc para arquivo), e só suja
  quando o alvo é código de produção DENTRO da árvore da sessão;
- o `plugin.json` registra os dois hooks no `PostToolUse` de `Bash`.
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
STALE = HOOKS / "mark-build-stale.py"
ACTIVITY = HOOKS / "session-activity.py"
PLUGIN = REPO / "common" / ".claude-plugin" / "plugin.json"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def run_hook(script, payload):
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload), capture_output=True, text=True,
    )


def bash(cwd, command, session_id="s-sed"):
    return {"tool_name": "Bash", "tool_input": {"command": command},
            "tool_response": {"stdout": ""}, "cwd": str(cwd),
            "session_id": session_id}


def green(root):
    (root / ".claude").mkdir(exist_ok=True)
    (root / ".claude" / "last-build.json").write_text(json.dumps(
        {"status": "SUCCESS", "at": "2026-09-27T00:00:00+00:00",
         "command": "./mvnw verify"}))


def state(root):
    return json.loads((root / ".claude" / "last-build.json").read_text())


print("\n# plugin.json — os dois hooks escutam Bash no PostToolUse")
grupos = json.loads(PLUGIN.read_text())["hooks"]["PostToolUse"]
bash_cmds = " ".join(h["command"] for g in grupos if g["matcher"] == "Bash"
                     for h in g["hooks"])
check("mark-build-stale registrado em Bash", "mark-build-stale.py" in bash_cmds, bash_cmds)
check("session-activity registrado em Bash", "session-activity.py" in bash_cmds, bash_cmds)

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp).resolve()
    repo = tmp / "repo"
    outra = tmp / "proof-wt"
    for d in (repo, outra):
        (d / "src" / "main").mkdir(parents=True)
        (d / "docs").mkdir()
        subprocess.run(["git", "init", "-q", str(d)], check=True)
    (repo / "src" / "main" / "X.java").write_text("class X {}\n")

    print("\n# mark-build-stale.py — escrita por shell")
    green(repo)
    r = run_hook(STALE, bash(repo, "sed -i '' 's/X/Z/' src/main/X.java"))
    check("sed -i em código de produção: STALE",
          r.returncode == 0 and state(repo)["status"] == "STALE", f"{state(repo)} {r.stderr}")
    check("sed -i: registra o arquivo editado",
          state(repo).get("after_edit_to") == "src/main/X.java", str(state(repo)))
    check("sed -i: guarda o último verde real",
          state(repo).get("last_known_status") == "SUCCESS", str(state(repo)))

    green(repo)
    r = run_hook(STALE, bash(repo, "cat > src/main/Y.java <<'EOF'\nclass Y {}\nEOF"))
    check("heredoc para arquivo de produção: STALE",
          state(repo)["status"] == "STALE" and state(repo).get("after_edit_to") == "src/main/Y.java",
          f"{state(repo)} {r.stderr}")

    green(repo)
    run_hook(STALE, bash(repo, f"cd {outra} && sed -i '' 's/a/b/' src/main/X.java"))
    check("sed -i depois de `cd` para fora da árvore: baseline intacta",
          state(repo)["status"] == "SUCCESS", str(state(repo)))

    green(repo)
    run_hook(STALE, bash(repo, "sed -i '' 's/a/b/' docs/guia.md && grep -rn X src"))
    check("sed -i em doc e leitura de código: baseline intacta",
          state(repo)["status"] == "SUCCESS", str(state(repo)))

    for teste in ("tests/test_x.py", "specs/x.py"):
        green(repo)
        run_hook(STALE, {"tool_name": "Edit", "cwd": str(repo),
                         "tool_input": {"file_path": str(repo / teste)}})
        run_hook(STALE, bash(repo, f"sed -i '' 's/a/b/' {teste}"))
        check(f"{teste} na raiz da árvore não é código de produção",
              state(repo)["status"] == "SUCCESS", str(state(repo)))

    green(repo)
    run_hook(STALE, bash(repo, "git commit -m 'sed -i conserta src/main/X.java > nada'"))
    check("prosa citada numa mensagem de commit: baseline intacta",
          state(repo)["status"] == "SUCCESS", str(state(repo)))

    green(repo)
    run_hook(STALE, {"tool_name": "Edit", "cwd": str(repo),
                     "tool_input": {"file_path": str(repo / "src" / "main" / "X.java")}})
    check("Edit continua sujando (comportamento de antes)",
          state(repo)["status"] == "STALE" and state(repo).get("after_edit_to") == "src/main/X.java",
          str(state(repo)))

    print("\n# session-activity.py — a sessão que edita por shell não parece parada")
    sessions = repo / ".claude" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / "s-sed.json").write_text(json.dumps({"session_id": "s-sed"}))
    run_hook(ACTIVITY, bash(repo, "sed -i '' 's/X/W/' src/main/X.java"))
    entry = json.loads((sessions / "s-sed.json").read_text())
    check("sed -i conta o diretório tocado",
          entry.get("touched_dirs", {}).get("src") == 1, str(entry))

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {FAILURES}")
    sys.exit(1)
print("all shell-write-marks-stale tests passed")
