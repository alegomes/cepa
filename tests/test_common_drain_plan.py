#!/usr/bin/env python3
"""Tests of stage 3 of "one writer, three sources": /common:drain-plan.

Run with `python3 tests/test_common_drain_plan.py` (it only needs PyYAML).
Two families, as in test_common_plan.py:

  - BEHAVIOR of `common/bin/cepa-plan` in the three subcommands the batch
    uses — `queue` (what can be executed now and where the batch stops), `start`
    (the reservation) and `finish` (the outcome). Each refusal here exists because
    the corresponding failure reorders the queue or erases debt in silence, which are
    the two things the document exists to prevent.
  - PROSE CONTRACT of `common/commands/drain-plan.md`. The command is a
    prompt; the only possible guard over an instruction is mechanical.

What these tests do NOT prove: that the command executes an item well. That is the
topology's flow, and only a real run tells.
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


def git_repo(base, given_name):
    d = Path(base) / given_name
    d.mkdir(parents=True)
    subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
    # DUR-2: `finish --status done` needs a clean tree and a HEAD to record.
    subprocess.run(["git", "-C", str(d), "-c", "user.email=t@t", "-c", "user.name=t",
                    "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty",
                    "-m", "init"], check=True)
    return d


def commit_all(d):
    """DUR-2: `done` needs a clean tree, so fixtures commit what they created."""
    subprocess.run(["git", "-C", str(d), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(d), "-c", "user.email=t@t", "-c", "user.name=t",
                    "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty",
                    "-m", "fixture"], check=True)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dead_pid():
    """A pid that certainly does not respond: a child already finished and reaped."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def item(ident, **kw):
    base = {"id": ident, "title": f"item {ident}", "why": f"porque {ident}",
            "status": "pending", "blocked_by": [], "human_pending": None}
    base.update(kw)
    return base


def write_queue(d, item_list, given_name="fila"):
    """Writes the queue through the writer itself, so the test does not fabricate YAML."""
    p = d / "itens.json"
    p.write_text(json.dumps(item_list, ensure_ascii=False), encoding="utf-8")
    r = run(d, "write", given_name, "--items", str(p), "--source", "teste",
            "--quando", "2026-08-25", "--repo", ".")
    assert r.returncode == 0, r.stderr
    p.unlink()  # DUR-2: a leftover untracked fixture would make the tree dirty
    return d / ".claude" / "queues" / given_name / "queue.yaml"


def queue(d, given_name="fila", *extra):
    r = run(d, "queue", given_name, "--json", "--repo", ".", *extra)
    return r, (json.loads(r.stdout) if r.returncode == 0 else None)


