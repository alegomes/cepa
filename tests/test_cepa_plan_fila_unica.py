#!/usr/bin/env python3
"""Testes de "Fila única, BACKLOG.md e plan.yaml convergem no plan.yaml"
(BACKLOG.md, decisão do dono em 2026-09-25): os três subcomandos que fazem a
metade mecânica do desenho — `add` (A1), `ordena` (A2) e `divergencia` (A3).

Rode com `python3 tests/test_cepa_plan_fila_unica.py` (só precisa do PyYAML
que o próprio `cepa-plan` usa). Mesma família de `test_common_plan.py`:
COMPORTAMENTO do escritor, com subprocess contra o CLI real, em repos git
temporários.

O que estes testes NÃO provam: que `/board-flow:capture`, `cepa-feedback
triar` ou `/board-flow:drain` de fato chamam estes subcomandos — isso é
prosa/prompt de outro arquivo, e só um run real diz.
"""

import json
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


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def run(repo, *args):
    return subprocess.run([sys.executable, str(CEPA_PLAN)] + list(args),
                          capture_output=True, text=True, cwd=str(repo))


def repo_git(base, nome):
    d = Path(base) / nome
    d.mkdir(parents=True)
    subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
    return d


def item(ident, **kw):
    base = {"id": ident, "title": f"item {ident}", "why": f"porque {ident}",
            "status": "pending", "blocked_by": [], "human_pending": None}
    base.update(kw)
    return base


def escreve_fila(d, itens, nome="fila"):
    """Grava a fila pelo próprio escritor, para o teste não fabricar YAML."""
    p = d / "itens.json"
    p.write_text(json.dumps(itens, ensure_ascii=False), encoding="utf-8")
    r = run(d, "write", nome, "--items", str(p), "--source", "teste",
            "--quando", "2026-09-25", "--repo", ".")
    assert r.returncode == 0, r.stderr
    return d / ".claude" / "programs" / nome / "plan.yaml"


def plano_de(caminho):
    return yaml.safe_load(Path(caminho).read_text(encoding="utf-8"))


def por_id(plan):
    return {i["id"]: i for i in plan["items"]}


def escreve_ondas(d, nome="ondas"):
    p = d / ".claude" / "programs" / nome
    p.mkdir(parents=True)
    (p / "plan.yaml").write_text(
        "schema_version: 2\nmode: parallel-waves\nprogram: ondas\nwaves: []\n")
    return p / "plan.yaml"


# ── add ──────────────────────────────────────────────────────────────────────

def test_add_recusa_fila_inexistente(base):
    d = repo_git(base, "add-sem-fila")
    r = run(d, "add", "fila", "X", "--title", "x", "--repo", ".")
    check("recusa: fila não existe", r.returncode == 2, r.stdout)
    check("a recusa aponta o /common:plan como quem cria a fila",
          "/common:plan" in r.stderr, r.stderr)


def test_add_recusa_plano_de_ondas(base):
    d = repo_git(base, "add-ondas")
    escreve_ondas(d)
    r = run(d, "add", "ondas", "X", "--title", "x", "--repo", ".")
    check("recusa: plano de ondas", r.returncode == 3, r.stdout)


def test_add_sem_antes_de_vai_pro_fim_e_diz_nao_priorizado(base):
    d = repo_git(base, "add-fim")
    alvo = escreve_fila(d, [item("A"), item("B", blocked_by=["A"])])
    r = run(d, "add", "fila", "C", "--title", "terceiro", "--repo", ".")
    check("grava", r.returncode == 0, r.stderr)
    check("diz a posição e o total na saída", "posição 3 de 3" in r.stdout, r.stdout)
    plan = plano_de(alvo)
    check("entra no FIM da fila", [i["id"] for i in plan["items"]] == ["A", "B", "C"])
    novo = por_id(plan)["C"]
    check("`why` carrega a frase 'ainda não priorizado'",
          "ainda não priorizado" in novo["why"], novo["why"])
    check("status pending, human_pending null, evidence null",
          novo["status"] == "pending" and novo["human_pending"] is None
          and novo.get("evidence") is None, novo)


def test_add_com_why_no_fim_preserva_o_why_e_anexa_a_frase(base):
    d = repo_git(base, "add-fim-why")
    alvo = escreve_fila(d, [item("A")])
    r = run(d, "add", "fila", "B", "--title", "b", "--why", "motivo do dono",
            "--repo", ".")
    check("grava", r.returncode == 0, r.stderr)
    why = por_id(plano_de(alvo))["B"]["why"]
    check("guarda o motivo dado", why.startswith("motivo do dono"), why)
    check("e ainda assim marca 'ainda não priorizado'",
          "ainda não priorizado" in why, why)


