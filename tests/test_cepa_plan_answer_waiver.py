#!/usr/bin/env python3
"""`cepa-plan responde` converts the waiver PROPOSED by the agent into a waiver.

Origin (BACKLOG.md § "Waiver recorded in the owner's name during an autonomous
run", fb-20261014-3): in an autonomous run the agent records a proposal
(`board-flow/bin/waivers.py` `propor`: `status: proposta`, `autor: null`, `fila`,
`item`) and opens the human route on the item. Only the owner's `responde`, in a terminal,
converts it. The `cepa-plan` conversion is an INLINE TWIN of `waivers.converter` /
`waivers.recusar` (it does not import the module); this test uses the real `waivers` to
write the proposal and to read the result, so it proves the two agree
on the file schema.

Against the real CLI, in a real git repo, in a PTY:
  - "sim: ..." -> without `status`, `autor` = git config user.name, `resposta_do_dono`,
    `proposto_por` preserved, `waivers.aplicavel` matches; plan.yaml committed;
  - "não: ..." -> `status: recusada`, `waivers.carregar` empty;
  - `--mantem` -> stays a proposal; "talvez depois" -> stays a proposal and says so;
  - a proposal of ANOTHER item is not touched.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "board-flow" / "bin"))
from test_cepa_until import item, build_repo  # noqa: E402
from test_cepa_until_decide import CEPA_PLAN, on_tty, items_of  # noqa: E402
import waivers  # noqa: E402

FAILURES = []

ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
for v in ("CEPA_UNTIL_RUN", "CLAUDE_AUTONOMOUS_RUN_ID"):
    ENV.pop(v, None)

REASON, SCOPE = "teste-cego", "PlugSignAdapter"
QUESTION = f"Aceito a dispensa de {SCOPE} por prova interna?"


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                          text=True).stdout.strip()


def builds(tmp, ident="a1", proposal_queue="fila", proposal_item=None):
    """Repo with `ident` blocked + human route, and a proposal tied to it."""
    stuck = item(ident, status="blocked", human_pending=f"Aceitar ou recusar a dispensa de {SCOPE}")
    stuck["owner_question"] = QUESTION
    root = build_repo(tmp, [stuck])
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Dona Fulana"], check=True)
    # The proposal is born as it is born in a run: with the run environment on.
    before = os.environ.get("CEPA_UNTIL_RUN")
    os.environ["CEPA_UNTIL_RUN"] = "1"
    try:
        path = waivers.gravar(str(root), REASON, SCOPE, "o fornecedor não é alcançável",
                              "alegomes", "quando o adapter mudar",
                              fila=proposal_queue, item=proposal_item or ident)
    finally:
        if before is None:
            os.environ.pop("CEPA_UNTIL_RUN")
        else:
            os.environ["CEPA_UNTIL_RUN"] = before
    return root, Path(path)


def answer(root, ident, plain_text, *extra):
    return on_tty([sys.executable, str(CEPA_PLAN), "answer", "fila", ident,
                   "--answer", plain_text, "--repo", str(root)] + list(extra),
                  str(root), env=ENV)


def test_yes_converts_the_proposal_into_a_waiver():
    with tempfile.TemporaryDirectory() as tmp:
        root, path = builds(tmp)
        check("a proposta nasce sem efeito",
              waivers.carregar(str(root)) == [] and len(waivers.propostas(str(root))) == 1)
        rc, out = answer(root, "a1", f"sim: {QUESTION}")
        check("responde sai 0", rc == 0, out)
        check("a saída nomeia a dispensa aceita",
              "dispensa aceita pelo dono: " in out and path.name in out, out)
        d = yaml.safe_load(path.read_text())
        check("sem `status`", "status" not in d, d)
        check("autor = git config user.name", d.get("autor") == "Dona Fulana", d)
        check("resposta_do_dono gravada", str(d.get("resposta_do_dono", "")).startswith("sim:"), d)
        check("proposto_por/proposto_em preservados",
              "alegomes" in str(d.get("proposto_por")) and d.get("proposto_em"), d)
        w = waivers.aplicavel(waivers.carregar(str(root)), REASON, SCOPE)
        check("o `waivers` real aplica a dispensa", bool(w) and w["autor"] == "Dona Fulana", w)
        check("a evidência do item diz que o dono aceitou",
              f"Dispensa {REASON} em {SCOPE}: aceita pelo dono" in items_of(root)["a1"]["evidence"],
              items_of(root)["a1"]["evidence"])
        check("o item voltou para pending", items_of(root)["a1"]["status"] == "pending")
        check("plan.yaml commitado (árvore limpa)",
              git(root, "status", "--porcelain", "--untracked-files=no") == "", git(root, "status", "--porcelain"))
        check("o commit é o da resposta", "owner's answer to a1" in git(root, "log", "-1", "--format=%s"))
        check("o arquivo da dispensa entrou no commit (não está mais sujo)",
              ".claude/waivers" not in git(root, "status", "--porcelain"), git(root, "status", "--porcelain"))


def test_yes_with_explicit_author():
    with tempfile.TemporaryDirectory() as tmp:
        root, path = builds(tmp)
        rc, out = answer(root, "a1", "Sim: aceito", "--author", "alegomes")
        check("responde sai 0 (Sim maiúsculo)", rc == 0, out)
        check("--author vence o git config", yaml.safe_load(path.read_text()).get("autor") == "alegomes")


def test_does_not_refuse_the_proposal():
    with tempfile.TemporaryDirectory() as tmp:
        root, path = builds(tmp)
        rc, out = answer(root, "a1", "não: prova de verdade, sem dispensa")
        check("responde sai 0", rc == 0, out)
        check("a saída diz dispensa recusada", "dispensa recusada: " in out and path.name in out, out)
        d = yaml.safe_load(path.read_text())
        check("status: recusada + resposta do dono",
              d.get("status") == "recusada" and d.get("resposta_do_dono", "").startswith("não"), d)
        check("carregar não enxerga nada", waivers.carregar(str(root)) == [])
        check("...nem como proposta", waivers.propostas(str(root)) == [])


def test_keep_and_answer_without_yes_or_no_leave_the_proposal():
    with tempfile.TemporaryDirectory() as tmp:
        root, path = builds(tmp)
        rc, out = answer(root, "a1", "sim: depois eu vejo", "--keep")
        check("--keep sai 0", rc == 0, out)
        check("...a proposta segue proposta",
              yaml.safe_load(path.read_text()).get("status") == "proposta")
        check("...e a saída diz quantas seguem pendentes", "1 dispensa(s) proposta(s) seguem" in out, out)
        check("...sem dispensa válida", waivers.carregar(str(root)) == [])
    with tempfile.TemporaryDirectory() as tmp:
        root, path = builds(tmp)
        rc, out = answer(root, "a1", "talvez depois")
        check("'talvez depois' sai 0", rc == 0, out)
        d = yaml.safe_load(path.read_text())
        check("...a proposta segue proposta", d.get("status") == "proposta" and d.get("autor") is None, d)
        check("...a saída diz que segue pendente e o que decide",
              "seguem pendente(s)" in out and "sim" in out and "não" in out, out)
        check("...evidência registra 'segue proposta'",
              "segue proposta" in items_of(root)["a1"]["evidence"])


def test_proposal_of_another_item_or_queue_is_not_touched():
    with tempfile.TemporaryDirectory() as tmp:
        root, path = builds(tmp, proposal_item="z9")
        rc, out = answer(root, "a1", "sim: aceito")
        check("responde sai 0", rc == 0, out)
        check("proposta de outro item intacta", yaml.safe_load(path.read_text()).get("status") == "proposta")
    with tempfile.TemporaryDirectory() as tmp:
        root, path = builds(tmp, proposal_queue="outra-fila")
        rc, out = answer(root, "a1", "sim: aceito")
        check("proposta de outra fila intacta", yaml.safe_load(path.read_text()).get("status") == "proposta", out)


def test_without_proposal_answer_proceeds_the_same():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1", status="blocked")])
        rc, out = answer(root, "a1", "sim: pode seguir")
        check("responde sem proposta sai 0", rc == 0 and "dispensa" not in out.lower(), out)


def test_gitignore_in_dot_claude_does_not_break_answer():
    with tempfile.TemporaryDirectory() as tmp:
        root, path = builds(tmp)
        (root / ".gitignore").write_text(".claude/waivers/\n")
        subprocess.run(["git", "-C", str(root), "add", ".gitignore"], check=True)
        subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "ignora"], check=True)
        rc, out = answer(root, "a1", "sim: aceito")
        check("com waivers ignorado o responde sai 0", rc == 0, out)
        check("...a dispensa foi convertida mesmo assim",
              "status" not in yaml.safe_load(path.read_text()))
        check("...e o plan.yaml foi commitado", "owner's answer to a1" in git(root, "log", "-1", "--format=%s"))


def test_broken_yaml_alongside_does_not_crash_answer():
    with tempfile.TemporaryDirectory() as tmp:
        root, path = builds(tmp)
        (path.parent / "quebrado.yaml").write_text("motivo: [unclosed", encoding="utf-8")
        rc, out = answer(root, "a1", "sim: aceito")
        check("com um YAML quebrado ao lado o responde sai 0", rc == 0, out)
        check("...e converte a proposta do item",
              "status" not in yaml.safe_load(path.read_text()))


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
