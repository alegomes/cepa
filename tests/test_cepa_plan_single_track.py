#!/usr/bin/env python3
"""Tests of "Single queue, BACKLOG.md and plan.yaml converge on plan.yaml"
(BACKLOG.md, owner's decision of 2026-09-25): the three subcommands that do the
mechanical half of the design — `add` (A1), `ordena` (A2) and `divergencia` (A3).

Run with `python3 tests/test_cepa_plan_single_track.py` (it only needs the PyYAML
that `cepa-plan` itself uses). Same family as `test_common_plan.py`:
BEHAVIOR of the writer, with subprocess against the real CLI, in temporary
git repos.

What these tests do NOT prove: that `/board-flow:capture`, `cepa-feedback
triar` or `/board-flow:drain` actually call these subcommands — that is
prose/prompt in another file, and only a real run tells.
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


def git_repo(base, given_name):
    d = Path(base) / given_name
    d.mkdir(parents=True)
    subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
    return d


def item(ident, **kw):
    base = {"id": ident, "title": f"item {ident}", "why": f"porque {ident}",
            "status": "pending", "blocked_by": [], "human_pending": None}
    base.update(kw)
    return base


def write_queue(d, items, given_name="fila"):
    """Writes the queue through the writer itself, so the test does not fabricate YAML."""
    p = d / "itens.json"
    p.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    r = run(d, "write", given_name, "--items", str(p), "--source", "teste",
            "--when", "2026-09-25", "--repo", ".")
    assert r.returncode == 0, r.stderr
    return d / ".claude" / "queues" / given_name / "queue.yaml"


def plan_of(path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def by_id(plan):
    return {i["id"]: i for i in plan["items"]}


def write_waves(d, given_name="ondas"):
    p = d / ".claude" / "programs" / given_name
    p.mkdir(parents=True)
    (p / "plan.yaml").write_text(
        "schema_version: 2\nmode: parallel-waves\nprogram: ondas\nwaves: []\n")
    return p / "plan.yaml"


# ── add ──────────────────────────────────────────────────────────────────────

def test_add_refuses_missing_queue(base):
    d = git_repo(base, "add-sem-fila")
    r = run(d, "add", "fila", "X", "--title", "x", "--repo", ".")
    check("recusa: fila não existe", r.returncode == 2, r.stdout)
    check("a recusa aponta o /common:plan como quem cria a fila",
          "/common:queue" in r.stderr, r.stderr)


def test_add_refuses_wave_plan(base):
    d = git_repo(base, "add-ondas")
    write_waves(d)
    r = run(d, "add", "ondas", "X", "--title", "x", "--repo", ".")
    check("recusa: plano de ondas", r.returncode == 3, r.stdout)


def test_add_without_before_goes_to_the_end_and_says_not_prioritized(base):
    d = git_repo(base, "add-fim")
    target = write_queue(d, [item("A"), item("B", blocked_by=["A"])])
    r = run(d, "add", "fila", "C", "--title", "terceiro", "--repo", ".")
    check("grava", r.returncode == 0, r.stderr)
    check("diz a posição e o total na saída", "posição 3 de 3" in r.stdout, r.stdout)
    plan = plan_of(target)
    check("entra no FIM da fila", [i["id"] for i in plan["items"]] == ["A", "B", "C"])
    new = by_id(plan)["C"]
    check("`why` carrega a frase 'ainda não priorizado'",
          "ainda não priorizado" in new["why"], new["why"])
    check("status pending, human_pending null, evidence null",
          new["status"] == "pending" and new["human_pending"] is None
          and new.get("evidence") is None, new)


def test_add_with_why_at_the_end_preserves_the_why_and_appends_the_sentence(base):
    d = git_repo(base, "add-fim-why")
    target = write_queue(d, [item("A")])
    r = run(d, "add", "fila", "B", "--title", "b", "--why", "motivo do dono",
            "--repo", ".")
    check("grava", r.returncode == 0, r.stderr)
    why = by_id(plan_of(target))["B"]["why"]
    check("guarda o motivo dado", why.startswith("motivo do dono"), why)
    check("e ainda assim marca 'ainda não priorizado'",
          "ainda não priorizado" in why, why)


def test_add_before_requires_why(base):
    d = git_repo(base, "add-antes-sem-why")
    target = write_queue(d, [item("A"), item("B")])
    r = run(d, "add", "fila", "C", "--title", "c", "--before", "B", "--repo", ".")
    check("recusa `--before` sem `--why`", r.returncode == 2, r.stdout)
    check("a recusa nomeia o motivo (posição sem porquê)",
          "why" in r.stderr, r.stderr)
    check("nada foi gravado", [i["id"] for i in plan_of(target)["items"]] == ["A", "B"])


def test_add_before_inserts_at_the_position(base):
    d = git_repo(base, "add-antes")
    target = write_queue(d, [item("A"), item("B"), item("C")])
    r = run(d, "add", "fila", "X", "--title", "x", "--before", "B",
            "--why", "decisão do dono", "--repo", ".")
    check("grava", r.returncode == 0, r.stderr)
    check("diz a posição 2 de 4", "posição 2 de 4" in r.stdout, r.stdout)
    plan = plan_of(target)
    check("insere IMEDIATAMENTE antes do alvo, sem tocar nos outros",
          [i["id"] for i in plan["items"]] == ["A", "X", "B", "C"])
    check("o `why` dado é o que fica (não ganha a frase de não-priorizado)",
          by_id(plan)["X"]["why"] == "decisão do dono")


def test_add_refuses_nonexistent_before(base):
    d = git_repo(base, "add-antes-fantasma")
    target = write_queue(d, [item("A")])
    r = run(d, "add", "fila", "X", "--title", "x", "--before", "ZZZ",
            "--why", "w", "--repo", ".")
    check("recusa `--before` para id que não existe", r.returncode == 2, r.stdout)
    check("nomeia o id", "ZZZ" in r.stderr, r.stderr)
    check("nada foi gravado", [i["id"] for i in plan_of(target)["items"]] == ["A"])


def test_add_refuses_existing_id_and_names_status(base):
    d = git_repo(base, "add-duplicado")
    target = write_queue(d, [item("A", status="done")])
    r = run(d, "add", "fila", "A", "--title", "outro", "--why", "w", "--repo", ".")
    check("recusa: id já existe", r.returncode == 4, r.stdout)
    check("a recusa nomeia o status que ele já tem (idempotência)",
          "done" in r.stderr, r.stderr)
    check("nada foi gravado (segue 1 item)", len(plan_of(target)["items"]) == 1)


def test_add_refuses_ghost_blocked_by(base):
    d = git_repo(base, "add-bloqueio-fantasma")
    target = write_queue(d, [item("A")])
    r = run(d, "add", "fila", "B", "--title", "b", "--why", "w",
            "--blocked-by", "ZZZ", "--repo", ".")
    check("recusa `--blocked-by` para id fora da fila", r.returncode == 2, r.stdout)
    check("nomeia o id fantasma", "ZZZ" in r.stderr, r.stderr)
    check("nada foi gravado", len(plan_of(target)["items"]) == 1)


def test_add_valid_and_multiple_blocked_by(base):
    d = git_repo(base, "add-bloqueio-ok")
    target = write_queue(d, [item("A"), item("B")])
    r = run(d, "add", "fila", "C", "--title", "c", "--why", "w",
            "--blocked-by", "A,B", "--repo", ".")
    check("grava com múltiplos bloqueios válidos", r.returncode == 0, r.stderr)
    new = by_id(plan_of(target))["C"]
    check("guarda os dois ids em `blocked_by`",
          sorted(new["blocked_by"]) == ["A", "B"], new)


def test_add_preserves_hand_written_header(base):
    """The file header (comments) must not fall victim to `add`:
    it uses `open_plan_for_marking` + `write_body`, the same pair as
    `start`/`finish`, which preserves the top of the file verbatim."""
    d = git_repo(base, "add-cabecalho")
    target = write_queue(d, [item("A")])
    original = target.read_text(encoding="utf-8")
    original_header = original[:original.index("schema_version")]
    check("a fila gravada tem um cabeçalho não-trivial",
          "queue.yaml" in original_header, original_header)

    run(d, "add", "fila", "B", "--title", "b", "--why", "w", "--repo", ".")
    after = target.read_text(encoding="utf-8")
    header_after = after[:after.index("schema_version")]
    check("o cabeçalho sobrevive ao `add` sem mudar uma vírgula",
          header_after == original_header, header_after)


def test_add_refuses_when_result_fails_validation(base):
    """`add` runs `validate_plan` on the WHOLE result, not only on the fields of the
    new item — a gap that already lived on disk (written by hand, or by an
    earlier version of the writer) cannot be ignored just because the new item
    itself is correct."""
    d = git_repo(base, "add-invalido")
    target = write_queue(d, [item("A")])
    plan = plan_of(target)
    # corrupt the disk by hand: A now points to a ghost block —
    # `write` would never let this in, but `add` reads the disk as it is
    plan["items"][0]["blocked_by"] = ["FANTASMA"]
    target.write_text(yaml.dump(plan, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")

    r = run(d, "add", "fila", "B", "--title", "b", "--why", "w", "--repo", ".")
    check("recusa: o resultado (item novo + disco) não passa em validate_plan",
          r.returncode == 2, r.stdout)
    check("a recusa nomeia o bloqueio fantasma pré-existente",
          "FANTASMA" in r.stderr, r.stderr)
    check("nada foi gravado (B não entrou)",
          "B" not in {i["id"] for i in plan_of(target)["items"]})


# ── ordena ───────────────────────────────────────────────────────────────────

def test_order_refuses_missing_queue(base):
    d = git_repo(base, "ordena-sem-fila")
    r = run(d, "order", "fila", "--keys", "A,B", "--repo", ".")
    check("recusa: fila não existe (quem chama cai para a ordem do Jira)",
          r.returncode == 2, r.stdout)


def test_order_mixes_inside_and_outside_the_plan(base):
    d = git_repo(base, "ordena")
    write_queue(d, [item("A"), item("B"), item("C", status="done")])
    # Jira order: C, ZZZ, A, B (nothing to do with the queue order)
    r = run(d, "order", "fila", "--keys", "C,ZZZ,A,B", "--json", "--repo", ".")
    check("ordena", r.returncode == 0, r.stderr)
    out = json.loads(r.stdout)
    keys = [o["key"] for o in out["ordem"]]
    check("as que estão no plano vêm primeiro, na ordem da FILA (não do Jira)",
          keys == ["A", "B", "C", "ZZZ"], keys)
    check("a que não está no plano vem depois, marcada fora_do_plano",
          out["fora_do_plano"] == ["ZZZ"], out["fora_do_plano"])
    by_key = {o["key"]: o for o in out["ordem"]}
    check("cada chave do plano carrega a posição e o status",
          by_key["C"]["posicao"] == 3 and by_key["C"]["status"] == "done",
          by_key["C"])
    check("a chave fora do plano vem com posição e status nulos",
          by_key["ZZZ"]["posicao"] is None and by_key["ZZZ"]["status"] is None,
          by_key["ZZZ"])


# ── divergencia ──────────────────────────────────────────────────────────────

BOARD_MAP = """\
defaults:
  project_key: WEGO
  status_map:
    to_do: "To Do"
    in_progress: "Doing"
    in_review: "Code Review"
    done: "Concluido"
    wont_do: "Wont Do"
