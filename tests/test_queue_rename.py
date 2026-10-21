#!/usr/bin/env python3
"""Testes da renomeação da fila single-track (decisão do dono, 2026-10-20):

    .claude/programs/<n>/plan.yaml  (chave `program:`, /common:plan)
 -> .claude/queues/<n>/queue.yaml   (chave `queue:`,   /common:queue)

Durante a transição todo consumidor LÊ os dois layouts e `cepa-plan migrate`
move as filas existentes. Cada teste chama o binário de verdade (subprocess)
num repo git temporário, como os vizinhos (`test_cepa_plan_escrita_commita.py`).

Rode com `python3 tests/test_queue_rename.py` ou com pytest (cada teste cria o
próprio diretório temporário).

O que estes testes NÃO provam: que o painel compass (TypeScript) lê os dois
layouts — ele tem o runner próprio (`claude plugin test`); nem que o comando
`/common:queue` conversa direito, que é prompt.
"""

import importlib.machinery
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
CEPA_PLAN = REPO / "common" / "bin" / "cepa-plan"
CEPA_UNTIL = REPO / "common" / "bin" / "cepa-until"
MAESTRO_PROGRAMS = REPO / "maestro" / "bin" / "maestro-programs"


def run(script, repo, *args):
    return subprocess.run([sys.executable, str(script)] + list(args),
                          capture_output=True, text=True, cwd=str(repo))


def plan(repo, *args):
    return run(CEPA_PLAN, repo, *args)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo)] + list(args),
                          capture_output=True, text=True, check=True).stdout


def novo_repo(base, nome="r"):
    d = Path(base) / nome
    d.mkdir(parents=True)
    git(d, "init", "-q")
    git(d, "config", "user.email", "t@t")
    git(d, "config", "user.name", "t")
    (d / "README").write_text("x\n")
    git(d, "add", "README")
    git(d, "commit", "-q", "-m", "init")
    return d


def item(ident, **kw):
    base = {"id": ident, "title": f"item {ident}", "why": f"porque {ident}",
            "status": "pending", "blocked_by": [], "human_pending": None}
    base.update(kw)
    return base


def escreve_itens(d, itens):
    p = Path(d) / "itens.json"
    p.write_text(json.dumps(itens), encoding="utf-8")
    return p


LEGADA = """\
# comentario que a migracao nao pode perder
schema_version: 2
mode: single-track
program: {nome}
source: teste
items:
- id: A
  title: item A
  why: porque A
  status: pending
  blocked_by: []
  human_pending: null
"""


def fila_legada(d, nome="x", texto=None, commita=True, bak=True):
    """Fila no layout antigo, escrita à mão, com `until/` e `.bak` ao lado."""
    pasta = Path(d) / ".claude" / "programs" / nome
    (pasta / "until").mkdir(parents=True)
    (pasta / "plan.yaml").write_text(texto or LEGADA.format(nome=nome),
                                     encoding="utf-8")
    (pasta / "until" / "2026-10-20-0900.jsonl").write_text("{}\n")
    if bak:
        (pasta / "plan.yaml.bak").write_text("# anterior\n")
    if commita:
        git(d, "add", "-f", ".claude")
        git(d, "commit", "-q", "-m", "fila legada")
    return pasta


def com_repo(fn):
    def corpo():
        with tempfile.TemporaryDirectory() as base:
            fn(novo_repo(base))
    corpo.__name__ = fn.__name__
    return corpo


# ── (a) fila nova nasce no layout novo ───────────────────────────────────────

@com_repo
def test_fila_nova_nasce_em_queues(d):
    r = plan(d, "write", "fila", "--items", str(escreve_itens(d, [item("A")])),
             "--source", "t", "--quando", "2026-10-20", "--repo", ".")
    assert r.returncode == 0, r.stderr
    novo = d / ".claude" / "queues" / "fila" / "queue.yaml"
    assert novo.is_file(), r.stdout
    assert not (d / ".claude" / "programs" / "fila").exists()
    dados = yaml.safe_load(novo.read_text(encoding="utf-8"))
    assert dados.get("queue") == "fila" and "program" not in dados, dados
    assert plan(d, "validate", str(novo)).returncode == 0
    r = plan(d, "status", "fila", "--json", "--repo", ".")
    saida = json.loads(r.stdout)
    assert saida["queue"] == "fila" and saida["program"] == "fila", saida


