#!/usr/bin/env python3
"""run-eval — executa a suíte de tarefas douradas e mede o harness.

Ver `tests/eval/README.md` para o desenho e o porquê. Resumo do mecanismo:

    worktree limpa no base_commit
      → agente recebe o enunciado do problema (sem a solução)
        → teste do fix_commit é trazido para a worktree
          → roda; passou/não passou é o resultado

O passo do teste-vindo-de-fora é o que impede a tarefa de se autoaprovar: se a
aceitação fosse escrita pelo próprio agente, a suíte mediria a capacidade dele
de escrever um teste que passa, que é sempre 100%.

Modos:
  --validate   roda a aceitação SEM agente e exige VERMELHO em toda tarefa.
               Barato (não gasta modelo) e obrigatório: tarefa que já passa no
               base_commit não mede nada e entraria na conta como verde grátis.
  --run        roda a suíte de verdade (GASTA MODELO — uma sessão headless por
               tarefa).
  --compare    compara dois resultados salvos.

Sem dependências de terceiros: o YAML das tarefas é lido por um parser mínimo
(o mesmo caminho que o path-lock do build-hex já usa para o build-hex.yaml).
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
REPO = EVAL_DIR.parent.parent
TASKS_DIR = EVAL_DIR / "tasks"
RESULTS_DIR = EVAL_DIR / "results"
WORKTREE_ROOT = Path(os.environ.get("CEPA_EVAL_WORKTREES", "/tmp/cepa-eval"))


# ── YAML mínimo (escalares, listas simples e blocos `|`) ─────────────────────

def parse_task_yaml(text: str) -> dict:
    """Só o que o schema de tarefa usa: `chave: valor` e `chave: |` multilinha.

    Não é um parser de YAML — é o subconjunto declarado no README. Qualquer
    coisa fora dele deve falhar aqui, ruidosamente, em vez de ser aceita pela
    metade: uma tarefa mal lida vira uma medição errada.
    """
    data, lines, i = {}, text.splitlines(), 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", raw)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val == "|":
            block, indent = [], None
            while i < len(lines):
                nxt = lines[i]
                if nxt.strip() and not nxt.startswith((" ", "\t")):
                    break
                if indent is None and nxt.strip():
                    indent = len(nxt) - len(nxt.lstrip())
                block.append(nxt[indent:] if indent and len(nxt) >= indent else nxt.strip())
                i += 1
            data[key] = "\n".join(block).strip()
        else:
            data[key] = val.strip("\"'")
    return data


def load_tasks(only=None) -> list:
    tasks = []
    for p in sorted(TASKS_DIR.glob("*.yaml")):
        t = parse_task_yaml(p.read_text(encoding="utf-8"))
        t["_file"] = str(p)
        missing = [k for k in ("id", "fix_commit", "base_commit",
                               "acceptance_test", "acceptance_cmd", "prompt") if not t.get(k)]
        if missing:
            print(f"⚠ {p.name}: campos ausentes {missing} — tarefa ignorada", file=sys.stderr)
            continue
        if only and t["id"] not in only:
            continue
        tasks.append(t)
    return tasks


# ── worktree ─────────────────────────────────────────────────────────────────

def git(*args, cwd=REPO, check=True):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, check=check)


def make_worktree(task: dict) -> Path:
    wt = WORKTREE_ROOT / f"{task['id']}-{int(time.time())}"
    WORKTREE_ROOT.mkdir(parents=True, exist_ok=True)
    git("worktree", "add", "--detach", str(wt), task["base_commit"])
    return wt


def drop_worktree(wt: Path):
    git("worktree", "remove", "--force", str(wt), check=False)
    shutil.rmtree(wt, ignore_errors=True)


def bring_acceptance(task: dict, wt: Path) -> bool:
    """Traz o teste do commit do conserto — a trava contra autoaprovação."""
    r = git("checkout", task["fix_commit"], "--", task["acceptance_test"],
            cwd=wt, check=False)
    if r.returncode != 0:
        print(f"    ! não consegui trazer {task['acceptance_test']}: {r.stderr.strip()[:160]}")
        return False
    # conftest.py é a cola entre os dois estilos de teste do repo; sem ele
    # algumas suítes reportam erro que não é defeito nenhum.
    git("checkout", task["fix_commit"], "--", "tests/conftest.py", cwd=wt, check=False)
    return True


def run_acceptance(task: dict, wt: Path, timeout=300) -> tuple:
    try:
        r = subprocess.run(task["acceptance_cmd"], shell=True, cwd=str(wt),
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout + r.stderr)[-1500:]
    except subprocess.TimeoutExpired:
        return False, f"timeout após {timeout}s"


# ── métricas de gate (delta na telemetria) ──────────────────────────────────

def telemetry_count() -> int:
    d = Path(os.environ.get("CEPA_TELEMETRY_DIR") or (Path.home() / ".claude" / "cepa-telemetry"))
    n = 0
    for f in d.glob("events-*.jsonl") if d.is_dir() else []:
        try:
            n += sum(1 for line in f.read_text(encoding="utf-8", errors="replace").splitlines()
                     if '"gate_block"' in line or '"loop_block"' in line or '"proof_block"' in line)
        except OSError:
            pass
    return n


# ── modos ────────────────────────────────────────────────────────────────────

def cmd_validate(tasks) -> int:
    """Toda tarefa TEM de falhar sem o agente. Sem isso a suíte se engana."""
    print(f"Validando {len(tasks)} tarefa(s) — a aceitação precisa ficar VERMELHA "
          f"no base_commit.\n")
    bad = []
    for t in tasks:
        print(f"  {t['id']:26} base={t['base_commit'][:8]} … ", end="", flush=True)
        wt = None
        try:
            wt = make_worktree(t)
            if not bring_acceptance(t, wt):
                print("INCONCLUSIVO (teste não veio)")
                bad.append((t["id"], "teste do fix_commit não pôde ser trazido"))
                continue
            passed, out = run_acceptance(t, wt)
            if passed:
                print("❌ PASSOU SEM AGENTE")
                bad.append((t["id"], "verde no base_commit — não mede nada"))
            else:
                print("✓ vermelha, como tem de ser")
        except subprocess.CalledProcessError as e:
            print(f"ERRO ({e.stderr.strip()[:80]})")
            bad.append((t["id"], "worktree falhou"))
        finally:
            if wt:
                drop_worktree(wt)
    print()
    if bad:
        print(f"{len(bad)} tarefa(s) inválida(s):")
        for tid, why in bad:
            print(f"  - {tid}: {why}")
        print("\nUma tarefa que passa sem o agente entra na conta como verde grátis "
              "e faz a suíte inteira parecer melhor do que é.")
        return 1
    print("todas as tarefas provam que exigem trabalho real.")
    return 0


def cmd_run(tasks, label: str, timeout_min: int) -> int:
    print(f"Rodando {len(tasks)} tarefa(s) — label '{label}'.")
    print("Cada tarefa é uma sessão headless: ISSO GASTA MODELO.\n")
    if not shutil.which("claude"):
        print("! `claude` não está no PATH — não dá para rodar o agente.", file=sys.stderr)
        return 2

    results = []
    for t in tasks:
        print(f"  {t['id']:26} … ", end="", flush=True)
        wt, started = None, time.time()
        rec = {"id": t["id"], "dificuldade": t.get("dificuldade", "?"),
               "base_commit": t["base_commit"]}
        try:
            wt = make_worktree(t)
            gates_before = telemetry_count()
            proc = subprocess.run(
                ["claude", "-p", t["prompt"], "--output-format", "json"],
                cwd=str(wt), capture_output=True, text=True, timeout=timeout_min * 60,
            )
            rec["agent_exit"] = proc.returncode
            try:
                meta = json.loads(proc.stdout)
                rec["turns"] = meta.get("num_turns")
                rec["cost_usd"] = meta.get("total_cost_usd")
            except (json.JSONDecodeError, AttributeError):
                rec["turns"] = rec["cost_usd"] = None
            rec["gate_blocks"] = telemetry_count() - gates_before
            if bring_acceptance(t, wt):
                rec["passed"], rec["output"] = run_acceptance(t, wt)
            else:
                rec["passed"], rec["output"] = False, "aceitação não pôde ser trazida"
        except subprocess.TimeoutExpired:
            rec["passed"], rec["output"] = False, f"timeout de {timeout_min}min"
        except Exception as e:  # noqa: BLE001
            rec["passed"], rec["output"] = False, f"erro do executor: {e}"
        finally:
            rec["duration_s"] = round(time.time() - started, 1)
            if wt:
                drop_worktree(wt)
        results.append(rec)
        print(f"{'PASSOU' if rec.get('passed') else 'falhou'} "
              f"({rec['duration_s']}s, {rec.get('turns') or '?'} voltas, "
              f"{rec.get('gate_blocks', '?')} bloqueios)")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{label}.json"
    out.write_text(json.dumps(
        {"label": label, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "harness_commit": git("rev-parse", "--short", "HEAD").stdout.strip(),
         "results": results}, indent=2, ensure_ascii=False), encoding="utf-8")

    n_ok = sum(1 for r in results if r.get("passed"))
    print(f"\n{n_ok}/{len(results)} passaram. Resultado em {out}")
    if n_ok == len(results):
        print("⚠ 100% — se repetir, a suíte parou de distinguir versões do harness; "
              "está na hora de uma tarefa mais difícil.")
    if n_ok == 0:
        print("⚠ 0% — idem: uma suíte que nunca passa também não compara nada.")
    return 0


def cmd_compare(a: str, b: str) -> int:
    pa, pb = RESULTS_DIR / f"{a}.json", RESULTS_DIR / f"{b}.json"
    for p in (pa, pb):
        if not p.exists():
            print(f"! {p} não existe", file=sys.stderr)
            return 2
    da, db = json.loads(pa.read_text()), json.loads(pb.read_text())
    ra = {r["id"]: r for r in da["results"]}
    rb = {r["id"]: r for r in db["results"]}

    print(f"{a} ({da.get('harness_commit','?')})  ×  {b} ({db.get('harness_commit','?')})\n")
    print(f"{'tarefa':26} {'antes':>10} {'depois':>10}   {'voltas':>13} {'bloqueios':>11}")
    for tid in sorted(set(ra) | set(rb)):
        x, y = ra.get(tid, {}), rb.get(tid, {})
        mark = {(True, False): "  ← REGREDIU", (False, True): "  ← melhorou"}.get(
            (bool(x.get("passed")), bool(y.get("passed"))), "")
        print(f"{tid:26} {'passou' if x.get('passed') else 'falhou':>10} "
              f"{'passou' if y.get('passed') else 'falhou':>10}   "
              f"{str(x.get('turns','?')) + '→' + str(y.get('turns','?')):>13} "
              f"{str(x.get('gate_blocks','?')) + '→' + str(y.get('gate_blocks','?')):>11}{mark}")

    na = sum(1 for r in da["results"] if r.get("passed"))
    nb = sum(1 for r in db["results"] if r.get("passed"))
    print(f"\ntaxa: {na}/{len(da['results'])} → {nb}/{len(db['results'])}")
    if nb < na:
        print("REGRESSÃO: a mudança fez o harness terminar menos tarefas.")
    print("\nLeitura de bloqueios: mais bloqueios COM mais tarefas terminadas é "
          "o gate funcionando; mais bloqueios com menos tarefas terminadas é "
          "atrito puro.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Suíte de tarefas douradas da Cepa.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--validate", action="store_true",
                   help="prova que cada tarefa falha sem agente (não gasta modelo)")
    g.add_argument("--run", action="store_true", help="roda a suíte (GASTA MODELO)")
    g.add_argument("--compare", nargs=2, metavar=("ANTES", "DEPOIS"))
    g.add_argument("--list", action="store_true", help="lista as tarefas declaradas")
    ap.add_argument("--task", action="append", help="restringe a estes ids")
    ap.add_argument("--label", default="run", help="nome do resultado salvo")
    ap.add_argument("--timeout-min", type=int, default=30)
    args = ap.parse_args()

    if args.compare:
        return cmd_compare(*args.compare)

    tasks = load_tasks(set(args.task) if args.task else None)
    if not tasks:
        print("nenhuma tarefa em tests/eval/tasks/", file=sys.stderr)
        return 2

    if args.list:
        for t in tasks:
            print(f"{t['id']:26} [{t.get('dificuldade','?'):6}] {t.get('titulo','')}")
        return 0
    if args.validate:
        return cmd_validate(tasks)
    return cmd_run(tasks, args.label, args.timeout_min)


if __name__ == "__main__":
    sys.exit(main())
