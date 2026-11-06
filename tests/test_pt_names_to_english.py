#!/usr/bin/env python3
"""Portuguese flag and subcommand names that moved to English (item `pt-names-to-english`).

The English name is primary, the old one stays as an alias. Each case runs the
old name and the new one and demands the same result. What the tools STORE or
PRINT as data (ledger statuses "aberto"/"triado", the `pedido`/`pronto`/`impede`
keys of `owner_summary` in queue.yaml, the state action id "aterrissar") did not
change and is not tested here as a name.

Run with `python3 tests/test_pt_names_to_english.py`.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# cepa-until and cepa-feedback emit telemetry: without isolating, the suite
# would write to the ledger of whoever runs it.
from _isolated_telemetry import isolate  # noqa: E402

isolate()

import yaml  # noqa: E402
import test_cepa_until as tu  # noqa: E402
import test_cepa_feedback as tf  # noqa: E402
import test_cepa_plan_single_track as tps  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "common" / "bin"
FAILURES = []

# The launcher runner of tests/test_cepa_prompt.py, reduced to what is needed
# here (that module runs its whole suite on import, so it cannot be imported).
for _k in ("CEPA_PROMPT", "CEPA_PROMPT_MODO"):
    os.environ.pop(_k, None)
CEPA = BIN / "cepa"
MARK = "---CEPA-ARG---"
FAKE_CLAUDE = f'#!/bin/sh\nfor a in "$@"; do printf "%s\\n{MARK}\\n" "$a"; done\n'


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def mask(text):
    """Removes digits and temporary paths, which vary between runs."""
    text = re.sub(r"/[^\s`')]*tmp[^\s`')]*", "<tmp>", text)
    return re.sub(r"\d", "#", text)


def test_autonomy_list_and_classify():
    def run(*args):
        p = subprocess.run([sys.executable, str(BIN / "cepa-autonomy")] + list(args)
                           + ["--repo", str(REPO)], capture_output=True, text=True,
                           timeout=60)
        return p.returncode, p.stdout, p.stderr

    old, new = run("listar"), run("list")
    check("autonomy: `list` roda (rc=0)", new[0] == 0 and new[1], new)
    check("autonomy: `list` == `listar`", old == new, (old, new))
    old, new = run("classificar", "--bash", "x"), run("classify", "--bash", "x")
    check("autonomy: `classify` roda (rc=0)", new[0] == 0 and new[1], new)
    check("autonomy: `classify --bash x` == `classificar --bash x`", old == new, (old, new))
    old, new = run("listar", "--json"), run("list", "--json")
    check("autonomy: `list --json` == `listar --json`", old == new and new[0] == 0, (old, new))
    top = subprocess.run([sys.executable, str(BIN / "cepa-autonomy"), "--help"],
                         capture_output=True, text=True, timeout=60).stdout
    check("autonomy: a ajuda mostra os nomes em inglês",
          "list " in top and "classify " in top, top)


def test_until_land_pending_close_dead():
    for old, new, extra in (("aterrissar", "land", ["fila/x"]),
                            ("fecha-morto", "close-dead", ["fila/x"]),
                            ("pendentes", "pending", [])):
        res = []
        for sub in (old, new):
            with tempfile.TemporaryDirectory() as tmp:
                p = subprocess.run([sys.executable, str(tu.CEPA_UNTIL), sub] + extra
                                   + ["--repo", tmp], capture_output=True, text=True,
                                   timeout=60)
                res.append((p.returncode, mask(p.stdout), mask(p.stderr)))
        seen = res[0][1] + res[0][2] + res[1][1] + res[1][2]
        check(f"until `{new}` == `{old}`", res[0] == res[1], res)
        check(f"until `{new}`: o parser entende (nada de 'unrecognized')",
              "unrecognized" not in seen and "is not a subcommand" not in seen, res)
    help_text = subprocess.run([sys.executable, str(tu.CEPA_UNTIL), "--help"],
                               capture_output=True, text=True, timeout=60).stdout
    check("until: a ajuda raiz lista land/pending/close-dead",
          all(n in help_text for n in ("land", "pending", "close-dead")), help_text)
    check("until: a ajuda raiz não lista mais os nomes antigos como subcomandos",
          not any(re.search(rf"^\s+{o}\s", help_text, re.M)
                  for o in ("aterrissar", "pendentes", "fecha-morto")), help_text)


def test_plan_finish_human_section_flags():
    texts = {"asked": "testar a parte que controla quem entra no sistema",
             "ready": "a maior parte dos casos já passa",
             "blocker": "o sistema responde em branco quando nega um acesso",
             "if-yes": "o trabalho segue para revisão com esses casos marcados",
             "if-no": "o trabalho espera o defeito ser corrigido"}
    old_name = {"asked": "pedido", "ready": "pronto", "blocker": "impede",
                "if-yes": "se-sim", "if-no": "se-nao"}
    got = {}
    for side in ("old", "new"):
        with tempfile.TemporaryDirectory() as tmp:
            d = tps.git_repo(tmp, "repo")
            queue = tps.write_queue(d, [tps.item("a1")])
            flags = []
            for k, v in texts.items():
                flags += [f"--{k}" if side == "new" else f"--{old_name[k]}", v]
            p = tps.run(d, "finish", "fila", "a1", "--status", "blocked",
                        "--evidence", "o servidor de teste caiu", "--repo", ".", *flags)
            check(f"plan finish ({side}): rc=0", p.returncode == 0, p.stderr)
            it = tps.by_id(tps.plan_of(queue))["a1"]
            got[side] = (it["status"], it.get("owner_summary"))
    check("plan finish: o owner_summary guarda as chaves de sempre",
          set((got["new"][1] or {})) == {"pedido", "pronto", "impede", "se_sim", "se_nao"},
          got["new"])
    check("plan finish: cinco flags novas == cinco antigas (mesmo owner_summary)",
          got["old"] == got["new"] and got["new"][1], got)
    with tempfile.TemporaryDirectory() as tmp:
        d = tps.git_repo(tmp, "repo")
        tps.write_queue(d, [tps.item("a1")])
        p = tps.run(d, "finish", "fila", "a1", "--status", "blocked",
                    "--evidence", "x", "--repo", ".")
        check("plan finish: o erro de `blocked` sem motivo nomeia --blocker",
              p.returncode == 2 and "--blocker" in p.stderr, p.stderr)


def test_feedback_list_status():
    out = {}
    for new, old in (("open", "aberto"), ("triaged", "triado"), ("all", "todos")):
        res = []
        for st in (old, new):
            with tf.Box() as c:
                tf._queue_box(c)
                p = c.cli("add", "o gate X barrou", "--origin", "skill")
                fid = c.lines()[0]["id"]
                c.cli("add", "outro incômodo", "--origin", "skill")
                p = c.cli("triage", fid, "--destination", "BACKLOG.md § X",
                          "--queue", "fila")
                if p.returncode != 0:
                    print(f"  (triage falhou: {p.stderr})")
                q = c.cli("list", "--status", st, "--json")
                ids = [r["id"] for r in json.loads(q.stdout)] if q.returncode == 0 else q.stderr
                res.append((q.returncode, [(r["status"]) for r in json.loads(q.stdout)]
                            if q.returncode == 0 else q.stderr, len(ids)))
        out[new] = res
        check(f"feedback list --status {new} == {old}", res[0] == res[1] and res[0][0] == 0, res)
    check("feedback list: aberto/triado/todos filtram de verdade",
          [len(out[k][1][1]) for k in ("open", "triaged", "all")] == [1, 1, 2], out)
    check("feedback list: o status guardado segue em português (dado)",
          out["open"][1][1] == ["aberto"] and out["triaged"][1][1] == ["triado"], out)
    with tf.Box() as c:
        q = c.cli("list")
        check("feedback list: o default é `open` (rc=0)", q.returncode == 0, q.stderr)


def test_doctor_project_flag():
    res = []
    for flag in ("--projeto", "--project"):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            home = Path(tmp) / "home"
            home.mkdir()
            subprocess.run(["git", "init", "-q", "."], cwd=repo, check=True)
            env = dict(os.environ, HOME=str(home))
            p = subprocess.run([sys.executable, str(BIN / "cepa-doctor"), flag, "--brief"],
                               cwd=repo, capture_output=True, text=True, env=env,
                               timeout=120)
            res.append((p.returncode, mask(p.stdout), mask(p.stderr)))
    check("doctor: --project == --projeto", res[0] == res[1], res)
    check("doctor: --project é entendido pelo parser",
          "unrecognized" not in res[1][2] and res[1][0] in (0, 1, 2), res)
    # Without the flag the global checks run too: the output would differ, so
    # a flag that is silently ignored would not pass the line above by luck.
    helptext = subprocess.run([sys.executable, str(BIN / "cepa-doctor"), "--help"],
                              capture_output=True, text=True, timeout=60).stdout
    check("doctor: a ajuda mostra --project", "--project" in helptext, helptext)


def test_launcher_prompt_replace():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", "."], cwd=repo, check=True)
        fake = Path(tmp) / "fakeclaude"
        fake.write_text(FAKE_CLAUDE)
        fake.chmod(0o755)
        lib = Path(tmp) / "prompts"
        lib.mkdir()

        def launch(*args):
            env = {**os.environ, "CLAUDE_WT_CLAUDE_BIN": str(fake), "CEPA_PREFLIGHT": "off",
                   "CEPA_MODO": "off", "CEPA_PROMPTS_HOME": str(lib)}
            return subprocess.run([str(CEPA), *args], cwd=repo, env=env,
                                  stdin=subprocess.DEVNULL, capture_output=True,
                                  text=True, timeout=30)

        def args_of(p):
            return p.stdout.split(f"\n{MARK}\n")[:-1]

        f = repo / "p.md"
        f.write_text("prompt inteiro\n")
        for old, new in ((["--prompt-substitui", str(f)], ["--prompt-replace", str(f)]),
                         ([f"--prompt-substitui={f}"], [f"--prompt-replace={f}"])):
            a_old, a_new = args_of(launch(*old)), args_of(launch(*new))
            label = new[0].split("=")[0]
            check(f"launcher: {label} usa --system-prompt e não usa append",
                  "--system-prompt" in a_new and "--append-system-prompt" not in a_new, a_new)
            check(f"launcher: {label} == {old[0].split('=')[0]}",
                  a_old == a_new and a_new, (a_old, a_new))
        p = launch("--prompt-replace")
        check("launcher: --prompt-replace sem valor recusa (rc=2)",
              p.returncode == 2 and "--prompt-replace" in p.stderr, p.stderr)
        h = launch("help")
        check("launcher: a ajuda cita --prompt-replace", "--prompt-replace" in h.stdout + h.stderr)


if __name__ == "__main__":
    print("nomes em português que passaram para inglês (com alias)\n")
    test_autonomy_list_and_classify()
    test_until_land_pending_close_dead()
    test_plan_finish_human_section_flags()
    test_feedback_list_status()
    test_doctor_project_flag()
    test_launcher_prompt_replace()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s): {FAILURES}")
        sys.exit(1)
    print("\ntudo verde")
