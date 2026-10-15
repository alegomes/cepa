#!/usr/bin/env python3
"""Toda escrita do `cepa-plan` commita a fila ou avisa que falta commitar, e
`responde` recusa texto que não responde à rota.

Origem (BACKLOG.md § "`cepa-plan responde` deixa o `plan.yaml` sujo e aceita
qualquer frase como resposta", fb-20261015-1 e fb-20261014-4):

  - em 2026-10-15 o dono rodou `responde` três vezes e cada vez o plan.yaml
    ficou modificado e sem commit; um agente commitou depois, uma resposta
    entrou num commit alheio com mensagem errada, e o `cepa-until`, que
    recusa árvore suja, não subiu;
  - em 2026-10-14 um "eu nao entendi a pergunta" dito no chat sobre outra
    coisa virou "Resposta do dono" na evidência de um item.

Comportamento, contra o CLI real num repo git de verdade:

  - `responde` e `add` commitam só o plan.yaml no mesmo passo (`git status`
    limpo depois); `--no-commit` grava e diz que falta commitar;
  - `start` e `finish` avisam que falta commitar (e qual comando); `--commit`
    commita; dentro de um run (`CEPA_UNTIL_RUN=1`) o aviso diz que o clone
    fica assim de propósito;
  - commit com outras mudanças na árvore avisa que levou só a fila;
  - `responde "não entendi"`, `"?"`, ou pergunta: exit 6, nada gravado, a
    pergunta da rota impressa; `--forca` grava; a resposta montada pelo
    `cepa-until decidir` ("não: <pergunta>?") passa.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import item, monta_repo  # noqa: E402
from test_cepa_until_decidir import CEPA_PLAN, em_tty, itens_de  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def git(raiz, *args):
    return subprocess.run(["git", "-C", str(raiz), *args], capture_output=True,
                          text=True).stdout.strip()


def status(raiz):
    return git(raiz, "status", "--porcelain", "--untracked-files=no")


def ultimo_commit(raiz):
    return git(raiz, "log", "-1", "--format=%s")


ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
ENV.pop("CEPA_UNTIL_RUN", None)


def plan(raiz, *args, env=None):
    return subprocess.run([sys.executable, str(CEPA_PLAN)] + list(args)
                          + ["--repo", str(raiz)],
                          capture_output=True, text=True, env=env or ENV)


def responde(raiz, ident, texto, *extra):
    return em_tty([sys.executable, str(CEPA_PLAN), "responde", "fila", ident,
                   "--resposta", texto, "--repo", str(raiz)] + list(extra),
                  str(raiz), env=ENV)


def test_responde_commita_so_a_fila_e_deixa_a_arvore_limpa():
    with tempfile.TemporaryDirectory() as tmp:
        travado = item("a1", status="blocked")
        travado["owner_question"] = "Fecho o card?"
        raiz = monta_repo(tmp, [travado])
        (raiz / "outro.txt").write_text("x")
        subprocess.run(["git", "-C", str(raiz), "add", "outro.txt"], check=True)
        subprocess.run(["git", "-C", str(raiz), "-c", "user.email=t@t", "-c",
                        "user.name=t", "commit", "-qm", "outro"], check=True)
        (raiz / "outro.txt").write_text("y")  # mudança alheia, sem commit
        rc, out = responde(raiz, "a1", "vira item do checklist")
        check("responde sai 0", rc == 0, out)
        check("o item voltou para pending",
              itens_de(raiz)["a1"]["status"] == "pending")
        check("a fila foi commitada no mesmo passo",
              "resposta do dono a a1" in ultimo_commit(raiz), ultimo_commit(raiz))
        check("...e a saída nomeia o commit", "commit " in out, out)
        check("o commit levou só a fila: a mudança alheia continua na árvore",
              status(raiz) == "M outro.txt", status(raiz))
        check("...e a saída avisa que há outra mudança sem commit",
              "1 outra(s) mudança(s) sem commit" in out, out)


def test_responde_em_repo_limpo_deixa_git_status_limpo():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a2", human_pending="valide o login")])
        rc, out = responde(raiz, "a2", "login ok, trilha gravada")
        check("responde sai 0", rc == 0, out)
        check("git status limpo depois do responde", status(raiz) == "",
              status(raiz))
        check("a rota fechou", itens_de(raiz)["a2"]["human_pending"] is None)


def test_responde_no_commit_grava_e_diz_que_falta_commitar():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1", status="blocked")])
        rc, out = responde(raiz, "a1", "pode seguir", "--no-commit")
        check("responde --no-commit sai 0", rc == 0, out)
        check("a fila ficou modificada", "plan.yaml" in status(raiz), status(raiz))
        check("...e a saída diz que falta commitar, com o comando",
              "Falta commitar" in out and "git -C" in out
              and "plan.yaml" in out, out)
        check("nenhum commit novo", ultimo_commit(raiz) == "base",
              ultimo_commit(raiz))


def test_responde_recusa_texto_que_nao_responde_a_rota():
    with tempfile.TemporaryDirectory() as tmp:
        travado = item("a1", status="blocked")
        travado["evidence"] = "sem produção para medir"
        travado["owner_question"] = "Fecho o card como medir depois do go-live?"
        raiz = monta_repo(tmp, [travado])
        for texto, motivo in [
            ("eu nao entendi a pergunta", "pede esclarecimento"),
            ("Não entendi. Como assim?", "pede esclarecimento"),
            ("o que isso quer dizer", "pede esclarecimento"),
            ("?", "só pontuação"),
            ("qual card?", "é uma pergunta"),
        ]:
            rc, out = responde(raiz, "a1", texto)
            check(f"recusa {texto!r} com exit 6", rc == 6, (rc, out))
            check(f"...dizendo o motivo ({motivo})", motivo in out, out)
            check("...e mostrando a pergunta da rota",
                  "a rota pergunta: Fecho o card como medir" in out, out)
            check("...e apontando o --forca para o caso raro",
                  "--forca" in out, out)
        a1 = itens_de(raiz)["a1"]
        check("nada foi gravado: o item segue blocked", a1["status"] == "blocked")
        check("...com a evidência intacta",
              a1["evidence"] == "sem produção para medir", a1["evidence"])
        check("...e a árvore limpa", status(raiz) == "", status(raiz))


def test_responde_forca_grava_o_texto_recusado():
    with tempfile.TemporaryDirectory() as tmp:
        travado = item("a1", status="blocked")
        travado["owner_question"] = "Fecho o card?"
        raiz = monta_repo(tmp, [travado])
        rc, out = responde(raiz, "a1", "não entendi, mas pode seguir?", "--forca")
        check("--forca grava", rc == 0, out)
        check("...com o texto na evidência",
              "não entendi, mas pode seguir?" in itens_de(raiz)["a1"]["evidence"])
        check("...e commitado como qualquer resposta", status(raiz) == "",
              status(raiz))


def test_resposta_do_decidir_passa_mesmo_citando_a_pergunta():
    """O `cepa-until decidir` monta 'sim: <pergunta>' / 'não: <pergunta>', e a
    pergunta citada termina em '?' e pode conter 'quer dizer'."""
    with tempfile.TemporaryDirectory() as tmp:
        travado = item("a1", status="blocked")
        travado["owner_question"] = "Libero a onda, o que quer dizer rodar sem acompanhar?"
        rota = item("a2", human_pending="valide na UI")
        raiz = monta_repo(tmp, [travado, rota])
        rc, out = responde(raiz, "a1",
                           "não: Libero a onda, o que quer dizer rodar sem "
                           "acompanhar?", "--mantem")
        check("'não: <pergunta>?' com --mantem passa", rc == 0, out)
        check("...e o item segue blocked", itens_de(raiz)["a1"]["status"] == "blocked")
        rc, out = responde(raiz, "a2", "sim: valide na UI. Instrução: refaça o login")
        check("'sim: <pergunta>' passa", rc == 0, out)
        check("...e fecha a rota", itens_de(raiz)["a2"]["human_pending"] is None)
        check("respostas curtas de sempre passam ('segue')",
              responde(monta_repo(tmp + "/b", [item("a1", status="blocked")]),
                       "a1", "segue")[0] == 0)


def test_entradas_adversariais_no_filtro_de_resposta():
    """Nível adversarial: o `nao_responde` interpreta texto digitado. Casos de
    borda que não podem recusar o que responde nem aceitar o que não."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        casos_aceitos = [
            ("pode? segue assim", "'?' no meio da frase não é pergunta"),
            ("não liguei", "'não' sem pedido de esclarecimento"),
            ("não sei se vale, mas pode seguir", "'não sei se' não é 'não sei o que'"),
            ("SIM: fecha", "prefixo do decidir em maiúsculas"),
            ("não :  mantém?", "prefixo do decidir com espaço antes dos dois pontos"),
            ("\u00e9 isso a\u00ed", "acentos não derrubam a checagem de palavra"),
            ("SIM: Fecho o card?", "prefixo do decidir em maiúsculas com pergunta no fim"),
            ("\u00e9", "texto só de letra acentuada não é 'só pontuação'"),
        ]
        for i, (texto, motivo) in enumerate(casos_aceitos):
            raiz = monta_repo(str(base / f"ok{i}"), [item("a1", status="blocked")])
            rc, out = responde(raiz, "a1", texto)
            check(f"aceita {texto!r} ({motivo})", rc == 0, (rc, out))
        casos_recusados = [
            ("...", "só pontuação"),
            ("¿?", "só pontuação unicode"),
            ("segue?", "pergunta curta"),
            ("sim? não entendi", "'sim' sem os dois pontos não é o decidir"),
            ("NÃO ENTENDI", "maiúsculas não escapam da regex"),
            ("pode repetir a pergunta", "pedido de repetição"),
        ]
        for i, (texto, motivo) in enumerate(casos_recusados):
            raiz = monta_repo(str(base / f"nao{i}"), [item("a1", status="blocked")])
            rc, out = responde(raiz, "a1", texto)
            check(f"recusa {texto!r} ({motivo})", rc == 6, (rc, out))
            check("...e não grava", itens_de(raiz)["a1"]["status"] == "blocked")
            check("...e a árvore fica limpa", status(raiz) == "", status(raiz))