# ── (b) fila legada segue sendo lida e marcada no lugar ─────────────────────

@com_repo
def test_fila_legada_e_lida_e_marcada_no_lugar(d):
    pasta = fila_legada(d, commita=False)
    r = plan(d, "queue", "x", "--json", "--repo", ".")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["path"].endswith("programs/x/plan.yaml")
    assert plan(d, "start", "x", "A", "--repo", ".").returncode == 0
    r = plan(d, "finish", "x", "A", "--status", "done", "--evidence", "ok",
             "--repo", ".")
    assert r.returncode == 0, r.stderr
    dados = yaml.safe_load((pasta / "plan.yaml").read_text(encoding="utf-8"))
    assert dados["items"][0]["status"] == "done"
    assert dados.get("program") == "x", "a chave antiga segue até migrar"
    assert not (d / ".claude" / "queues").exists()
    # reescrever uma fila legada mantém o arquivo e a chave dela
    r = plan(d, "write", "x", "--items", str(escreve_itens(d, [item("A"), item("B")])),
             "--repo", ".")
    assert r.returncode == 0, r.stderr
    assert (pasta / "plan.yaml.bak").is_file()
    assert yaml.safe_load((pasta / "plan.yaml").read_text())["program"] == "x"
    assert not (d / ".claude" / "queues").exists()


# ── (c) mesmo nome nos dois layouts: o novo ganha ───────────────────────────

@com_repo
def test_nome_nos_dois_layouts_o_novo_ganha(d):
    fila_legada(d, commita=False)
    novo = d / ".claude" / "queues" / "x"
    novo.mkdir(parents=True)
    (novo / "queue.yaml").write_text(
        LEGADA.format(nome="x").replace("program:", "queue:").replace("item A", "item NOVO"),
        encoding="utf-8")
    r = plan(d, "status", "x", "--json", "--repo", ".")
    assert r.returncode == 0, r.stderr
    saida = json.loads(r.stdout)
    assert saida["path"].endswith("queues/x/queue.yaml"), saida["path"]
    assert saida["items"][0]["title"] == "item NOVO"


# ── (d) migrate ──────────────────────────────────────────────────────────────

@com_repo
def test_migrate_move_renomeia_reescreve_commita_e_e_idempotente(d):
    fila_legada(d)
    antes = git(d, "rev-list", "--count", "HEAD").strip()
    r = plan(d, "migrate", "--all", "--dry-run", "--repo", ".")
    assert r.returncode == 0 and "x" in r.stdout, r.stdout + r.stderr
    assert (d / ".claude" / "programs" / "x" / "plan.yaml").is_file(), \
        "--dry-run não move nada"

    r = plan(d, "migrate", "--all", "--repo", ".")
    assert r.returncode == 0, r.stdout + r.stderr
    novo = d / ".claude" / "queues" / "x"
    assert not (d / ".claude" / "programs" / "x").exists()
    assert (novo / "queue.yaml").is_file() and not (novo / "plan.yaml").exists()
    assert (novo / "queue.yaml.bak").is_file()
    assert (novo / "until" / "2026-10-20-0900.jsonl").is_file()
    texto = (novo / "queue.yaml").read_text(encoding="utf-8")
    assert texto.startswith("# comentario que a migracao nao pode perder\n"), texto
    assert "\nqueue: x\n" in texto and "program:" not in texto, texto
    assert git(d, "rev-list", "--count", "HEAD").strip() == str(int(antes) + 1), \
        "um commit só"
    assert git(d, "status", "--porcelain").strip() == "", git(d, "status", "--porcelain")

    r = plan(d, "migrate", "--all", "--repo", ".")
    assert r.returncode == 0 and "nada a migrar" in r.stdout, r.stdout + r.stderr
    assert git(d, "rev-list", "--count", "HEAD").strip() == str(int(antes) + 1)
    r = plan(d, "migrate", "x", "--repo", ".")
    assert r.returncode == 0, r.stdout + r.stderr


