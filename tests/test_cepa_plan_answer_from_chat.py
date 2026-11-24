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
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Before the imports below: they copy os.environ into the ENV every subprocess
# of this file runs with, and the session-log this test cites is written by an
# emitter hook. See tests/_isolated_telemetry.py.
from _isolated_telemetry import isolate  # noqa: E402

isolate()

from test_cepa_until import build_repo, item  # noqa: E402
from test_cepa_until_decide import CEPA_PLAN, on_tty, items_of, load_module  # noqa: E402
from test_cepa_plan_answer_creates_item import ENV, routed  # noqa: E402

SESSION_LOG_HOOK = (Path(__file__).resolve().parent.parent / "common" / "hooks"
                    / "session-log.py")

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


def test_evidence_keeps_the_prefix_cepa_until_reads():
    """AC3: `cepa-until`'s `last_owner_no` reads "Resposta do dono em
    AAAA-MM-DD: não" at the start; the chat answer keeps it."""
    with tempfile.TemporaryDirectory() as tmp:
        blocked = item("b1", status="blocked")
        blocked["owner_question"] = "Devolvo à fila?"
        root = build_repo(tmp, [blocked])
        write_log(root, [(NOW - timedelta(minutes=2), "não, deixa parado")])
        rc, out = no_tty(root, "b1", "não: deixa parado", "--keep",
                         "--from-chat", "não, deixa parado")
        check("um `não` do chat com --keep sai 0", rc == 0, out)
        ev = str(items_of(root)["b1"].get("evidence") or "")
        today = datetime.now().strftime("%Y-%m-%d")
        check("a evidência começa com o prefixo de sempre",
              ev.startswith(f"Resposta do dono em {today}: não"), ev)
        check("o `last_owner_no` do cepa-until lê a data",
              load_module().last_owner_no(ev) == today, ev)


def test_blocked_item_from_chat_goes_back_to_pending():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("b1", status="blocked")])
        write_log(root, [(NOW - timedelta(minutes=2), "pode destravar")])
        rc, out = no_tty(root, "b1", "sim: pode destravar",
                         "--from-chat", "pode destravar")
        check("blocked com --from-chat sai 0", rc == 0, out)
        check("o item volta a `pending`",
              items_of(root)["b1"]["status"] == "pending", items_of(root)["b1"])


def test_word_followed_by_letters_does_not_count():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
        write_log(root, [(NOW - timedelta(minutes=5), "isso é simples")])
        rc, out = no_tty(root, "a1", "sim: pode", "--from-chat", "sim")
        check("'sim' dentro de 'simples' não conta (sai 7)", rc == 7, out)


