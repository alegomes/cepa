#!/usr/bin/env python3
"""Every `cepa-plan` write commits the queue or warns that a commit is missing, and
`responde` refuses text that does not answer the route.

Origin (BACKLOG.md § "`cepa-plan responde` leaves `plan.yaml` dirty and accepts
any sentence as an answer", fb-20261015-1 and fb-20261014-4):

  - on 2026-10-15 the owner ran `responde` three times and each time plan.yaml
    stayed modified and uncommitted; an agent committed it later, an answer
    went into someone else's commit with the wrong message, and `cepa-until`, which
    refuses a dirty tree, did not start;
  - on 2026-10-14 an "eu nao entendi a pergunta" said in the chat about something else
    became "Owner's answer" in the evidence of an item.

Behavior, against the real CLI in a real git repo:

  - `responde` and `add` commit only plan.yaml in the same step (`git status`
    clean afterwards); `--no-commit` writes and says a commit is missing;
  - `start` and `finish` warn that a commit is missing (and which command); `--commit`
    commits; inside a run (`CEPA_UNTIL_RUN=1`) the warning says the clone
    stays that way on purpose;
  - a commit with other changes in the tree warns that it took only the queue;
  - `responde "não entendi"`, `"?"`, or a question: exit 6, nothing written, the
    route's question printed; `--forca` writes; the answer built by
    `cepa-until decidir` ("não: <question>?") passes.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import item, build_repo  # noqa: E402
from test_cepa_until_decide import CEPA_PLAN, on_tty, items_of  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                          text=True).stdout.strip()


def status(root):
    return git(root, "status", "--porcelain", "--untracked-files=no")


def last_commit(root):
    return git(root, "log", "-1", "--format=%s")


ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
ENV.pop("CEPA_UNTIL_RUN", None)


def plan(root, *args, env=None):
    return subprocess.run([sys.executable, str(CEPA_PLAN)] + list(args)
                          + ["--repo", str(root)],
                          capture_output=True, text=True, env=env or ENV)


def answer(root, ident, plain_text, *extra):
    return on_tty([sys.executable, str(CEPA_PLAN), "answer", "fila", ident,
                   "--answer", plain_text, "--repo", str(root)] + list(extra),
                  str(root), env=ENV)


def test_answer_commits_only_the_queue_and_leaves_the_tree_clean():
    with tempfile.TemporaryDirectory() as tmp:
        stuck = item("a1", status="blocked")
        stuck["owner_question"] = "Fecho o card?"
        root = build_repo(tmp, [stuck])
        (root / "outro.txt").write_text("x")
        subprocess.run(["git", "-C", str(root), "add", "outro.txt"], check=True)
        subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c",
                        "user.name=t", "commit", "-qm", "outro"], check=True)
        (root / "outro.txt").write_text("y")  # someone else's change, uncommitted
        rc, out = answer(root, "a1", "vira item do checklist")
        check("responde sai 0", rc == 0, out)
        check("o item voltou para pending",
              items_of(root)["a1"]["status"] == "pending")
        check("a fila foi commitada no mesmo passo",
              "owner's answer to a1" in last_commit(root), last_commit(root))
        check("...e a saída nomeia o commit", "commit " in out, out)
        check("o commit levou só a fila: a mudança alheia continua na árvore",
              status(root) == "M outro.txt", status(root))
        check("...e a saída avisa que há outra mudança sem commit",
              "1 outra(s) mudança(s) sem commit" in out, out)


def test_answer_in_clean_repo_leaves_git_status_clean():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a2", human_pending="valide o login")])
        rc, out = answer(root, "a2", "login ok, trilha gravada")
        check("responde sai 0", rc == 0, out)
        check("git status limpo depois do responde", status(root) == "",
              status(root))
        check("a rota fechou", items_of(root)["a2"]["human_pending"] is None)


def test_answer_no_commit_writes_and_says_commit_is_missing():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1", status="blocked")])
        rc, out = answer(root, "a1", "pode seguir", "--no-commit")
        check("responde --no-commit sai 0", rc == 0, out)
        check("a fila ficou modificada", "plan.yaml" in status(root), status(root))
        check("...e a saída diz que falta commitar, com o comando",
              "Falta commitar" in out and "git -C" in out
              and "plan.yaml" in out, out)
        check("nenhum commit novo", last_commit(root) == "base",
              last_commit(root))


def test_answer_refuses_text_that_does_not_answer_the_route():
    with tempfile.TemporaryDirectory() as tmp:
        stuck = item("a1", status="blocked")
        stuck["evidence"] = "sem produção para medir"
        stuck["owner_question"] = "Fecho o card como medir depois do go-live?"
        root = build_repo(tmp, [stuck])
        for plain_text, reason in [
            ("eu nao entendi a pergunta", "pede esclarecimento"),
            ("Não entendi. Como assim?", "pede esclarecimento"),
            ("o que isso quer dizer", "pede esclarecimento"),
            ("?", "só pontuação"),
            ("qual card?", "é uma pergunta"),
        ]:
            rc, out = answer(root, "a1", plain_text)
            check(f"recusa {plain_text!r} com exit 6", rc == 6, (rc, out))
            check(f"...dizendo o motivo ({reason})", reason in out, out)
            check("...e mostrando a pergunta da rota",
                  "a rota pergunta: Fecho o card como medir" in out, out)
            check("...e apontando o --force para o caso raro",
                  "--force" in out, out)
        a1 = items_of(root)["a1"]
        check("nada foi gravado: o item segue blocked", a1["status"] == "blocked")
        check("...com a evidência intacta",
              a1["evidence"] == "sem produção para medir", a1["evidence"])
        check("...e a árvore limpa", status(root) == "", status(root))


def test_answer_force_writes_the_refused_text():
    with tempfile.TemporaryDirectory() as tmp:
        stuck = item("a1", status="blocked")
        stuck["owner_question"] = "Fecho o card?"
        root = build_repo(tmp, [stuck])
        rc, out = answer(root, "a1", "não entendi, mas pode seguir?", "--force")
        check("--force grava", rc == 0, out)
        check("...com o texto na evidência",
              "não entendi, mas pode seguir?" in items_of(root)["a1"]["evidence"])
        check("...e commitado como qualquer resposta", status(root) == "",
              status(root))


def test_decide_answer_passes_even_when_quoting_the_question():
    """`cepa-until decidir` builds 'sim: <question>' / 'não: <question>', and the
    quoted question ends in '?' and may contain 'quer dizer'."""
    with tempfile.TemporaryDirectory() as tmp:
        stuck = item("a1", status="blocked")
        stuck["owner_question"] = "Libero a onda, o que quer dizer rodar sem acompanhar?"
        route = item("a2", human_pending="valide na UI")
        root = build_repo(tmp, [stuck, route])
        rc, out = answer(root, "a1",
                           "não: Libero a onda, o que quer dizer rodar sem "
                           "acompanhar?", "--keep")
        check("'não: <pergunta>?' com --keep passa", rc == 0, out)
        check("...e o item segue blocked", items_of(root)["a1"]["status"] == "blocked")
        rc, out = answer(root, "a2", "sim: valide na UI. Instrução: refaça o login")
        check("'sim: <pergunta>' passa", rc == 0, out)
        check("...e fecha a rota", items_of(root)["a2"]["human_pending"] is None)
        check("respostas curtas de sempre passam ('segue')",
              answer(build_repo(tmp + "/b", [item("a1", status="blocked")]),
                       "a1", "segue")[0] == 0)


def test_adversarial_inputs_in_the_answer_filter():
    """Adversarial level: `not_an_answer` interprets typed text. Edge cases
    that cannot refuse what answers nor accept what does not."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        accepted_cases = [
            ("pode? segue assim", "'?' no meio da frase não é pergunta"),
            ("não liguei", "'não' sem pedido de esclarecimento"),
            ("não sei se vale, mas pode seguir", "'não sei se' não é 'não sei o que'"),
            ("SIM: fecha", "prefixo do decidir em maiúsculas"),
            ("não :  mantém?", "prefixo do decidir com espaço antes dos dois pontos"),
            ("\u00e9 isso a\u00ed", "acentos não derrubam a checagem de palavra"),
            ("SIM: Fecho o card?", "prefixo do decidir em maiúsculas com pergunta no fim"),
            ("\u00e9", "texto só de letra acentuada não é 'só pontuação'"),
        ]
        for i, (plain_text, reason) in enumerate(accepted_cases):
            root = build_repo(str(base / f"ok{i}"), [item("a1", status="blocked")])
            rc, out = answer(root, "a1", plain_text)
            check(f"aceita {plain_text!r} ({reason})", rc == 0, (rc, out))
        refused_cases = [
            ("...", "só pontuação"),
            ("¿?", "só pontuação unicode"),
            ("segue?", "pergunta curta"),
            ("sim? não entendi", "'sim' sem os dois pontos não é o decidir"),
            ("NÃO ENTENDI", "maiúsculas não escapam da regex"),
            ("pode repetir a pergunta", "pedido de repetição"),
        ]
        for i, (plain_text, reason) in enumerate(refused_cases):
            root = build_repo(str(base / f"nao{i}"), [item("a1", status="blocked")])
            rc, out = answer(root, "a1", plain_text)
            check(f"recusa {plain_text!r} ({reason})", rc == 6, (rc, out))
            check("...e não grava", items_of(root)["a1"]["status"] == "blocked")
            check("...e a árvore fica limpa", status(root) == "", status(root))


