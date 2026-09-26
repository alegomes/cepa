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
import os
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
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


def agora_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pid_morto():
    """Um pid que com certeza não responde: um filho já terminado e recolhido."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


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


def test_human_pending_aberto_ADIA_o_item_e_o_lote_segue(base):
    """Decisão do dono em 2026-08-28, revendo a de 08-25: a rota humana não
    barra mais o fluxo. Ela adia o item e é cobrada no fim — travar a fila até
    o humano voltar transformava um lote de 3 num lote de 1."""
    d = repo_git(base, "divida")
    escreve_fila(d, [item("A"),
                     item("B", human_pending="abrir /admin e conferir a recusa"),
                     item("C")])
    _, out = queue(d)
    check("o lote PASSA pela dívida e continua",
          [i["id"] for i in out["batch"]] == ["A", "C"], out)
    check("a rota aberta não vira parada", out["stop"]["reason"] != "human_pending",
          out["stop"])
    check("o item adiado é nomeado, com o motivo",
          [a["id"] for a in out["deferred"]] == ["B"]
          and out["deferred"][0]["reason"] == "human_pending", out["deferred"])
    check("o adiamento REPETE a rota, em vez de só dizer que existe",
          "abrir /admin" in out["deferred"][0]["detail"], out["deferred"])
    check("conta os adiados no resumo", out["totals"]["adiados"] == 1,
          out["totals"])


def test_adiar_um_item_adia_quem_depende_dele(base):
    """Sem cascata, adiar B faria C parar o lote por dependência — e o
    adiamento não teria servido para nada."""
    d = repo_git(base, "cascata")
    escreve_fila(d, [item("A"),
                     item("B", human_pending="conferir à mão"),
                     item("C", blocked_by=["B"]),
                     item("D")])
    _, out = queue(d)
    check("quem depende do adiado é adiado junto",
          [i["id"] for i in out["batch"]] == ["A", "D"], out)
    check("e a cascata é DITA, com o nome do item que ela espera",
          any(a["id"] == "C" and a["reason"] == "depende-de-adiado"
              and "B" in a["detail"] for a in out["deferred"]), out["deferred"])


def test_adiar_nao_reescreve_a_ordem_gravada(base):
    """Adiar é decisão de execução. Reordenar o documento é do /common:plan —
    um executor que mexe na ordem é o que a fila existe para impedir.

    Comparar só o CONTEÚDO não prova isso: o `grava_corpo` é idempotente, então
    um `queue` que regravasse o arquivo com os mesmos bytes passaria calado (o
    gate de prova pegou exatamente essa perturbação sobrevivendo). Por isso o
    teste olha também se o arquivo foi TOCADO — a garantia é que o `queue` não
    escreve, não que ele escreve a mesma coisa.
    """
    d = repo_git(base, "ordem-intacta")
    alvo = escreve_fila(d, [item("A"), item("B", human_pending="rota"), item("C")])
    antes = Path(alvo).read_text(encoding="utf-8")
    marca = os.stat(alvo)
    queue(d)
    depois = os.stat(alvo)
    check("o plan.yaml sai do `queue` byte a byte igual",
          Path(alvo).read_text(encoding="utf-8") == antes)
    check("e o arquivo não foi sequer TOCADO — o `queue` é read-only",
          (depois.st_mtime_ns, depois.st_ino) == (marca.st_mtime_ns, marca.st_ino),
          "o queue regravou o arquivo; conteúdo igual não é o mesmo que não "
          "escrever, e a próxima regravação pode não ser idempotente")


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


def test_reserva_com_dono_vivo_adia_e_NOMEIA_quem_esta_nele(base):
    """A recusa antiga oferecia as duas leituras ("outra sessão, ou run
    morto?") porque o arquivo não sabia responder. Com dono registrado, sabe."""
    d = repo_git(base, "reservado")
    dono = {"session_id": "sessao-viva", "pid": os.getpid(),
            "hostname": socket.gethostname(), "cwd": str(d),
            "started_at": agora_iso()}
    escreve_fila(d, [item("A", status="in_progress", claimed_by=dono), item("B")])
    _, out = queue(d)
    check("o item de outra sessão não para o lote — adia",
          [i["id"] for i in out["batch"]] == ["B"], out)
    check("e o adiamento diz QUEM está nele",
          any(a["id"] == "A" and a["reason"] == "reservado"
              and "sessao-viva" in a["detail"] for a in out["deferred"]),
          out["deferred"])


def test_reserva_orfa_e_recuperada_em_vez_de_travar_a_fila(base):
    """Run morto deixava o item `in_progress` para sempre, e o lote parava ali
    toda vez. Pid morto no mesmo host = reserva órfã, recuperável."""
    d = repo_git(base, "orfa")
    dono = {"session_id": "sessao-morta", "pid": pid_morto(),
            "hostname": socket.gethostname(), "cwd": str(d),
            "started_at": agora_iso()}
    escreve_fila(d, [item("A", status="in_progress", claimed_by=dono), item("B")])
    _, out = queue(d)
    check("a reserva órfã volta a ser executável",
          [i["id"] for i in out["batch"]] == ["A", "B"], out)
    check("mas a recuperação é DITA, não silenciosa",
          any("órfã" in a for a in out["warnings"]), out["warnings"])


def test_reserva_de_outra_maquina_vence_por_idade(base):
    """De outro host não dá para sondar pid — sobra a idade. Sem isso a fila
    trava para sempre por causa de uma máquina que você não está usando."""
    d = repo_git(base, "outro-host")
    velho = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    dono = {"session_id": "sessao-remota", "pid": 999999,
            "hostname": "outra-maquina", "cwd": "/outro/lugar",
            "started_at": velho}
    escreve_fila(d, [item("A", status="in_progress", claimed_by=dono), item("B")])
    _, out = queue(d)
    check("reserva remota além do horizonte é órfã",
          [i["id"] for i in out["batch"]] == ["A", "B"], out)

    novo = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    d2 = repo_git(base, "outro-host-recente")
    escreve_fila(d2, [item("A", status="in_progress",
                           claimed_by=dict(dono, started_at=novo)), item("B")])
    _, out = queue(d2)
    check("reserva remota recente é tratada como viva (não dá para sondar)",
          [i["id"] for i in out["batch"]] == ["B"], out)


def test_in_progress_sem_dono_registrado_adia_e_admite_que_nao_sabe(base):
    """Fila marcada antes do registro de dono existir. Chutar um dos dois lados
    é pior que dizer que não dá para saber."""
    d = repo_git(base, "sem-dono")
    escreve_fila(d, [item("A", status="in_progress"), item("B")])
    _, out = queue(d)
    check("segue o lote sem executar por cima",
          [i["id"] for i in out["batch"]] == ["B"], out)
    check("e diz que a reserva não tem dono registrado",
          any(a["id"] == "A" and "sem dono registrado" in a["detail"]
              for a in out["deferred"]), out["deferred"])


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
    # Decisão do dono 2026-08-30: `blocked` ADIA, não para. Não re-executar
    # continua valendo (seria o mesmo travamento); o que mudou é que ele deixou
    # de travar a fila atrás dele — numa janela desatendida isso custava a noite.
    adiados = {a["id"]: a for a in out["deferred"]}
    check("item que saiu `blocked` de um run anterior é ADIADO, "
          "em vez de ser re-executado no mesmo travamento",
          "A" in adiados and adiados["A"]["reason"] == "bloqueado-antes",
          out["deferred"])
    check("o adiamento repete o motivo registrado no desfecho",
          "docker" in adiados.get("A", {}).get("detail", ""), out["deferred"])
    check("e ele NÃO aparece no lote", "A" not in {i["id"] for i in out["batch"]},
          out["batch"])
    check("e a parada não é mais `bloqueado-antes`",
          out["stop"]["reason"] != "bloqueado-antes", out["stop"])


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
    check("declara que rota humana ADIA o item em vez de parar o lote",
          "human_pending" in f and "adia o item" in limpo,
          "sem isso a prosa volta a mandar parar, e um lote de 3 vira um de 1")
    check("declara a cascata do adiamento",
          "cascata" in limpo,
          "adiar B sem adiar quem depende de B faz o dependente parar o lote, "
          "e o adiamento não serve para nada")
    check("declara que adiar NÃO reescreve a ordem gravada",
          "adiar é execução" in limpo or "não reescreve a ordem" in limpo,
          "um executor que reordena o documento é o que a fila existe para "
          "impedir")
    check("declara o teto e o default",
          "--max" in f and "3" in f)
    check("manda reconciliar com o quadro ANTES de montar o lote",
          "cepa-plan reconcile" in f,
          "sem reconciliar, o lote executa item que alguém já fechou em outro "
          "lugar")
    # Por posição, não por corte de string: `split("### 0.")[-1]` devolve o
    # texto INTEIRO quando o marcador não vem antes do passo 1, e o texto
    # inteiro cita `cepa-plan reconcile` na introdução — a checagem passava por
    # acidente exatamente no caso que ela existe para pegar (o gate de prova
    # inverteu a ordem dos dois passos e viu isto verde).
    i0 = f.find("### 0.")
    i1 = f.find("### 1.")
    check("o passo 0 existe e vem ANTES do passo 1",
          i0 != -1 and i1 != -1 and i0 < i1,
          f"i0={i0} i1={i1}")
    check("e a reconciliação acontece DENTRO dele, antes de resolver a fila",
          i0 != -1 and i1 != -1 and i0 < i1
          and "cepa-plan reconcile" in f[i0:i1],
          "reconciliar DEPOIS de montar o lote não evita executar o que já "
          "fechou em outro lugar — a ordem dos passos é o comportamento")
    check("declara o `--offline` como a condição que desliga quadro",
          "--offline" in f,
          "sem a saída offline declarada, um Jira fora do ar trava o lote "
          "inteiro num repo que sabe rodar sem tracker")
    check("e o --offline desliga as DUAS pontas (leitura e transição)",
          limpo.count("--offline") >= 3,
          "declarar a opção só nas variáveis deixa os passos 0 e 3.d livres "
          "para ignorá-la")
    check("manda transicionar o card ao fechar, quando há quadro",
          "status_map.in_review" in f,
          "sem a transição, cada lote drenado PRODUZ a divergência que a "
          "reconciliação seguinte teria que consertar")
    check("mas a ordem continua vindo da fila, nunca do rank do quadro",
          "a ordem nunca vem do quadro" in limpo,
          "tirar a ordem do board é o /board-flow:drain, que é o que este "
          "comando existe para substituir")
    check("e o Jira é sempre falado pelo agente que tem as ferramentas",
          "atlassian-expert" in f)
    check("exige desfecho terminal nomeado por item",
          "BLOCKED" in f and "DEFERRED" in f,
          "item tocado sem desfecho volta na semana seguinte sem ninguém saber "
          "o que houve")
    check("fecha apontando para o /common:next",
          "/common:next" in f)
    # 2026-08-30: as duas únicas falhas não-triviais do run de 2h no WEGO foram
    # o turno acabando com o build rodando de lado — 34 dos 49 minutos, exit 0
    # nas duas, item `in_progress` sem desfecho. Sob `claude -p` (que é como o
    # `cepa-until` roda cada item) não existe o turno seguinte que ia colher.
    check("proíbe encerrar o turno com build em segundo plano",
          "segundo plano" in limpo and "não há turno seguinte" in limpo,
          "sem a proibição escrita, o agente segue o conselho do no-busy-wait "
          "(mandar para o segundo plano), que só vale em sessão interativa")
    check("e diz o que fazer no lugar: nomear o desfecho antes de parar",
          "build disparado e não colhido" in limpo,
          "proibir sem dar a saída faz o agente escolher outra forma de "
          "silêncio")
    check("e 'esperando o build' não passa como desfecho",
          "esperando o build" in limpo,
          "a tabela de desfechos terminais é o que impede status vestido de "
          "decisão")
    # A prosa é a instrução; o hook é a rede. Só a prosa erode sem nenhum teste
    # ficar vermelho — a lição registrada no próprio cepa-plan.
    plugin = json.loads(
        (REPO / "common" / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    bash = [b for b in plugin["hooks"]["PreToolUse"] if b.get("matcher") == "Bash"]
    check("e a proibição tem rede mecânica registrada no plugin",
          bash and any("no-background-build" in h["command"]
                       for h in bash[0]["hooks"]),
          "prosa sem hook é promessa; o hook é o que dispara quando ela erode")
    check("diz que a fila mora no clone principal",
          "git-common-dir" in f or "clone principal" in f)


def test_start_grava_o_dono_e_o_finish_o_apaga(base):
    """Sem dono gravado, "outra sessão ou run morto?" é indecidível a partir do
    arquivo — que era o estado até 2026-08-28."""
    d = repo_git(base, "assinatura")
    alvo = escreve_fila(d, [item("A")])
    r = run(d, "start", "fila", "A", "--repo", ".")
    check("reserva", r.returncode == 0, r.stderr)
    dono = por_id(plano_de(alvo))["A"].get("claimed_by")
    check("a reserva é assinada", isinstance(dono, dict), dono)
    check("com o que a liveness precisa (pid, host, horário)",
          dono and all(dono.get(k) for k in ("pid", "hostname", "started_at")),
          dono)

    r = run(d, "finish", "fila", "A", "--status", "done",
            "--evidence", "commit abc", "--repo", ".")
    check("fecha", r.returncode == 0, r.stderr)
    check("item fechado não fica reservado por ninguém",
          "claimed_by" not in por_id(plano_de(alvo))["A"],
          por_id(plano_de(alvo))["A"])


def test_start_recupera_reserva_orfa_e_recusa_a_viva(base):
    d = repo_git(base, "reivindica")
    morto = {"session_id": "sessao-morta", "pid": pid_morto(),
             "hostname": socket.gethostname(), "cwd": str(d),
             "started_at": agora_iso()}
    alvo = escreve_fila(d, [item("A", status="in_progress", claimed_by=morto)])
    r = run(d, "start", "fila", "A", "--repo", ".")
    check("reivindica a reserva órfã", r.returncode == 0, r.stderr)
    check("e diz que recuperou, em vez de fingir que estava livre",
          "órfã" in r.stdout, r.stdout)
    check("o dono novo substitui o morto",
          por_id(plano_de(alvo))["A"]["claimed_by"]["session_id"] != "sessao-morta")

    vivo = {"session_id": "sessao-viva", "pid": os.getpid(),
            "hostname": socket.gethostname(), "cwd": str(d),
            "started_at": agora_iso()}
    d2 = repo_git(base, "reivindica2")
    escreve_fila(d2, [item("A", status="in_progress", claimed_by=vivo)])
    r = run(d2, "start", "fila", "A", "--repo", ".")
    check("recusa reservar o que uma sessão viva tem", r.returncode == 5, r.stdout)
    check("e a recusa NOMEIA a sessão, em vez de oferecer duas leituras",
          "sessao-viva" in r.stderr, r.stderr)


# ── reconcile: a fila contra o quadro ────────────────────────────────────────

MAPA = {"defaults": {"project_key": "WEGO", "status_map": {
    "to_do": "To Do", "in_progress": "Doing", "in_review": "Code Review",
    "done": "Concluído", "wont_do": "Won't Do"}}}


def com_quadro(d):
    (d / "board-flow.yaml").write_text(yaml.dump(MAPA, allow_unicode=True),
                                       encoding="utf-8")


def board(d, cards, missing=(), nome="board.json"):
    f = d / nome
    f.write_text(json.dumps({"cards": cards, "missing": list(missing)}),
                 encoding="utf-8")
    return str(f)


def reconcile(d, arquivo, *extra, nome="fila"):
    r = run(d, "reconcile", nome, "--board", arquivo, "--repo", ".", "--json",
            *extra)
    return r, (json.loads(r.stdout) if r.returncode == 0 else None)


def test_reconcile_traz_o_quadro_para_a_fila(base):
    d = repo_git(base, "reconcilia")
    com_quadro(d)
    alvo = escreve_fila(d, [item("W-1"), item("W-2", status="done"),
                            item("W-3"), item("W-4")])
    arq = board(d, [{"key": "W-1", "status": "Concluído"},
                    {"key": "W-2", "status": "Doing"},
                    {"key": "W-3", "status": "To Do"}],
                missing=["W-4"])
    _, out = reconcile(d, arq)
    div = {x["id"]: x["para"] for x in out["divergences"]}
    check("card que fechou fora do plano vira done", div.get("W-1") == "done", div)
    check("card que voltou atrás volta a ser trabalho",
          div.get("W-2") == "pending", div)
    check("bounce é lido como bounce, não como novidade",
          "bounce" in [x for x in out["divergences"] if x["id"] == "W-2"][0]["leitura"],
          out["divergences"])
    check("card em dia não vira divergência", "W-3" in out["in_sync"], out)
    check("card que sumiu do quadro vira dropped", div.get("W-4") == "dropped", div)
    check("sem --apply não grava nada", out["wrote"] is False, out)
    check("o disco continua igual", por_id(plano_de(alvo))["W-1"]["status"] == "pending")

    _, out = reconcile(d, arq, "--apply")
    p2 = por_id(plano_de(alvo))
    check("com --apply grava", p2["W-1"]["status"] == "done", p2["W-1"])
    check("e deixa rastro de que veio do quadro, não do trabalho",
          p2["W-1"]["reconciled"]["board"] == "Concluído", p2["W-1"])
    check("o `why` de cada posição sobrevive à reconciliação",
          p2["W-1"]["why"] == "porque W-1", p2["W-1"])


def test_reconcile_done_em_review_nao_e_bounce(base):
    """Item fechado aqui vai para Review e espera o gate de prova. Ler isso
    como bounce reabriu 8 itens prontos por rodada no run 2026-09-26-1102."""
    d = repo_git(base, "review")
    com_quadro(d)
    alvo = escreve_fila(d, [item("W-1", status="done"),
                            item("W-2", status="done"),
                            item("W-3")])
    arq = board(d, [{"key": "W-1", "status": "Code Review"},
                    {"key": "W-2", "status": "Doing"},
                    {"key": "W-3", "status": "Code Review"}])
    _, out = reconcile(d, arq, "--apply")
    div = {x["id"]: x["para"] for x in out["divergences"]}
    check("done + Code Review fica em dia", "W-1" in out["in_sync"]
          and "W-1" not in div, out)
    check("e continua done no disco",
          por_id(plano_de(alvo))["W-1"]["status"] == "done")
    check("done + Doing continua sendo bounce", div.get("W-2") == "pending", div)
    check("pending + Code Review avisa que alguém pode estar nele",
          any("W-3" in a for a in out["warnings"]), out["warnings"])


def test_reconcile_nunca_anexa_card_nem_fecha_divida_humana(base):
    d = repo_git(base, "limites")
    com_quadro(d)
    alvo = escreve_fila(d, [item("W-1", human_pending="conferir /admin à mão")])
    arq = board(d, [{"key": "W-1", "status": "Concluído"},
                    {"key": "W-9", "status": "To Do"}])
    _, out = reconcile(d, arq, "--apply")
    check("card do quadro sem posição na fila é NOMEADO",
          out["missing_from_plan"] == ["W-9"], out)
    # O relatório dizer que não anexou não prova que o disco não recebeu: o
    # gate de prova viu um `--apply` que anexava passar com este teste verde.
    # Quem responde a pergunta é o plan.yaml gravado.
    no_disco = plano_de(alvo)
    check("e NÃO entra na fila gravada — posição sem `why` é a decisão que a "
          "fila existe para guardar",
          "W-9" not in por_id(no_disco),
          [i["id"] for i in no_disco["items"]])
    it = por_id(no_disco)["W-1"]
    check("a dívida humana continua aberta — só o humano fecha",
          it["human_pending"] == "conferir /admin à mão", it)
    check("e o relatório avisa que a rota humana do que fechou fora não veio",
          any("validação humana" in x["leitura"] for x in out["divergences"]),
          out["divergences"])


def test_reconcile_recusa_status_que_o_mapa_nao_conhece(base):
    d = repo_git(base, "desconhecido")
    com_quadro(d)
    alvo = escreve_fila(d, [item("W-1")])
    arq = board(d, [{"key": "W-1", "status": "Em Homologação"}])
    _, out = reconcile(d, arq, "--apply")
    check("não inventa papel para status fora do status_map",
          out["divergences"] == [], out)
    check("mas diz que não reconciliou, em vez de calar",
          any("Em Homologação" in a for a in out["warnings"]), out["warnings"])
    check("e o item fica como estava",
          por_id(plano_de(alvo))["W-1"]["status"] == "pending")

    d2 = repo_git(base, "sem-quadro")
    escreve_fila(d2, [item("W-1")])
    r, _ = reconcile(d2, board(d2, [{"key": "W-1", "status": "Concluído"}]))
    check("sem board-flow.yaml, recusa em vez de chutar os nomes de status",
          r.returncode == 2, r.stdout)
    check("e diz por quê", "status_map" in r.stderr, r.stderr)


def test_na_branch_da_noite(base):
    """O `cepa-until` passa `--na-branch`. Sem o comando declarar o que isso
    muda, o agente volta a abrir worktree própria a partir de `origin/main`,
    que foi o que deixou 20 de 25 rodadas travadas em 2026-09-23."""
    f = CMD.read_text(encoding="utf-8")
    limpo = f.replace("`", "").lower()
    check("declara --na-branch nos argumentos",
          "--na-branch" in f.split("## Instructions")[0])
    i = limpo.find("na branch da noite (--na-branch")
    trecho = limpo[i:i + 2500] if i != -1 else ""
    check("o passo 3 diz o que muda na branch da noite", bool(trecho))
    check("...não criar worktree nem branch para o item",
          "não crie worktree nem branch" in trecho, trecho[:300])
    check("...não partir de origin/main", "origin/main" in trecho)
    check("...commit direto na branch", "commit direto nesta branch" in trecho)
    check("...sem merge, sem push", "sem merge, sem push" in trecho)
    check("...e confere a branch antes de começar",
          "rev-parse --abbrev-ref head" in trecho)
    i = limpo.find("não rode o build completo")
    regra = limpo[i:i + 1500] if i != -1 else ""
    check("...não roda o build completo, que é do supervisor",
          bool(regra) and "supervisor" in regra, regra[:200])
    check("...roda só os testes focados, dentro do teto de 10 minutos",
          "10 minutos" in regra and "-dtest" in regra, regra[:300])
    check("...e passa a regra aos agentes que delega",
          "qa-engineer" in regra and "validation-lead" in regra, regra[:300])


def main():
    with tempfile.TemporaryDirectory() as base:
        for fn in (test_lote_segue_a_ordem_da_fila_e_o_teto,
                   test_item_done_ou_dropped_nao_entra_e_nao_para,
                   test_human_pending_aberto_ADIA_o_item_e_o_lote_segue,
                   test_adiar_um_item_adia_quem_depende_dele,
                   test_adiar_nao_reescreve_a_ordem_gravada,
                   test_bloqueio_para_o_lote_mas_dependencia_interna_nao,
                   test_bloqueador_dropped_avisa_em_vez_de_prender_para_sempre,
                   test_reserva_com_dono_vivo_adia_e_NOMEIA_quem_esta_nele,
                   test_reserva_orfa_e_recuperada_em_vez_de_travar_a_fila,
                   test_reserva_de_outra_maquina_vence_por_idade,
                   test_in_progress_sem_dono_registrado_adia_e_admite_que_nao_sabe,
                   test_start_grava_o_dono_e_o_finish_o_apaga,
                   test_start_recupera_reserva_orfa_e_recusa_a_viva,
                   test_reconcile_traz_o_quadro_para_a_fila,
                   test_reconcile_done_em_review_nao_e_bounce,
                   test_reconcile_nunca_anexa_card_nem_fecha_divida_humana,
                   test_reconcile_recusa_status_que_o_mapa_nao_conhece,
                   test_queue_recusa_ondas_e_fila_inexistente,
                   test_start_reserva_e_recusa_reserva_dupla,
                   test_start_recusa_item_fechado_e_item_com_rota_aberta,
                   test_finish_exige_evidencia,
                   test_finish_abre_divida_mas_nunca_fecha,
                   test_marcacao_preserva_cabecalho_e_campos_extras,
                   test_na_branch_da_noite,
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
