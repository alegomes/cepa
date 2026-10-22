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



# ── (j) lacunas da prova: consumidores do layout NOVO ───────────────────────
# Cada teste abaixo existe porque uma perturbação de docs/proof/
# renomear-para-queue.yaml sobrevivia com a suíte verde (id entre colchetes).

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shutil  # noqa: E402

DOCTOR = REPO / "common" / "bin" / "cepa-doctor"
DIGEST = REPO / "common" / "bin" / "cepa-until-digest"


def para_layout_novo(raiz, nome="fila"):
    """Converte a fila `nome` de um repo montado por `monta_repo` (que escreve
    no layout antigo) para `.claude/queues/<nome>/queue.yaml` com `queue:`, e
    commita."""
    velho = Path(raiz) / ".claude" / "programs" / nome
    novo = Path(raiz) / ".claude" / "queues" / nome
    novo.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(velho), str(novo))
    (novo / "plan.yaml").rename(novo / "queue.yaml")
    dados = yaml.safe_load((novo / "queue.yaml").read_text(encoding="utf-8"))
    dados["queue"] = dados.pop("program")
    (novo / "queue.yaml").write_text(yaml.safe_dump(dados, allow_unicode=True),
                                     encoding="utf-8")
    shutil.rmtree(Path(raiz) / ".claude" / "programs", ignore_errors=True)
    git(raiz, "add", "-A")
    git(raiz, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm",
        "fila no layout novo")


# [R4] queue_files: nome nos dois layouts, o novo ganha (direto e pela CLI)

def test_queue_files_nome_nos_dois_layouts_devolve_o_caminho_novo():
    qp = carrega_until().qp
    with tempfile.TemporaryDirectory() as base:
        d = novo_repo(base)
        fila_legada(d, nome="x", commita=False)
        fila_legada(d, nome="so-velha", commita=False)
        novo = d / ".claude" / "queues" / "x"
        novo.mkdir(parents=True)
        (novo / "queue.yaml").write_text("queue: x\n")
        achados = dict(qp.queue_files(d))
        assert achados["x"] == novo / "queue.yaml", achados
        assert achados["so-velha"].name == "plan.yaml", achados
        assert [n for n, _ in qp.queue_files(d)] == ["so-velha", "x"]


@com_repo
def test_cepa_plan_status_sem_nome_escolhe_a_fila_nova_quando_o_nome_esta_nos_dois(d):
    fila_legada(d, nome="x", commita=False)
    novo = d / ".claude" / "queues" / "x"
    novo.mkdir(parents=True)
    (novo / "queue.yaml").write_text(
        LEGADA.format(nome="x").replace("program:", "queue:").replace("item A", "item NOVO"),
        encoding="utf-8")
    # sem nome: a lista de candidatas vem de queue_files; é ela que escolhe o arquivo
    r = plan(d, "status", "--json", "--repo", ".")
    assert r.returncode == 0, r.stderr
    saida = json.loads(r.stdout)
    assert saida["path"].endswith("queues/x/queue.yaml"), saida["path"]
    assert saida["items"][0]["title"] == "item NOVO"


# [W3] sobrescrever fila do layout novo: backup é queue.yaml.bak

@com_repo
def test_cepa_plan_sobrescrever_fila_nova_faz_backup_queue_yaml_bak(d):
    itens = escreve_itens(d, [item("A")])
    r = plan(d, "write", "fila", "--items", str(itens), "--repo", ".")
    assert r.returncode == 0, r.stderr
    pasta = d / ".claude" / "queues" / "fila"
    assert (pasta / "queue.yaml").is_file()
    assert not (pasta / "queue.yaml.bak").exists()
    antes = (pasta / "queue.yaml").read_text(encoding="utf-8")
    itens = escreve_itens(d, [item("A"), item("B")])
    r = plan(d, "write", "fila", "--items", str(itens), "--repo", ".")
    assert r.returncode == 0, r.stderr
    assert sorted(p.name for p in pasta.iterdir() if p.is_file()) == \
        ["queue.yaml", "queue.yaml.bak"], list(pasta.iterdir())
    assert (pasta / "queue.yaml.bak").read_text(encoding="utf-8") == antes


# [U4 U5 U6 G1] cepa-until com fila no layout novo, de ponta a ponta

def test_cepa_until_dry_run_fila_nova_cabecalho_e_ledger_dir():
    """[G1] o cabeçalho mostra o nome vindo de `queue:`; [U6] a pasta do
    registro nasce em queues/<n>/until, e não em programs/."""
    from test_cepa_until import monta_repo, item as it
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [it("a1")])
        para_layout_novo(raiz)
        r = subprocess.run([sys.executable, str(CEPA_UNTIL), "fila", "--repo",
                            str(raiz), "--for", "1h", "--dry-run", "--sem-verify",
                            "--sem-analise"], capture_output=True, text=True,
                           cwd=str(raiz), timeout=120)
        assert r.returncode == 0, r.stdout + r.stderr
        primeira = r.stdout.splitlines()[0]
        assert "fila fila" in primeira.replace("\x1b[36m", "").replace("\x1b[0m", ""), \
            primeira
        assert (raiz / ".claude" / "queues" / "fila" / "until").is_dir()
        assert not (raiz / ".claude" / "programs").exists()