def test_add_commits_and_no_commit_warns():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        p = plan(root, "add", "fila", "novo", "--title", "um item novo")
        check("add sai 0", p.returncode == 0, p.stderr)
        check("add commita a fila", last_commit(root) == "queue fila: add novo",
              last_commit(root))
        check("...e deixa a árvore limpa", status(root) == "", status(root))
        p = plan(root, "add", "fila", "outro", "--title", "mais um", "--no-commit")
        check("add --no-commit sai 0", p.returncode == 0, p.stderr)
        check("...grava sem commit", "plan.yaml" in status(root), status(root))
        check("...e diz que falta commitar", "Falta commitar" in p.stdout, p.stdout)
        check("...sem commit novo", last_commit(root) == "queue fila: add novo",
              last_commit(root))


def test_start_and_finish_warn_to_commit_and_commit_commits():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        p = plan(root, "start", "fila", "a1")
        check("start sai 0", p.returncode == 0, p.stderr)
        check("start sem --commit avisa que falta commitar, com o comando",
              "Falta commitar" in p.stdout and "git -C" in p.stdout
              and "--commit" in p.stdout, p.stdout)
        check("...e não commitou", last_commit(root) == "base")
        p = plan(root, "finish", "fila", "a1", "--status", "blocked",
                 "--evidence", "condição de fora", "--impede", "falta um acesso de fora",
                 "--commit")
        check("finish --commit sai 0", p.returncode == 0, p.stderr)
        check("...commita a fila", last_commit(root) == "queue fila: a1 -> blocked",
              last_commit(root))
        check("...e deixa a árvore limpa", status(root) == "", status(root))
        env = dict(ENV, CEPA_UNTIL_RUN="1")
        p = plan(root, "start", "fila", "a2", env=env)
        check("dentro de um run, start diz que o clone fica assim de propósito",
              "de propósito" in p.stdout and "Falta commitar" not in p.stdout,
              p.stdout)
        p = plan(root, "finish", "fila", "a2", "--status", "pending",
                 "--evidence", "voltou", env=env)
        check("...e finish também", "de propósito" in p.stdout, p.stdout)
        check("...sem commit nenhum",
              last_commit(root) == "queue fila: a1 -> blocked")


