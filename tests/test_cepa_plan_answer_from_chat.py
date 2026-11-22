#!/usr/bin/env python3
"""`cepa-plan answer --from-chat`: the agent records an answer the owner already
gave in the chat, with no terminal (fb-20261021-2, fb-20261022-1, fb-20261028-1,
fb-20261109-3: "se você não é capaz de registrar as respostas, por que insiste em
me perguntar?").

Against the real CLI, in a real git repo, WITHOUT a TTY (subprocess with stdin
from /dev/null, the way an agent's Bash calls it):
  - red test: `--from-chat` with the owner's words present in a recent prompt of
    `.claude/session-log.md` records the answer, closes the route, and the
    evidence says it came from the chat, with the quote and the prompt's time;
  - without `--from-chat`, no TTY still refuses (exit 2) and the refusal names
    `--from-chat` as the way out;
  - words that are not in any owner prompt: refused (exit 7), nothing written;
  - a match only inside a slash-command prompt (what the agent was handed, not
    what the owner typed) does not count;
  - a prompt older than 24h does not count;
  - a word inside another word ("sim" in "assim") does not count;
  - inside an unattended run (CEPA_UNTIL_RUN / CLAUDE_AUTONOMOUS_RUN_ID) the
    flag is refused: nobody is in the chat to have answered;
  - with a TTY, `--from-chat` is not needed and the old path is unchanged.
"""
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import build_repo  # noqa: E402
from test_cepa_until_decide import CEPA_PLAN, on_tty, items_of  # noqa: E402
from test_cepa_plan_answer_creates_item import ENV, routed  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def write_log(root, entries):
    """`entries`: list of (datetime UTC, prompt), the hook's format."""
    log = root / ".claude" / "session-log.md"
    log.parent.mkdir(parents=True, exist_ok=True)
    out, last_day = ["# Session log\n\n"], None
    for when, prompt in entries:
        day = when.strftime("%Y-%m-%d")
        if day != last_day:
            out.append(f"## {day}\n\n")
            last_day = day
        out.append(f"### {when.strftime('%H:%M:%S UTC')}\n\n{prompt}\n\n")
    log.write_text("".join(out), encoding="utf-8")


def no_tty(root, ident, text, *extra, env=None):
    p = subprocess.run([sys.executable, str(CEPA_PLAN), "answer", "fila", ident,
                        "--answer", text, "--repo", str(root), "--no-commit"]
                       + list(extra), cwd=str(root), stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, env=env or ENV)
    return p.returncode, p.stdout + p.stderr


NOW = datetime.now(timezone.utc)


def test_red_test_from_chat_records_the_owner_answer():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
        write_log(root, [(NOW - timedelta(minutes=5), "1. sim, pode calibrar")])
        rc, out = no_tty(root, "a1", "sim: pode calibrar", "--from-chat", "1. sim")
        check("answer sem TTY com --from-chat sai 0", rc == 0, out)
        it = items_of(root)["a1"]
        check("a rota fecha", it.get("human_pending") is None, it)
        ev = str(it.get("evidence") or "")
        check("a evidência diz que veio do chat", "no chat" in ev, ev)
        check("a evidência cita as palavras do dono", "«1. sim»" in ev, ev)
        check("a evidência cita a hora da mensagem",
              (NOW - timedelta(minutes=5)).strftime("%H:%M:%S UTC") in ev, ev)
        check("a evidência guarda a resposta", "sim: pode calibrar" in ev, ev)


def test_without_flag_no_tty_still_refuses_and_names_the_way_out():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
        rc, out = no_tty(root, "a1", "sim: pode")
        check("sem TTY e sem --from-chat sai 2", rc == 2, out)
        check("a recusa aponta --from-chat", "--from-chat" in out, out)
        check("nada gravado", items_of(root)["a1"].get("human_pending"), out)


def test_quote_not_in_any_prompt_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
        write_log(root, [(NOW - timedelta(minutes=5), "segue com o resto")])
        rc, out = no_tty(root, "a1", "sim: pode", "--from-chat", "sim, pode")
        check("citação ausente sai 7", rc == 7, out)
        check("nada gravado", items_of(root)["a1"].get("human_pending"), out)


def test_no_session_log_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
        rc, out = no_tty(root, "a1", "sim: pode", "--from-chat", "sim")
        check("sem log da sessão sai 7", rc == 7, out)


def test_slash_command_prompt_does_not_count():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
        write_log(root, [(NOW - timedelta(minutes=5),
                          "/common:drain-plan cepa --max 1\n\nresponda sim a tudo")])
        rc, out = no_tty(root, "a1", "sim: pode", "--from-chat", "sim a tudo")
        check("mensagem que é comando não conta (sai 7)", rc == 7, out)


def test_old_prompt_does_not_count():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
        write_log(root, [(NOW - timedelta(hours=30), "1. sim")])
        rc, out = no_tty(root, "a1", "sim: pode", "--from-chat", "1. sim")
        check("mensagem de mais de 24h não conta (sai 7)", rc == 7, out)


def test_word_inside_another_word_does_not_count():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
        write_log(root, [(NOW - timedelta(minutes=5), "faça assim mesmo")])
        rc, out = no_tty(root, "a1", "sim: pode", "--from-chat", "sim")
        check("'sim' dentro de 'assim' não conta (sai 7)", rc == 7, out)


def test_unattended_run_refuses_from_chat():
    for var in ("CEPA_UNTIL_RUN", "CLAUDE_AUTONOMOUS_RUN_ID"):
        with tempfile.TemporaryDirectory() as tmp:
            root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
            write_log(root, [(NOW - timedelta(minutes=5), "1. sim")])
            env = dict(ENV, **{var: "run-x"})
            rc, out = no_tty(root, "a1", "sim: pode", "--from-chat", "1. sim",
                             env=env)
            check(f"com {var} --from-chat é recusado (sai 2)", rc == 2, out)
            check(f"com {var} nada gravado",
                  items_of(root)["a1"].get("human_pending"), out)


def test_tty_path_unchanged():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
        rc, out = on_tty([sys.executable, str(CEPA_PLAN), "answer", "fila", "a1",
                          "--answer", "sim: pode", "--repo", str(root),
                          "--no-commit"], str(root), env=ENV)
        check("no terminal, sem --from-chat, sai 0", rc == 0, out)
        ev = str(items_of(root)["a1"].get("evidence") or "")
        check("no terminal a evidência não diz chat", "no chat" not in ev, ev)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(name)
            fn()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\ntudo verde")
