#!/usr/bin/env python3
"""`cepa-until pending` reinstalls the plugins when it closes a landed run, with the
same rule and the same guards as `land` (spec docs/spec/pouso-ja-feito-sai-da-lista.md,
CS-6; owner's answer: "yes, like `land`, same rule and same guards").

Against the real CLI, in a temporary git repo with a remote and a fake HOME (never the
real `~/.claude`), whose `bin/install.sh` only writes down that it ran:

  - cepa repo (marketplace `cepa` + `bin/install.sh`), `a/r1` landed: `pending` closes
    it, runs the installer once from the clone, and the `.jsonl` of `a/r1` gains
    `instalado_no_pouso`
  - `last-install.json` pointing at the worktree of ANOTHER live run: the `.jsonl` gains
    `instalacao_adiada` and the installer does not run
  - a repo that is not the cepa repo: no event, no install
  - `--json` still parses as JSON when an install happened
  - a call that closes nothing, or only discards a run, does not install
  - two runs closed in one call: one install, both `.jsonl` carry the event

Run with `python3 tests/test_cepa_until_pending_install.py`.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until_pending_says_what_closed import (  # noqa: E402
    CEPA_UNTIL, FAILURES, check, git, make_repo, add_run, state_path)

RED = {"parou": "build-vermelho", "motivo": "exit 1"}


def as_cepa_repo(root, name="cepa"):
    (root / ".claude-plugin").mkdir()
    (root / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": name, "plugins": []}))
    (root / "bin").mkdir()
    (root / "bin" / "install.sh").write_text(
        f"#!/bin/sh\npwd -P >> '{calls_file(root)}'\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "cepa repo")
    git(root, "push", "-q", "origin", "main")


def calls_file(root):
    return root.parent / "install-calls.txt"


def calls(root):
    f = calls_file(root)
    return f.read_text().splitlines() if f.exists() else []


def pending(root, home, *extra, repo=None):
    env = dict(os.environ, HOME=str(home))
    return subprocess.run([sys.executable, str(CEPA_UNTIL), "pending",
                           "--repo", str(repo or root), *extra],
                          capture_output=True, text=True, cwd=str(root), env=env)


INSTALL_TEXT = "installing the plugins from the clone"


def jsonl_of(root, queue, run):
    return (root / ".claude" / "queues" / queue / "until" / f"{run}.jsonl")


def lines_of(root, queue, run):
    f = jsonl_of(root, queue, run)
    return f.read_text().splitlines() if f.exists() else []


def waiting_in_queue_b(root, run):
    """A run of queue `b` that stays waiting (branch not landed), named `run`."""
    tmp_run = f"tmp{run}"
    add_run(root, tmp_run, keep_branch=True, merged=False, aterrissagem=RED)
    data = json.loads(state_path(root, tmp_run).read_text())
    state_path(root, tmp_run).unlink()
    d = root / ".claude" / "queues" / "b" / "until"
    d.mkdir(parents=True, exist_ok=True)
    data.update({"fila": "b", "run": run})
    (d / f"{run}.estado.json").write_text(json.dumps(data))
    (d / f"{run}.jsonl").write_text(
        json.dumps({"evento": "run_start", "fila": "b"}) + "\n")


def events(root, run, name=None):
    f = state_path(root, run).with_name(f"{run}.jsonl")
    out = ([json.loads(l) for l in f.read_text().splitlines() if l.strip()]
           if f.exists() else [])
    return [e for e in out if name is None or e.get("evento") == name]


def landed_repo(tmp, cepa=True, runs=("r1",)):
    root = make_repo(tmp)
    if cepa:
        as_cepa_repo(root)
    for r in runs:
        add_run(root, r, keep_branch=True, aterrissagem=RED)
    git(root, "push", "-q", "origin", "main")
    return root


def live_other_run(root, tree, pid):
    d = root / ".claude" / "queues" / "outra" / "until"
    d.mkdir(parents=True, exist_ok=True)
    Path(tree).mkdir(parents=True, exist_ok=True)
    (d / "o1.estado.json").write_text(json.dumps(
        {"run": "o1", "fila": "outra", "estado": "rodando", "branch": "until/o1",
         "registro": "o1.jsonl", "pid": pid, "host": socket.gethostname()}))
    (d / "o1.jsonl").write_text(json.dumps(
        {"evento": "run_start", "fila": "outra", "branch": "until/o1", "pid": pid,
         "arvore": str(tree)}) + "\n")


def last_install_in(home, repo_dir):
    ops = Path(home) / ".claude" / "ops"
    ops.mkdir(parents=True, exist_ok=True)
    (ops / "last-install.json").write_text(json.dumps(
        {"repo_dir": str(repo_dir), "main_clone": "/x", "live_dir": "/y"}))


def test_installs_when_it_closes():
    print("CS-6: fecha a/r1 no repo do cepa e instala do clone")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp)
        p = pending(root, Path(tmp) / "home")
        check("sai 0", p.returncode == 0, p.stderr)
        check("a/r1 foi fechado", "closed: queue a" in p.stdout, p.stdout)
        ev = events(root, "r1", "instalado_no_pouso")
        check("o .jsonl de a/r1 ganha instalado_no_pouso",
              len(ev) == 1 and ev[0].get("ok") is True, str(ev))
        check("o instalador rodou uma vez, no clone",
              calls(root) == [str(root.resolve())], str(calls(root)))
        p2 = pending(root, Path(tmp) / "home")
        check("segunda chamada nao instala de novo", len(calls(root)) == 1
              and not events(root, "r1", "instalacao_adiada"), str(calls(root)))
        del p2


def test_live_other_run_defers():
    print("CS-6: last-install na worktree de outro run vivo adia")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp)
        home = Path(tmp) / "home"
        other_tree = Path(tmp) / "wt" / "outra"
        alive = subprocess.Popen([sys.executable, "-c",
                                  "import time; time.sleep(120)", "cepa-until"])
        try:
            live_other_run(root, other_tree, alive.pid)
            last_install_in(home, other_tree)
            p = pending(root, home)
        finally:
            alive.kill()
            alive.wait()
        check("sai 0", p.returncode == 0, p.stderr)
        ev = events(root, "r1", "instalacao_adiada")
        check("o .jsonl ganha instalacao_adiada nomeando a outra rodada",
              len(ev) == 1 and "o1" in json.dumps(ev[0]), str(ev))
        check("sem instalado_no_pouso", not events(root, "r1", "instalado_no_pouso"))
        check("o instalador nao rodou", calls(root) == [], str(calls(root)))


def test_other_repo_does_not_install():
    print("CS-6: repo que nao e o do cepa nao instala")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp, cepa=False)
        p = pending(root, Path(tmp) / "home")
        check("fecha e sai 0", p.returncode == 0 and "closed:" in p.stdout, p.stdout)
        check("nenhum evento de instalacao",
              not events(root, "r1", "instalado_no_pouso")
              and not events(root, "r1", "instalacao_adiada"))
        check("sem install.sh no repo, nada rodou", calls(root) == [])
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        as_cepa_repo(root, name="outro")
        add_run(root, "r1", keep_branch=True, aterrissagem=RED)
        git(root, "push", "-q", "origin", "main")
        p = pending(root, Path(tmp) / "home")
        check("marketplace com outro nome: fecha sem instalar",
              "closed:" in p.stdout and calls(root) == []
              and not events(root, "r1", "instalado_no_pouso"), p.stdout)


def test_json_stays_json():
    print("CS-6: --json continua JSON quando instalou")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp)
        p = pending(root, Path(tmp) / "home", "--json")
        try:
            j = json.loads(p.stdout)
        except ValueError:
            j = None
        check("stdout e JSON", j is not None, p.stdout)
        check("...com fechados e instalou",
              j is not None and len(j["fechados"]) == 1
              and len(calls(root)) == 1, p.stdout)


def test_nothing_closed_does_not_install():
    print("CS-6: chamada que nao fecha nada, ou so descarta, nao instala")
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        as_cepa_repo(root)
        add_run(root, "r2", keep_branch=True, aterrissagem=RED)   # local only
        p = pending(root, Path(tmp) / "home")
        check("nada fechado, nada instalado",
              "closed:" not in p.stdout and calls(root) == [], p.stdout)
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        as_cepa_repo(root)
        add_run(root, "r4", keep_branch=False, merged=False)       # never landed
        p = pending(root, Path(tmp) / "home")
        check("so descartado: fecha, nao instala",
              "discarded" in p.stdout and calls(root) == []
              and not events(root, "r4", "instalado_no_pouso"), p.stdout)


def test_two_closed_install_once():
    print("CS-6: dois fechados na mesma chamada, uma instalacao")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp, runs=("r1", "r3"))
        pending(root, Path(tmp) / "home")
        check("o instalador rodou uma vez", len(calls(root)) == 1, str(calls(root)))
        check("os dois .jsonl trazem instalado_no_pouso",
              all(len(events(root, r, "instalado_no_pouso")) == 1
                  for r in ("r1", "r3")))


def test_ledger_match_is_by_queue_and_run():
    print("CS-6: so o run fechado ganha o evento (par fila+run)")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp)                    # a/r1 landed
        add_run(root, "r2", keep_branch=True, aterrissagem=RED)   # a/r2 stays
        waiting_in_queue_b(root, "r1")             # b/r1: same run id, stays
        p = pending(root, Path(tmp) / "home")
        check("fechou so a/r1", p.stdout.count("closed:") == 1, p.stdout)
        check("a/r1 ganha o evento", len(events(root, "r1", "instalado_no_pouso")) == 1)
        check("a/r2 (mesma fila, nao fechado) nao ganha",
              not any("instalado_no_pouso" in l for l in lines_of(root, "a", "r2")))
        check("b/r1 (mesmo run id, outra fila) nao ganha",
              not any("instalado_no_pouso" in l for l in lines_of(root, "b", "r1")),
              str(lines_of(root, "b", "r1")))


def test_copy_carries_only_new_lines():
    print("CS-6: a copia para o segundo run leva so as linhas novas")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp, runs=("r1", "r3"))
        old = "".join(json.dumps({"evento": "velho_r1", "n": i}) + "\n"
                      for i in range(3))
        with jsonl_of(root, "a", "r1").open("a") as f:
            f.write(old)
        pending(root, Path(tmp) / "home")
        second = lines_of(root, "a", "r3")
        check("r3 nao herda as linhas antigas de r1",
              not any("velho_r1" in l for l in second), str(second))
        check("r3 tem o instalado_no_pouso",
              any("instalado_no_pouso" in l for l in second), str(second))


def test_install_text_placement():
    print("CS-6: texto da instalacao em stdout (texto) ou stderr (--json)")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp)
        p = pending(root, Path(tmp) / "home")
        check("texto: stdout traz o texto da instalacao",
              INSTALL_TEXT in p.stdout, p.stdout)
        check("texto: stderr nao traz", INSTALL_TEXT not in p.stderr, p.stderr)
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp)
        p = pending(root, Path(tmp) / "home", "--json")
        check("--json: stderr traz o texto da instalacao",
              INSTALL_TEXT in p.stderr, p.stderr)
        try:
            json.loads(p.stdout)
            ok = True
        except ValueError:
            ok = False
        check("--json: stdout continua so o JSON",
              ok and INSTALL_TEXT not in p.stdout, p.stdout)


def test_failed_copy_is_reported():
    print("CS-6: falha ao gravar no segundo .jsonl e dita, e sai 0")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp, runs=("r1", "r3"))
        second = jsonl_of(root, "a", "r3")
        if second.exists():
            second.unlink()
        second.mkdir()                              # cannot be opened for append
        p = pending(root, Path(tmp) / "home")
        check("sai 0", p.returncode == 0, p.stderr)
        check("diz que nao conseguiu registrar",
              "install after closing: could not record it" in p.stdout + p.stderr,
              p.stdout + p.stderr)


def failing_installer(root):
    """The fake install.sh of the cepa repo fails (exit 1); its `--rollback` goes through."""
    (root / "bin" / "install.sh").write_text(
        "#!/bin/sh\n"
        "case \" $* \" in *\" --rollback \"*) exit 0;; esac\n"
        "exit 1\n")


def test_copy_reaches_every_other_run():
    print("CS-6: tres fechados, a copia chega ao terceiro")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp, runs=("r1", "r3", "r5"))
        p = pending(root, Path(tmp) / "home")
        check("sai 0 e fechou os tres", p.returncode == 0
              and p.stdout.count("closed:") == 3, p.stdout)
        check("r5 (o terceiro) tem o instalado_no_pouso",
              len(events(root, "r5", "instalado_no_pouso")) == 1,
              str(lines_of(root, "a", "r5")))


def test_copy_appends_and_keeps_earlier_lines():
    print("CS-6: a copia anexa ao .jsonl do segundo run, sem apagar o que ja tinha")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp, runs=("r1", "r3"))
        mine = [json.dumps({"evento": "meu_antigo", "n": i}) for i in range(2)]
        with jsonl_of(root, "a", "r3").open("a") as f:
            f.write("".join(l + "\n" for l in mine))
        pending(root, Path(tmp) / "home")
        got = lines_of(root, "a", "r3")
        check("as linhas antigas de r3 continuam, no comeco, na ordem",
              [l for l in got if "meu_antigo" in l] == mine
              and all(l in got[:len(got)] for l in mine)
              and got.index(mine[0]) < got.index(mine[1]), str(got))
        check("...seguidas do instalado_no_pouso copiado",
              "instalado_no_pouso" in got[-1]
              and not any("instalado_no_pouso" in l
                          for l in got[:got.index(mine[1])]), str(got))


def evento_or_bad(line):
    try:
        return json.loads(line).get("evento")
    except (ValueError, AttributeError):
        return "bad"


def test_copy_carries_every_new_line_in_order():
    print("CS-6: instalacao que falha: o segundo run recebe as duas linhas novas")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp, runs=("r1", "r3"))
        failing_installer(root)
        p = pending(root, Path(tmp) / "home")
        check("sai 0", p.returncode == 0, p.stderr)
        for r in ("r1", "r3"):
            names = [evento_or_bad(l) for l in lines_of(root, "a", r)]
            new = [n for n in names if n in ("instalado_no_pouso",
                                             "reinstalacao_desfeita")]
            check(f"{r}: instalado_no_pouso e depois reinstalacao_desfeita",
                  new == ["instalado_no_pouso", "reinstalacao_desfeita"]
                  and names[-2:] == new, str(names))
        check("r3: instalado_no_pouso com ok falso",
              ['"ok": false' in l for l in lines_of(root, "a", "r3")][:1] == [True])


def test_copy_ends_with_newline_and_each_line_is_json():
    print("CS-6: o .jsonl copiado termina em newline e cada linha e JSON")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp, runs=("r1", "r3"))
        failing_installer(root)
        pending(root, Path(tmp) / "home")
        raw = jsonl_of(root, "a", "r3").read_text()
        check("termina com \\n", raw.endswith("\n"), repr(raw[-80:]))
        parts = raw.split("\n")[:-1]
        ok = True
        for l in parts:
            try:
                ok = ok and isinstance(json.loads(l), dict)
            except ValueError:
                ok = False
        check("cada linha (separada so por \\n) e um JSON sozinha, sem linha "
              "colada nem vazia", ok and len(parts) >= 2
              and all(l.strip() for l in parts), repr(raw))


def test_failed_copy_message_goes_where_the_install_text_goes():
    print("CS-6: a mensagem de falha da copia vai para stdout (texto) ou stderr (--json)")
    msg = "install after closing: could not record it"
    for mode in ("texto", "--json"):
        with tempfile.TemporaryDirectory() as tmp:
            root = landed_repo(tmp, runs=("r1", "r3"))
            second = jsonl_of(root, "a", "r3")
            if second.exists():
                second.unlink()
            second.mkdir()
            extra = ("--json",) if mode == "--json" else ()
            p = pending(root, Path(tmp) / "home", *extra)
            if mode == "texto":
                check("texto: a mensagem esta em stdout", msg in p.stdout, p.stdout)
                check("texto: ...e nao em stderr", msg not in p.stderr, p.stderr)
            else:
                check("--json: a mensagem esta em stderr", msg in p.stderr, p.stderr)
                try:
                    json.loads(p.stdout)
                    pure = True
                except ValueError:
                    pure = False
                check("--json: stdout continua so o JSON, sem a mensagem",
                      pure and msg not in p.stdout, p.stdout)


def test_runs_from_subdir_and_worktree():
    print("CS-6: --repo em subdiretorio ou worktree do clone instala do clone")
    for kind in ("subdir", "worktree"):
        with tempfile.TemporaryDirectory() as tmp:
            root = landed_repo(tmp)
            if kind == "subdir":
                where = root / "sub"
                where.mkdir()
            else:
                where = Path(tmp) / "linked"
                git(root, "worktree", "add", "-q", "-b", "side", str(where))
            p = pending(root, Path(tmp) / "home", repo=where)
            check(f"{kind}: sai 0", p.returncode == 0, p.stderr)
            check(f"{kind}: instalou do clone",
                  calls(root) == [str(root.resolve())], str(calls(root)) + p.stderr)
            check(f"{kind}: evento no .jsonl do clone",
                  len(events(root, "r1", "instalado_no_pouso")) == 1)


def commit_fixture(root):
    """What the repo has before `pending` runs: `.estado.json` and `.log` ignored by git (as in
    the real repos) and the fixture committed, so any change `git status` shows
    afterwards was written by the closing."""
    (root / ".gitignore").write_text(
        ".claude/queues/*/until/*.estado.json\n.claude/queues/*/until/*.log\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "fixture")


def files_of(root, rev):
    return sorted(git(root, "show", "--name-only", "--pretty=format:", rev).split())


def test_closing_commits_what_it_wrote():
    print("CS-7: o que o fechamento escreve entra num commit e a arvore fica limpa")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp)
        commit_fixture(root)
        before = git(root, "rev-parse", "HEAD")
        origin_before = git(root, "rev-parse", "origin/main")
        p = pending(root, Path(tmp) / "home")
        check("sai 0", p.returncode == 0, p.stderr)
        check("git status --porcelain vazio",
              git(root, "status", "--porcelain") == "", git(root, "status", "--porcelain"))
        check("um commit novo no topo", git(root, "rev-parse", "HEAD~1") == before)
        check("mensagem `until a/r1 pending: ...`",
              git(root, "log", "-1", "--format=%s").startswith("until a/r1 pending: "),
              git(root, "log", "-1", "--format=%s"))
        check("o commit contem so o .jsonl do run",
              files_of(root, "HEAD") == [".claude/queues/a/until/r1.jsonl"],
              str(files_of(root, "HEAD")))
        check("sem push: origin/main nao se mexeu",
              git(root, "rev-parse", "origin/main") == origin_before)
        p2 = pending(root, Path(tmp) / "home")
        check("segunda chamada nao faz outro commit", git(root, "rev-parse", "HEAD~1") == before
              and git(root, "status", "--porcelain") == "", p2.stdout)


def test_two_closed_both_committed_clean_tree():
    print("CS-7: dois fechados na mesma chamada, cada .jsonl num commit e arvore limpa")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp, runs=("r1", "r3"))
        commit_fixture(root)
        before = git(root, "rev-parse", "HEAD")
        pending(root, Path(tmp) / "home")
        check("git status --porcelain vazio", git(root, "status", "--porcelain") == "",
              git(root, "status", "--porcelain"))
        subjects = git(root, "log", f"{before}..HEAD", "--format=%s").splitlines()
        check("um commit por run fechado, `until <fila>/<run> pending: ...`",
              sorted(s.split(":")[0] for s in subjects)
              == ["until a/r1 pending", "until a/r3 pending"], str(subjects))
        touched = sorted(git(root, "diff", "--name-only", before, "HEAD").split())
        check("os dois .jsonl, e nada mais, foram commitados",
              touched == [".claude/queues/a/until/r1.jsonl",
                          ".claude/queues/a/until/r3.jsonl"], str(touched))


def test_json_stdout_stays_json_with_commit():
    print("CS-7: --json continua so o JSON quando houve commit")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp)
        commit_fixture(root)
        p = pending(root, Path(tmp) / "home", "--json")
        try:
            json.loads(p.stdout)
            pure = True
        except ValueError:
            pure = False
        check("stdout e so o JSON", pure, p.stdout)
        check("o commit foi feito mesmo assim",
              git(root, "log", "-1", "--format=%s").startswith("until a/r1 pending: "))


def test_non_cepa_repo_makes_no_commit():
    print("CS-7: repo que nao e o do cepa nao escreve nada versionado, nao commita")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp, cepa=False)
        commit_fixture(root)
        before = git(root, "rev-parse", "HEAD")
        pending(root, Path(tmp) / "home")
        check("HEAD nao se mexeu", git(root, "rev-parse", "HEAD") == before)


def test_record_written_before_a_failed_write_is_still_committed():
    print("CS-7: .jsonl que ganhou conteudo antes de uma escrita falhar entra no commit")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp)
        record = jsonl_of(root, "a", "r1")
        # The install fails, and its rollback makes the record read-only: the first
        # append (`instalado_no_pouso`) succeeded, the second (`reinstalacao_desfeita`)
        # raises OSError inside `install_on_landing`.
        (root / "bin" / "install.sh").write_text(
            "#!/bin/sh\n"
            f"case \" $* \" in *\" --rollback \"*) chmod a-w '{record}'; exit 0;; esac\n"
            "exit 1\n")
        commit_fixture(root)
        before = git(root, "rev-parse", "HEAD")
        p = pending(root, Path(tmp) / "home")
        record.chmod(0o644)
        if any(e.get("evento") == "reinstalacao_desfeita" for e in events(root, "r1")):
            print("  (a escrita nao falhou neste ambiente: root ignora chmod; nada a provar)")
            return
        check("sai 0", p.returncode == 0, p.stderr)
        check("o .jsonl ganhou o primeiro evento",
              len(events(root, "r1", "instalado_no_pouso")) == 1)
        check("git status --porcelain vazio",
              git(root, "status", "--porcelain") == "", git(root, "status", "--porcelain"))
        check("o .jsonl foi commitado",
              ".claude/queues/a/until/r1.jsonl" in
              git(root, "diff", "--name-only", before, "HEAD").split())


if __name__ == "__main__":
    test_installs_when_it_closes()
    test_live_other_run_defers()
    test_other_repo_does_not_install()
    test_json_stays_json()
    test_nothing_closed_does_not_install()
    test_two_closed_install_once()
    test_ledger_match_is_by_queue_and_run()
    test_copy_carries_only_new_lines()
    test_install_text_placement()
    test_failed_copy_is_reported()
    test_copy_reaches_every_other_run()
    test_copy_appends_and_keeps_earlier_lines()
    test_copy_carries_every_new_line_in_order()
    test_copy_ends_with_newline_and_each_line_is_json()
    test_failed_copy_message_goes_where_the_install_text_goes()
    test_runs_from_subdir_and_worktree()
    test_closing_commits_what_it_wrote()
    test_two_closed_both_committed_clean_tree()
    test_json_stdout_stays_json_with_commit()
    test_non_cepa_repo_makes_no_commit()
    test_record_written_before_a_failed_write_is_still_committed()
    if FAILURES:
        print(f"\n✗ {len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\n✓ tudo passou")