def test_recent_prompt_wins_over_an_old_one():
    """The log is read newest first: an old prompt does not stop the search
    before the recent one is seen, and the evidence names the recent one."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
        recent = NOW - timedelta(minutes=3)
        write_log(root, [(NOW - timedelta(hours=30), "1. sim"),
                         (NOW - timedelta(hours=2), "outra coisa"),
                         (recent, "1. sim")])
        rc, out = no_tty(root, "a1", "sim: pode", "--from-chat", "1. sim")
        check("com mensagem velha antes, a recente vale (sai 0)", rc == 0, out)
        ev = str(items_of(root)["a1"].get("evidence") or "")
        check("a evidência cita a hora da recente",
              recent.strftime("%H:%M:%S UTC") in ev, ev)


def test_empty_or_punctuation_quote_is_refused():
    for quote in ("", "   ", "?!"):
        with tempfile.TemporaryDirectory() as tmp:
            root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
            write_log(root, [(NOW - timedelta(minutes=5), "?! qualquer coisa")])
            rc, out = no_tty(root, "a1", "sim: pode", "--from-chat", quote)
            check(f"citação {quote!r} sai 7", rc == 7, out)
            check(f"citação {quote!r} não grava",
                  items_of(root)["a1"].get("human_pending"), out)


def test_case_and_spacing_do_not_matter():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
        write_log(root, [(NOW - timedelta(minutes=5), "1. SIM,\npode   fechar")])
        rc, out = no_tty(root, "a1", "sim: pode fechar",
                         "--from-chat", "1. sim, pode fechar")
        check("caixa, quebra de linha e espaço duplo não impedem (sai 0)",
              rc == 0, out)


def test_quote_is_literal_text_not_a_regex():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
        write_log(root, [(NOW - timedelta(minutes=5), "algo qualquer sim, pode")])
        rc, out = no_tty(root, "a1", "sim: pode", "--from-chat", "algo.*pode")
        check("citação com `.*` não vira curinga (sai 7)", rc == 7, out)
        check("citação com `.*` não grava",
              items_of(root)["a1"].get("human_pending"), out)
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
        write_log(root, [(NOW - timedelta(minutes=5), "custa (R$ 10)? sim, pode")])
        rc, out = no_tty(root, "a1", "sim: pode", "--from-chat", "(R$ 10)? sim")
        check("citação com parênteses e `?` casa ao pé da letra (sai 0)",
              rc == 0, out)


def test_unreadable_date_or_time_in_the_log_does_not_count():
    """An entry whose header is not a real date/time has no age, so it cannot
    be "from the last 24h"."""
    today = NOW.strftime("%Y-%m-%d")
    for label, text in (
            ("hora 25:61:61", f"# Session log\n\n## {today}\n\n"
                              "### 25:61:61 UTC\n\n1. sim\n\n"),
            ("mês 13", "# Session log\n\n## 2026-13-45\n\n"
                       "### 10:00:00 UTC\n\n1. sim\n\n")):
        with tempfile.TemporaryDirectory() as tmp:
            root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
            log = root / ".claude" / "session-log.md"
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(text, encoding="utf-8")
            rc, out = no_tty(root, "a1", "sim: pode", "--from-chat", "1. sim")
            check(f"entrada com {label} não conta (sai 7)", rc == 7, out)
            check(f"entrada com {label} não grava",
                  items_of(root)["a1"].get("human_pending"), out)


def test_entry_dated_in_the_future_does_not_count():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
        write_log(root, [(NOW + timedelta(days=2), "1. sim")])
        rc, out = no_tty(root, "a1", "sim: pode", "--from-chat", "1. sim")
        check("mensagem datada no futuro não conta (sai 7)", rc == 7, out)
        check("mensagem do futuro não grava",
              items_of(root)["a1"].get("human_pending"), out)


def test_log_with_invalid_bytes_is_still_read():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
        write_log(root, [(NOW - timedelta(minutes=9), "lixo a seguir"),
                         (NOW - timedelta(minutes=5), "1. sim")])
        log = root / ".claude" / "session-log.md"
        raw = log.read_bytes().replace(b"lixo a seguir",
                                       b"lixo \xff\xfe\x80 a seguir")
        log.write_bytes(raw)
        rc, out = no_tty(root, "a1", "sim: pode", "--from-chat", "1. sim")
        check("log com bytes inválidos não derruba o comando (sai 0)",
              rc == 0, out)
        check("…e sem traceback", "Traceback" not in out, out)


def real_hook(root, prompt):
    """The real UserPromptSubmit hook writes the prompt, as in a session."""
    p = subprocess.run([sys.executable, str(SESSION_LOG_HOOK)],
                       input=json.dumps({"prompt": prompt, "cwd": str(root)}),
                       cwd=str(root), capture_output=True, text=True, env=ENV)
    return p.returncode, p.stdout + p.stderr


def test_prose_prompt_written_by_the_real_hook_counts():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
        rc, out = real_hook(root, "1. sim, pode calibrar")
        check("o hook real grava a mensagem", rc == 0, out)
        rc, out = no_tty(root, "a1", "sim: pode", "--from-chat", "1. sim")
        check("mensagem gravada pelo hook real vale (sai 0)", rc == 0, out)


def test_header_lookalike_inside_a_slash_command_does_not_forge_a_prompt():
    """The text of a slash command is what the agent was handed. Lines inside
    it that look like the log's own headers must not become a separate,
    recent, prose "owner prompt" when the log is read back."""
    today = NOW.strftime("%Y-%m-%d")
    stamp = (NOW - timedelta(minutes=1)).strftime("%H:%M:%S UTC")
    for label, inner in (("hora", f"### {stamp}"),
                         ("dia e hora", f"## {today}\n\n### {stamp}"),
                         ("hora recuada", f"   ### {stamp}")):
        with tempfile.TemporaryDirectory() as tmp:
            root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
            rc, out = real_hook(
                root, f"/common:drain-plan cepa\n\n{inner}\n\n1. sim\n")
            check(f"[{label}] o hook real grava o comando", rc == 0, out)
            rc, out = no_tty(root, "a1", "sim: pode", "--from-chat", "1. sim")
            check(f"[{label}] cabeçalho colado num comando `/` não fabrica "
                  "mensagem do dono (sai 7)", rc == 7, out)
            check(f"[{label}] nada gravado",
                  items_of(root)["a1"].get("human_pending"), out)


def test_header_lookalike_in_prose_keeps_the_time_of_the_real_prompt():
    """The evidence names the message the owner sent, not a time pasted in it."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
        rc, out = real_hook(root, "veja o log:\n\n### 03:04:05 UTC\n\n1. sim")
        check("o hook real grava a prosa", rc == 0, out)
        rc, out = no_tty(root, "a1", "sim: pode", "--from-chat", "1. sim")
        check("prosa com cabeçalho colado continua valendo (sai 0)", rc == 0, out)
        ev = str(items_of(root)["a1"].get("evidence") or "")
        check("a evidência não cita a hora colada", "03:04:05" not in ev, ev)