# ── (e) migrate pula ondas e recusa destino existente ───────────────────────

@com_repo
def test_migrate_pula_ondas_e_recusa_destino_existente(d):
    ondas = d / ".claude" / "programs" / "ondas"
    ondas.mkdir(parents=True)
    (ondas / "plan.yaml").write_text(yaml.dump(
        {"schema_version": 2, "mode": "parallel-waves", "program": "ondas",
         "waves": []}), encoding="utf-8")
    r = plan(d, "migrate", "--all", "--repo", ".")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (ondas / "plan.yaml").is_file() and not (d / ".claude" / "queues").exists()
    r = plan(d, "migrate", "ondas", "--repo", ".")
    assert r.returncode != 0 and (ondas / "plan.yaml").is_file()

    pasta = fila_legada(d, commita=False)
    (d / ".claude" / "queues" / "x").mkdir(parents=True)
    r = plan(d, "migrate", "x", "--repo", ".")
    assert r.returncode != 0 and "já existe" in r.stderr, r.stderr
    assert (pasta / "plan.yaml").is_file(), "nada foi movido"
    assert "program: x" in (pasta / "plan.yaml").read_text()


# ── (f) migrate recusa reserva viva ──────────────────────────────────────────

@com_repo
def test_migrate_recusa_reserva_viva(d):
    dono = {"session_id": "S-VIVA", "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "started_at": datetime.now(timezone.utc).isoformat()}
    texto = LEGADA.format(nome="x").replace(
        "  status: pending\n",
        "  status: in_progress\n  claimed_by: " + json.dumps(dono) + "\n")
    pasta = fila_legada(d, texto=texto)
    r = plan(d, "migrate", "x", "--repo", ".")
    assert r.returncode != 0 and "VIVA" in r.stderr, r.stdout + r.stderr
    assert (pasta / "plan.yaml").is_file()
    assert not (d / ".claude" / "queues").exists()

    # reserva órfã (pid morto) não segura a migração
    morto = dict(dono, pid=2 ** 22 + 12345, session_id="S-MORTA")
    (pasta / "plan.yaml").write_text(texto.replace(json.dumps(dono), json.dumps(morto)),
                                     encoding="utf-8")
    git(d, "commit", "-q", "-am", "reserva órfã")
    r = plan(d, "migrate", "x", "--repo", ".")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (d / ".claude" / "queues" / "x" / "queue.yaml").is_file()


# ── (f2) migrate recusa run vivo do cepa-until, mesmo entre itens ───────────

def _estado_rodando(pasta, pid):
    (pasta / "until" / "2026-10-20-2055.estado.json").write_text(json.dumps(
        {"estado": "rodando", "pid": pid, "host": socket.gethostname(),
         "run": "2026-10-20-2055"}), encoding="utf-8")


@com_repo
def test_migrate_recusa_run_vivo_do_cepa_until(d):
    pasta = fila_legada(d)
    falso = subprocess.Popen(["bash", "-c", "exec -a cepa-until sleep 60"])
    try:
        _estado_rodando(pasta, falso.pid)
        r = plan(d, "migrate", "x", "--repo", ".")
        assert r.returncode != 0 and "cepa-until" in r.stderr, r.stdout + r.stderr
        assert (pasta / "plan.yaml").is_file()
        assert not (d / ".claude" / "queues").exists()
    finally:
        falso.kill()
        falso.wait()
    _estado_rodando(pasta, falso.pid)  # agora morto
    r = plan(d, "migrate", "x", "--repo", ".")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (d / ".claude" / "queues" / "x" / "queue.yaml").is_file()


# ── (f3) migrate recusa fila com mudança não commitada ──────────────────────

@com_repo
def test_migrate_recusa_fila_nao_commitada(d):
    pasta = fila_legada(d)
    with open(pasta / "plan.yaml", "a", encoding="utf-8") as f:
        f.write("# status mexido e não commitado\n")
    r = plan(d, "migrate", "x", "--repo", ".")
    assert r.returncode != 0 and "não commitadas" in r.stderr, r.stdout + r.stderr
    assert (pasta / "plan.yaml").is_file()
    assert not (d / ".claude" / "queues").exists()


# ── (f4) fila sem `program:` no topo ganha `queue:` na migração ─────────────

@com_repo
def test_migrate_fila_sem_chave_ganha_queue(d):
    fila_legada(d, texto=LEGADA.format(nome="x").replace("program: x\n", ""))
    r = plan(d, "migrate", "x", "--repo", ".")
    assert r.returncode == 0, r.stdout + r.stderr
    texto = (d / ".claude" / "queues" / "x" / "queue.yaml").read_text()
    assert texto.startswith("# comentario que a migracao nao pode perder\n"), texto
    assert yaml.safe_load(texto)["queue"] == "x", texto


# ── (g) cepa-until: sujeira ignora o registro nos dois layouts ──────────────

def carrega_until():
    loader = importlib.machinery.SourceFileLoader("cepa_until_qr", str(CEPA_UNTIL))
    spec = importlib.util.spec_from_loader("cepa_until_qr", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def test_cepa_until_filtros_de_sujeira_aceitam_os_dois_layouts():
    cu = carrega_until()
    for base, arq in ((".claude/programs", "plan.yaml"), (".claude/queues", "queue.yaml")):
        assert cu.REGISTRO_DO_RUN.match(f"?? {base}/f/until/2026-10-20-0900.jsonl"), base
        assert cu.BAK_DA_FILA.match(f"?? {base}/f/{arq}.bak"), base
        m = cu.PLANO_MODIFICADO.match(f" M {base}/f/{arq}")
        assert m and m.group(1) == f"{base}/f/{arq}", base
        assert (m.group(2) or m.group(3)) == "f", base
    assert not cu.BAK_DA_FILA.match("?? .claude/queues/f/plan.yaml.bak")
    assert not cu.REGISTRO_DO_RUN.match("?? .claude/outro/f/until/x")


@com_repo
def test_cepa_until_arvore_suja_ignora_registro_e_bak_dos_dois_layouts(d):
    cu = carrega_until()
    # com algo rastreado em .claude/ o git lista cada arquivo não rastreado
    for base in ("programs", "queues"):
        (d / ".claude" / base / "f" / "until").mkdir(parents=True)
        (d / ".claude" / base / "f" / "keep").write_text("x\n")
    git(d, "add", "-f", ".claude")
    git(d, "commit", "-q", "-m", "keep")
    for base, arq in (("programs", "plan.yaml"), ("queues", "queue.yaml")):
        pasta = d / ".claude" / base / "f"
        (pasta / "until" / "2026-10-20-0900.jsonl").write_text("{}\n")
        (pasta / (arq + ".bak")).write_text("x\n")
    assert cu.arvore_suja(d) == [], cu.arvore_suja(d)
    (d / "sujeira.txt").write_text("x\n")
    assert [l for l in cu.arvore_suja(d)] == ["?? sujeira.txt"]


@com_repo
def test_cepa_until_resolve_ledger_e_fila_pelo_resolvedor(d):
    cu = carrega_until()
    assert cu.qp.queue_dir(d, "f") == d / ".claude" / "queues" / "f"
    fila_legada(d, nome="f", commita=False)
    assert cu.qp.queue_dir(d, "f") == d / ".claude" / "programs" / "f"
    (d / ".claude" / "queues" / "f").mkdir(parents=True)
    (d / ".claude" / "queues" / "f" / "queue.yaml").write_text("queue: f\n")
    assert cu.qp.queue_dir(d, "f") == d / ".claude" / "queues" / "f"
    assert cu.qp.queue_name_of({"queue": "a", "program": "b"}) == "a"
    assert cu.qp.queue_name_of({"program": "b"}) == "b"
    assert cu.qp.queue_name_of({}, "z") == "z"


# ── (h) maestro-programs --check-name enxerga o layout novo ─────────────────

@com_repo
def test_maestro_programs_check_name_recusa_nome_de_fila_nova(d):
    pasta = d / ".claude" / "queues" / "minha"
    pasta.mkdir(parents=True)
    (pasta / "queue.yaml").write_text(
        LEGADA.format(nome="minha").replace("program:", "queue:"), encoding="utf-8")
    r = run(MAESTRO_PROGRAMS, d, str(d), "--check-name", "minha")
    assert r.returncode == 3, r.stdout + r.stderr
    assert "minha" in r.stderr
    r = run(MAESTRO_PROGRAMS, d, str(d), "--check-name", "livre")
    assert r.returncode == 0, r.stderr
    r = run(MAESTRO_PROGRAMS, d, str(d), "--json")
    nomes = [p["nome"] for p in json.loads(r.stdout)["programas"]]
    assert "minha" in nomes, nomes


@com_repo
def test_cepa_plan_check_name_ve_onda_legada(d):
    ondas = d / ".claude" / "programs" / "ondas"
    ondas.mkdir(parents=True)
    (ondas / "plan.yaml").write_text(yaml.dump(
        {"schema_version": 2, "mode": "parallel-waves", "program": "ondas",
         "waves": []}), encoding="utf-8")
    assert plan(d, "check-name", "ondas", "--repo", ".").returncode == 3
    r = plan(d, "write", "ondas", "--items", str(escreve_itens(d, [item("A")])),
             "--repo", ".")
    assert r.returncode == 3, "plano de ondas no caminho antigo segue recusado"
    assert not (d / ".claude" / "queues").exists()


# ── (i) o comando ────────────────────────────────────────────────────────────

def test_comando_queue_existe_e_plan_e_alias():
    q = REPO / "common" / "commands" / "queue.md"
    p = REPO / "common" / "commands" / "plan.md"
    assert q.is_file() and p.is_file()
    qt, pt = q.read_text(encoding="utf-8"), p.read_text(encoding="utf-8")
    assert qt.splitlines()[0] == "---" and "# /common:queue" in qt
    assert "/common:plan" not in qt.split("## Purpose")[1], \
        "o corpo do /common:queue não pode mandar o leitor de volta ao nome velho"
    assert "/common:queue" in pt and "renamed" in pt.lower()
    assert len(pt.splitlines()) < 30, "o alias é curto; os passos moram no queue.md"
    cat = (REPO / "docs" / "commands.md").read_text(encoding="utf-8")
    assert "| `/common:queue` |" in cat and "| `/common:plan` |" in cat


def test_doctor_avisa_nome_nos_dois_layouts_e_sugere_migrar():
    with tempfile.TemporaryDirectory() as base:
        d = novo_repo(base)
        fila_legada(d, commita=False)
        loader = importlib.machinery.SourceFileLoader(
            "cepa_doctor_qr", str(REPO / "common" / "bin" / "cepa-doctor"))
        spec = importlib.util.spec_from_loader("cepa_doctor_qr", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        mod.RESULTS.clear()
        mod.check_layout_da_fila(d)
        assert any("migrate --all" in m for _, _, m, _ in mod.RESULTS), mod.RESULTS
        novo = d / ".claude" / "queues" / "x"
        novo.mkdir(parents=True)
        (novo / "queue.yaml").write_text("queue: x\nmode: single-track\n")
        mod.RESULTS.clear()
        mod.check_layout_da_fila(d)
        assert any(k == "warn" and "dois layouts" in m for k, _, m, _ in mod.RESULTS), \
            mod.RESULTS


if __name__ == "__main__":
    falhas = []
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok  {nome}")
            except Exception as e:  # noqa: BLE001
                print(f"FAIL  {nome}  {e!r}")
                falhas.append(nome)
    sys.exit(1 if falhas else 0)