def test_cepa_until_cabecalho_mostra_nome_de_fila_com_so_queue():
    """[G1] o `cepa-plan queue` hoje devolve `program` E `queue`; se um dia só
    devolver `queue:`, o cabeçalho tem de continuar mostrando o nome. Chama o
    `main()` de verdade, com a consulta da fila devolvendo só `queue`."""
    import contextlib
    import io
    from test_cepa_until import monta_repo, item as it
    cu = carrega_until()
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [it("a1")])
        para_layout_novo(raiz)
        real = cu.consulta_fila

        def so_queue(nome, repo):
            dados, erro = real(nome, repo)
            dados.pop("program", None)
            dados["queue"] = "NOME-GRAVADO"
            return dados, erro
        cu.consulta_fila = so_queue
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            rc = cu.main(["fila", "--repo", str(raiz), "--for", "1h", "--dry-run",
                          "--sem-verify", "--sem-analise"])
        assert rc == 0, saida.getvalue()
        assert "NOME-GRAVADO" in saida.getvalue().splitlines()[0], saida.getvalue()[:300]
        assert (raiz / ".claude" / "queues" / "fila" / "until").is_dir()


def test_cepa_until_noite_aterrissa_e_pendentes_e_doctor_enxergam_fila_nova():
    """[U6] ledger e log em queues/<n>/until; [U5] o run vivo ali é achado por
    `pendentes` e pelo doctor ([D5]: repo só com .claude/queues); [U4] a fila
    suja no clone, no layout novo, não impede `aterrissar`."""
    from test_cepa_until import fake_claude, item as it, monta_repo, roda
    from test_cepa_until_branch_da_noite import TRABALHA, VERIFY
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [it("a1")])
        para_layout_novo(raiz)
        binv = fake_claude(Path(tmp), TRABALHA)
        plano = raiz / ".claude" / "queues" / "fila" / "queue.yaml"
        roda(raiz, binv, plano, ["--for", "2h", "--verify", VERIFY])
        until = raiz / ".claude" / "queues" / "fila" / "until"
        assert list(until.glob("*.jsonl")) and list(until.glob("*.log")), list(until.glob("*"))
        assert not (raiz / ".claude" / "programs").exists()
        run_id = sorted(until.glob("*.jsonl"))[-1].stem
        assert "status: done" in plano.read_text(), "a fila do clone foi marcada (suja)"
        assert git(raiz, "status", "--porcelain").count("queues/fila/queue.yaml") == 1

        p = subprocess.run([sys.executable, str(CEPA_UNTIL), "pendentes",
                            "--repo", str(raiz)], capture_output=True, text=True,
                           cwd=str(raiz), timeout=60)
        assert f"cepa-until aterrissar fila/{run_id}" in p.stdout, p.stdout + p.stderr

        d = subprocess.run([sys.executable, str(DOCTOR), "--projeto"],
                           cwd=str(raiz), capture_output=True, text=True,
                           timeout=120, env=dict(os.environ, CEPA_DOCTOR_INSTALL="off"))
        out = d.stdout + d.stderr
        assert "[until]" in out and f"cepa-until aterrissar fila/{run_id}" in out, out[-1500:]

        (raiz / ".claude" / "doctor-last-run").unlink(missing_ok=True)  # rastro do doctor
        env = dict(os.environ, CEPA_WORKTREE_HOME=str(Path(tmp) / "worktrees"))
        a = subprocess.run([sys.executable, str(CEPA_UNTIL), "aterrissar",
                            f"fila/{run_id}", "--repo", str(raiz), "--sim"],
                           capture_output=True, text=True, cwd=str(raiz), env=env,
                           timeout=120)
        assert a.returncode == 0, a.stdout + a.stderr
        assert "mudança sem commit" not in a.stderr


# [U7 U8] cepa-until-digest com o registro em queues/<n>/until

def _monta_run_novo(tmp):
    from test_cepa_until_digest import monta_run
    ledger = monta_run(tmp)
    velho = Path(tmp) / ".claude" / "programs" / "F"
    novo = Path(tmp) / ".claude" / "queues" / "F"
    novo.parent.mkdir(parents=True)
    shutil.move(str(velho), str(novo))
    (novo / "plan.yaml").rename(novo / "queue.yaml")
    return novo / "until" / ledger.name, novo / "queue.yaml"