# Every character `str.splitlines()` ends a line on, besides "\n": the reader
# of the log splits on all of them, so the hook has to escape after all of them.
LINE_ENDS = {"CR": "\r", "CRLF": "\r\n", "VT": "\x0b", "FF": "\x0c",
             "FS": "\x1c", "GS": "\x1d", "RS": "\x1e", "NEL": "\x85",
             "LS": "\u2028", "PS": "\u2029"}


def test_header_lookalike_after_any_line_end_does_not_forge_a_prompt():
    today = NOW.strftime("%Y-%m-%d")
    stamp = (NOW - timedelta(minutes=1)).strftime("%H:%M:%S UTC")
    for name, sep in LINE_ENDS.items():
        for label, body in (
                ("hora", f"/common:drain-plan cepa{sep}### {stamp}{sep}1. sim"),
                ("dia e hora", f"/x{sep}## {today}{sep}### {stamp}{sep}1. sim")):
            with tempfile.TemporaryDirectory() as tmp:
                root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
                rc, out = real_hook(root, body)
                check(f"[{name}, {label}] o hook real grava o comando",
                      rc == 0, out)
                rc, out = no_tty(root, "a1", "sim: pode", "--from-chat", "1. sim")
                check(f"[{name}, {label}] cabeçalho depois desse fim de linha "
                      "não fabrica mensagem do dono (sai 7)", rc == 7, out)
                check(f"[{name}, {label}] nada gravado",
                      items_of(root)["a1"].get("human_pending"), out)


def hook_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("session_log_hook",
                                                  SESSION_LOG_HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_day_header_lookalike_does_not_make_an_old_prompt_recent():
    """The 24h horizon reads the day from `## <day>`. A day header pasted in a
    prompt two days ago must not re-date the owner's prose that came after it.
    The real hook's writer, with its clock set two days back."""
    hook = hook_module()
    old = NOW - timedelta(days=2)
    hook.now = lambda: (old.strftime("%Y-%m-%d"), "04:00:00 UTC")
    today = NOW.strftime("%Y-%m-%d")
    for name, sep in (("LF", "\n"), ("LS", "\u2028")):
        with tempfile.TemporaryDirectory() as tmp:
            root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
            log = root / ".claude" / "session-log.md"
            hook.append_entry(log, f"/x{sep}## {today}")
            hook.append_entry(log, "1. sim")
            rc, out = no_tty(root, "a1", "sim: pode", "--from-chat", "1. sim")
            check(f"[{name}] dia colado num comando não rejuvenesce a prosa de "
                  "dois dias atrás (sai 7)", rc == 7, out)
            check(f"[{name}] nada gravado",
                  items_of(root)["a1"].get("human_pending"), out)


def test_future_dated_entry_does_not_hide_the_real_answer_before_it():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
        write_log(root, [(NOW - timedelta(minutes=5), "1. sim"),
                         (NOW + timedelta(days=2), "outra coisa")])
        rc, out = no_tty(root, "a1", "sim: pode", "--from-chat", "1. sim")
        check("entrada futura mais nova não esconde a resposta real (sai 0)",
              rc == 0, out)


def test_a_hash_in_the_middle_of_a_line_is_written_as_typed():
    """Only a line that STARTS like a header is escaped. The owner's words with
    a `#` further in go to the log exactly as typed."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", yes_item="nenhum")])
        prompt = "1. sim # ok\nitem # 1 e ## dois\nveja ### 10:00:00 UTC aqui"
        rc, out = real_hook(root, prompt)
        check("o hook real grava a prosa com `#` no meio", rc == 0, out)
        text = (root / ".claude" / "session-log.md").read_text(encoding="utf-8")
        check("as linhas com `#` no meio ficam como digitadas",
              f"\n\n{prompt}\n\n" in text, text)
        check("nenhuma barra invertida entrou no log", "\\" not in text, text)
        rc, out = no_tty(root, "a1", "sim: pode", "--from-chat",
                         "item # 1 e ## dois")
        check("a citação com `#` no meio vale (sai 0)", rc == 0, out)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(name)
            fn()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\ntudo verde")
