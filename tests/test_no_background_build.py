#!/usr/bin/env python3
"""Tests of `common/hooks/no-background-build.py`.

The hook closes the door through which 34 of the 49 minutes of the 2026-08-30 run went:
inside `cepa-until` each item is a `claude -p`, and a build sent to the
background is never harvested — the turn ends, the process dies, the item stays
`in_progress` with no outcome.

Three axes, and each is a different way for the hook to become useless:
  - the SCOPE (only inside the window) — without it the hook ruins an interactive session,
    where sending to the background is the right thing;
  - the EFFECT (the two ways of detaching) — blocking only `run_in_background`
    leaves `&` free, which is the pattern recorded in the memory
    `gate-por-nome-de-ferramenta-falha-aberto`;
  - the TARGET (build yes, server no) — blocking a server would kill the UI proof
    gate, which depends on starting the app on the side.

The two doors added on 2026-09-04, after the run that lost 6h54 of
an 8h window without going through the Bash door:
  - the WATCHER (Monitor) — a watcher that does not end by itself holds the turn until the
    item's clock kills everything; a watcher with a declared end remains allowed;
  - the STOP (Stop) — stopping with a dispatched subagent without a result, or an armed
    watcher without `TaskStop`, is the same effect through a third door.

Run with `python3 tests/test_no_background_build.py`.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "no-background-build.py"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def run_hook(command, background=False, in_window=True):
    """Calls the hook the way the harness calls it: payload on stdin, verdict in the exit."""
    import os
    env = dict(os.environ)
    if in_window:
        env["CEPA_UNTIL_RUN"] = "1"
    else:
        env.pop("CEPA_UNTIL_RUN", None)
    payload = {"tool_name": "Bash",
               "tool_input": {"command": command,
                              "run_in_background": background}}
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env)


# ── scope: only inside the window ───────────────────────────────────────────

def test_outside_window_the_hook_does_not_exist():
    """In an interactive session, `run_in_background` is the RIGHT advice — it is what
    no-busy-wait itself orders to do. The hook must not get in the way of that.
    """
    p = run_hook("./mvnw verify", background=True, in_window=False)
    check("build em segundo plano passa fora da janela", p.returncode == 0,
          f"saiu {p.returncode}: {p.stderr[:200]}")


def test_inside_window_background_build_is_blocked():
    p = run_hook("./mvnw clean verify", background=True)
    check("build com run_in_background é bloqueado", p.returncode == 2,
          f"saiu {p.returncode}")
    check("...e a recusa explica que não há turno seguinte",
          "NÃO HÁ TURNO SEGUINTE" in p.stderr, p.stderr[:300])
    check("...e diz o que fazer no lugar (primeiro plano ou desfecho nomeado)",
          "PRIMEIRO PLANO" in p.stderr and "cepa-plan finish" in p.stderr,
          p.stderr[:400])


# ── effect: the two ways of detaching ───────────────────────────────────────

def test_the_same_effect_through_the_shell_is_also_blocked():
    """Blocking only the tool name releases quietly when another mechanism appears
    for the same effect — it is the 4th time this pattern appears in the repo.
    """
    for cmd in ("./mvnw verify &",
                "nohup ./mvnw verify > /tmp/b.log 2>&1 &",
                "setsid npm test",
                "./gradlew test & disown"):
        p = run_hook(cmd)
        check(f"desanexado no shell é bloqueado: {cmd[:34]}", p.returncode == 2,
              f"saiu {p.returncode}")


def test_foreground_build_passes():
    """It is the exit the hook orders taking. If it blocked this too, there would be
    no way left to run the build and the item would never close.
    """
    for cmd in ("./mvnw clean verify",
                "./mvnw verify 2>&1 | tail -40",
                "npm test && echo ok"):
        p = run_hook(cmd)
        check(f"primeiro plano passa: {cmd[:34]}", p.returncode == 0,
              f"saiu {p.returncode}: {p.stderr[:200]}")


# ── target: build yes, server no ────────────────────────────────────────────

def test_starting_support_service_in_background_passes():
    """The UI proof gate starts the app on the side and runs the flow against it.
    Blocking that would kill the gate — and a server produces no verdict
    for anyone to harvest.
    """
    for cmd in ("./mvnw quarkus:dev", "npm run dev", "docker compose up",
                "python3 -m http.server 8080"):
        p = run_hook(cmd, background=True)
        check(f"serviço de apoio passa: {cmd[:34]}", p.returncode == 0,
              f"saiu {p.returncode}: {p.stderr[:200]}")


def test_any_command_in_background_passes():
    """The hook charges for build, not background. Blocking everything would become a second
    no-busy-wait, with another name and without the measurement that justifies it.
    """
    p = run_hook("git fetch --all", background=True)
    check("comando sem veredito de build passa", p.returncode == 0,
          f"saiu {p.returncode}: {p.stderr[:200]}")


# ── edges ───────────────────────────────────────────────────────────────────

def test_declared_escape_hatch():
    p = run_hook("./mvnw verify  # fundo-ok", background=True)
    check("`# fundo-ok` libera", p.returncode == 0,
          f"saiu {p.returncode}: {p.stderr[:200]}")


def test_quoted_text_is_not_shell():
    """WEGO-2087: a multi-line commit message read as several commands has already
    blocked a phantom write. A `&` inside quotes is text.
    """
    p = run_hook('git commit -m "roda ./mvnw verify & confere o log"')
    check("`&` dentro de aspas não é desanexação", p.returncode == 0,
          f"saiu {p.returncode}: {p.stderr[:200]}")


def test_unreadable_payload_releases_instead_of_blowing_up():
    import os
    env = dict(os.environ); env["CEPA_UNTIL_RUN"] = "1"
    p = subprocess.run([sys.executable, str(HOOK)], input="{nao json",
                       capture_output=True, text=True, env=env)
    check("payload quebrado não bloqueia nem estoura", p.returncode == 0,
          f"saiu {p.returncode}")


def test_other_tool_passes_straight_through():
    import os
    env = dict(os.environ); env["CEPA_UNTIL_RUN"] = "1"
    payload = {"tool_name": "Write", "tool_input": {"file_path": "/tmp/x"}}
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       capture_output=True, text=True, env=env)
    check("hook de Bash não opina sobre Write", p.returncode == 0,
          f"saiu {p.returncode}")


# ── door 2: the watcher (Monitor) ──────────────────────────────────────────
def run_monitor(entry, in_window=True):
    import os
    env = dict(os.environ)
    if in_window:
        env["CEPA_UNTIL_RUN"] = "1"
    else:
        env.pop("CEPA_UNTIL_RUN", None)
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Monitor",
               "tool_input": entry}
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env)


def test_watcher_without_end_is_blocked_in_window():
    cases = [
        ("while true", {"command": "while true; do git log -1; sleep 30; done",
                        "description": "branches", "timeout_ms": 3600000,
                        "persistent": False}),
        ("persistent", {"command": "gh pr checks 1 && break", "persistent": True}),
        ("tail -f", {"command": "tail -f app.log | grep --line-buffered ERROR"}),
        ("websocket", {"ws": {"url": "wss://x/y"}, "description": "eventos"}),
    ]
    for name, entry in cases:
        p = run_monitor(entry)
        check(f"vigia sem fim bloqueado: {name}", p.returncode == 2,
              f"saiu {p.returncode}")


def test_watcher_with_declared_end_passes():
    entry = {"command": "for i in 1 2 3; do gh run view --json status; done",
               "description": "CI", "timeout_ms": 60000, "persistent": False}
    p = run_monitor(entry)
    check("vigia que termina sozinho passa", p.returncode == 0,
          f"saiu {p.returncode}: {p.stderr[:120]}")


def test_watcher_outside_window_passes():
    entry = {"command": "while true; do sleep 5; done", "persistent": True}
    p = run_monitor(entry, in_window=False)
    check("vigia sem fim passa fora da janela", p.returncode == 0,
          f"saiu {p.returncode}")


def test_watcher_with_declared_escape_passes():
    entry = {"command": "while true; do sleep 5; done  # fundo-ok"}
    p = run_monitor(entry)
    check("escape `# fundo-ok` libera o vigia", p.returncode == 0,
          f"saiu {p.returncode}")


# ── door 3: the stop (Stop) ────────────────────────────────────────────────
def _transcript(tmp, blocks_per_line):
    """Writes a transcript in the format the harness records."""
    path = tmp / "t.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for blocks in blocks_per_line:
            f.write(json.dumps({"type": "assistant",
                                "message": {"content": blocks}}) + "\n")
    return path


def run_stop(path, in_window=True, stop_hook_active=False):
    import os
    env = dict(os.environ)
    if in_window:
        env["CEPA_UNTIL_RUN"] = "1"
    else:
        env.pop("CEPA_UNTIL_RUN", None)
    payload = {"hook_event_name": "Stop", "transcript_path": str(path),
               "stop_hook_active": stop_hook_active}
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       capture_output=True, text=True, env=env)
    try:
        output = json.loads(p.stdout) if p.stdout.strip() else {}
    except json.JSONDecodeError:
        output = {}
    return p, output


DISPATCH = [{"type": "tool_use", "id": "tu_1", "name": "Agent",
             "input": {"description": "Build WEGO-2224"}}]
RESULT = [{"type": "tool_result", "tool_use_id": "tu_1",
              "content": "pronto, Tasks mescladas"}]
CALLS_WATCHER = [{"type": "tool_use", "id": "tu_2", "name": "Monitor",
                "input": {"command": "...", "description": "vigia do build"}}]
ARMS_WATCHER = [{"type": "tool_result", "tool_use_id": "tu_2",
               "content": "Monitor started (task bqwpma178, timeout 3600000ms)."}]
STOPS_WATCHER = [{"type": "tool_result", "tool_use_id": "tu_3",
               "content": "{\"message\":\"Successfully stopped task: bqwpma178 (...)\"}"}]


def test_stop_with_pending_subagent_is_blocked():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        c = _transcript(Path(d), [DISPATCH])
        p, output = run_stop(c)
        check("parada com subagente sem resultado é bloqueada",
              output.get("decision") == "block" and p.returncode == 0,
              f"saiu {p.returncode}: {p.stdout[:120]}")
        check("o bloqueio nomeia o subagente pendente",
              "Build WEGO-2224" in (output.get("reason") or ""),
              (output.get("reason") or "")[:120])


def test_stop_with_armed_watcher_is_blocked():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        c = _transcript(Path(d), [CALLS_WATCHER, ARMS_WATCHER])
        _, output = run_stop(c)
        check("parada com vigia armado é bloqueada",
              output.get("decision") == "block",
              json.dumps(output)[:160])


def test_monitor_started_text_in_another_tools_output_does_not_arm_watcher():
    import tempfile
    grep_use = [{"type": "tool_use", "id": "tu_grep", "name": "Bash",
                 "input": {"command":
                           "grep -h 'Monitor started' ~/.claude/projects/*/*.jsonl"}}]
    grep_result = [{"type": "tool_result", "tool_use_id": "tu_grep",
                     "content": "Monitor started (task b1pa0ro5t, timeout 3600000ms)."}]
    with tempfile.TemporaryDirectory() as d:
        c = _transcript(Path(d), [grep_use, grep_result])
        p, output = run_stop(c)
        check("texto 'Monitor started' na saída de um Bash não arma vigia",
              not output and p.returncode == 0,
              f"saiu {p.returncode}: {p.stdout[:160]}")
    orphan = [{"type": "tool_result", "tool_use_id": "tu_sem_tool_use",
              "content": "Monitor started (task b1pa0ro5t, timeout 3600000ms)."}]
    with tempfile.TemporaryDirectory() as d:
        c = _transcript(Path(d), [orphan])
        p, output = run_stop(c)
        check("tool_result sem tool_use Monitor correspondente não arma vigia",
              not output and p.returncode == 0,
              f"saiu {p.returncode}: {p.stdout[:160]}")
    monitor_without_id = [{"type": "tool_use", "name": "Monitor",
                        "input": {"command": "..."}}]
    result_without_id = [{"type": "tool_result",
                          "content": "Monitor started (task b1pa0ro5t, timeout 3600000ms)."}]
    with tempfile.TemporaryDirectory() as d:
        c = _transcript(Path(d), [monitor_without_id, result_without_id])
        p, output = run_stop(c)
        check("Monitor sem id e tool_result sem tool_use_id não colidem em None",
              not output and p.returncode == 0,
              f"saiu {p.returncode}: {p.stdout[:160]}")


def test_clean_stop_passes():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        c = _transcript(Path(d), [DISPATCH, RESULT, CALLS_WATCHER, ARMS_WATCHER, STOPS_WATCHER])
        p, output = run_stop(c)
        check("subagente colhido e vigia parado: a parada passa",
              not output and p.returncode == 0,
              f"saiu {p.returncode}: {p.stdout[:160]}")


# A watcher that ends BY ITSELF: without `TaskStop`, the end arrives as a notice from the
# harness. Formats copied from the transcripts of run 2026-09-26-2203.
def _notice(body):
    return f"<task-notification>\n{body}\n</task-notification>"


END_OF_SOURCE = {"type": "queue-operation", "operation": "enqueue",
                "content": _notice(
                    "<task-id>bqwpma178</task-id>\n<status>completed</status>\n"
                    "<summary>Monitor \"commit\" stream ended</summary>")}
EXPIRED = {"type": "attachment", "attachment": {
    "type": "queued_command", "prompt": _notice(
        "<task-id>bqwpma178</task-id>\n<summary>Monitor event</summary>\n"
        "<event>[Monitor expired after 10m with no events delivered.]</event>")}}
TIMED_OUT = {"type": "user", "message": {"role": "user", "content": _notice(
    "<task-id>bqwpma178</task-id>\n<event>[Monitor timed out — re-arm if "
    "needed.]</event>")}}
FAILED, DEAD = ({"type": "queue-operation", "operation": "enqueue",
                  "content": _notice(f"<task-id>bqwpma178</task-id>\n"
                                    f"<status>{st}</status>")}
                 for st in ("failed", "killed"))
STILL_RUNNING = {"type": "queue-operation", "operation": "enqueue",
                 "content": _notice("<task-id>bqwpma178</task-id>\n"
                                   "<status>running</status>")}
LATE_TASKSTOP = [{"type": "tool_result", "tool_use_id": "tu_4",
                    "content": "<tool_use_error>No task found with ID: "
                               "bqwpma178</tool_use_error>"}]


def _mixed_transcript(tmp, lines):
    path = tmp / "t.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for l in lines:
            if isinstance(l, list):
                l = {"type": "assistant", "message": {"content": l}}
            f.write(json.dumps(l, ensure_ascii=False) + "\n")
    return path


def test_watcher_that_ends_by_itself_does_not_block_the_stop():
    import tempfile
    for name, end in (("fonte acabou (status completed)", END_OF_SOURCE),
                      ("expirou aos 10 min", EXPIRED),
                      ("timed out", TIMED_OUT),
                      ("status failed", FAILED),
                      ("status killed", DEAD),
                      ("TaskStop respondeu que a tarefa não existe",
                       LATE_TASKSTOP)):
        with tempfile.TemporaryDirectory() as d:
            c = _mixed_transcript(Path(d), [CALLS_WATCHER, ARMS_WATCHER, end])
            p, output = run_stop(c)
            check(f"vigia encerrado sozinho ({name}): a parada passa",
                  not output and p.returncode == 0,
                  f"saiu {p.returncode}: {p.stdout[:160]}")


def test_non_terminal_or_quoted_notice_does_not_release_the_watcher():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        c = _mixed_transcript(Path(d), [CALLS_WATCHER, ARMS_WATCHER, STILL_RUNNING])
        _, output = run_stop(c)
        check("aviso com status running não encerra o vigia",
              output.get("decision") == "block", json.dumps(output)[:160])
    with tempfile.TemporaryDirectory() as d:
        quoted = [{"type": "text", "text": END_OF_SOURCE["content"]}]
        c = _mixed_transcript(Path(d), [CALLS_WATCHER, ARMS_WATCHER, quoted])
        _, output = run_stop(c)
        check("o agente citar o aviso não encerra o vigia",
              output.get("decision") == "block", json.dumps(output)[:160])
    with tempfile.TemporaryDirectory() as d:
        other = {"type": "queue-operation", "content": _notice(
            "<task-id>outra123</task-id>\n<status>completed</status>")}
        c = _mixed_transcript(Path(d), [CALLS_WATCHER, ARMS_WATCHER, other])
        _, output = run_stop(c)
        check("fim de OUTRA tarefa não encerra este vigia",
              output.get("decision") == "block", json.dumps(output)[:160])


def test_stop_outside_window_passes():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        c = _transcript(Path(d), [DISPATCH, CALLS_WATCHER, ARMS_WATCHER])
        _, output = run_stop(c, in_window=False)
        check("fora da janela a parada nunca é bloqueada", not output,
              json.dumps(output)[:160])


def test_stop_does_not_block_twice_in_a_row():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        c = _transcript(Path(d), [DISPATCH])
        _, output = run_stop(c, stop_hook_active=True)
        check("trava anti-loop: bloqueio já ativo não bloqueia de novo",
              not output, json.dumps(output)[:160])


def test_missing_transcript_does_not_blow_up():
    p, output = run_stop(Path("/nao/existe/t.jsonl"))
    check("transcript ausente libera em vez de estourar",
          p.returncode == 0 and not output, f"saiu {p.returncode}")


# ── long build with declared end (item until-build-longo-sem-trava) ─────────
# Measured on 2026-09-27: `claude -p` kills the background at the end of the turn and
# `Monitor` does not hold the turn. A build of more than 10 min can only be harvested by writing
# `EXIT=` to a file and waiting for that file in the foreground.

LONG = "./mvnw -B clean verify > /tmp/b.log 2>&1; echo EXIT=$? >> {fim}"


def test_long_build_with_declared_end_passes_in_window():
    p = run_hook(LONG.format(fim="/tmp/b.fim"), background=True)
    check("build em segundo plano que grava EXIT= num arquivo passa",
          p.returncode == 0, f"saiu {p.returncode}: {p.stderr[:200]}")
    p = run_hook(LONG.format(fim="/tmp/b.fim") + " &")
    check("...também desanexado no shell", p.returncode == 0,
          f"saiu {p.returncode}: {p.stderr[:200]}")


def test_long_build_without_declared_end_stays_blocked_and_teaches_the_recipe():
    p = run_hook("./mvnw -B clean verify > /tmp/b.log 2>&1", background=True)
    check("sem EXIT= num arquivo, o segundo plano segue bloqueado",
          p.returncode == 2, f"saiu {p.returncode}")
    check("...e a recusa ensina gravar EXIT= e esperar em primeiro plano",
          "echo EXIT=$? >>" in p.stderr and "# espera-ok" in p.stderr
          and "Monitor` NÃO serve" in p.stderr, p.stderr[-600:])
    check("...com um laço que sai antes dos 10 min (27 x 20s = 9 min)",
          "seq 27" in p.stderr and "timeout 590000" in p.stderr,
          p.stderr[-600:])


def _launch_long(end):
    return [{"type": "tool_use", "id": "tu_9", "name": "Bash",
             "input": {"command": LONG.format(fim=end),
                       "description": "verify da noite",
                       "run_in_background": True}}]


def test_stop_before_the_long_build_exit_is_blocked():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        end = Path(d) / "b.fim"
        c = _transcript(Path(d), [_launch_long(end)])
        p, output = run_stop(c)
        check("parar com o build longo sem EXIT= é bloqueado",
              output.get("decision") == "block", str(output)[:300])
        check("...e o motivo nomeia o arquivo e a espera em primeiro plano",
              str(end) in output.get("reason", "")
              and "PRIMEIRO PLANO" in output.get("reason", "")
              and "seq 27" in output.get("reason", ""),
              output.get("reason", "")[:400])
        end.write_text("EXIT=0\n")
        p, output = run_stop(c)
        check("com EXIT= gravado, a parada passa", output == {}, str(output)[:300])


def test_stop_after_the_exit_in_subshell_passes():
    """Run of 09/27 (e2e F): the agent wrote `(<build>; echo EXIT=$? >>
    /tmp/b.fim) &`, and the `)` stuck to the file name. The hook looked for
    `/tmp/b.fim)`, did not find it, and blocked the stop with the build already harvested.
    """
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        end = Path(d) / "b.fim"
        end.write_text("EXIT=0\n")
        cmd = f"(make verify > /tmp/b.log 2>&1; echo EXIT=$? >> {end}) & disown"
        c = _transcript(Path(d), [[{"type": "tool_use", "id": "tu_8",
                                    "name": "Bash",
                                    "input": {"command": cmd}}]])
        p, output = run_stop(c)
        check("build em subshell com EXIT= gravado não barra a parada",
              output == {}, str(output)[:300])


def test_stop_with_long_build_outside_window_passes():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        c = _transcript(Path(d), [_launch_long(Path(d) / "b.fim")])
        p, output = run_stop(c, in_window=False)
        check("fora da janela a parada não olha build nenhum", output == {},
              str(output)[:300])


def main():
    print("no-background-build — build em segundo plano dentro do cepa-until\n")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"{name}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