def test_failing_commit_becomes_warning_and_does_not_change_the_exit():
    """Queue outside git (`.claude/programs` ignored): the write happens, the
    commit does not, and the output says so instead of pretending."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        (root / ".gitignore").write_text(".claude/\n")
        subprocess.run(["git", "-C", str(root), "rm", "-rq", "--cached", ".claude"],
                       check=True)
        subprocess.run(["git", "-C", str(root), "add", ".gitignore"], check=True)
        subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c",
                        "user.name=t", "commit", "-qm", "ignora"], check=True)
        p = plan(root, "add", "fila", "novo", "--title", "um item novo")
        check("add com fila ignorada sai 0", p.returncode == 0, p.stderr)
        check("...gravou o item", "novo" in items_of(root), items_of(root).keys())
        check("...e avisa que NÃO commitou", "NÃO commitada" in p.stdout, p.stdout)


def old_answer(root, ident, plain_text, *extra):
    """The name from before 2026-10-23: subcommand `responde` and flag `--resposta`."""
    return on_tty([sys.executable, str(CEPA_PLAN), "responde", "fila", ident,
                   "--resposta", plain_text, "--repo", str(root)] + list(extra),
                  str(root), env=ENV)


def test_old_names_still_work_and_the_commit_says_queue():
    """`cepa-plan responde --resposta` (and --forca/--mantem/--autor) does the same
    as `answer --answer` (--force/--keep/--author); the queue commit starts with
    `queue <name>:`."""
    results = []
    for fn in (answer, old_answer):
        with tempfile.TemporaryDirectory() as tmp:
            stuck = item("a1", status="blocked")
            stuck["owner_question"] = "Fecho o card?"
            root = build_repo(tmp, [stuck])
            rc, out = fn(root, "a1", "sim: pode seguir")
            a1 = items_of(root)["a1"]
            results.append((rc, a1["status"], a1["human_pending"],
                               "pode seguir" in str(a1["evidence"]),
                               last_commit(root), status(root)))
            check(f"{fn.__name__} sai 0", rc == 0, out)
            check(f"{fn.__name__}: o commit começa com `queue fila:`",
                  last_commit(root).startswith("queue fila: "),
                  last_commit(root))
    check("answer --answer e responde --resposta dão o mesmo resultado",
          results[0] == results[1], results)
    with tempfile.TemporaryDirectory() as tmp:
        stuck = item("a1", status="blocked")
        stuck["owner_question"] = "Fecho o card?"
        root = build_repo(tmp, [stuck])
        rc, out = old_answer(root, "a1", "não entendi, mas pode seguir?",
                                  "--forca")
        check("responde --forca (antigo) grava o texto recusado", rc == 0, out)
        root2 = build_repo(tmp + "/b", [item("a1", status="blocked")])
        rc, out = old_answer(root2, "a1", "mantenha travado", "--mantem")
        check("responde --mantem (antigo) segue blocked", rc == 0
              and items_of(root2)["a1"]["status"] == "blocked", out)


def test_order_divergence_and_add_before_with_new_and_old_names():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        for new, old in (("order", "ordena"),):
            n = plan(root, new, "fila", "--keys", "X-1,X-2", "--json")
            o = plan(root, old, "fila", "--keys", "X-1,X-2", "--json")
            check(f"`{new}` e `{old}` saem iguais",
                  n.returncode == 0 == o.returncode and n.stdout == o.stdout != "",
                  (n.stderr, o.stderr))
        n = plan(root, "divergence", "fila", "--json")
        o = plan(root, "divergencia", "fila", "--json")
        check("`divergence` e `divergencia` saem iguais",
              n.returncode == 0 == o.returncode and n.stdout == o.stdout != "",
              (n.stdout, n.stderr, o.stderr))
        p = plan(root, "add", "fila", "n1", "--title", "novo", "--before", "a2",
                 "--why", "porque sim", "--no-commit")
        check("add --before sai 0", p.returncode == 0, p.stderr)
        p = plan(root, "add", "fila", "n2", "--title", "novo2", "--antes-de", "a2",
                 "--why", "porque sim", "--no-commit")
        check("add --antes-de (antigo) sai 0", p.returncode == 0, p.stderr)
        order = list(items_of(root))
        check("os dois entram antes do a2", order == ["a1", "n1", "n2", "a2"], order)


def main():
    for given_name, fn in sorted(globals().items()):
        if given_name.startswith("test_") and callable(fn):
            print(f"\n{given_name}")
            fn()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s): {FAILURES}")
        return 1
    print("\nall green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