def test_digest_le_o_arquivo_vizinho_queue_yaml_fora_de_repo_git():
    """[U8] sem git, a fila é o arquivo ao lado do registro: queue.yaml."""
    with tempfile.TemporaryDirectory() as tmp:
        ledger, arq = _monta_run_novo(tmp)
        p = subprocess.run([sys.executable, str(DIGEST), str(ledger)],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, p.stderr
        assert "depende do A1 que não está na main" in p.stdout, p.stdout[-900:]
        assert "queue.yaml" in p.stdout, p.stdout[-900:]


def test_digest_le_a_fila_do_clone_principal_no_layout_novo():
    """[U7] com o registro numa worktree, a fila de verdade é a do clone
    principal em queues/<n>/queue.yaml (a cópia da worktree está velha)."""
    from test_cepa_until_digest import monta_run
    with tempfile.TemporaryDirectory() as tmp:
        principal = Path(tmp) / "principal"
        principal.mkdir()
        git(principal, "init", "-q")
        git(principal, "-c", "user.email=t@t", "-c", "user.name=t", "commit",
            "-q", "--allow-empty", "-m", "raiz")
        wt = Path(tmp) / "wt"
        git(principal, "worktree", "add", "-q", "--detach", str(wt))
        ledger, copia = _monta_run_novo(wt)
        fila = principal / ".claude" / "queues" / "F"
        fila.mkdir(parents=True)
        (fila / "queue.yaml").write_text(yaml.safe_dump({"items": [
            {"id": "A1", "status": "done", "blocked_by": [], "evidence": "ok"},
            {"id": "A2", "status": "done", "blocked_by": [],
             "evidence": "FECHADO NO CLONE PRINCIPAL"}]}), encoding="utf-8")
        p = subprocess.run([sys.executable, str(DIGEST), str(ledger)],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, p.stderr
        assert "FECHADO NO CLONE PRINCIPAL" in p.stdout, p.stdout[-900:]
        assert "depende do A1 que não está na main" not in p.stdout
        assert str(fila / "queue.yaml") in p.stdout or \
            str((fila / "queue.yaml").resolve()) in p.stdout, p.stdout[-900:]


# [D4] o doctor CHAMA check_layout_da_fila (pela CLI)

def test_doctor_cli_avisa_nome_nos_dois_layouts():
    with tempfile.TemporaryDirectory() as base:
        d = novo_repo(base)
        fila_legada(d, nome="x", commita=False)
        novo = d / ".claude" / "queues" / "x"
        novo.mkdir(parents=True)
        (novo / "queue.yaml").write_text("queue: x\nmode: single-track\n")
        r = subprocess.run([sys.executable, str(DOCTOR), "--projeto"],
                           cwd=str(d), capture_output=True, text=True, timeout=120,
                           env=dict(os.environ, CEPA_DOCTOR_INSTALL="off"))
        out = r.stdout + r.stderr
        assert "dois layouts" in out, out[-1500:]


# [MP] maestro-programs lista as filas do layout novo

@com_repo
def test_maestro_programs_lista_filas_novas_junto_com_ondas_e_dedupe(d):
    ondas = d / ".claude" / "programs" / "ondas"
    ondas.mkdir(parents=True)
    (ondas / "plan.yaml").write_text(yaml.dump(
        {"schema_version": 2, "mode": "parallel-waves", "program": "ondas",
         "waves": [{"id": 1, "status": "pending", "slices": []}]}), encoding="utf-8")
    fila_legada(d, nome="dupla", commita=False)           # nos dois layouts
    fila_legada(d, nome="so-velha", commita=False)
    for nome in ("dupla", "so-nova"):
        pasta = d / ".claude" / "queues" / nome
        pasta.mkdir(parents=True)
        (pasta / "queue.yaml").write_text(
            LEGADA.format(nome=nome).replace("program:", "queue:"), encoding="utf-8")
    (d / ".claude" / "queues" / "sem-arquivo").mkdir()      # pasta sem queue.yaml
    r = run(MAESTRO_PROGRAMS, d, str(d), "--json")
    assert r.returncode == 0, r.stderr
    lista = json.loads(r.stdout)["programas"]
    assert len(lista) == len({p["nome"] for p in lista}), \
        f"nome nos dois layouts aparece uma vez só: {[p['nome'] for p in lista]}"
    progs = {p["nome"]: p for p in lista}
    assert sorted(progs) == ["dupla", "ondas", "so-nova", "so-velha"], sorted(progs)
    for nome in ("dupla", "so-nova"):
        assert progs[nome]["dir"].endswith(f".claude/queues/{nome}"), progs[nome]
        assert progs[nome]["mode"] == "single-track" and not progs[nome]["elegivel"]
        assert ".claude/queues" in progs[nome]["motivo"]
    assert progs["so-velha"]["dir"].endswith(".claude/programs/so-velha")
    assert progs["ondas"]["elegivel"] is True


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