def test_add_antes_de_exige_why(base):
    d = repo_git(base, "add-antes-sem-why")
    alvo = escreve_fila(d, [item("A"), item("B")])
    r = run(d, "add", "fila", "C", "--title", "c", "--antes-de", "B", "--repo", ".")
    check("recusa `--antes-de` sem `--why`", r.returncode == 2, r.stdout)
    check("a recusa nomeia o motivo (posição sem porquê)",
          "why" in r.stderr, r.stderr)
    check("nada foi gravado", [i["id"] for i in plano_de(alvo)["items"]] == ["A", "B"])


def test_add_antes_de_insere_na_posicao(base):
    d = repo_git(base, "add-antes")
    alvo = escreve_fila(d, [item("A"), item("B"), item("C")])
    r = run(d, "add", "fila", "X", "--title", "x", "--antes-de", "B",
            "--why", "decisão do dono", "--repo", ".")
    check("grava", r.returncode == 0, r.stderr)
    check("diz a posição 2 de 4", "posição 2 de 4" in r.stdout, r.stdout)
    plan = plano_de(alvo)
    check("insere IMEDIATAMENTE antes do alvo, sem tocar nos outros",
          [i["id"] for i in plan["items"]] == ["A", "X", "B", "C"])
    check("o `why` dado é o que fica (não ganha a frase de não-priorizado)",
          por_id(plan)["X"]["why"] == "decisão do dono")


def test_add_recusa_antes_de_inexistente(base):
    d = repo_git(base, "add-antes-fantasma")
    alvo = escreve_fila(d, [item("A")])
    r = run(d, "add", "fila", "X", "--title", "x", "--antes-de", "ZZZ",
            "--why", "w", "--repo", ".")
    check("recusa `--antes-de` para id que não existe", r.returncode == 2, r.stdout)
    check("nomeia o id", "ZZZ" in r.stderr, r.stderr)
    check("nada foi gravado", [i["id"] for i in plano_de(alvo)["items"]] == ["A"])


def test_add_recusa_id_ja_existente_e_nomeia_status(base):
    d = repo_git(base, "add-duplicado")
    alvo = escreve_fila(d, [item("A", status="done")])
    r = run(d, "add", "fila", "A", "--title", "outro", "--why", "w", "--repo", ".")
    check("recusa: id já existe", r.returncode == 4, r.stdout)
    check("a recusa nomeia o status que ele já tem (idempotência)",
          "done" in r.stderr, r.stderr)
    check("nada foi gravado (segue 1 item)", len(plano_de(alvo)["items"]) == 1)


def test_add_recusa_blocked_by_fantasma(base):
    d = repo_git(base, "add-bloqueio-fantasma")
    alvo = escreve_fila(d, [item("A")])
    r = run(d, "add", "fila", "B", "--title", "b", "--why", "w",
            "--blocked-by", "ZZZ", "--repo", ".")
    check("recusa `--blocked-by` para id fora da fila", r.returncode == 2, r.stdout)
    check("nomeia o id fantasma", "ZZZ" in r.stderr, r.stderr)
    check("nada foi gravado", len(plano_de(alvo)["items"]) == 1)


def test_add_blocked_by_valido_e_multiplo(base):
    d = repo_git(base, "add-bloqueio-ok")
    alvo = escreve_fila(d, [item("A"), item("B")])
    r = run(d, "add", "fila", "C", "--title", "c", "--why", "w",
            "--blocked-by", "A,B", "--repo", ".")
    check("grava com múltiplos bloqueios válidos", r.returncode == 0, r.stderr)
    novo = por_id(plano_de(alvo))["C"]
    check("guarda os dois ids em `blocked_by`",
          sorted(novo["blocked_by"]) == ["A", "B"], novo)


def test_add_preserva_cabecalho_escrito_a_mao(base):
    """O cabeçalho do arquivo (comentários) não pode virar vítima do `add`:
    ele usa `abre_plano_para_marcar` + `grava_corpo`, a mesma dupla do
    `start`/`finish`, que preserva o topo do arquivo verbatim."""
    d = repo_git(base, "add-cabecalho")
    alvo = escreve_fila(d, [item("A")])
    original = alvo.read_text(encoding="utf-8")
    cabecalho_original = original[:original.index("schema_version")]
    check("a fila gravada tem um cabeçalho não-trivial",
          "plan.yaml" in cabecalho_original, cabecalho_original)

    run(d, "add", "fila", "B", "--title", "b", "--why", "w", "--repo", ".")
    depois = alvo.read_text(encoding="utf-8")
    cabecalho_depois = depois[:depois.index("schema_version")]
    check("o cabeçalho sobrevive ao `add` sem mudar uma vírgula",
          cabecalho_depois == cabecalho_original, cabecalho_depois)