"""


def with_board(d):
    (d / "board-flow.yaml").write_text(BOARD_MAP, encoding="utf-8")


def board(d, cards, missing=(), given_name="board.json"):
    f = d / given_name
    f.write_text(json.dumps({"cards": cards, "missing": list(missing)}),
                 encoding="utf-8")
    return str(f)


def test_divergence_without_board_nor_backlog_only_warns(base):
    d = git_repo(base, "div-vazio")
    write_queue(d, [item("A")])
    r = run(d, "divergence", "fila", "--json", "--repo", ".")
    check("exit 0 mesmo sem nenhuma das duas entradas", r.returncode == 0, r.stderr)
    out = json.loads(r.stdout)
    check("cards_sem_item vazio, sem --board", out["cards_sem_item"] == [])
    check("secoes_sem_plano vazio, sem --backlog", out["secoes_sem_plano"] == [])
    check("avisa que não avaliou os dois pares",
          any("--board" in a for a in out["avisos"])
          and any("--backlog" in a for a in out["avisos"]), out["avisos"])


def test_divergence_cards_without_item(base):
    d = git_repo(base, "div-cards-sem-item")
    with_board(d)
    write_queue(d, [item("A")])
    fname = board(d, [{"key": "A", "status": "To Do"},
                    {"key": "NOVO", "status": "Doing"},
                    {"key": "FECHADO-SEM-ITEM", "status": "Concluido"}])
    r = run(d, "divergence", "fila", "--board", fname, "--json", "--repo", ".")
    check("roda", r.returncode == 0, r.stderr)
    out = json.loads(r.stdout)
    keys = [c["key"] for c in out["cards_sem_item"]]
    check("card aberto sem item no plano aparece",
          keys == ["NOVO"], keys)
    check("card FECHADO sem item não entra na lista (só cards ABERTOS)",
          "FECHADO-SEM-ITEM" not in keys, keys)


def test_divergence_items_with_done_card(base):
    d = git_repo(base, "div-item-done")
    with_board(d)
    write_queue(d, [item("A"), item("B", status="done"),
                     item("C", status="dropped")])
    fname = board(d, [{"key": "A", "status": "Concluido"},
                    {"key": "B", "status": "Concluido"},
                    {"key": "C", "status": "Concluido"}])
    r = run(d, "divergence", "fila", "--board", fname, "--json", "--repo", ".")
    out = json.loads(r.stdout)
    ids = [i["id"] for i in out["itens_com_card_done"]]
    check("item não fechado cujo card já é done aparece",
          ids == ["A"], ids)
    check("item já done/dropped não entra (não é divergência nova)",
          "B" not in ids and "C" not in ids, ids)


def test_divergence_unknown_status_becomes_warning_not_guess(base):
    d = git_repo(base, "div-status-desconhecido")
    with_board(d)
    write_queue(d, [item("A")])
    fname = board(d, [{"key": "NOVO", "status": "Em Homologação"}])
    r = run(d, "divergence", "fila", "--board", fname, "--json", "--repo", ".")
    out = json.loads(r.stdout)
    check("não classifica um status que o status_map não conhece",
          out["cards_sem_item"] == [], out)
    check("mas avisa em vez de calar", any("Em Homologação" in a for a in out["avisos"]),
          out["avisos"])


def test_divergence_sections_without_plan_and_missing_plan(base):
    d = git_repo(base, "div-backlog")
    write_queue(d, [item("A")])
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
    r = run(d, "divergence", "fila", "--backlog", str(backlog), "--json",
            "--repo", ".")
    check("roda", r.returncode == 0, r.stderr)
    out = json.loads(r.stdout)
    without_plan = [s["secao"] for s in out["secoes_sem_plano"]]
    check("seção sem `**Plano:**` é listada, com o heading",
          without_plan == ["Sem nenhuma linha de plano"], without_plan)
    check("a linha reportada é a do heading",
          out["secoes_sem_plano"][0]["linha"] > 0, out["secoes_sem_plano"])
    missing_ones = [p["secao"] for p in out["plano_inexistente"]]
    check("`**Plano:**` citando id fora da fila é listado",
          missing_ones == ["Cita um id que não existe na fila"], missing_ones)
    check("`**Plano:** fora da fila (...)` está isento, não aparece em nenhuma lista",
          "Está isenta de propósito" not in without_plan
          and "Está isenta de propósito" not in missing_ones)
    check("seção com plano válido não aparece em nenhuma lista",
          "Com plano válido" not in without_plan
          and "Com plano válido" not in missing_ones)


def test_divergence_plan_mid_line_is_not_false_positive(base):
    """Regression of the false positive measured in the real BACKLOG.md (lines 3390 and
    3426): `**Plano:**` appears in the MIDDLE of a line of fields separated by
    ` · ` (`**Status:** ... · **Plano:** ... · **Lar:** ...`), not alone at the
    start of it. The previous version only looked for the mark at the start of the line and
    read the whole section as "without `**Plano:**`"."""
    d = git_repo(base, "div-plano-meio-linha")
    write_queue(d, [item("acceptance-gate-cego-em-worktree")], given_name="cepa")
    backlog = d / "BACKLOG.md"
    backlog.write_text(
        "## `acceptance-gate.py` fica cego em worktree e libera Done sem "
        "auditoria\n\n"
        "**Status:** 🔵 ABERTO · **Plano:** "
        "`acceptance-gate-cego-em-worktree` · **Lar:**\n"
        "`common/hooks/acceptance-gate.py` · **Origem:** feedback "
        "`fb-20260919-1`, diagnosticado no card WEGO-2287\n",
        encoding="utf-8")
    r = run(d, "divergence", "cepa", "--backlog", str(backlog), "--json",
            "--repo", ".")
    check("roda", r.returncode == 0, r.stderr)
    out = json.loads(r.stdout)
    check("a seção NÃO é listada como sem `**Plano:**`",
          out["secoes_sem_plano"] == [], out["secoes_sem_plano"])
    check("o id, achado no meio da linha, existe na fila — sem divergência",
          out["plano_inexistente"] == [], out["plano_inexistente"])


def test_divergence_id_with_text_after_the_closing_backtick(base):
    """Regression of the false positive measured in the real BACKLOG.md (lines 484 and
    1749): `**Plano:** \\`cepa/baseline-cega-builds-longos\\` (descartado)` —
    the previous version only cut the backticks at the ENDS of the whole line, so
    the closing backtick stayed stuck to the id (`...longos\\``) and it never
    matched the real id in the queue, even though it existed (`dropped`)."""
    d = git_repo(base, "div-plano-texto-apos-crase")
    write_queue(d, [item("baseline-cega-builds-longos", status="dropped")],
                given_name="cepa")
    backlog = d / "BACKLOG.md"
    backlog.write_text(
        "## Baseline cega para builds longos (> teto de foreground do Bash)\n\n"
        "**Plano:** `cepa/baseline-cega-builds-longos` (descartado)\n\n"
        "**Status:** pendente · **Lar:** `algum arquivo qualquer` "
        "(+ possivelmente outros)\n",
        encoding="utf-8")
    r = run(d, "divergence", "cepa", "--backlog", str(backlog), "--json",
            "--repo", ".")
    check("roda", r.returncode == 0, r.stderr)
    out = json.loads(r.stdout)
    check("o id com texto solto depois da crase de fechamento resolve certo",
          out["plano_inexistente"] == [], out["plano_inexistente"])


def test_divergence_unreadable_refuses(base):
    d = git_repo(base, "div-ilegivel")
    write_queue(d, [item("A")])
    r = run(d, "divergence", "fila", "--board", "/nao/existe.json", "--repo", ".")
    check("exit 2 quando o --board não existe (entrada ilegível, não relatório)",
          r.returncode == 2, r.stdout)


def main():
    with tempfile.TemporaryDirectory() as base:
        for fn in (
            test_add_refuses_missing_queue,
            test_add_refuses_wave_plan,
            test_add_without_before_goes_to_the_end_and_says_not_prioritized,
            test_add_with_why_at_the_end_preserves_the_why_and_appends_the_sentence,
            test_add_before_requires_why,
            test_add_before_inserts_at_the_position,
            test_add_refuses_nonexistent_before,
            test_add_refuses_existing_id_and_names_status,
            test_add_refuses_ghost_blocked_by,
            test_add_valid_and_multiple_blocked_by,
            test_add_preserves_hand_written_header,
            test_add_refuses_when_result_fails_validation,
            test_order_refuses_missing_queue,
            test_order_mixes_inside_and_outside_the_plan,
            test_divergence_without_board_nor_backlog_only_warns,
            test_divergence_cards_without_item,
            test_divergence_items_with_done_card,
            test_divergence_unknown_status_becomes_warning_not_guess,
            test_divergence_sections_without_plan_and_missing_plan,
            test_divergence_plan_mid_line_is_not_false_positive,
            test_divergence_id_with_text_after_the_closing_backtick,
            test_divergence_unreadable_refuses,
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
