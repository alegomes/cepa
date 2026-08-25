#!/usr/bin/env python3
"""Testes da etapa 3 de "um escritor, três fontes": /common:drain-plan.

Rode com `python3 tests/test_common_drain_plan.py` (só precisa do PyYAML).
Duas famílias, como em test_common_plan.py:

  - COMPORTAMENTO do `common/bin/cepa-plan` nos três subcomandos que o lote
    usa — `queue` (o que dá para executar agora e onde o lote para), `start`
    (a reserva) e `finish` (o desfecho). Cada recusa aqui existe porque a
    falha correspondente reordena a fila ou apaga dívida em silêncio, que são
    as duas coisas que o documento existe para impedir.
  - CONTRATO DE PROSA do `common/commands/drain-plan.md`. O comando é um
    prompt; a única guarda possível sobre uma instrução é mecânica.

O que estes testes NÃO provam: que o comando executa bem um item. Isso é o
flow da topologia, e só um run real diz.
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
CMD = REPO / "common" / "commands" / "drain-plan.md"

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
            "--quando", "2026-08-25", "--repo", ".")
    assert r.returncode == 0, r.stderr
    return d / ".claude" / "programs" / nome / "plan.yaml"


def queue(d, nome="fila", *extra):
    r = run(d, "queue", nome, "--json", "--repo", ".", *extra)
    return r, (json.loads(r.stdout) if r.returncode == 0 else None)


def plano_de(caminho):
    return yaml.safe_load(Path(caminho).read_text(encoding="utf-8"))


def por_id(plan):
    return {i["id"]: i for i in plan["items"]}


# ── queue: o lote e onde ele para ────────────────────────────────────────────

def test_lote_segue_a_ordem_da_fila_e_o_teto(base):
    d = repo_git(base, "ordem")
    escreve_fila(d, [item("A"), item("B"), item("C"), item("D")])
    r, out = queue(d, "fila", "--max", "2")
    check("monta o lote", r.returncode == 0, r.stderr)
    check("o lote sai NA ORDEM da fila, não reordenado",
          [i["id"] for i in out["batch"]] == ["A", "B"], out)
    check("o teto para o lote", out["stop"]["reason"] == "teto", out["stop"])
    check("a parada NOMEIA o item que ficou de fora",
          out["stop"]["item"] == "C", out["stop"])
    check("leva o `why` de cada posição junto",
          out["batch"][0]["why"] == "porque A")
    check("diz quantos pendentes ficaram fora do lote",
          out["totals"]["pendentes_fora_do_lote"] == 2, out["totals"])


def test_item_done_ou_dropped_nao_entra_e_nao_para(base):
    d = repo_git(base, "feitos")
    escreve_fila(d, [item("A", status="done"), item("B", status="dropped"),
                     item("C")])
    _, out = queue(d)
    check("item já fechado não volta para o lote",
          [i["id"] for i in out["batch"]] == ["C"], out)
    check("a fila acabou é um desfecho nomeado",
          out["stop"]["reason"] == "fim-da-fila", out["stop"])


def test_human_pending_aberto_para_o_lote(base):
    """Decisão do dono em 2026-08-25: para. O item seguinte costuma se apoiar
    no que a rota valida, e seguir sem ela constrói sobre o não-conferido."""
    d = repo_git(base, "divida")
    escreve_fila(d, [item("A"),
                     item("B", human_pending="abrir /admin e conferir a recusa"),
                     item("C")])
    _, out = queue(d)
    check("o lote pega o que vem antes da dívida",
          [i["id"] for i in out["batch"]] == ["A"], out)
    check("para na rota humana aberta",
          out["stop"]["reason"] == "human_pending", out["stop"])
    check("a parada REPETE a rota, em vez de só dizer que existe",
          "abrir /admin" in out["stop"]["detail"], out["stop"])


def test_bloqueio_para_o_lote_mas_dependencia_interna_nao(base):
    d = repo_git(base, "bloqueio")
    # B depende de A, que ENTRA no mesmo lote e fecha antes — não é bloqueio.
    escreve_fila(d, [item("A"), item("B", blocked_by=["A"])])
    _, out = queue(d)
    check("dependência de item que já está no lote não trava o lote",
          [i["id"] for i in out["batch"]] == ["A", "B"], out)

    # Agora o bloqueador fica FORA do lote, por causa do teto.
    _, out = queue(d, "fila", "--max", "1")
    check("com o bloqueador fora do lote, o teto é quem para",
          out["stop"]["reason"] == "teto", out["stop"])

    d2 = repo_git(base, "bloqueio2")
    escreve_fila(d2, [item("A", blocked_by=["Z"]), item("Z"), item("C")])
    _, out = queue(d2)
    check("para no primeiro item bloqueado por algo que vem DEPOIS",
          out["stop"]["reason"] == "bloqueado" and out["stop"]["item"] == "A",
          out["stop"])
    check("nomeia o bloqueador", "Z" in out["stop"]["detail"], out["stop"])
    check("não pula o bloqueado para alcançar o de baixo — isso reordenaria "
          "a fila em silêncio", out["batch"] == [], out["batch"])


def test_bloqueador_dropped_avisa_em_vez_de_prender_para_sempre(base):
    d = repo_git(base, "abandonado")
    escreve_fila(d, [item("Z", status="dropped"), item("A", blocked_by=["Z"])])
    _, out = queue(d)
    check("item bloqueado por um `dropped` não fica preso para sempre",
          [i["id"] for i in out["batch"]] == ["A"], out)
    check("mas o abandono é DITO, não absorvido",
          any("dropped" in a for a in out["warnings"]), out["warnings"])


def test_in_progress_para_o_lote(base):
    """A reserva de outra sessão (ou o resto de um run que morreu) não se
    resolve executando por cima."""
    d = repo_git(base, "reservado")
    escreve_fila(d, [item("A", status="in_progress"), item("B")])
    _, out = queue(d)
    check("para no item reservado", out["stop"]["reason"] == "in_progress",
          out["stop"])
    check("a parada oferece as DUAS leituras (outra sessão / run morto)",
          "outra sessão" in out["stop"]["detail"]
          and "morreu" in out["stop"]["detail"], out["stop"])


def test_queue_recusa_ondas_e_fila_inexistente(base):
    d = repo_git(base, "ondas")
    alvo = d / ".claude" / "programs" / "w" / "plan.yaml"
    alvo.parent.mkdir(parents=True)
    alvo.write_text(yaml.dump({"schema_version": 2, "mode": "parallel-waves",
                               "program": "w", "waves": []}), encoding="utf-8")
    r, _ = queue(d, "w")
    check("recusa montar lote sobre um plano de ondas", r.returncode == 3, r.stdout)
    check("manda para o executor certo", "/maestro:run" in r.stderr, r.stderr)

    r, _ = queue(d, "nao-existe")
    check("fila inexistente é exit 2, não estouro", r.returncode == 2, r.stdout)
    check("diz quem escreve a fila", "/common:plan" in r.stderr, r.stderr)


# ── start: a reserva ─────────────────────────────────────────────────────────

def test_start_reserva_e_recusa_reserva_dupla(base):
    d = repo_git(base, "reserva")
    alvo = escreve_fila(d, [item("A"), item("B")])
    r = run(d, "start", "fila", "A", "--repo", ".")
    check("reserva o item", r.returncode == 0, r.stderr)
    check("a reserva é o `in_progress` no disco",
          por_id(plano_de(alvo))["A"]["status"] == "in_progress")

    r = run(d, "start", "fila", "A", "--repo", ".")
    check("recusa reservar o que já está reservado", r.returncode == 5, r.stdout)
    check("a recusa explica o custo (trabalho refeito)",
          "refaz trabalho" in r.stderr, r.stderr)


def test_start_recusa_item_fechado_e_item_com_rota_aberta(base):
    d = repo_git(base, "reserva2")
    escreve_fila(d, [item("A", status="done"),
                     item("B", human_pending="rodar bin/install.sh --clean")])
    r = run(d, "start", "fila", "A", "--repo", ".")
    check("não reserva item que já fechou", r.returncode == 5, r.stdout)
    r = run(d, "start", "fila", "B", "--repo", ".")
    check("não passa por cima de rota humana aberta", r.returncode == 5, r.stdout)
    check("a recusa repete a rota", "install.sh" in r.stderr, r.stderr)
    r = run(d, "start", "fila", "FANTASMA", "--repo", ".")
    check("id que não existe é exit 2", r.returncode == 2, r.stdout)


# ── finish: o desfecho ───────────────────────────────────────────────────────

def test_finish_exige_evidencia(base):
    d = repo_git(base, "desfecho")
    alvo = escreve_fila(d, [item("A")])
    r = run(d, "finish", "fila", "A", "--status", "done", "--evidence", "   ",
            "--repo", ".")
    check("recusa desfecho sem evidência", r.returncode == 2, r.stdout)
    check("a recusa diz por que (a palavra `done` não é auditável sozinha)",
          "auditável" in r.stderr, r.stderr)
    check("nada mudou no disco na recusa",
          por_id(plano_de(alvo))["A"]["status"] == "pending")

    r = run(d, "finish", "fila", "A", "--status", "done",
            "--evidence", "commit abc123, proof PROVEN", "--repo", ".")
    check("grava o desfecho", r.returncode == 0, r.stderr)
    it = por_id(plano_de(alvo))["A"]
    check("status e evidência ficam no item",
          it["status"] == "done" and "abc123" in it["evidence"], it)


def test_finish_abre_divida_mas_nunca_fecha(base):
    """Abrir uma rota é do agente (ele acabou de produzir a coisa a validar);
    fechar é só do humano, que é quem sabe se rodou."""
    d = repo_git(base, "divida2")
    alvo = escreve_fila(d, [item("A"), item("B", human_pending="conferir na UI")])
    r = run(d, "finish", "fila", "A", "--status", "done", "--evidence", "e",
            "--human-pending", "abrir /admin/devolucoes e conferir a recusa",
            "--repo", ".")
    check("o desfecho pode ABRIR uma rota humana", r.returncode == 0, r.stderr)
    check("a rota fica no item",
          "devolucoes" in por_id(plano_de(alvo))["A"]["human_pending"])

    r = run(d, "finish", "fila", "B", "--status", "done", "--evidence", "e",
            "--human-pending", "", "--repo", ".")
    check("recusa FECHAR a rota pelo agente", r.returncode == 2, r.stdout)
    check("a recusa diz que só o humano fecha", "só o humano" in r.stderr, r.stderr)
    check("a rota de B continua aberta no disco",
          por_id(plano_de(alvo))["B"]["human_pending"] == "conferir na UI")

    r = run(d, "finish", "fila", "B", "--status", "done", "--evidence", "e",
            "--repo", ".")
    check("fechar o item sem citar a rota não apaga a rota",
          r.returncode == 0 and
          por_id(plano_de(alvo))["B"]["human_pending"] == "conferir na UI",
          r.stderr)


def test_marcacao_preserva_cabecalho_e_campos_extras(base):
    """Regenerar o cabeçalho a cada item fechado datava o documento com HOJE e
    apagava quando a fila foi escrita; e um campo que o schema não prevê é
    alguém registrando alguma coisa, não lixo."""
    d = repo_git(base, "cabecalho")
    alvo = escreve_fila(d, [item("A", evidence="veio da triagem", extra="xyz"),
                            item("B")])
    antes = alvo.read_text(encoding="utf-8")
    cabecalho = "".join(l for l in antes.splitlines(keepends=True)
                        if l.startswith("#") or not l.strip())
    run(d, "start", "fila", "A", "--repo", ".")
    r = run(d, "finish", "fila", "A", "--status", "blocked",
            "--evidence", "travou no docker ausente", "--repo", ".")
    depois = alvo.read_text(encoding="utf-8")
    check("o cabeçalho escrito à mão sobrevive à marcação",
          depois.startswith(cabecalho.rstrip("\n")), depois[:200])
    check("a data de escrita da fila não é reescrita",
          "2026-08-25" in depois)
    it = por_id(plano_de(alvo))["A"]
    check("campo fora do schema sobrevive", it.get("extra") == "xyz", it)
    check("a evidência nova substitui a antiga, e é a do desfecho",
          it["evidence"] == "travou no docker ausente", it)
    check("o arquivo marcado continua válido para o próprio validador",
          run(d, "validate", str(alvo)).returncode == 0)
    out = queue(d)[1]
    check("item que saiu `blocked` de um run anterior PARA o lote seguinte, "
          "em vez de ser re-executado no mesmo travamento",
          out["stop"]["reason"] == "bloqueado-antes", out["stop"])
    check("a parada repete o motivo registrado no desfecho",
          "docker" in out["stop"]["detail"], out["stop"])


# ── contrato de prosa do comando ─────────────────────────────────────────────

def test_contrato_do_comando(base):
    check("o comando existe", CMD.is_file(), str(CMD))
    if not CMD.is_file():
        return
    f = CMD.read_text(encoding="utf-8")
    # sem crases: a instrução não pode depender de como o markdown a formatou
    limpo = f.replace("`", "").lower()
    check("manda montar o lote pelo cepa-plan, não pelo olho",
          "cepa-plan queue" in f,
          "sem isso a ordem da fila volta a ser interpretada a cada run")
    check("reserva o item antes de executar", "cepa-plan start" in f)
    check("registra o desfecho de cada item", "cepa-plan finish" in f)
    check("proíbe escrever o YAML à mão",
          "edite o plan.yaml à mão" in limpo,
          "sem a proibição, um Write no arquivo contorna TODAS as recusas do "
          "cepa-plan e nenhuma delas dispara")
    check("declara que para em `human_pending` aberto",
          "human_pending" in f and "para" in f)
    check("declara o teto e o default",
          "--max" in f and "3" in f)
    check("declara, como restrição, que não fala com tracker nenhum",
          "não fala com tracker nenhum" in limpo,
          "o lote existe justamente para funcionar sem tracker; sem a restrição "
          "escrita, a primeira fila com chave de card vira transição de Jira")
    check("e não manda delegar ao agente que escreve no Jira",
          "delegue a `atlassian-expert`" not in f
          and "delegate to `atlassian-expert`" not in f)
    check("exige desfecho terminal nomeado por item",
          "BLOCKED" in f and "DEFERRED" in f,
          "item tocado sem desfecho volta na semana seguinte sem ninguém saber "
          "o que houve")
    check("fecha apontando para o /common:next",
          "/common:next" in f)
    check("diz que a fila mora no clone principal",
          "git-common-dir" in f or "clone principal" in f)


def main():
    with tempfile.TemporaryDirectory() as base:
        for fn in (test_lote_segue_a_ordem_da_fila_e_o_teto,
                   test_item_done_ou_dropped_nao_entra_e_nao_para,
                   test_human_pending_aberto_para_o_lote,
                   test_bloqueio_para_o_lote_mas_dependencia_interna_nao,
                   test_bloqueador_dropped_avisa_em_vez_de_prender_para_sempre,
                   test_in_progress_para_o_lote,
                   test_queue_recusa_ondas_e_fila_inexistente,
                   test_start_reserva_e_recusa_reserva_dupla,
                   test_start_recusa_item_fechado_e_item_com_rota_aberta,
                   test_finish_exige_evidencia,
                   test_finish_abre_divida_mas_nunca_fecha,
                   test_marcacao_preserva_cabecalho_e_campos_extras,
                   test_contrato_do_comando):
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