def test_add_recusa_quando_resultado_falha_na_validacao(base):
    """O `add` roda `valida_plano` no resultado INTEIRO, não só nos campos do
    item novo — uma lacuna que já morava no disco (escrita à mão, ou de uma
    versão anterior do escritor) não pode ser ignorada só porque o item novo
    em si está correto."""
    d = repo_git(base, "add-invalido")
    alvo = escreve_fila(d, [item("A")])
    plan = plano_de(alvo)
    # corrompe o disco à mão: A passa a apontar para um bloqueio fantasma —
    # o `write` nunca deixaria isso entrar, mas o `add` lê o disco como está
    plan["items"][0]["blocked_by"] = ["FANTASMA"]
    alvo.write_text(yaml.dump(plan, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")

    r = run(d, "add", "fila", "B", "--title", "b", "--why", "w", "--repo", ".")
    check("recusa: o resultado (item novo + disco) não passa em valida_plano",
          r.returncode == 2, r.stdout)
    check("a recusa nomeia o bloqueio fantasma pré-existente",
          "FANTASMA" in r.stderr, r.stderr)
    check("nada foi gravado (B não entrou)",
          "B" not in {i["id"] for i in plano_de(alvo)["items"]})


# ── ordena ───────────────────────────────────────────────────────────────────

def test_ordena_recusa_fila_inexistente(base):
    d = repo_git(base, "ordena-sem-fila")
    r = run(d, "ordena", "fila", "--keys", "A,B", "--repo", ".")
    check("recusa: fila não existe (quem chama cai para a ordem do Jira)",
          r.returncode == 2, r.stdout)


def test_ordena_mistura_dentro_e_fora_do_plano(base):
    d = repo_git(base, "ordena")
    escreve_fila(d, [item("A"), item("B"), item("C", status="done")])
    # ordem do Jira: C, ZZZ, A, B (nada a ver com a ordem da fila)
    r = run(d, "ordena", "fila", "--keys", "C,ZZZ,A,B", "--json", "--repo", ".")
    check("ordena", r.returncode == 0, r.stderr)
    out = json.loads(r.stdout)
    chaves = [o["key"] for o in out["ordem"]]
    check("as que estão no plano vêm primeiro, na ordem da FILA (não do Jira)",
          chaves == ["A", "B", "C", "ZZZ"], chaves)
    check("a que não está no plano vem depois, marcada fora_do_plano",
          out["fora_do_plano"] == ["ZZZ"], out["fora_do_plano"])
    por_key = {o["key"]: o for o in out["ordem"]}
    check("cada chave do plano carrega a posição e o status",
          por_key["C"]["posicao"] == 3 and por_key["C"]["status"] == "done",
          por_key["C"])
    check("a chave fora do plano vem com posição e status nulos",
          por_key["ZZZ"]["posicao"] is None and por_key["ZZZ"]["status"] is None,
          por_key["ZZZ"])


# ── divergencia ──────────────────────────────────────────────────────────────

MAPA_BOARD = """\
defaults:
  project_key: WEGO
  status_map:
    to_do: "To Do"
    in_progress: "Doing"
    in_review: "Code Review"
    done: "Concluido"
    wont_do: "Wont Do"
"""


def com_quadro(d):
    (d / "board-flow.yaml").write_text(MAPA_BOARD, encoding="utf-8")


def board(d, cards, missing=(), nome="board.json"):
    f = d / nome
    f.write_text(json.dumps({"cards": cards, "missing": list(missing)}),
                 encoding="utf-8")
    return str(f)


def test_divergencia_sem_board_nem_backlog_so_avisa(base):
    d = repo_git(base, "div-vazio")
    escreve_fila(d, [item("A")])
    r = run(d, "divergencia", "fila", "--json", "--repo", ".")
    check("exit 0 mesmo sem nenhuma das duas entradas", r.returncode == 0, r.stderr)
    out = json.loads(r.stdout)
    check("cards_sem_item vazio, sem --board", out["cards_sem_item"] == [])
    check("secoes_sem_plano vazio, sem --backlog", out["secoes_sem_plano"] == [])
    check("avisa que não avaliou os dois pares",
          any("--board" in a for a in out["avisos"])
          and any("--backlog" in a for a in out["avisos"]), out["avisos"])


def test_divergencia_cards_sem_item(base):
    d = repo_git(base, "div-cards-sem-item")
    com_quadro(d)
    escreve_fila(d, [item("A")])
    arq = board(d, [{"key": "A", "status": "To Do"},
                    {"key": "NOVO", "status": "Doing"},
                    {"key": "FECHADO-SEM-ITEM", "status": "Concluido"}])
    r = run(d, "divergencia", "fila", "--board", arq, "--json", "--repo", ".")
    check("roda", r.returncode == 0, r.stderr)
    out = json.loads(r.stdout)
    chaves = [c["key"] for c in out["cards_sem_item"]]
    check("card aberto sem item no plano aparece",
          chaves == ["NOVO"], chaves)
    check("card FECHADO sem item não entra na lista (só cards ABERTOS)",
          "FECHADO-SEM-ITEM" not in chaves, chaves)


def test_divergencia_itens_com_card_done(base):
    d = repo_git(base, "div-item-done")
    com_quadro(d)
    escreve_fila(d, [item("A"), item("B", status="done"),
                     item("C", status="dropped")])
    arq = board(d, [{"key": "A", "status": "Concluido"},
                    {"key": "B", "status": "Concluido"},
                    {"key": "C", "status": "Concluido"}])
    r = run(d, "divergencia", "fila", "--board", arq, "--json", "--repo", ".")
    out = json.loads(r.stdout)
    ids = [i["id"] for i in out["itens_com_card_done"]]
    check("item não fechado cujo card já é done aparece",
          ids == ["A"], ids)
    check("item já done/dropped não entra (não é divergência nova)",
          "B" not in ids and "C" not in ids, ids)


def test_divergencia_status_desconhecido_vira_aviso_nao_chute(base):
    d = repo_git(base, "div-status-desconhecido")
    com_quadro(d)
    escreve_fila(d, [item("A")])
    arq = board(d, [{"key": "NOVO", "status": "Em Homologação"}])
    r = run(d, "divergencia", "fila", "--board", arq, "--json", "--repo", ".")
    out = json.loads(r.stdout)
    check("não classifica um status que o status_map não conhece",
          out["cards_sem_item"] == [], out)
    check("mas avisa em vez de calar", any("Em Homologação" in a for a in out["avisos"]),
          out["avisos"])


def test_divergencia_secoes_sem_plano_e_plano_inexistente(base):
    d = repo_git(base, "div-backlog")
    escreve_fila(d, [item("A")])
    backlog = d / "BACKLOG.md"
    backlog.write_text(
        "## Com plano válido\n"
        "**Plano:** `fila/A`\n\n"
        "## Sem nenhuma linha de plano\n"
        "texto qualquer, nada de plano registrado aqui\n\n"
        "## Cita um id que não existe na fila\n"
        "**Plano:** `fila/FANTASMA`\n\n"
        "## Está isenta de propósito\n"
        "**Plano:** fora da fila (concluído)\n",
        encoding="utf-8")
    r = run(d, "divergencia", "fila", "--backlog", str(backlog), "--json",
            "--repo", ".")
    check("roda", r.returncode == 0, r.stderr)
    out = json.loads(r.stdout)
    sem_plano = [s["secao"] for s in out["secoes_sem_plano"]]
    check("seção sem `**Plano:**` é listada, com o heading",
          sem_plano == ["Sem nenhuma linha de plano"], sem_plano)
    check("a linha reportada é a do heading",
          out["secoes_sem_plano"][0]["linha"] > 0, out["secoes_sem_plano"])
    inexistentes = [p["secao"] for p in out["plano_inexistente"]]
    check("`**Plano:**` citando id fora da fila é listado",
          inexistentes == ["Cita um id que não existe na fila"], inexistentes)
    check("`**Plano:** fora da fila (...)` está isento, não aparece em nenhuma lista",
          "Está isenta de propósito" not in sem_plano
          and "Está isenta de propósito" not in inexistentes)
    check("seção com plano válido não aparece em nenhuma lista",
          "Com plano válido" not in sem_plano
          and "Com plano válido" not in inexistentes)


def test_divergencia_plano_no_meio_da_linha_nao_e_falso_positivo(base):
    """Regressão do falso positivo medido no BACKLOG.md real (linhas 3390 e
    3426): `**Plano:**` aparece no MEIO de uma linha de campos separados por
    ` · ` (`**Status:** ... · **Plano:** ... · **Lar:** ...`), não sozinho no
    início dela. A versão anterior só procurava a marca no início da linha e
    lia a seção inteira como "sem `**Plano:**`"."""
    d = repo_git(base, "div-plano-meio-linha")
    escreve_fila(d, [item("acceptance-gate-cego-em-worktree")], nome="cepa")
    backlog = d / "BACKLOG.md"
    backlog.write_text(
        "## `acceptance-gate.py` fica cego em worktree e libera Done sem "
        "auditoria\n\n"
        "**Status:** 🔵 ABERTO · **Plano:** "
        "`acceptance-gate-cego-em-worktree` · **Lar:**\n"
        "`common/hooks/acceptance-gate.py` · **Origem:** feedback "
        "`fb-20260919-1`, diagnosticado no card WEGO-2287\n",
        encoding="utf-8")
    r = run(d, "divergencia", "cepa", "--backlog", str(backlog), "--json",
            "--repo", ".")
    check("roda", r.returncode == 0, r.stderr)
    out = json.loads(r.stdout)
    check("a seção NÃO é listada como sem `**Plano:**`",
          out["secoes_sem_plano"] == [], out["secoes_sem_plano"])
    check("o id, achado no meio da linha, existe na fila — sem divergência",
          out["plano_inexistente"] == [], out["plano_inexistente"])


def test_divergencia_id_com_texto_apos_a_crase_de_fechamento(base):
    """Regressão do falso positivo medido no BACKLOG.md real (linhas 484 e
    1749): `**Plano:** \\`cepa/baseline-cega-builds-longos\\` (descartado)` —
    a versão anterior cortava só as crases das PONTAS da linha inteira, então
    a crase de fechamento ficava colada no id (`...longos\\``) e ele nunca
    batia com o id de verdade na fila, mesmo existindo (`dropped`)."""
    d = repo_git(base, "div-plano-texto-apos-crase")
    escreve_fila(d, [item("baseline-cega-builds-longos", status="dropped")],
                nome="cepa")
    backlog = d / "BACKLOG.md"
    backlog.write_text(
        "## Baseline cega para builds longos (> teto de foreground do Bash)\n\n"
        "**Plano:** `cepa/baseline-cega-builds-longos` (descartado)\n\n"
        "**Status:** pendente · **Lar:** `algum arquivo qualquer` "
        "(+ possivelmente outros)\n",
        encoding="utf-8")
    r = run(d, "divergencia", "cepa", "--backlog", str(backlog), "--json",
            "--repo", ".")
    check("roda", r.returncode == 0, r.stderr)
    out = json.loads(r.stdout)
    check("o id com texto solto depois da crase de fechamento resolve certo",
          out["plano_inexistente"] == [], out["plano_inexistente"])


def test_divergencia_ilegivel_recusa(base):
    d = repo_git(base, "div-ilegivel")
    escreve_fila(d, [item("A")])
    r = run(d, "divergencia", "fila", "--board", "/nao/existe.json", "--repo", ".")
    check("exit 2 quando o --board não existe (entrada ilegível, não relatório)",
          r.returncode == 2, r.stdout)


def main():
    with tempfile.TemporaryDirectory() as base:
        for fn in (
            test_add_recusa_fila_inexistente,
            test_add_recusa_plano_de_ondas,
            test_add_sem_antes_de_vai_pro_fim_e_diz_nao_priorizado,
            test_add_com_why_no_fim_preserva_o_why_e_anexa_a_frase,
            test_add_antes_de_exige_why,
            test_add_antes_de_insere_na_posicao,
            test_add_recusa_antes_de_inexistente,
            test_add_recusa_id_ja_existente_e_nomeia_status,
            test_add_recusa_blocked_by_fantasma,
            test_add_blocked_by_valido_e_multiplo,
            test_add_preserva_cabecalho_escrito_a_mao,
            test_add_recusa_quando_resultado_falha_na_validacao,
            test_ordena_recusa_fila_inexistente,
            test_ordena_mistura_dentro_e_fora_do_plano,
            test_divergencia_sem_board_nem_backlog_so_avisa,
            test_divergencia_cards_sem_item,
            test_divergencia_itens_com_card_done,
            test_divergencia_status_desconhecido_vira_aviso_nao_chute,
            test_divergencia_secoes_sem_plano_e_plano_inexistente,
            test_divergencia_plano_no_meio_da_linha_nao_e_falso_positivo,
            test_divergencia_id_com_texto_apos_a_crase_de_fechamento,
            test_divergencia_ilegivel_recusa,
        ):
            print(f"\n{fn.__name__}")
            fn(base)
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