def plan_of(path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def by_id(plan):
    return {i["id"]: i for i in plan["items"]}


# ── queue: the batch and where it stops ──────────────────────────────────────

def test_batch_follows_the_queue_order_and_the_ceiling(base):
    d = git_repo(base, "ordem")
    write_queue(d, [item("A"), item("B"), item("C"), item("D")])
    r, out = queue(d, "fila", "--max", "2")
    check("monta o lote", r.returncode == 0, r.stderr)
    check("o lote sai NA ORDEM da fila, não reordenado",
          [i["id"] for i in out["batch"]] == ["A", "B"], out)
    check("o teto para o lote", out["stop"]["reason"] == "cap", out["stop"])
    check("a parada NOMEIA o item que ficou de fora",
          out["stop"]["item"] == "C", out["stop"])
    check("leva o `why` de cada posição junto",
          out["batch"][0]["why"] == "porque A")
    check("diz quantos pendentes ficaram fora do lote",
          out["totals"]["pendentes_fora_do_lote"] == 2, out["totals"])


def test_done_or_dropped_item_does_not_enter_and_does_not_stop(base):
    d = git_repo(base, "feitos")
    write_queue(d, [item("A", status="done"), item("B", status="dropped"),
                     item("C")])
    _, out = queue(d)
    check("item já fechado não volta para o lote",
          [i["id"] for i in out["batch"]] == ["C"], out)
    check("a fila acabou é um desfecho nomeado",
          out["stop"]["reason"] == "end-of-queue", out["stop"])


def test_open_human_pending_DEFERS_the_item_and_the_batch_goes_on(base):
    """Owner's decision on 2026-08-28, revising that of 08-25: the human route no longer
    blocks the flow. It defers the item and is charged at the end — jamming the queue until
    the human came back turned a batch of 3 into a batch of 1."""
    d = git_repo(base, "divida")
    write_queue(d, [item("A"),
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


def test_deferring_an_item_defers_whoever_depends_on_it(base):
    """Without a cascade, deferring B would make C stop the batch through dependency — and the
    deferral would have served nothing."""
    d = git_repo(base, "cascata")
    write_queue(d, [item("A"),
                     item("B", human_pending="conferir à mão"),
                     item("C", blocked_by=["B"]),
                     item("D")])
    _, out = queue(d)
    check("quem depende do adiado é adiado junto",
          [i["id"] for i in out["batch"]] == ["A", "D"], out)
    check("e a cascata é DITA, com o nome do item que ela espera",
          any(a["id"] == "C" and a["reason"] == "depends-on-deferred"
              and "B" in a["detail"] for a in out["deferred"]), out["deferred"])


def test_deferring_does_not_rewrite_the_recorded_order(base):
    """Deferring is an execution decision. Reordering the document belongs to /common:plan —
    an executor that touches the order is what the queue exists to prevent.

    Comparing only the CONTENT does not prove this: `write_body` is idempotent, so
    a `queue` that rewrote the file with the same bytes would pass silently (the
    proof gate caught exactly that perturbation surviving). That is why the
    test also looks at whether the file was TOUCHED — the guarantee is that `queue` does not
    write, not that it writes the same thing.
    """
    d = git_repo(base, "ordem-intacta")
    target = write_queue(d, [item("A"), item("B", human_pending="rota"), item("C")])
    before = Path(target).read_text(encoding="utf-8")
    mark = os.stat(target)
    queue(d)
    after = os.stat(target)
    check("o plan.yaml sai do `queue` byte a byte igual",
          Path(target).read_text(encoding="utf-8") == before)
    check("e o arquivo não foi sequer TOCADO — o `queue` é read-only",
          (after.st_mtime_ns, after.st_ino) == (mark.st_mtime_ns, mark.st_ino),
          "o queue regravou o arquivo; conteúdo igual não é o mesmo que não "
          "escrever, e a próxima regravação pode não ser idempotente")


def test_block_stops_the_batch_but_internal_dependency_does_not(base):
    d = git_repo(base, "bloqueio")
    # B depends on A, which ENTERS the same batch and closes first — it is not a block.
    write_queue(d, [item("A"), item("B", blocked_by=["A"])])
    _, out = queue(d)
    check("dependência de item que já está no lote não trava o lote",
          [i["id"] for i in out["batch"]] == ["A", "B"], out)

    # Now the blocker is OUTSIDE the batch, because of the ceiling.
    _, out = queue(d, "fila", "--max", "1")
    check("com o bloqueador fora do lote, o teto é quem para",
          out["stop"]["reason"] == "cap", out["stop"])

    d2 = git_repo(base, "bloqueio2")
    write_queue(d2, [item("A", blocked_by=["Z"]), item("Z"), item("C")])
    _, out = queue(d2)
    check("para no primeiro item bloqueado por algo que vem DEPOIS",
          out["stop"]["reason"] == "blocked" and out["stop"]["item"] == "A",
          out["stop"])
    check("nomeia o bloqueador", "Z" in out["stop"]["detail"], out["stop"])
    check("não pula o bloqueado para alcançar o de baixo — isso reordenaria "
          "a fila em silêncio", out["batch"] == [], out["batch"])


def test_dropped_blocker_warns_instead_of_holding_forever(base):
    d = git_repo(base, "abandonado")
    write_queue(d, [item("Z", status="dropped"), item("A", blocked_by=["Z"])])
    _, out = queue(d)
    check("item bloqueado por um `dropped` não fica preso para sempre",
          [i["id"] for i in out["batch"]] == ["A"], out)
    check("mas o abandono é DITO, não absorvido",
          any("dropped" in a for a in out["warnings"]), out["warnings"])


def test_reservation_with_live_owner_defers_and_NAMES_who_is_on_it(base):
    """The old refusal offered both readings ("another session, or dead
    run?") because the file did not know how to answer. With a registered owner, it does."""
    d = git_repo(base, "reservado")
    owner = {"session_id": "sessao-viva", "pid": os.getpid(),
            "hostname": socket.gethostname(), "cwd": str(d),
            "started_at": now_iso()}
    write_queue(d, [item("A", status="in_progress", claimed_by=owner), item("B")])
    _, out = queue(d)
    check("o item de outra sessão não para o lote — adia",
          [i["id"] for i in out["batch"]] == ["B"], out)
    check("e o adiamento diz QUEM está nele",
          any(a["id"] == "A" and a["reason"] == "reserved"
              and "sessao-viva" in a["detail"] for a in out["deferred"]),
          out["deferred"])


def test_orphan_reservation_is_recovered_instead_of_blocking_the_queue(base):
    """A dead run left the item `in_progress` forever, and the batch stopped there
    every time. Dead pid on the same host = orphan reservation, recoverable."""
    d = git_repo(base, "orfa")
    owner = {"session_id": "sessao-morta", "pid": dead_pid(),
            "hostname": socket.gethostname(), "cwd": str(d),
            "started_at": now_iso()}
    write_queue(d, [item("A", status="in_progress", claimed_by=owner), item("B")])
    _, out = queue(d)
    check("a reserva órfã volta a ser executável",
          [i["id"] for i in out["batch"]] == ["A", "B"], out)
    check("mas a recuperação é DITA, não silenciosa",
          any("órfã" in a for a in out["warnings"]), out["warnings"])


def test_reservation_from_another_machine_expires_by_age(base):
    """From another host the pid cannot be probed — only the age is left. Without it the queue
    jams forever because of a machine you are not using."""
    d = git_repo(base, "outro-host")
    old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    owner = {"session_id": "sessao-remota", "pid": 999999,
            "hostname": "outra-maquina", "cwd": "/outro/lugar",
            "started_at": old}
    write_queue(d, [item("A", status="in_progress", claimed_by=owner), item("B")])
    _, out = queue(d)
    check("reserva remota além do horizonte é órfã",
          [i["id"] for i in out["batch"]] == ["A", "B"], out)

    new = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    d2 = git_repo(base, "outro-host-recente")
    write_queue(d2, [item("A", status="in_progress",
                           claimed_by=dict(owner, started_at=new)), item("B")])
    _, out = queue(d2)
    check("reserva remota recente é tratada como viva (não dá para sondar)",
          [i["id"] for i in out["batch"]] == ["B"], out)


def test_in_progress_without_registered_owner_defers_and_admits_not_knowing(base):
    """Queue marked before the owner record existed. Guessing one of the two sides
    is worse than saying it cannot be known."""
    d = git_repo(base, "sem-dono")
    write_queue(d, [item("A", status="in_progress"), item("B")])
    _, out = queue(d)
    check("segue o lote sem executar por cima",
          [i["id"] for i in out["batch"]] == ["B"], out)
    check("e diz que a reserva não tem dono registrado",
          any(a["id"] == "A" and "sem dono registrado" in a["detail"]
              for a in out["deferred"]), out["deferred"])


def test_queue_refuses_waves_and_missing_queue(base):
    d = git_repo(base, "ondas")
    target = d / ".claude" / "programs" / "w" / "plan.yaml"
    target.parent.mkdir(parents=True)
    target.write_text(yaml.dump({"schema_version": 2, "mode": "parallel-waves",
                               "program": "w", "waves": []}), encoding="utf-8")
    r, _ = queue(d, "w")
    check("recusa montar lote sobre um plano de ondas", r.returncode == 3, r.stdout)
    check("manda para o executor certo", "/maestro:run" in r.stderr, r.stderr)

    r, _ = queue(d, "nao-existe")
    check("fila inexistente é exit 2, não estouro", r.returncode == 2, r.stdout)
    check("diz quem escreve a fila", "/common:queue" in r.stderr, r.stderr)


# ── start: the reservation ───────────────────────────────────────────────────

def test_start_reserves_and_refuses_double_reservation(base):
    d = git_repo(base, "reserva")
    target = write_queue(d, [item("A"), item("B")])
    r = run(d, "start", "fila", "A", "--repo", ".")
    check("reserva o item", r.returncode == 0, r.stderr)
    check("a reserva é o `in_progress` no disco",
          by_id(plan_of(target))["A"]["status"] == "in_progress")

    r = run(d, "start", "fila", "A", "--repo", ".")
    check("recusa reservar o que já está reservado", r.returncode == 5, r.stdout)
    check("a recusa explica o custo (trabalho refeito)",
          "refaz trabalho" in r.stderr, r.stderr)


def test_start_refuses_closed_item_and_item_with_open_route(base):
    d = git_repo(base, "reserva2")
    write_queue(d, [item("A", status="done"),
                     item("B", human_pending="rodar bin/install.sh --clean")])
    r = run(d, "start", "fila", "A", "--repo", ".")
    check("não reserva item que já fechou", r.returncode == 5, r.stdout)
    r = run(d, "start", "fila", "B", "--repo", ".")
    check("não passa por cima de rota humana aberta", r.returncode == 5, r.stdout)
    check("a recusa repete a rota", "install.sh" in r.stderr, r.stderr)
    r = run(d, "start", "fila", "FANTASMA", "--repo", ".")
    check("id que não existe é exit 2", r.returncode == 2, r.stdout)


# ── finish: the outcome ──────────────────────────────────────────────────────

def test_finish_requires_evidence(base):
    d = git_repo(base, "desfecho")
    target = write_queue(d, [item("A")])
    r = run(d, "finish", "fila", "A", "--status", "done", "--evidence", "   ",
            "--repo", ".")
    check("recusa desfecho sem evidência", r.returncode == 2, r.stdout)
    check("a recusa diz por que (a palavra `done` não é auditável sozinha)",
          "auditável" in r.stderr, r.stderr)
    check("nada mudou no disco na recusa",
          by_id(plan_of(target))["A"]["status"] == "pending")

    r = run(d, "finish", "fila", "A", "--status", "done",
            "--evidence", "commit abc123, proof PROVEN", "--repo", ".")
    check("grava o desfecho", r.returncode == 0, r.stderr)
    it = by_id(plan_of(target))["A"]
    check("status e evidência ficam no item",
          it["status"] == "done" and "abc123" in it["evidence"], it)


def test_finish_opens_debt_but_never_closes(base):
    """Opening a route belongs to the agent (it has just produced the thing to validate);
    closing belongs only to the human, who is the one who knows whether it ran."""
    d = git_repo(base, "divida2")
    target = write_queue(d, [item("A"), item("B", human_pending="conferir na UI")])
    r = run(d, "finish", "fila", "A", "--status", "done", "--evidence", "e",
            "--human-pending", "abrir /admin/devolucoes e conferir a recusa",
            "--repo", ".")
    check("o desfecho pode ABRIR uma rota humana", r.returncode == 0, r.stderr)
    check("a rota fica no item",
          "devolucoes" in by_id(plan_of(target))["A"]["human_pending"])

    r = run(d, "finish", "fila", "B", "--status", "done", "--evidence", "e",
            "--human-pending", "", "--repo", ".")
    check("recusa FECHAR a rota pelo agente", r.returncode == 2, r.stdout)
    check("a recusa diz que só o humano fecha", "só o humano" in r.stderr, r.stderr)
    check("a rota de B continua aberta no disco",
          by_id(plan_of(target))["B"]["human_pending"] == "conferir na UI")

    r = run(d, "finish", "fila", "B", "--status", "done", "--evidence", "e",
            "--repo", ".")
    check("fechar o item sem citar a rota não apaga a rota",
          r.returncode == 0 and
          by_id(plan_of(target))["B"]["human_pending"] == "conferir na UI",
          r.stderr)


def test_marking_preserves_header_and_extra_fields(base):
    """Regenerating the header at each closed item dated the document with TODAY and
    erased when the queue was written; and a field the schema does not foresee is
    someone recording something, not trash."""
    d = git_repo(base, "cabecalho")
    target = write_queue(d, [item("A", evidence="veio da triagem", extra="xyz"),
                            item("B")])
    before = target.read_text(encoding="utf-8")
    header = "".join(l for l in before.splitlines(keepends=True)
                        if l.startswith("#") or not l.strip())
    run(d, "start", "fila", "A", "--repo", ".")
    r = run(d, "finish", "fila", "A", "--status", "blocked",
            "--evidence", "travou no docker ausente",
            "--impede", "falta o programa que sobe o banco de testes", "--repo", ".")
    after = target.read_text(encoding="utf-8")
    check("o cabeçalho escrito à mão sobrevive à marcação",
          after.startswith(header.rstrip("\n")), after[:200])
    check("a data de escrita da fila não é reescrita",
          "2026-08-25" in after)
    it = by_id(plan_of(target))["A"]
    check("campo fora do schema sobrevive", it.get("extra") == "xyz", it)
    check("a evidência nova substitui a antiga, e é a do desfecho",
          it["evidence"] == "travou no docker ausente", it)
    check("o arquivo marcado continua válido para o próprio validador",
          run(d, "validate", str(target)).returncode == 0)
    out = queue(d)[1]
    # Owner's decision 2026-08-30: `blocked` DEFERS, it does not stop. Not re-executing
    # still holds (it would be the same jam); what changed is that it stopped
    # jamming the queue behind it — in an unattended window that cost the night.
    deferred_ones = {a["id"]: a for a in out["deferred"]}
    check("item que saiu `blocked` de um run anterior é ADIADO, "
          "em vez de ser re-executado no mesmo travamento",
          "A" in deferred_ones and deferred_ones["A"]["reason"] == "blocked-before",
          out["deferred"])
    check("o adiamento repete o motivo registrado no desfecho",
          "docker" in deferred_ones.get("A", {}).get("detail", ""), out["deferred"])
    check("e ele NÃO aparece no lote", "A" not in {i["id"] for i in out["batch"]},
          out["batch"])
    check("e a parada não é mais `blocked-before`",
          out["stop"]["reason"] != "blocked-before", out["stop"])


# ── prose contract of the command ────────────────────────────────────────────

def test_command_contract(base):
    check("o comando existe", CMD.is_file(), str(CMD))
    if not CMD.is_file():
        return
    f = CMD.read_text(encoding="utf-8")
    # without backticks: the instruction cannot depend on how markdown formatted it
    clean = f.replace("`", "").lower()
    check("manda montar o lote pelo cepa-plan, não pelo olho",
          "cepa-plan queue" in f,
          "sem isso a ordem da fila volta a ser interpretada a cada run")
    check("reserva o item antes de executar", "cepa-plan start" in f)
    check("registra o desfecho de cada item", "cepa-plan finish" in f)
    check("proíbe escrever o YAML à mão",
          "never edit queue.yaml by hand" in clean,
          "sem a proibição, um Write no arquivo contorna TODAS as recusas do "
          "cepa-plan e nenhuma delas dispara")
    check("declara que rota humana ADIA o item em vez de parar o lote",
          "human_pending" in f and "defers the item" in clean,
          "sem isso a prosa volta a mandar parar, e um lote de 3 vira um de 1")
    check("declara a cascata do adiamento",
          "cascade" in clean,
          "adiar B sem adiar quem depende de B faz o dependente parar o lote, "
          "e o adiamento não serve para nada")
    check("declara que adiar NÃO reescreve a ordem gravada",
          "deferring is execution" in clean or "never rewrites the order" in clean,
          "um executor que reordena o documento é o que a fila existe para "
          "impedir")
    check("declara o teto e o default",
          "--max" in f and "3" in f)
    check("manda reconciliar com o quadro ANTES de montar o lote",
          "cepa-plan reconcile" in f,
          "sem reconciliar, o lote executa item que alguém já fechou em outro "
          "lugar")
    # By position, not by string cut: `split("### 0.")[-1]` returns the
    # WHOLE text when the marker does not come before step 1, and the whole
    # text cites `cepa-plan reconcile` in the introduction — the check passed by
    # accident in exactly the case it exists to catch (the proof gate
    # inverted the order of the two steps and saw this green).
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
          clean.count("--offline") >= 3,
          "declarar a opção só nas variáveis deixa os passos 0 e 3.d livres "
          "para ignorá-la")
    check("manda transicionar o card ao fechar, quando há quadro",
          "status_map.in_review" in f,
          "sem a transição, cada lote drenado PRODUZ a divergência que a "
          "reconciliação seguinte teria que consertar")
    check("mas a ordem continua vindo da fila, nunca do rank do quadro",
          "the order never comes from the board" in clean,
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
    # 2026-08-30: the only two non-trivial failures of the 2h run on WEGO were
    # the turn ending with the build running on the side — 34 of the 49 minutes, exit 0
    # in both, item `in_progress` without outcome. Under `claude -p` (which is how
    # `cepa-until` runs each item) there is no following turn that would reap it.
    check("proíbe encerrar o turno com build em segundo plano",
          "build in the background" in clean and "there is no next turn" in clean,
          "sem a proibição escrita, o agente segue o conselho do no-busy-wait "
          "(mandar para o segundo plano), que só vale em sessão interativa")
    check("e diz o que fazer no lugar: nomear o desfecho antes de parar",
          "build disparado e não colhido" in clean,
          "proibir sem dar a saída faz o agente escolher outra forma de "
          "silêncio")
    check("e 'esperando o build' não passa como desfecho",
          "waiting for the build" in clean,
          "a tabela de desfechos terminais é o que impede status vestido de "
          "decisão")
    # The prose is the instruction; the hook is the net. Only the prose erodes with no test
    # going red — the lesson recorded in cepa-plan itself.
    plugin = json.loads(
        (REPO / "common" / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    bash = [b for b in plugin["hooks"]["PreToolUse"] if b.get("matcher") == "Bash"]
    check("e a proibição tem rede mecânica registrada no plugin",
          bash and any("no-background-build" in h["command"]
                       for h in bash[0]["hooks"]),
          "prosa sem hook é promessa; o hook é o que dispara quando ela erode")
    check("diz que a fila mora no clone principal",
          "git-common-dir" in f or "clone principal" in f)


def test_start_writes_the_owner_and_finish_erases_it(base):
    """Without a recorded owner, "another session or dead run?" is undecidable from the
    file — which was the state until 2026-08-28."""
    d = git_repo(base, "assinatura")
    target = write_queue(d, [item("A")])
    r = run(d, "start", "fila", "A", "--repo", ".")
    check("reserva", r.returncode == 0, r.stderr)
    owner = by_id(plan_of(target))["A"].get("claimed_by")
    check("a reserva é assinada", isinstance(owner, dict), owner)
    check("com o que a liveness precisa (pid, host, horário)",
          owner and all(owner.get(k) for k in ("pid", "hostname", "started_at")),
          owner)

    r = run(d, "finish", "fila", "A", "--status", "done",
            "--evidence", "commit abc", "--repo", ".")
    check("fecha", r.returncode == 0, r.stderr)
    check("item fechado não fica reservado por ninguém",
          "claimed_by" not in by_id(plan_of(target))["A"],
          by_id(plan_of(target))["A"])


def test_start_prints_the_previous_evidence(base):
    """Revision 3 of until-fim-sem-dono, step 4c: the item that goes back to `pending`
    after a red build carries the note in the `evidence`, and whoever reads the
    note is the agent that reserves the item again. Without `start` printing it, the
    note stays in the file with nobody reading it."""
    d = git_repo(base, "recado")
    write_queue(d, [item("A", evidence="recado X: build vermelho, lateral "
                                        "until/r-vermelho-A"),
                     item("B")])
    r = run(d, "start", "fila", "A", "--repo", ".")
    check("o start reserva o item com evidence", r.returncode == 0, r.stderr)
    check("...e imprime a evidence anterior", "recado X" in r.stdout, r.stdout)
    r = run(d, "start", "fila", "B", "--repo", ".")
    check("item sem evidence não imprime seção de recado",
          "evidence anterior" not in r.stdout, r.stdout)
    plain_text = CMD.read_text(encoding="utf-8")
    check("o drain-plan manda levar a evidence anterior ao flow",
          "evidence anterior" in plain_text and "side branch" in plain_text)


def test_start_recovers_orphan_reservation_and_refuses_the_live_one(base):
    d = git_repo(base, "reivindica")
    dead = {"session_id": "sessao-morta", "pid": dead_pid(),
             "hostname": socket.gethostname(), "cwd": str(d),
             "started_at": now_iso()}
    target = write_queue(d, [item("A", status="in_progress", claimed_by=dead)])
    r = run(d, "start", "fila", "A", "--repo", ".")
    check("reivindica a reserva órfã", r.returncode == 0, r.stderr)
    check("e diz que recuperou, em vez de fingir que estava livre",
          "órfã" in r.stdout, r.stdout)
    check("o dono novo substitui o morto",
          by_id(plan_of(target))["A"]["claimed_by"]["session_id"] != "sessao-morta")

    alive = {"session_id": "sessao-viva", "pid": os.getpid(),
            "hostname": socket.gethostname(), "cwd": str(d),
            "started_at": now_iso()}
    d2 = git_repo(base, "reivindica2")
    write_queue(d2, [item("A", status="in_progress", claimed_by=alive)])
    r = run(d2, "start", "fila", "A", "--repo", ".")
    check("recusa reservar o que uma sessão viva tem", r.returncode == 5, r.stdout)
    check("e a recusa NOMEIA a sessão, em vez de oferecer duas leituras",
          "sessao-viva" in r.stderr, r.stderr)


# ── reconcile: the queue against the board ───────────────────────────────────

MAP = {"defaults": {"project_key": "WEGO", "status_map": {
    "to_do": "To Do", "in_progress": "Doing", "in_review": "Code Review",
    "done": "Concluído", "wont_do": "Won't Do"}}}


def with_board(d):
    (d / "board-flow.yaml").write_text(yaml.dump(MAP, allow_unicode=True),
                                       encoding="utf-8")


def board(d, cards, missing=(), given_name="board.json"):
    f = d / given_name
    f.write_text(json.dumps({"cards": cards, "missing": list(missing)}),
                 encoding="utf-8")
    return str(f)


def reconcile(d, filename, *extra, given_name="fila"):
    r = run(d, "reconcile", given_name, "--board", filename, "--repo", ".", "--json",
            *extra)
    return r, (json.loads(r.stdout) if r.returncode == 0 else None)


def test_reconcile_brings_the_board_to_the_queue(base):
    d = git_repo(base, "reconcilia")
    with_board(d)
    target = write_queue(d, [item("W-1"), item("W-2", status="done"),
                            item("W-3"), item("W-4")])
    fname = board(d, [{"key": "W-1", "status": "Concluído"},
                    {"key": "W-2", "status": "Doing"},
                    {"key": "W-3", "status": "To Do"}],
                missing=["W-4"])
    _, out = reconcile(d, fname)
    div = {x["id"]: x["para"] for x in out["divergences"]}
    check("card que fechou fora do plano vira done", div.get("W-1") == "done", div)
    check("card done que voltou atrás no quadro NÃO vira divergência (R3)",
          "W-2" not in div, div)
    check("mas é nomeado num aviso, em vez de sumir calado",
          any("W-2" in a and "R3" in a for a in out["warnings"]), out["warnings"])
    check("card em dia não vira divergência", "W-3" in out["in_sync"], out)
    check("card que sumiu do quadro vira dropped", div.get("W-4") == "dropped", div)
    check("sem --apply não grava nada", out["wrote"] is False, out)
    check("o disco continua igual", by_id(plan_of(target))["W-1"]["status"] == "pending")

    _, out = reconcile(d, fname, "--apply")
    p2 = by_id(plan_of(target))
    check("com --apply grava", p2["W-1"]["status"] == "done", p2["W-1"])
    check("e deixa rastro de que veio do quadro, não do trabalho",
          p2["W-1"]["reconciled"]["board"] == "Concluído", p2["W-1"])
    check("o `why` de cada posição sobrevive à reconciliação",
          p2["W-1"]["why"] == "porque W-1", p2["W-1"])


def test_reconcile_done_in_review_is_not_bounce(base):
    """An item closed here goes to Review and waits for the proof gate. Reading that
    as a bounce reopened 8 ready items per round in run 2026-09-26-1102."""
    d = git_repo(base, "review")
    with_board(d)
    target = write_queue(d, [item("W-1", status="done"),
                            item("W-2", status="done"),
                            item("W-3")])
    fname = board(d, [{"key": "W-1", "status": "Code Review"},
                    {"key": "W-2", "status": "Doing"},
                    {"key": "W-3", "status": "Code Review"}])
    _, out = reconcile(d, fname, "--apply")
    div = {x["id"]: x["para"] for x in out["divergences"]}
    check("done + Code Review fica em dia", "W-1" in out["in_sync"]
          and "W-1" not in div, out)
    check("e continua done no disco",
          by_id(plan_of(target))["W-1"]["status"] == "done")
    check("done + Doing não é rebaixado (R3)", "W-2" not in div, div)
    check("e continua done no disco, mesmo com --apply",
          by_id(plan_of(target))["W-2"]["status"] == "done")
    check("pending + Code Review avisa que alguém pode estar nele",
          any("W-3" in a for a in out["warnings"]), out["warnings"])


def test_reconcile_never_downgrades_done_item(base):
    """Rule R3 (owner, 2026-09-25): status goes from the board to the plan and never
    downgrades a `done` item. The old `--apply` read done + To Do as a bounce and
    downgraded 11 ready cards in wego-acesso-backend."""
    d = git_repo(base, "r3")
    with_board(d)
    target = write_queue(d, [item("W-1", status="done"), item("W-2", status="done"),
                            item("W-3", status="done"), item("W-4", status="done"),
                            item("W-5", status="done"), item("W-6")])
    fname = board(d, [{"key": "W-1", "status": "To Do"},
                    {"key": "W-2", "status": "Doing"},
                    {"key": "W-3", "status": "Won't Do"},
                    {"key": "W-5", "status": "Concluído"},
                    {"key": "W-6", "status": "To Do"}],
                missing=["W-4"])
    _, out = reconcile(d, fname, "--apply")
    ids_div = {x["id"] for x in out["divergences"]}
    check("nenhum item done vira divergência, qualquer que seja o quadro",
          ids_div.isdisjoint({"W-1", "W-2", "W-3", "W-4", "W-5"}), out["divergences"])
    on_disk = by_id(plan_of(target))
    check("e o disco guarda todos como done depois do --apply",
          all(on_disk[k]["status"] == "done" for k in ("W-1", "W-2", "W-3", "W-4", "W-5")),
          {k: v["status"] for k, v in on_disk.items()})
    check("sem carimbo de reconciliação em quem não mudou",
          all("reconciled" not in on_disk[k] for k in ("W-1", "W-2", "W-3", "W-4")),
          on_disk)
    for k in ("W-1", "W-2", "W-3", "W-4"):
        check(f"{k} divergente é nomeado num aviso com a regra",
              any(k in a and "R3" in a for a in out["warnings"]), out["warnings"])
    check("done + Concluído fica em dia, sem aviso", "W-5" in out["in_sync"]
          and not any("W-5" in a for a in out["warnings"]), out)
    check("item pending não é afetado pela regra", on_disk["W-6"]["status"] == "pending")
    check("nada gravado quando não há o que mudar", out["wrote"] is False, out)


def test_reconcile_never_attaches_card_nor_closes_human_debt(base):
    d = git_repo(base, "limites")
    with_board(d)
    target = write_queue(d, [item("W-1", human_pending="conferir /admin à mão")])
    fname = board(d, [{"key": "W-1", "status": "Concluído"},
                    {"key": "W-9", "status": "To Do"}])
    _, out = reconcile(d, fname, "--apply")
    check("card do quadro sem posição na fila é NOMEADO",
          out["missing_from_plan"] == ["W-9"], out)
    # The report saying it did not attach does not prove the disk did not receive: the
    # proof gate saw an `--apply` that attached pass with this test green.
    # What answers the question is the written plan.yaml.
    on_disk = plan_of(target)
    check("e NÃO entra na fila gravada — posição sem `why` é a decisão que a "
          "fila existe para guardar",
          "W-9" not in by_id(on_disk),
          [i["id"] for i in on_disk["items"]])
    it = by_id(on_disk)["W-1"]
    check("a dívida humana continua aberta — só o humano fecha",
          it["human_pending"] == "conferir /admin à mão", it)
    check("e o relatório avisa que a rota humana do que fechou fora não veio",
          any("validação humana" in x["leitura"] for x in out["divergences"]),
          out["divergences"])


def test_reconcile_refuses_status_the_map_does_not_know(base):
    d = git_repo(base, "desconhecido")
    with_board(d)
    target = write_queue(d, [item("W-1")])
    fname = board(d, [{"key": "W-1", "status": "Em Homologação"}])
    _, out = reconcile(d, fname, "--apply")
    check("não inventa papel para status fora do status_map",
          out["divergences"] == [], out)
    check("mas diz que não reconciliou, em vez de calar",
          any("Em Homologação" in a for a in out["warnings"]), out["warnings"])
    check("e o item fica como estava",
          by_id(plan_of(target))["W-1"]["status"] == "pending")

    d2 = git_repo(base, "sem-quadro")
    write_queue(d2, [item("W-1")])
    r, _ = reconcile(d2, board(d2, [{"key": "W-1", "status": "Concluído"}]))
    check("sem board-flow.yaml, recusa em vez de chutar os nomes de status",
          r.returncode == 2, r.stdout)
    check("e diz por quê", "status_map" in r.stderr, r.stderr)


def test_reconcile_does_not_list_dropped_equal_on_both_sides(base):
    """WEGO 2026-09-28-0558: `reconcile` listed 12 items as `dropped →
    dropped`, noise that hid the only real divergence (a `pending →
    done`). An item already `dropped` in the queue and discarded on the board — by both
    paths (`missing` and status `Won't Do`) — is not a divergence."""
    d = git_repo(base, "dropped-igual")
    with_board(d)
    target = write_queue(d, [item("W-1", status="dropped"),
                            item("W-2", status="dropped"),
                            item("W-3", status="pending"),
                            item("W-4", status="pending"),
                            item("W-5", status="pending")])
    fname = board(d, [{"key": "W-1", "status": "Won't Do"},
                    {"key": "W-3", "status": "Concluído"},
                    {"key": "W-4", "status": "Won't Do"}],
                missing=["W-2", "W-5"])
    _, out = reconcile(d, fname)
    ids_div = {x["id"] for x in out["divergences"]}
    check("divergem o pending → done e os dois pending → dropped "
          "(quadro e sumido), não os dropped → dropped",
          ids_div == {"W-3", "W-4", "W-5"}, out["divergences"])
    div_by_id = {x["id"]: x for x in out["divergences"]}
    check("W-4 (pending, Won't Do no quadro) vira pending → dropped",
          div_by_id["W-4"]["de"] == "pending"
          and div_by_id["W-4"]["para"] == "dropped", div_by_id["W-4"])
    check("W-5 (pending, sumido do quadro) vira pending → dropped",
          div_by_id["W-5"]["de"] == "pending"
          and div_by_id["W-5"]["para"] == "dropped", div_by_id["W-5"])
    check("dropped descartado no quadro (Won't Do) fica em dia",
          "W-1" in out["in_sync"], out)
    check("dropped sumido do quadro (missing) fica em dia",
          "W-2" in out["in_sync"], out)
    check("W-4 não fica em dia, é divergência",
          "W-4" not in out["in_sync"], out)
    check("W-5 não fica em dia, é divergência",
          "W-5" not in out["in_sync"], out)

    _, out = reconcile(d, fname, "--apply")
    on_disk = by_id(plan_of(target))
    check("dropped que já estava certo não recebe carimbo de reconciliação",
          "reconciled" not in on_disk["W-1"], on_disk["W-1"])
    check("nem o outro dropped",
          "reconciled" not in on_disk["W-2"], on_disk["W-2"])
    check("W-4 vira dropped no disco",
          on_disk["W-4"]["status"] == "dropped", on_disk["W-4"])
    check("W-4 recebe carimbo de reconciliação",
          "reconciled" in on_disk["W-4"], on_disk["W-4"])
    check("W-5 vira dropped no disco",
          on_disk["W-5"]["status"] == "dropped", on_disk["W-5"])
    check("W-5 recebe carimbo de reconciliação",
          "reconciled" in on_disk["W-5"], on_disk["W-5"])


def test_on_the_night_branch(base):
    """`cepa-until` passes `--na-branch`. Without the command declaring what that
    changes, the agent goes back to opening its own worktree from `origin/main`,
    which is what left 20 of 25 rounds jammed on 2026-09-23.
    Run until/2026-10-15-1946: 10 hand resumptions in 5 of 7 rounds, because the
    leads ended the turn waiting for the workers. The command needs to tell
    every lead to delegate with `run_in_background: false` and wait in the same turn."""
    f = CMD.read_text(encoding="utf-8")
    clean = f.replace("`", "").lower()
    check("declara --na-branch nos argumentos",
          "--na-branch" in f.split("## Instructions")[0])
    i = clean.find("on the overnight branch (--na-branch")
    excerpt = clean[i:i + 2500] if i != -1 else ""
    check("o passo 3 diz o que muda na branch da noite", bool(excerpt))
    check("...não criar worktree nem branch para o item",
          "do not create a worktree or branch" in excerpt, excerpt[:300])
    check("...não partir de origin/main", "origin/main" in excerpt)
    check("...commit direto na branch", "commit directly on this branch" in excerpt)
    check("...sem merge, sem push", "no merge, no push" in excerpt)
    check("...e confere a branch antes de começar",
          "rev-parse --abbrev-ref head" in excerpt)
    i = clean.find("do not run the full build")
    rule = clean[i:i + 1500] if i != -1 else ""
    check("...não roda o build completo, que é do supervisor",
          bool(rule) and "supervisor" in rule, rule[:200])
    check("...roda só os testes focados, dentro do teto de 10 minutos",
          "10 minutes" in rule and "-dtest" in rule, rule[:300])
    check("...e passa a regra aos agentes que delega",
          "qa-engineer" in rule and "validation-lead" in rule, rule[:300])
    i = clean.find("whoever delegates waits for the worker in the same turn")
    waiting = clean[i:].split("\n\n")[0] if i != -1 else ""
    check("...quem delega espera o worker no mesmo turno",
          bool(waiting), "bullet ausente")
    check("...com run_in_background: false e 'mesmo turno'",
          "run_in_background: false" in waiting and "same turn" in waiting,
          waiting[:300])
    check("...e manda a regra aos três leads",
          all(l in waiting for l in ("engineering-lead", "validation-lead",
                                    "planning-lead")), waiting[:600])


def test_board_labels_state_the_write_direction(base):
    """deviations.md 2026-08-29: "Reconciliar" and "Sync" are synonyms in
    ordinary Portuguese, and the owner had to ask which wrote where. Each end
    of the board is named by direction: one writes to the plan, the other to the board."""
    f = CMD.read_text(encoding="utf-8")
    brings = "Trazer status do Jira (grava no plano)"
    takes = "Atualizar o Jira (grava no quadro)"
    i0, i1 = f.find("### 0."), f.find("### 1.")
    header0 = f[i0:f.find("\n", i0)] if i0 != -1 else ""
    check("o título do passo 0 diz que ele grava no plano",
          brings in header0, header0)
    check("e não se chama mais só 'Reconciliar'",
          not header0.startswith("### 0. Reconciliar"), header0)
    i2, i3 = f.find("### 2."), f.find("### 3.")
    screen = f[i2:i3] if -1 not in (i2, i3) else ""
    check("a tela da largada nomeia as duas pontas pela direção",
          brings in screen and takes in screen,
          "a pergunta do lote é onde o dono lê o que vai ser escrito, e onde")
    i4 = f.find("### 4.")
    step3 = f[i3:i4] if -1 not in (i3, i4) else ""
    k = step3.find("status_map.in_review")
    check("a transição do card no passo 3 leva o rótulo de quem grava no quadro",
          k != -1 and takes in step3[max(0, k - 600):k + 200],
          step3[max(0, k - 600):k + 200][:300])
    ii, iw = f.find("## Instructions"), f.find("## Workflow")
    intro = f[ii:iw] if -1 not in (ii, iw) else ""
    check("as Instructions apresentam as duas pontas pela direção",
          brings in intro and takes in intro,
          "é ali que o leitor encontra as duas pontas pela primeira vez")
    i5 = f.find("### 5.")
    rel = f[i5:f.find("## Constraints")] if i5 != -1 else ""
    check("o relatório separa as duas pontas pela direção",
          brings in rel and takes in rel, rel[:300])


def test_finish_done_requires_the_validation_lead_verdict(base):
    """Item `drain-plan-pula-validacao-build-hex`: in the 2026-09-23 run none
    of WEGO's 5 cards went through the validation-lead, and WEGO-2318 closed without
    security review. With a topology that has a validation-lead, `done` without the
    recorded verdict is refused; the rest of the queue does not change."""
    d = git_repo(base, "validacao")
    target = write_queue(d, [item("A"), item("B"), item("C")])
    (d / ".claude" / "topology").write_text("build-hex\n", encoding="utf-8")

    r = run(d, "finish", "fila", "A", "--status", "done",
            "--evidence", "commit abc", "--repo", ".")
    check("build-hex sem docs/validation/A.yaml: done RECUSADO",
          r.returncode == 2, r.stdout + r.stderr)
    check("a recusa nomeia o validation-lead e o arquivo que falta",
          "validation-lead" in r.stderr and "docs/validation/A.yaml" in r.stderr,
          r.stderr)
    check("nada mudou no disco na recusa",
          by_id(plan_of(target))["A"]["status"] == "pending")

    r = run(d, "finish", "fila", "A", "--status", "blocked",
            "--evidence", "validation-lead não rodou",
            "--impede", "a revisão final não rodou", "--repo", ".")
    check("sem o veredito, blocked continua aceito", r.returncode == 0, r.stderr)

    val = d / "docs" / "validation"
    val.mkdir(parents=True)
    (val / "B.yaml").write_text("key: B\nverdict: BLOCKED\n", encoding="utf-8")
    r = run(d, "finish", "fila", "B", "--status", "done",
            "--evidence", "commit def", "--repo", ".")
    check("veredito BLOCKED: done RECUSADO e o veredito aparece na recusa",
          r.returncode == 2 and "BLOCKED" in r.stderr, r.stderr)

    (val / "B.yaml").write_text("key: B\nverdict: READY-WITH-CAVEATS\n",
                                encoding="utf-8")
    commit_all(d)
    r = run(d, "finish", "fila", "B", "--status", "done",
            "--evidence", "commit def", "--repo", ".")
    check("READY-WITH-CAVEATS fecha done", r.returncode == 0, r.stderr)
    (val / "C.yaml").write_text("key: C\nverdict: READY-TO-SHIP\n",
                                encoding="utf-8")
    commit_all(d)
    r = run(d, "finish", "fila", "C", "--status", "done",
            "--evidence", "commit ghi", "--repo", ".")
    check("READY-TO-SHIP fecha done", r.returncode == 0, r.stderr)

    d2 = git_repo(base, "validacao-solo")
    write_queue(d2, [item("A")])
    (d2 / ".claude" / "topology").write_text("build-solo\n", encoding="utf-8")
    commit_all(d2)
    r = run(d2, "finish", "fila", "A", "--status", "done",
            "--evidence", "commit abc", "--repo", ".")
    check("build-solo (sem validation-lead) não exige o arquivo",
          r.returncode == 0, r.stderr)

    # The old path is still READ: verdicts recorded in .claude/validation/
    # before 27/09/2026 cannot become a refusal just because the destination changed.
    d3 = git_repo(base, "validacao-legado")
    write_queue(d3, [item("A")])
    (d3 / ".claude" / "topology").write_text("build-hex\n", encoding="utf-8")
    legacy = d3 / ".claude" / "validation"
    legacy.mkdir(parents=True)
    (legacy / "A.yaml").write_text("key: A\nverdict: READY-TO-SHIP\n",
                                   encoding="utf-8")
    commit_all(d3)
    r = run(d3, "finish", "fila", "A", "--status", "done",
            "--evidence", "commit abc", "--repo", ".")
    check("veredito no caminho antigo .claude/validation/ ainda fecha done",
          r.returncode == 0, r.stderr)


def test_topologies_with_validation_match_the_agents(base):
    """The cepa-plan list is a copy of what is on disk; without this
    check, a new topology with a validation-lead would close without it."""
    import re as _re
    source = CEPA_PLAN.read_text(encoding="utf-8")
    m = _re.search(r"^TOPOLOGIES_WITH_VALIDATION = \(([^)]*)\)", source, _re.M)
    declared = set(_re.findall(r'"([^"]+)"', m.group(1))) if m else set()
    on_disk = {a.parent.parent.name
                for a in REPO.glob("*/agents/validation-lead.md")}
    check("TOPOLOGIES_WITH_VALIDATION == plugins com agents/validation-lead.md",
          declared == on_disk, f"{declared} != {on_disk}")
    for f in on_disk:
        spec = (REPO / f / "agents" / "validation-lead.md").read_text(
            encoding="utf-8")
        check(f"{f}/validation-lead grava docs/validation/<KEY>.yaml",
              "docs/validation/<KEY>.yaml" in spec
              and ".claude/validation" not in spec
              and "Write" in spec.split("\n", 5)[3], f)
    clean = CMD.read_text(encoding="utf-8").replace("`", "")
    i = clean.find("c. **Go through both gates**")
    step = clean[i:i + 2000] if i != -1 else ""
    check("drain-plan 3.c exige o validation-lead na topologia que o tem",
          "validation-lead" in step and "docs/validation/<id>.yaml" in step
          and "delegated-to-supervisor" in step, step[:300])


def test_card_moves_on_the_board_in_every_outcome(base):
    """Run 2026-10-02-0838 on WEGO: WEGO-2349 was reserved, gained 7
    commits, jammed at the proof gate and stayed in To Do on the board. The command
    only said to transition when closing `done`, and the last rule said "Does not talk
    to any tracker". Owner's decision: a queue item that is a card moves the card,
    mandatorily, in every outcome."""
    f = CMD.read_text(encoding="utf-8")
    i3, i4 = f.find("### 3."), f.find("### 4.")
    step3 = f[i3:i4] if -1 not in (i3, i4) else ""
    ia = step3.find("cepa-plan start")
    ib = step3.find("  b. ")
    reservation = " ".join((step3[ia:ib] if -1 not in (ia, ib) else "").split())
    check("a reserva move o card para in_progress antes de qualquer trabalho",
          "status_map.in_progress" in reservation
          and "atlassian-expert" in reservation
          and "before any work" in reservation,
          "sem isso o card fica em To Do enquanto o item é trabalhado")
    i_e = step3.find("  e. ")
    closes = step3[i_e:step3.find("  f. ")] if i_e != -1 else ""
    check("o done leva o card para in_review com o Implementation Summary",
          "status_map.in_review" in closes
          and "Implementation Summary" in closes)
    i_f = step3.find("on block.**")
    jams = step3[i_f:] if i_f != -1 else ""
    check("o item travado comenta o motivo no card",
          "atlassian-expert" in jams and "comment on the card" in jams,
          "sem isso o card travado não diz no quadro por que parou")
    check("e vai para a coluna de bloqueados quando o quadro a declara",
          "status_map.blocked" in jams)
    check("o travamento cobre também o item que volta para pending",
          "pending" in jams and "status_map.blocked" in jams)
    check("e proíbe deixar o card em to_do",
          "Never leave it in `to_do`" in jams)
    i2 = f.find("### 2.")
    screen = f[i2:i3] if -1 not in (i2, i3) else ""
    check("a tela da largada nomeia as três pontas do quadro",
          all(s in screen for s in ("<in_progress>", "<in_review>", "when it gets stuck")),
          "o dono aprova o lote lendo esta tela")
    i5 = f.find("### 5.")
    rel = " ".join((f[i5:f.find("## Constraints")] if i5 != -1 else "").split())
    check("o relatório lista as três pontas do quadro",
          all(s in rel for s in ("In Progress", "In Review",
                                 "stuck ones commented")))
    ii, iw = f.find("## Instructions"), f.find("## Workflow")
    intro = " ".join((f[ii:iw] if -1 not in (ii, iw) else "").split())
    k = intro.find("during")
    check("a transição é declarada obrigatória nas Instructions",
          k != -1 and "is **mandatory**, not optional" in intro[k:k + 300],
          "a palavra solta já existia no arquivo (`--evidence` é obrigatório)")
    end = f[f.find("## Constraints"):]
    check("as Constraints não dizem mais que o comando não fala com tracker",
          "não fala com tracker" not in end.lower(),
          "a regra contradizia os passos 0 e 3 e foi lida como proibição")
    i0, i1 = f.find("### 0."), f.find("### 1.")
    step0 = f[i0:i1] if -1 not in (i0, i1) else ""
    check("o 'Do not transition' do passo 0 é marcado como só da leitura",
          "Do not transition" in step0 and "applies only to THIS request" in step0,
          "a frase foi lida como política do lote no relatório do WEGO-2349")


def main():
    with tempfile.TemporaryDirectory() as base:
        for fn in (test_batch_follows_the_queue_order_and_the_ceiling,
                   test_done_or_dropped_item_does_not_enter_and_does_not_stop,
                   test_open_human_pending_DEFERS_the_item_and_the_batch_goes_on,
                   test_deferring_an_item_defers_whoever_depends_on_it,
                   test_deferring_does_not_rewrite_the_recorded_order,
                   test_block_stops_the_batch_but_internal_dependency_does_not,
                   test_dropped_blocker_warns_instead_of_holding_forever,
                   test_reservation_with_live_owner_defers_and_NAMES_who_is_on_it,
                   test_orphan_reservation_is_recovered_instead_of_blocking_the_queue,
                   test_reservation_from_another_machine_expires_by_age,
                   test_in_progress_without_registered_owner_defers_and_admits_not_knowing,
                   test_start_writes_the_owner_and_finish_erases_it,
                   test_start_recovers_orphan_reservation_and_refuses_the_live_one,
                   test_start_prints_the_previous_evidence,
                   test_reconcile_brings_the_board_to_the_queue,
                   test_reconcile_done_in_review_is_not_bounce,
                   test_reconcile_never_downgrades_done_item,
                   test_reconcile_never_attaches_card_nor_closes_human_debt,
                   test_reconcile_refuses_status_the_map_does_not_know,
                   test_reconcile_does_not_list_dropped_equal_on_both_sides,
                   test_queue_refuses_waves_and_missing_queue,
                   test_start_reserves_and_refuses_double_reservation,
                   test_start_refuses_closed_item_and_item_with_open_route,
                   test_finish_requires_evidence,
                   test_finish_opens_debt_but_never_closes,
                   test_finish_done_requires_the_validation_lead_verdict,
                   test_topologies_with_validation_match_the_agents,
                   test_marking_preserves_header_and_extra_fields,
                   test_on_the_night_branch,
                   test_board_labels_state_the_write_direction,
                   test_card_moves_on_the_board_in_every_outcome,
                   test_command_contract):
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
