#!/usr/bin/env python3
"""PreToolUse hook (common) -- inside `cepa-until`, sending a build to the
background means losing the item. It blocks.

WHY THIS EXISTS
---------------
`cepa-until` runs each queue item as a separate `claude -p`. In that mode
**there is no next turn**: the process dies when the turn ends. A build started
in the background is never collected -- it becomes an orphan process, the item
stays `in_progress` with no outcome, and the next window finds it as an orphan
reservation and starts over from zero.

Measured in the 2026-08-30 run (`WEGO`, 2h window):

| attempt | item      | spent  | exit | how it ended                                  |
|---------|-----------|--------|------|-----------------------------------------------|
| 1       | WEGO-2206 | 10m50s |    0 | "I await the notification of `clean verify`"  |
| 3       | WEGO-1941 | 23m46s |    0 | "it is compiling in the background... when    |
|         |           |        |      |  it turns green: push, `finish`, transition"  |

34 of the window's 49 minutes, and the only TWO failures that were not the
account's usage ceiling. Both exited 0: from the outside that is
indistinguishable from work done.

And the agent was not being creative -- it was following house advice.
`no-busy-wait` blocks waiting, and its output suggests `run_in_background` as
the alternative. That holds in an interactive session, where the completion
notification RE-INVOKES the session. Under `claude -p` it does not hold, and
that is exactly where `cepa-until` runs. This hook closes that door only where
it is a trap.

SCOPE -- fires only with `CEPA_UNTIL_RUN` in the environment, which
`cepa-until` exports to every subprocess. Outside it the hook does not exist:
in an interactive session sending the build to the background is the right
thing.

It blocks a BUILD/TEST command that goes to the background, by both routes:
  1. `run_in_background: true` on the Bash call itself;
  2. detaching in the shell (trailing `&`, `nohup`, `disown`, `setsid`), outside
     quotes -- because blocking only the tool name makes the next mechanism for
     the same effect appear (memory `gate-por-nome-de-ferramenta-falha-
     aberto`, "a gate keyed on a tool name fails open").

It does NOT block starting a server/service in the background (`quarkus:dev`,
`npm run dev`, `serve`, `docker compose up`): those are support processes that
MUST stay on the side, and the UI proof gate depends on them. What this hook
charges is the command that produces a VERDICT somebody has to collect.

THE OTHER TWO DOORS FOR THE SAME EFFECT (2026-09-04)
----------------------------------------------------
The 2026-09-03 run lost 6h54 of an 8h window without going through either of
them: item WEGO-2224 armed a `Monitor` with `while true` (a watcher that
observes branches and NEVER ends on its own) and ended the turn writing
"I wait", with subagents still running. `claude -p` waited for the background,
hit the 600s ceiling and killed itself -- exit 0, item half done, main clone
parked on an integration branch. `cepa-until`'s branch check read that as a
branch switch and ended the whole window.

Blocking only `Bash` was blocking by MECHANISM. The effect is `the turn ends
with background work nobody will collect`, and it has three doors:

  Bash      -- detached build (the original door, above);
  Monitor   -- endless watcher: `persistent: true`, `ws:`, or a command that
               does not return (`while true`, `tail -f`, `inotifywait -m`).
               Inside the window it only holds the turn until the item clock
               kills everything. A watcher with a declared end stays allowed:
               it finishes and is collected;
  Stop      -- the stop itself. If a dispatched subagent has no result in the
               transcript, or an armed watcher received neither `TaskStop` nor
               ended on its own (end `<task-notification>` notice), the stop is
               blocked once with the list of what is left to collect.

The pairing with `cepa-until`: the supervisor now exports
`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0` so the item waits for the background
instead of dying at 10 minutes. That is only safe because these two new doors
block background work that never ends -- without them, waiting with no ceiling
would trade a 10 min cut for the limit of the whole item.

BUILD OF MORE THAN 10 MIN (2026-09-27)
--------------------------------------
Blocking every background build left the build of more than 10 min with no way
out: Bash pushes it to the background at 10 min anyway, and in the WEGO run of
09-25 WEGO-2334 hung with `EXIT=124` and became an owner task. Measured on
09-27 (claude 2.1.283): the wait that the paragraph above attributes to
`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0` does not happen. `claude -p` exits at
the end of the turn and kills the background with the ceiling at 0, absent or
120000, and an armed `Monitor` does not hold the turn (the agent stopped saying
"the notification will re-invoke me", and nothing was collected).

So the background is allowed when the command DECLARES THE END
(`...; echo EXIT=$? >> <file>`), and the wait is in the foreground, in the same
turn, in a loop that exits on its own before 10 min (`for i in $(seq 27); do
grep -q EXIT= <file> && break; sleep 20; done # espera-ok`), repeated until
`EXIT=`. A full 10 min wait is pushed to the background like the build itself:
in the 09-27 experiment that is what made the agent stop "awaiting the
notification", and only door 3 held it. Door 3 blocks stopping while that file
has no `EXIT=`. With no declared end, the block stays as before.

ESCAPE HATCH: `# fundo-ok` in the command (Bash and Monitor).

Exit codes:
  0 -- allowed (and, on Stop, the block travels in the stdout JSON)
  2 -- blocked: background work inside a cepa-until window
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import _telemetry as T
except Exception:  # telemetry must never break the gate

    class T:  # type: ignore
        @staticmethod
        def emit(*a, **k):
            pass


try:
    import _shellscan as S

    _unquoted_view = S._unquoted_view
except Exception:  # without the shared engine, analyze the raw line

    def _unquoted_view(c):
        return c


_ESCAPE = "fundo-ok"
ENV_WINDOW = "CEPA_UNTIL_RUN"

# Commands that produce a VERDICT -- somebody has to read the result, and that
# somebody is exactly who does not exist in the next turn.
_BUILD = re.compile(
    r"\b(?:\./)?mvnw?\b(?!.*\b(?:quarkus:dev|spring-boot:run)\b)"
    r"|\bgradlew?\b(?!.*\bbootRun\b)"
    r"|\bnpm\s+(?:run\s+)?(?:test|build|ci)\b"
    r"|\b(?:pnpm|yarn)\s+(?:run\s+)?(?:test|build)\b"
    r"|\bpytest\b|\bpython3?\s+-m\s+pytest\b"
    r"|\bcargo\s+(?:test|build)\b"
    r"|\bgo\s+(?:test|build)\b"
    r"|\bmake\s+(?:test|check|build|verify)\b"
    r"|\bctest\b|\btox\b",
    re.I)

# Detaching written in the shell. `&` only counts when it is not `&&` nor `2>&1`.
_DETACH = re.compile(r"\bnohup\b|\bdisown\b|\bsetsid\b|(?<![&>])&\s*(?:$|[;\n])")


def detached_via(command: str, background: bool):
    """(via, snippet) of how the command goes to the background, or None."""
    if background:
        return ("run_in_background", command.strip()[:90])
    v = _unquoted_view(command)
    m = _DETACH.search(v)
    if m:
        return ("desanexado no shell", v[max(0, m.start() - 60):m.end()].strip())
    return None


def blocks(command: str, background: bool, environ=None):
    """The full decision: (via, snippet) or None.

    The environment comes in as a parameter so the test can exercise both
    halves -- inside and outside the window -- without touching its own process.
    """
    env = os.environ if environ is None else environ
    if not env.get(ENV_WINDOW):
        return None
    if not command or _ESCAPE in command:
        return None
    if not _BUILD.search(_unquoted_view(command)):
        return None
    if end_marker(command):
        # Build with a declared end: the turn collects by waiting for the file
        # in the foreground, and door 3 (Stop) blocks stopping before `EXIT=`.
        return None
    return detached_via(command, background)


# A build that runs past 10 min does not fit in the foreground: Bash pushes it
# to the background at 10 min anyway. The collectable way is for the command
# to write its own end to a file (`...; echo EXIT=$? >> /tmp/x.fim`) and for
# the turn to wait for that file in the foreground. Measured on 2026-09-27
# (claude 2.1.283): `claude -p` does NOT wait for a background task at the end
# of the turn, with `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` at 0, absent or
# 120000 (it exited in 15s and killed the build in all three), and an armed
# `Monitor` does not hold the turn.
_END_MARKER = re.compile(
    r"""EXIT=\$\?["']?\s*>{1,2}\s*["']?([^\s;&|"'()`<>]+)""")


def end_marker(command: str):
    """The file where the command writes `EXIT=<code>` when it finishes, or None."""
    m = _END_MARKER.search(command or "")
    return m.group(1) if m else None


# ── door 2: the watcher that does not end (Monitor) ──────────────────────────────
# A `Monitor` is only collectable inside the window if it ENDS. These are the
# ways to write one that does not end -- the first is the 2026-09-03 run's.
_ENDLESS_WATCHER = re.compile(
    r"\bwhile\s+(?:true|:)\b"
    r"|\buntil\s+false\b"
    r"|\bfor\s*\(\s*;\s*;\s*\)"
    r"|\btail\s+-[A-Za-z]*f\b"
    r"|\binotifywait\b[^;|]*\s-m\b",
    re.I)


def watcher_blocks(tool_input, environ=None):
    """(via, snippet) if this Monitor does not end on its own inside the window."""
    env = os.environ if environ is None else environ
    if not env.get(ENV_WINDOW):
        return None
    tool_input = tool_input or {}
    command = tool_input.get("command") or ""
    label = (tool_input.get("description") or command).strip()[:90]
    if _ESCAPE in command:
        return None
    if tool_input.get("persistent"):
        return ("persistent: true", label)
    if tool_input.get("ws"):
        # The socket only closes when the other side closes: from here there is no end.
        return ("ws (o socket não fecha sozinho)", label)
    m = _ENDLESS_WATCHER.search(_unquoted_view(command))
    if m:
        return ("comando sem fim", command[max(0, m.start() - 40):m.end() + 20].strip())
    return None


# ── door 3: the stop with pending work (Stop) ──────────────────────────
_WATCHER_ARMED = re.compile(r"Monitor started \(task ([A-Za-z0-9_-]{4,})")
_WATCHER_STOPPED = re.compile(
    r"[Ss]topped task:? ([A-Za-z0-9_-]{4,})"
    r"|No task found with ID:? ([A-Za-z0-9_-]{4,})")
_DISPATCH = ("Agent", "Task")

# A watcher that ends ON ITS OWN does not go through `TaskStop`: the harness
# writes a `<task-notification>` with a terminal `<status>` (source finished)
# or with the expiry event. Without reading that, the hook treated the watcher
# as armed forever and blocked the legitimate stop -- in the 2026-09-27 run
# (item until-build-longo-sem-trava) the final report became a reply to the
# block. Formats checked in the 2026-09 transcripts: `completed`/`failed`/
# `killed` and "Monitor expired after 10m ..." / "Monitor timed out".
# `running` does not close.
_NOTICE = re.compile(r"<task-notification>(.*?)</task-notification>", re.S)
_NOTICE_ID = re.compile(r"<task-id>([A-Za-z0-9_-]{4,})</task-id>")
_NOTICE_END = re.compile(
    r"<status>(?:completed|failed|killed)</status>"
    r"|Monitor expired\b|Monitor timed out\b")


def _blocks(line):
    content = ((line.get("message") or {}).get("content"))
    return content if isinstance(content, list) else []


def _harness_texts(line):
    """The text the HARNESS wrote on this line -- where the end notice lives.

    The notice shows up as `queue-operation` (content), as `attachment`
    (prompt) or as a user message. Assistant lines are left out: the agent
    quoting a notice does not end any watcher.
    """
    if line.get("type") == "assistant":
        return []
    texts = []
    if isinstance(line.get("content"), str):
        texts.append(line["content"])
    attachment = line.get("attachment")
    if isinstance(attachment, dict) and isinstance(attachment.get("prompt"), str):
        texts.append(attachment["prompt"])
    content = (line.get("message") or {}).get("content")
    if isinstance(content, str):
        texts.append(content)
    elif isinstance(content, list):
        texts.extend(b.get("text") for b in content
                      if isinstance(b, dict) and b.get("type") == "text"
                      and isinstance(b.get("text"), str))
    return texts


def closed_watchers(text):
    """Task ids that a terminal `<task-notification>` reports as ended."""
    for m in _NOTICE.finditer(text or ""):
        body = m.group(1)
        task_id = _NOTICE_ID.search(body)
        if task_id and _NOTICE_END.search(body):
            yield task_id.group(1)


def pending(transcript_path):
    """(dispatched subagents without a result, armed watchers without a stop).

    Reads the transcript because it is the ONLY source that knows what was
    dispatched: the Stop payload lists no background task at all.
    """
    dispatched, answered, armed, stopped = {}, set(), {}, set()
    markers = {}
    monitor_calls = set()
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    line = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(line, dict):
                    continue
                for text in _harness_texts(line):
                    stopped.update(closed_watchers(text))
                for b in _blocks(line):
                    kind = b.get("type")
                    if kind == "tool_use" and b.get("name") == "Bash":
                        inp = b.get("input") or {}
                        cmd = inp.get("command") or ""
                        marker_file = end_marker(cmd)
                        if marker_file and _BUILD.search(_unquoted_view(cmd)) and \
                                detached_via(cmd, bool(inp.get("run_in_background"))):
                            markers[marker_file] = (inp.get("description") or cmd)[:80]
                    if kind == "tool_use" and b.get("name") == "Monitor":
                        task_id = b.get("id")
                        if task_id:
                            monitor_calls.add(task_id)
                    if kind == "tool_use" and b.get("name") in _DISPATCH:
                        label = (b.get("input") or {}).get("description") or b.get("name")
                        dispatched[b.get("id")] = str(label)[:80]
                    elif kind == "tool_result":
                        target = b.get("tool_use_id")
                        if target:
                            answered.add(target)
                        text = b.get("content")
                        if not isinstance(text, str):
                            text = json.dumps(text, ensure_ascii=False)
                        # Only count "Monitor started" as an armed watcher if
                        # the tool_result answers a real Monitor tool_use.
                        # Without that, an agent `grep` over old transcripts
                        # that echoes this text in the Bash result already
                        # triggered a false alarm (run 2026-09-28-0558): the
                        # Stop was blocked by a watcher that never existed.
                        if target in monitor_calls:
                            for m in _WATCHER_ARMED.finditer(text):
                                armed[m.group(1)] = m.group(1)
                        for m in _WATCHER_STOPPED.finditer(text):
                            stopped.add(m.group(1) or m.group(2))
    except OSError:
        return [], [], []
    subagents = [r for i, r in dispatched.items() if i not in answered]
    watchers = [v for v in armed if v not in stopped]
    builds = [f"{label} (sem `EXIT=` em {marker_file})"
              for marker_file, label in markers.items() if not _finished(marker_file)]
    return subagents, watchers, builds


def _finished(path):
    try:
        with open(os.path.expanduser(path), encoding="utf-8",
                  errors="replace") as f:
            return "EXIT=" in f.read()
    except OSError:
        return False


def stop_reason(payload, environ=None):
    """The stop block text, or None if there is nothing to collect."""
    env = os.environ if environ is None else environ
    if not env.get(ENV_WINDOW):
        return None
    # Anti-loop: if this stop ALREADY came from a block, do not block again.
    # One chance to collect is the squeeze; trapping the session would trade a
    # lost item for a stuck window.
    if payload.get("stop_hook_active"):
        return None
    transcript = payload.get("transcript_path")
    if not transcript:
        return None
    subagents, watchers, builds = pending(transcript)
    if not subagents and not watchers and not builds:
        return None
    parts = []
    if subagents:
        parts.append("subagente(s) despachado(s) e sem resultado no "
                      "transcript: " + ", ".join(subagents[:5]))
    if watchers:
        parts.append("vigia(s) do Monitor ainda armado(s): " + ", ".join(watchers[:5]))
    if builds:
        parts.append("build(s) em segundo plano ainda sem fim: "
                      + ", ".join(builds[:5]) + ". Espere o arquivo em "
                      "PRIMEIRO PLANO com um laço que sai antes dos 10 min: "
                      "`for i in $(seq 27); do grep -q EXIT= <arquivo> && "
                      "break; sleep 20; done # espera-ok` (timeout 590000), "
                      "e repita até aparecer o `EXIT=`. Espera de 10 min ou "
                      "mais é empurrada para o segundo plano e morre com o "
                      "turno")
    return (
        "[no-background-build] Você está numa janela do `cepa-until` e NÃO HÁ "
        "TURNO SEGUINTE: parar agora mata o processo com trabalho por colher.\n"
        + "".join(f"  - {p}\n" for p in parts) +
        "\n  Faça uma destas, na ordem:\n"
        "    1. Colha agora: espere o resultado do subagente e siga o item até "
        "o fim neste turno.\n"
        "    2. Se um vigia já cumpriu o papel, encerre-o com `TaskStop` antes "
        "de parar.\n"
        "    3. Se o item não cabe no turno, NOMEIE O DESFECHO antes de parar: "
        "`cepa-plan finish <fila> <id> --status blocked --evidence \"...\"`, e "
        "deixe o clone na branch da largada — foi a branch parada numa "
        "integração que encerrou a janela de 2026-09-03 com 6h54 de sobra.")


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[no-background-build] payload ilegível; liberando", file=sys.stderr)
        sys.exit(0)

    if (payload.get("hook_event_name") or "") == "Stop":
        try:
            reason = stop_reason(payload)
        except Exception:
            reason = None  # the gate never takes the turn down over its own error
        if reason:
            T.emit("background_pending_stop_block")
            print(json.dumps({"decision": "block", "reason": reason},
                             ensure_ascii=False))
        sys.exit(0)

    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}

    if tool_name == "Monitor":
        found = watcher_blocks(tool_input)
        if not found:
            sys.exit(0)
        via, snippet = found
        T.emit("background_monitor_block", reason=via)
        print(
            f"[no-background-build] BLOQUEADO: vigia sem fim ({via}).\n"
            f"  Trecho: {snippet}\n\n"
            "  Você está dentro de uma janela do `cepa-until`: este processo é\n"
            "  um `claude -p` e NÃO HÁ TURNO SEGUINTE. Um vigia que não termina\n"
            "  sozinho segura o turno até o relógio do item matar tudo — foi\n"
            "  assim que o WEGO-2224 morreu pela metade em 2026-09-03, e a\n"
            "  branch em que ele parou encerrou a janela com 6h54 de sobra.\n\n"
            "  Faça uma destas, na ordem:\n"
            "    1. Colha em PRIMEIRO PLANO: espere o resultado agora, no turno.\n"
            "    2. Se precisa mesmo de um vigia, escreva um que TERMINE — laço\n"
            "       que sai no primeiro estado terminal (`break`), sem\n"
            "       `persistent: true`.\n"
            "    3. Se o comando não produz veredito para ninguém colher,\n"
            "       acrescente `# fundo-ok`.",
            file=sys.stderr,
        )
        sys.exit(2)

    if tool_name != "Bash":
        sys.exit(0)

    found = blocks(tool_input.get("command", "") or "",
                      bool(tool_input.get("run_in_background")))
    if not found:
        sys.exit(0)

    via, snippet = found
    T.emit("background_build_block", reason=via)
    print(
        f"[no-background-build] BLOQUEADO: build em segundo plano ({via}).\n"
        f"  Trecho: {snippet}\n\n"
        "  Você está dentro de uma janela do `cepa-until`: este processo é um\n"
        "  `claude -p` e NÃO HÁ TURNO SEGUINTE. O turno acaba, o processo morre,\n"
        "  o build vira órfão e o item fica `in_progress` sem desfecho — a\n"
        "  próxima janela o encontra como reserva órfã e recomeça do zero.\n"
        "  Foi assim que 34 dos 49 minutos do run de 2026-08-30 foram perdidos.\n\n"
        "  Faça uma destas, na ordem:\n"
        "    1. Rode o build em PRIMEIRO PLANO e colha o resultado agora. Build\n"
        "       em primeiro plano não é espera ativa: o `no-busy-wait` não o\n"
        "       bloqueia, ele barra laço com `sleep`.\n"
        "    2. Se o build não cabe no turno, NOMEIE O DESFECHO antes de parar:\n"
        "       `cepa-plan finish <fila> <id> --status blocked --evidence`\n"
        "       \"build disparado e não colhido: <comando>, log em <caminho>\".\n"
        "       Um item com desfecho volta sabendo onde parou.\n"
        "    3. Se o build passa de 10 min (o Bash o empurraria para o segundo\n"
        "       plano de qualquer jeito), declare o fim e espere em primeiro\n"
        "       plano, no MESMO turno:\n"
        "         <build> > /tmp/b.log 2>&1; echo EXIT=$? >> /tmp/b.fim\n"
        "       em segundo plano, e depois, com timeout 590000:\n"
        "         for i in $(seq 27); do grep -q EXIT= /tmp/b.fim && break;\n"
        "           sleep 20; done # espera-ok\n"
        "       repetindo até o `EXIT=`. O laço sai antes dos 10 min de\n"
        "       propósito: espera mais longa é empurrada para o segundo plano\n"
        "       como o build. Um `Monitor` NÃO serve: ele não segura\n"
        "       o turno, e o `claude -p` mata o segundo plano quando o turno\n"
        "       acaba. Parar antes do `EXIT=` é barrado na parada.\n"
        "    4. Se o comando NÃO produz veredito (subir servidor, serviço de\n"
        "       apoio), acrescente `# fundo-ok`.\n\n"
        "  A opção 4 é uma afirmação sua de que ninguém precisa ler a saída.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
