#!/usr/bin/env python3
"""`cepa-plan responde` converte a dispensa PROPOSTA pelo agente em dispensa.

Origem (BACKLOG.md § "Dispensa (waiver) gravada em nome do dono durante run
autônomo", fb-20261014-3): em run autônomo o agente grava uma proposta
(`board-flow/bin/waivers.py` `propor`: `status: proposta`, `autor: null`, `fila`,
`item`) e abre a rota humana no item. Só o `responde` do dono, num terminal,
converte. A conversão do `cepa-plan` é um GÊMEO INLINE de `waivers.converter` /
`waivers.recusar` (não importa o módulo); este teste usa o `waivers` real para
escrever a proposta e para ler o resultado, então prova que os dois concordam
no esquema do arquivo.

Contra o CLI real, num repo git de verdade, num PTY:
  - "sim: ..." -> sem `status`, `autor` = git config user.name, `resposta_do_dono`,
    `proposto_por` preservado, `waivers.aplicavel` casa; plan.yaml commitado;
  - "não: ..." -> `status: recusada`, `waivers.carregar` vazio;
  - `--mantem` -> segue proposta; "talvez depois" -> segue proposta e diz;
  - proposta de OUTRO item não é tocada.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "board-flow" / "bin"))
from test_cepa_until import item, monta_repo  # noqa: E402
from test_cepa_until_decidir import CEPA_PLAN, em_tty, itens_de  # noqa: E402
import waivers  # noqa: E402

FAILURES = []

ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
for v in ("CEPA_UNTIL_RUN", "CLAUDE_AUTONOMOUS_RUN_ID"):
    ENV.pop(v, None)

MOTIVO, ESCOPO = "teste-cego", "PlugSignAdapter"
PERGUNTA = f"Aceito a dispensa de {ESCOPO} por prova interna?"


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def git(raiz, *args):
    return subprocess.run(["git", "-C", str(raiz), *args], capture_output=True,
                          text=True).stdout.strip()


def monta(tmp, ident="a1", fila_da_proposta="fila", item_da_proposta=None):
    """Repo com `ident` blocked + rota humana, e uma proposta amarrada a ele."""
    travado = item(ident, status="blocked", human_pending=f"Aceitar ou recusar a dispensa de {ESCOPO}")
    travado["owner_question"] = PERGUNTA
    raiz = monta_repo(tmp, [travado])
    subprocess.run(["git", "-C", str(raiz), "config", "user.name", "Dona Fulana"], check=True)
    # A proposta nasce como nasce em run: com o ambiente de run ligado.
    antes = os.environ.get("CEPA_UNTIL_RUN")
    os.environ["CEPA_UNTIL_RUN"] = "1"
    try:
        path = waivers.gravar(str(raiz), MOTIVO, ESCOPO, "o fornecedor não é alcançável",
                              "alegomes", "quando o adapter mudar",
                              fila=fila_da_proposta, item=item_da_proposta or ident)
    finally:
        if antes is None:
            os.environ.pop("CEPA_UNTIL_RUN")
        else:
            os.environ["CEPA_UNTIL_RUN"] = antes
    return raiz, Path(path)


def responde(raiz, ident, texto, *extra):
    return em_tty([sys.executable, str(CEPA_PLAN), "responde", "fila", ident,
                   "--resposta", texto, "--repo", str(raiz)] + list(extra),
                  str(raiz), env=ENV)


def test_sim_converte_a_proposta_em_dispensa():
    with tempfile.TemporaryDirectory() as tmp:
        raiz, path = monta(tmp)
        check("a proposta nasce sem efeito",
              waivers.carregar(str(raiz)) == [] and len(waivers.propostas(str(raiz))) == 1)
        rc, out = responde(raiz, "a1", f"sim: {PERGUNTA}")
        check("responde sai 0", rc == 0, out)
        check("a saída nomeia a dispensa aceita",
              "dispensa aceita pelo dono: " in out and path.name in out, out)
        d = yaml.safe_load(path.read_text())
        check("sem `status`", "status" not in d, d)
        check("autor = git config user.name", d.get("autor") == "Dona Fulana", d)
        check("resposta_do_dono gravada", str(d.get("resposta_do_dono", "")).startswith("sim:"), d)
        check("proposto_por/proposto_em preservados",
              "alegomes" in str(d.get("proposto_por")) and d.get("proposto_em"), d)
        w = waivers.aplicavel(waivers.carregar(str(raiz)), MOTIVO, ESCOPO)
        check("o `waivers` real aplica a dispensa", bool(w) and w["autor"] == "Dona Fulana", w)
        check("a evidência do item diz que o dono aceitou",
              f"Dispensa {MOTIVO} em {ESCOPO}: aceita pelo dono" in itens_de(raiz)["a1"]["evidence"],
              itens_de(raiz)["a1"]["evidence"])
        check("o item voltou para pending", itens_de(raiz)["a1"]["status"] == "pending")
        check("plan.yaml commitado (árvore limpa)",
              git(raiz, "status", "--porcelain", "--untracked-files=no") == "", git(raiz, "status", "--porcelain"))
        check("o commit é o da resposta", "resposta do dono a a1" in git(raiz, "log", "-1", "--format=%s"))
        check("o arquivo da dispensa entrou no commit (não está mais sujo)",
              ".claude/waivers" not in git(raiz, "status", "--porcelain"), git(raiz, "status", "--porcelain"))


def test_sim_com_autor_explicito():
    with tempfile.TemporaryDirectory() as tmp:
        raiz, path = monta(tmp)
        rc, out = responde(raiz, "a1", "Sim: aceito", "--autor", "alegomes")
        check("responde sai 0 (Sim maiúsculo)", rc == 0, out)
        check("--autor vence o git config", yaml.safe_load(path.read_text()).get("autor") == "alegomes")


def test_nao_recusa_a_proposta():
    with tempfile.TemporaryDirectory() as tmp:
        raiz, path = monta(tmp)
        rc, out = responde(raiz, "a1", "não: prova de verdade, sem dispensa")
        check("responde sai 0", rc == 0, out)
        check("a saída diz dispensa recusada", "dispensa recusada: " in out and path.name in out, out)
        d = yaml.safe_load(path.read_text())
        check("status: recusada + resposta do dono",
              d.get("status") == "recusada" and d.get("resposta_do_dono", "").startswith("não"), d)
        check("carregar não enxerga nada", waivers.carregar(str(raiz)) == [])
        check("...nem como proposta", waivers.propostas(str(raiz)) == [])


def test_mantem_e_resposta_sem_sim_nem_nao_deixam_a_proposta():
    with tempfile.TemporaryDirectory() as tmp:
        raiz, path = monta(tmp)
        rc, out = responde(raiz, "a1", "sim: depois eu vejo", "--mantem")
        check("--mantem sai 0", rc == 0, out)
        check("...a proposta segue proposta",
              yaml.safe_load(path.read_text()).get("status") == "proposta")
        check("...e a saída diz quantas seguem pendentes", "1 dispensa(s) proposta(s) seguem" in out, out)
        check("...sem dispensa válida", waivers.carregar(str(raiz)) == [])
    with tempfile.TemporaryDirectory() as tmp:
        raiz, path = monta(tmp)
        rc, out = responde(raiz, "a1", "talvez depois")
        check("'talvez depois' sai 0", rc == 0, out)
        d = yaml.safe_load(path.read_text())
        check("...a proposta segue proposta", d.get("status") == "proposta" and d.get("autor") is None, d)
        check("...a saída diz que segue pendente e o que decide",
              "seguem pendente(s)" in out and "sim" in out and "não" in out, out)
        check("...evidência registra 'segue proposta'",
              "segue proposta" in itens_de(raiz)["a1"]["evidence"])


def test_proposta_de_outro_item_ou_fila_nao_e_tocada():
    with tempfile.TemporaryDirectory() as tmp:
        raiz, path = monta(tmp, item_da_proposta="z9")
        rc, out = responde(raiz, "a1", "sim: aceito")
        check("responde sai 0", rc == 0, out)
        check("proposta de outro item intacta", yaml.safe_load(path.read_text()).get("status") == "proposta")
    with tempfile.TemporaryDirectory() as tmp:
        raiz, path = monta(tmp, fila_da_proposta="outra-fila")
        rc, out = responde(raiz, "a1", "sim: aceito")
        check("proposta de outra fila intacta", yaml.safe_load(path.read_text()).get("status") == "proposta", out)


def test_sem_proposta_o_responde_segue_igual():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1", status="blocked")])
        rc, out = responde(raiz, "a1", "sim: pode seguir")
        check("responde sem proposta sai 0", rc == 0 and "dispensa" not in out.lower(), out)


def test_gitignore_em_dot_claude_nao_quebra_o_responde():
    with tempfile.TemporaryDirectory() as tmp:
        raiz, path = monta(tmp)
        (raiz / ".gitignore").write_text(".claude/waivers/\n")
        subprocess.run(["git", "-C", str(raiz), "add", ".gitignore"], check=True)
        subprocess.run(["git", "-C", str(raiz), "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "ignora"], check=True)
        rc, out = responde(raiz, "a1", "sim: aceito")
        check("com waivers ignorado o responde sai 0", rc == 0, out)
        check("...a dispensa foi convertida mesmo assim",
              "status" not in yaml.safe_load(path.read_text()))
        check("...e o plan.yaml foi commitado", "resposta do dono a a1" in git(raiz, "log", "-1", "--format=%s"))


def test_yaml_quebrado_ao_lado_nao_derruba_o_responde():
    with tempfile.TemporaryDirectory() as tmp:
        raiz, path = monta(tmp)
        (path.parent / "quebrado.yaml").write_text("motivo: [unclosed", encoding="utf-8")
        rc, out = responde(raiz, "a1", "sim: aceito")
        check("com um YAML quebrado ao lado o responde sai 0", rc == 0, out)
        check("...e converte a proposta do item",
              "status" not in yaml.safe_load(path.read_text()))


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