def test_add_commita_e_no_commit_avisa():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        p = plan(raiz, "add", "fila", "novo", "--title", "um item novo")
        check("add sai 0", p.returncode == 0, p.stderr)
        check("add commita a fila", ultimo_commit(raiz) == "fila fila: add novo",
              ultimo_commit(raiz))
        check("...e deixa a árvore limpa", status(raiz) == "", status(raiz))
        p = plan(raiz, "add", "fila", "outro", "--title", "mais um", "--no-commit")
        check("add --no-commit sai 0", p.returncode == 0, p.stderr)
        check("...grava sem commit", "plan.yaml" in status(raiz), status(raiz))
        check("...e diz que falta commitar", "Falta commitar" in p.stdout, p.stdout)
        check("...sem commit novo", ultimo_commit(raiz) == "fila fila: add novo",
              ultimo_commit(raiz))


def test_start_e_finish_avisam_que_falta_commitar_e_commit_commita():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        p = plan(raiz, "start", "fila", "a1")
        check("start sai 0", p.returncode == 0, p.stderr)
        check("start sem --commit avisa que falta commitar, com o comando",
              "Falta commitar" in p.stdout and "git -C" in p.stdout
              and "--commit" in p.stdout, p.stdout)
        check("...e não commitou", ultimo_commit(raiz) == "base")
        p = plan(raiz, "finish", "fila", "a1", "--status", "blocked",
                 "--evidence", "condição de fora", "--commit")
        check("finish --commit sai 0", p.returncode == 0, p.stderr)
        check("...commita a fila", ultimo_commit(raiz) == "fila fila: a1 -> blocked",
              ultimo_commit(raiz))
        check("...e deixa a árvore limpa", status(raiz) == "", status(raiz))
        env = dict(ENV, CEPA_UNTIL_RUN="1")
        p = plan(raiz, "start", "fila", "a2", env=env)
        check("dentro de um run, start diz que o clone fica assim de propósito",
              "de propósito" in p.stdout and "Falta commitar" not in p.stdout,
              p.stdout)
        p = plan(raiz, "finish", "fila", "a2", "--status", "pending",
                 "--evidence", "voltou", env=env)
        check("...e finish também", "de propósito" in p.stdout, p.stdout)
        check("...sem commit nenhum",
              ultimo_commit(raiz) == "fila fila: a1 -> blocked")


def test_commit_que_falha_vira_aviso_e_nao_muda_o_exit():
    """Fila fora do git (`.claude/programs` ignorado): a escrita acontece, o
    commit não, e a saída diz isso em vez de fingir."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        (raiz / ".gitignore").write_text(".claude/\n")
        subprocess.run(["git", "-C", str(raiz), "rm", "-rq", "--cached", ".claude"],
                       check=True)
        subprocess.run(["git", "-C", str(raiz), "add", ".gitignore"], check=True)
        subprocess.run(["git", "-C", str(raiz), "-c", "user.email=t@t", "-c",
                        "user.name=t", "commit", "-qm", "ignora"], check=True)
        p = plan(raiz, "add", "fila", "novo", "--title", "um item novo")
        check("add com fila ignorada sai 0", p.returncode == 0, p.stderr)
        check("...gravou o item", "novo" in itens_de(raiz), itens_de(raiz).keys())
        check("...e avisa que NÃO commitou", "NÃO commitada" in p.stdout, p.stdout)


def main():
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            print(f"\n{nome}")
            fn()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s): {FAILURES}")
        return 1
    print("\nall green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
