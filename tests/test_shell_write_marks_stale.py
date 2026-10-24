#!/usr/bin/env python3
"""A shell edit dirties the build baseline as much as an Edit/Write edit does.

No dependencies — run with `python3 tests/test_shell_write_marks_stale.py`.

The defect (BACKLOG, "Automatic mode edits by `sed` and three hooks only listen to
`Edit|Write`", 2026-08-25): automatic mode orders preferring `sed`, heredoc and
a short script to `Edit`/`Write`, and `mark-build-stale.py` was only registered in
`Edit|Write|MultiEdit`. The code changed, `.claude/last-build.json` stayed
SUCCESS, and `gate-advance` released a green that described code that no longer
existed. `session-activity.py` had the same door: a session that edited through
`sed` looked idle.

The test covers both halves of the fix, because either one alone is a
hook that never fires:

- the hook understands the Bash payload (`sed -i`, heredoc to a file), and only dirties
  when the target is production code INSIDE the session's tree;
- `plugin.json` registers both hooks in the `PostToolUse` of `Bash`.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from _isolated_telemetry import isolate

isolate()

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
groups = json.loads(PLUGIN.read_text())["hooks"]["PostToolUse"]
bash_cmds = " ".join(h["command"] for g in groups if g["matcher"] == "Bash"
                     for h in g["hooks"])
check("mark-build-stale registrado em Bash", "mark-build-stale.py" in bash_cmds, bash_cmds)
check("session-activity registrado em Bash", "session-activity.py" in bash_cmds, bash_cmds)

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp).resolve()
    repo = tmp / "repo"
    other = tmp / "proof-wt"
    for d in (repo, other):
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
    run_hook(STALE, bash(repo, f"cd {other} && sed -i '' 's/a/b/' src/main/X.java"))
    check("sed -i depois de `cd` para fora da árvore: baseline intacta",
          state(repo)["status"] == "SUCCESS", str(state(repo)))

    green(repo)
    run_hook(STALE, bash(repo, "sed -i '' 's/a/b/' docs/guia.md && grep -rn X src"))
    check("sed -i em doc e leitura de código: baseline intacta",
          state(repo)["status"] == "SUCCESS", str(state(repo)))

    for test_file in ("tests/test_x.py", "specs/x.py"):
        green(repo)
        run_hook(STALE, {"tool_name": "Edit", "cwd": str(repo),
                         "tool_input": {"file_path": str(repo / test_file)}})
        run_hook(STALE, bash(repo, f"sed -i '' 's/a/b/' {test_file}"))
        check(f"{test_file} na raiz da árvore não é código de produção",
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
