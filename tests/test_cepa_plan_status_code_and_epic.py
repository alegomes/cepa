#!/usr/bin/env python3
"""Two checks `cepa-plan status` makes beyond the text of the queue
(owner, 2026-11-10, fb-20261110-1):

1. Where the item's code is. `evidence` is prose written once, and it goes
   stale: C1-17 of wego-digitacao-backend said "sem merge" after the merge,
   and C1-18 of wego-faturamento-backend had 19 commits on a branch the
   committed queue never named. `status` asks git:
     - a commit cited in `evidence` (or `head_commit`) outside main -> "código
       fora do main"
     - a branch cited in `evidence`, the reservation's branch, or a local
       branch whose name carries the item id, with commits not in main ->
       "código fora do main" with the count
     - everything cited already in main -> `codigo.fora` empty (JSON)
     - the id matches the branch name only as a whole token (C1-1 is not
       C1-18)
     - a done item with code outside main still says so (one extra line)
     - a hex string that is no commit here is ignored
     - a commit brought to main by cherry-pick counts as in main, and the
       same commit cited short and as `head_commit` is listed once

2. Items that entered by `cepa-plan add` have no Epic. `add` writes
   `sem_epic: true`; an older item whose `why` carries the phrase `add`
   writes ("ainda não priorizado: entrou no fim da fila") counts too. The
   status line about ready items leaves them out and counts them apart; the
   JSON carries `prontos` without them and `sem_epic` with their ids; each
   item says `pronto: false` and `pegavel: true` (a run still takes it), and
   the list and `show` print "pegável", never "pronto", for it.

Against the real CLI, in a temporary git repo. Run with
`python3 tests/test_cepa_plan_status_code_and_epic.py`.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    print("✗ precisa de PyYAML (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

REPO = Path(__file__).resolve().parent.parent
CEPA_PLAN = REPO / "common" / "bin" / "cepa-plan"
FAILURES = []
NOT_PRIORITIZED = "ainda não priorizado: entrou no fim da fila"


def check(name, cond, detail=""):
    print(f"  ok  {name}" if cond else f"FAIL  {name}  {detail}")
    if not cond:
        FAILURES.append(name)


def run(repo, *args, screen=False):
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
           "HOME": str(repo)}
    env.update({"CEPA_COR": "sempre", "COLUMNS": "200"} if screen else {"NO_COLOR": "1"})
    return subprocess.run([sys.executable, str(CEPA_PLAN)] + list(args),
                          capture_output=True, text=True, cwd=str(repo), env=env)


def plain(text):
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def commit(root, name):
    (root / name).write_text(name, encoding="utf-8")
    git(root, "add", name)
    git(root, "commit", "-q", "-m", name)
    return git(root, "rev-parse", "HEAD")


def item(ident, status="pending", evidence=None, why="porque", **extra):
    return {"id": ident, "title": f"item {ident}", "why": why,
            "status": status, "blocked_by": [], "human_pending": None,
            "evidence": evidence, **extra}


def write_queue(root, items):
    d = root / ".claude" / "queues" / "q"
    d.mkdir(parents=True, exist_ok=True)
    plan = {"schema_version": 2, "mode": "single-track", "queue": "q",
            "source": "teste", "items": items}
    (d / "queue.yaml").write_text(yaml.safe_dump(plan, allow_unicode=True),
                                  encoding="utf-8")


def setup(tmp):
    root = Path(tmp) / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main", ".")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    on_main = commit(root, "a.txt")
    git(root, "checkout", "-q", "-b", "feat/x")
    off_cited = commit(root, "b.txt")
    git(root, "checkout", "-q", "-b", "until/run-travado-C1-18", "main")
    commit(root, "c.txt")
    commit(root, "d.txt")
    git(root, "checkout", "-q", "-b", "session/C1-1x", "main")
    commit(root, "e.txt")
    git(root, "checkout", "-q", "-b", "side", "main")
    picked = commit(root, "f.txt")
    git(root, "checkout", "-q", "main")
    commit(root, "g.txt")   # main moves, so the cherry-pick gets another hash
    git(root, "cherry-pick", picked)
    git(root, "branch", "-q", "-D", "side")
    return root, on_main, off_cited, picked


def side_commit(root, branch, name, orphan=False):
    """One commit on a new branch off main (or with no parent), back on main."""
    git(root, "checkout", "-q", *(["--orphan", branch] if orphan else ["-b", branch, "main"]))
    sha = commit(root, name)
    git(root, "checkout", "-q", "-f", "main")
    return sha


def code_checks():
    print("código citado contra o main")
    with tempfile.TemporaryDirectory() as tmp:
        root, on_main, off_cited, picked = setup(tmp)
        check("o cherry-pick do teste gerou outro hash",
              git(root, "log", "--format=%H", "main").find(picked) < 0)
        side_commit(root, "wip/reserva", "h.txt")
        side_commit(root, "feat/y", "i.txt")
        only_head = side_commit(root, "solta", "j.txt")
        side_commit(root, "fix/c9-minusculo", "k.txt")
        full = side_commit(root, "longa", "l.txt")
        glued = side_commit(root, "colada", "m.txt")
        orphan = side_commit(root, "orfa", "n.txt", orphan=True)
        # two commits on a branch, only the second cherry-picked into main
        git(root, "checkout", "-q", "-b", "duas", "main")
        commit(root, "o.txt")
        second = commit(root, "p.txt")
        git(root, "checkout", "-q", "main")
        git(root, "cherry-pick", second)
        write_queue(root, [
            item("C1-17", "done", f"código em {on_main[:7]}; sem merge e sem push"),
            item("C2", "pending", "trabalho na branch feat/x, ainda sem merge"),
            item("C1-18", "pending", "evidência antiga, não cita branch"),
            item("C4", "done", f"código em {off_cited[:7]}"),
            item("C5", "pending", "nada citado; deadbeef1 não é commit daqui"),
            item("C1-1", "pending", None),
            item("C7", "done", f"código {picked[:7]}, trazido por cherry-pick"),
            item("C8", "in_progress", None,
                 claimed_by={"session_id": "s", "branch": "wip/reserva",
                             "started_at": "2026-11-10T00:00:00Z"}),
            item("C19", "pending", None, owner_summary="está na branch feat/y"),
            item("C10", "done", f"commit {only_head[:7]}", head_commit=only_head),
            item("C10b", "done", None, head_commit=only_head),
            item("C11", "pending", f"branch feat/x, commit {off_cited[:7]}"),
            item("C12", "pending", None, human_pending="espera o dono"),
            item("C13", "dropped", "branch feat/x"),
            item("C9", "pending", None),
            item("C14", "pending", f"commit {full}"),
            item("C15", "pending", f"zz{glued[:7]} e {glued[:7]}zz não são hash solto"),
            item("C16", "pending", f"commit {orphan[:7]} sem pai"),
            item("C17", "done", f"commit {second[:7]}, só ele foi ao main"),
        ])
        r = run(root, "status", "q", "--json")
        check("status --json sai 0", r.returncode == 0, r.stderr)
        data = json.loads(r.stdout) if r.returncode == 0 else {"items": []}
        by = {i["id"]: i for i in data["items"]}
        c17 = (by.get("C1-17") or {}).get("codigo") or {}
        check("commit citado já no main: nada fora",
              c17.get("fora") == [] and c17.get("no_main"), c17)
        c2 = (by.get("C2") or {}).get("codigo") or {}
        check("branch citada com commit fora do main",
              any("feat/x" in f and "+1" in f for f in c2.get("fora") or []), c2)
        c18 = (by.get("C1-18") or {}).get("codigo") or {}
        check("branch com o id no nome, não citada, aparece com a contagem",
              any("until/run-travado-C1-18" in f and "+2" in f
                  for f in c18.get("fora") or []), c18)
        c4 = (by.get("C4") or {}).get("codigo") or {}
        check("commit citado fora do main (item done)",
              any(off_cited[:7] in f for f in c4.get("fora") or []), c4)
        check("hex que não é commit é ignorado",
              (by.get("C5") or {}).get("codigo") is None, by.get("C5"))
        c11 = (by.get("C1-1") or {}).get("codigo") or {}
        check("id casa o nome da branch só como palavra inteira",
              not any("C1-18" in f for f in c11.get("fora") or [])
              and not any("C1-1x" in f for f in c11.get("fora") or []), c11)

        c7 = (by.get("C7") or {}).get("codigo") or {}
        check("commit trazido ao main por cherry-pick conta como no main",
              c7.get("fora") == [] and c7.get("no_main") == [picked[:7]], c7)
        fora = lambda i: ((by.get(i) or {}).get("codigo") or {}).get("fora")
        check("branch da reserva entra", fora("C8") == ["wip/reserva (+1 commit)"], fora("C8"))
        check("owner_summary é lido", fora("C19") == ["feat/y (+1 commit)"], fora("C19"))
        check("head_commit sozinho é lido", fora("C10b") == [only_head[:12]], fora("C10b"))
        check("o mesmo commit citado curto e em head_commit sai uma vez",
              fora("C10") == [only_head[:7]], fora("C10"))
        check("commit já dentro de branch listada não se repete",
              fora("C11") == ["feat/x (+1 commit)"], fora("C11"))
        check("item descartado não é checado", (by.get("C13") or {}).get("codigo") is None,
              by.get("C13"))
        check("id casa o nome da branch sem diferenciar maiúscula",
              fora("C9") == ["fix/c9-minusculo (+1 commit)"], fora("C9"))
        check("hash de 40 caracteres é lido", fora("C14") == [full[:12]], fora("C14"))
        check("hex colado em letras não é hash", (by.get("C15") or {}).get("codigo") is None,
              by.get("C15"))
        c17 = (by.get("C17") or {}).get("codigo") or {}
        check("só o commit citado conta, não o anterior da branch",
              c17.get("fora") == [] and c17.get("no_main") == [second[:7]], c17)
        check("commit sem pai fora do main ainda é contado", fora("C16") == [orphan[:7]],
              fora("C16"))

        r = run(root, "status", "q")
        out = r.stdout
        check("texto mostra 'código fora do main' no pendente",
              "código fora do main: feat/x (+1 commit)" in out, out)
        check("texto mostra o item done com código fora do main",
              f"código fora do main: {off_cited[:7]}" in out, out)
        check("texto não acusa o C1-17, que está no main",
              "C1-17 — item C1-17\n       código" not in out, out)
        check("plural com mais de um commit",
              "until/run-travado-C1-18 (+2 commits)" in out, out)
        check("pendente com rota humana faz o resumo dizer que os outros esperam",
              "os outros esperam você ou outro item" in out, out)
        show = run(root, "show", "q", "C2").stdout
        check("show mostra o código fora do main",
              "código fora do main: feat/x (+1 commit)" in show, show)
        show = run(root, "status", "q", "C1-17").stdout
        check("status <id> mostra o código no main",
              f"no main: {on_main[:7]}" in show, show)
        screen = plain(run(root, "status", "q", screen=True).stdout)
        check("tela mostra o código fora do main no pendente",
              "código: fora do main: feat/x (+1 commit)" in screen, screen)
        check("tela mostra o código fora do main no item done",
              f"↳ código fora do main: {off_cited[:7]}" in screen, screen)


def fallback_checks():
    print("qual ref é o main")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        root.mkdir()
        git(root, "init", "-q", "-b", "master", ".")
        git(root, "config", "user.email", "t@t")
        git(root, "config", "user.name", "t")
        commit(root, "a.txt")
        git(root, "checkout", "-q", "-b", "feat/x")
        commit(root, "b.txt")
        git(root, "checkout", "-q", "master")
        write_queue(root, [item("M1", "pending", "branch feat/x")])
        data = json.loads(run(root, "status", "q", "--json").stdout)
        c = data["items"][0]["codigo"] or {}
        check("sem main, usa master", c.get("ref") == "master"
              and c.get("fora") == ["feat/x (+1 commit)"], c)

        clone = Path(tmp) / "clone"
        subprocess.run(["git", "clone", "-q", str(root), str(clone)], check=True)
        git(clone, "checkout", "-q", "--detach")
        git(clone, "branch", "-q", "-D", "master")
        git(clone, "branch", "-q", "feat/x", "origin/feat/x")
        write_queue(clone, [item("M1", "pending", "branch feat/x")])
        data = json.loads(run(clone, "status", "q", "--json").stdout)
        c = data["items"][0]["codigo"] or {}
        check("sem main nem master local, usa origin/HEAD",
              c.get("ref") == "origin/HEAD" and c.get("fora") == ["feat/x (+1 commit)"], c)


def epic_checks():
    print("item sem Epic")
    with tempfile.TemporaryDirectory() as tmp:
        root, _, _, _ = setup(tmp)
        write_queue(root, [
            item("E1"),
            item("OLD", why=f"decisão do dono ({NOT_PRIORITIZED})"),
            item("FLAG", why="motivo escrito à mão", sem_epic=True),
            item("FEITO", "done", why=f"x ({NOT_PRIORITIZED})"),
        ])
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "fila")
        r = run(root, "add", "q", "NEW", "--title", "novo", "--no-commit")
        check("add sai 0", r.returncode == 0, r.stderr)
        plan = yaml.safe_load((root / ".claude/queues/q/queue.yaml")
                              .read_text(encoding="utf-8"))
        new = next((i for i in plan["items"] if i["id"] == "NEW"), {})
        check("add grava sem_epic: true", new.get("sem_epic") is True, new)

        r = run(root, "status", "q", "--json")
        data = json.loads(r.stdout) if r.returncode == 0 else {}
        check("prontos não conta os sem Epic", data.get("prontos") == 1, data.get("prontos"))
        check("sem_epic lista os pendentes: pelo flag, pela frase do add, e não o done",
              sorted(data.get("sem_epic") or []) == ["FLAG", "NEW", "OLD"],
              data.get("sem_epic"))
        by = {i["id"]: i for i in data.get("items", [])}
        check("item marca sem_epic no JSON",
              by.get("NEW", {}).get("sem_epic") is True
              and by.get("E1", {}).get("sem_epic") is False, by)
        check("item sem Epic não sai como pronto, sai como pegável",
              by.get("NEW", {}).get("pronto") is False
              and by.get("NEW", {}).get("pegavel") is True
              and by.get("E1", {}).get("pronto") is True, by)

        out = run(root, "status", "q").stdout
        check("linha de prontos conta só o item com Epic",
              "1 de 4 pendentes prontos para o agente: E1\n" in out, out)
        check("sem Epic contado à parte com os ids",
              "3 sem Epic à parte: OLD, FLAG, NEW" in out, out)
        check("item sem Epic marcado na lista",
              out.count("sem Epic: entrou por cepa-plan add") == 3, out)
        check("a lista diz 'pronto' só no item com Epic",
              out.count("pronto: o próximo cepa-until pega") == 1
              and out.count("pegável: não conta como pronto") == 3, out)
        screen = plain(run(root, "status", "q", screen=True).stdout)
        check("tela marca sem Epic e pegável",
              screen.count("↳ sem Epic: entrou por") == 3
              and screen.count("↳ pegável: não conta") == 3, screen)
        show = run(root, "show", "q", "NEW").stdout
        detail = run(root, "status", "q", "NEW").stdout
        check("status <id> traz a linha sem Epic",
              "sem Epic:\n  entrou por cepa-plan add, as decisões de domínio" in detail, detail)
        check("show do item sem Epic não diz pronto",
              "pronto:" not in show and "pegável" in show and "sem Epic" in show, show)


code_checks()
fallback_checks()
epic_checks()
print(f"\n{len(FAILURES)} falha(s)" if FAILURES else "\ntudo verde")
sys.exit(1 if FAILURES else 0)
