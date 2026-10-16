#!/usr/bin/env python3
"""Executa common/gauntlet/gauntlet.workflow.js com agent/parallel/phase/log SIMULADOS.

Sem gastar token: um harness em node lê o script, troca `export const meta` por
`const meta`, embrulha o corpo numa função async (o `return` no topo vira
válido) e injeta fakes que gravam cada chamada e devolvem JSON pronto por label.
O teste então inspeciona as chamadas e o retorno: ordem das fases, isolamento
dos builders, cegueira e rotação dos juízes, Borda, desempate, rótulo
desconhecido, menos de 2 designs, e `args` como string JSON.

Sem `node` o teste FALHA (não pula): execução do script é a única prova de que
ele roda; pular esconderia a regressão.
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "common" / "gauntlet" / "gauntlet.workflow.js"
FAILURES = []

HARNESS = r"""
import fs from 'node:fs'
const [scriptPath] = process.argv.slice(2)
const sc = JSON.parse(fs.readFileSync(0, 'utf8'))
let src = fs.readFileSync(scriptPath, 'utf8').replace('export const meta', 'const meta')
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
const run = new AsyncFunction('args', 'agent', 'parallel', 'phase', 'log', src)

const events = []   // {t:'phase'|'agent'|'log', ...} em ordem
const phase = n => events.push({ t: 'phase', name: n })
const log = m => events.push({ t: 'log', msg: String(m) })
const parallel = fns => Promise.all(fns.map(f => f()))
const bar = { criteria: [1, 2, 3, 4, 5].map(i => ({ id: 'c' + i, text: 't' + i, how_to_judge: 'h' })), reference_bar: 'ref' }
const design = (title) => ({ title, mechanism: 'MECH of ' + title, surfaces: [], worst_case_handling: 'w', failure_modes: 'f', test_plan: 't', cost: 'c' })

const agent = async (prompt, opts) => {
  const label = opts.label
  events.push({ t: 'agent', label, phase: opts.phase, prompt })
  if (label === 'bar-setter') return bar
  if (label.startsWith('builder:')) {
    const i = events.filter(e => e.t === 'agent' && e.label.startsWith('builder:')).length - 1
    if ((sc.null_builders || []).includes(i)) return null
    return design(sc.markers[i])
  }
  if (label.startsWith('judge-')) {
    const j = Number(label.slice(6)) - 1
    return { ranking: sc.rankings[j], scores: [], biggest_gaps: [] }
  }
  if (label === 'reviser') return design('REVISED')
  if (label === 'final-check') return { bar_met: true, remaining_gaps: [], verdict_note: 'ok' }
  throw new Error('label inesperado ' + label)
}

const result = await run(sc.as_string ? JSON.stringify(sc.args) : sc.args, agent, parallel, phase, log)
process.stdout.write(JSON.stringify({ events, result }))
"""

ANGLES = [
    {"key": "ang-um", "brief": "BRIEF-UM do primeiro angulo"},
    {"key": "ang-dois", "brief": "BRIEF-DOIS do segundo angulo"},
    {"key": "ang-tres", "brief": "BRIEF-TRES do terceiro angulo"},
]
MARKERS = ["MARCA-ZQ1", "MARCA-ZQ2", "MARCA-ZQ3"]
ARGS = {"repo": "/tmp/repo-fake", "goal": "GOAL-FAKE reduzir atrito",
        "context": "CTX-FAKE contexto", "angles": ANGLES, "reads": ["a.md", "b.md"]}


def check(nome, cond, detalhe=""):
    print(("  ok  " if cond else "FAIL  ") + nome + ("" if cond else f"  {detalhe}"))
    if not cond:
        FAILURES.append(nome)


def run(tmp, rankings, angles=None, null_builders=(), as_string=False):
    angles = angles or ANGLES
    sc = {"args": dict(ARGS, angles=angles), "rankings": rankings, "markers": MARKERS,
          "null_builders": list(null_builders), "as_string": as_string}
    p = subprocess.run(["node", str(tmp / "harness.mjs"), str(SCRIPT)],
                       input=json.dumps(sc), capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        return None, p.stderr[-800:]
    return json.loads(p.stdout), ""


def agents(out, prefix):
    return [e for e in out["events"] if e["t"] == "agent" and e["label"].startswith(prefix)]


def logs(out):
    return [e["msg"] for e in out["events"] if e["t"] == "log"]


def main():
    print("gauntlet.workflow.js — execução simulada\n")
    if shutil.which("node") is None:
        check("node instalado (brew install node)", False, "node ausente: sem ele o script não é executado")
        return 1
    check("o script existe", SCRIPT.is_file(), str(SCRIPT))
    tmp = Path(tempfile.mkdtemp(prefix="gauntlet-wf-"))
    (tmp / "harness.mjs").write_text(HARNESS, encoding="utf-8")

    base = [["A", "B", "C"], ["A", "C", "B"], ["B", "A", "C"]]
    out, err = run(tmp, base)
    check("execução base roda", out is not None, err)
    if out is None:
        return 1

    # a. ordem das fases
    fases = [e["name"] for e in out["events"] if e["t"] == "phase"]
    check("a. fases na ordem Barra, Builders, Julgamento, Revisão",
          fases == ["Barra", "Builders", "Julgamento", "Revisão"], str(fases))
    ordem = [e["label"] for e in out["events"] if e["t"] == "agent"]
    ib = ordem.index("bar-setter")
    check("a. bar-setter roda antes de qualquer builder",
          all(ordem.index(b["label"]) > ib for b in agents(out, "builder:")))
    check("a. builders antes dos juízes, juízes antes do reviser e da checagem",
          ordem.index("judge-1") > ordem.index(agents(out, "builder:")[-1]["label"])
          and ordem.index("reviser") > ordem.index("judge-3")
          and ordem[-1] == "final-check", str(ordem))

    # b. isolamento dos builders
    bs = agents(out, "builder:")
    check("b. um builder por ângulo", len(bs) == 3, str(len(bs)))
    for i, b in enumerate(bs):
        outros = [MARKERS[k] for k in range(3) if k != i]
        check(f"b. builder {i+1} não contém design de outro builder",
              not any(m in b["prompt"] for m in outros))
        check(f"b. builder {i+1} contém o próprio brief",
              ANGLES[i]["brief"] in b["prompt"])
        check(f"b. builder {i+1} não contém o brief dos outros",
              not any(ANGLES[k]["brief"] in b["prompt"] for k in range(3) if k != i))

    # c. juízes
    js = agents(out, "judge-")
    check("c. exatamente 3 juízes", len(js) == 3, str(len(js)))
    for j, jd in enumerate(js):
        p = jd["prompt"]
        check(f"c. juiz {j+1} não vê ângulo, brief nem label de builder",
              not any(a["key"] in p or a["brief"] in p for a in ANGLES) and "builder:" not in p)
        marcas = re.findall(r"=== DESIGN ([A-Z]) ===", p)
        esperado = [("ABC")[(i + j) % 3] for i in range(3)]
        check(f"c. juiz {j+1} recebe ordem rotacionada {''.join(esperado)}",
              marcas == esperado, str(marcas))
        check(f"c. juiz {j+1} recebe objetivo e barra",
              "GOAL-FAKE" in p and "QUALITY BAR" in p)

    # d. Borda
    r = out["result"]
    check("d. Borda [A,B,C],[A,C,B],[B,A,C]: A=3+3+2=8, B=2+1+3=6, C=1+2+1=4",
          r["borda_points"] == {"A": 8, "B": 6, "C": 4}, str(r["borda_points"]))
    check("d. vencedor A", r["winner"]["label"] == "A" and r["winner"]["angle"] == "ang-um")
    check("d. retorno tem o formato do piloto",
          set(r) == {"bar", "designs", "full_designs", "verdicts", "borda_points",
                     "winner", "revised_design", "final_check"}, str(sorted(r)))

    # e. desempate
    o, _ = run(tmp, [["A", "B", "C"], ["B", "A", "C"], ["C", "A", "B"]])
    check("e. sem empate: A=3+2+2=7, B=2+3+1=6, C=1+1+3=5, vence A",
          o["result"]["borda_points"] == {"A": 7, "B": 6, "C": 5} and o["result"]["winner"]["label"] == "A")
    o, _ = run(tmp, [["A", "B"], ["B", "A"], ["A", "B"]], angles=ANGLES[:2])
    check("e. 2 designs: A=2+1+2=5, B=1+2+1=4, vence A",
          o["result"]["borda_points"] == {"A": 5, "B": 4} and o["result"]["winner"]["label"] == "A")
    o, _ = run(tmp, [["A", "B", "C"], ["B", "C", "A"], ["C", "A", "B"]])
    check("e. empate total (6/6/6, um 1º cada): vence o primeiro na ordem, A",
          o["result"]["borda_points"] == {"A": 6, "B": 6, "C": 6} and o["result"]["winner"]["label"] == "A")
    check("e. o log menciona o empate", any("empate" in m for m in logs(o)), str(logs(o)))
    o, _ = run(tmp, [["A", "B", "C"], ["C", "A", "B"], ["C", "A", "B"]])
    check("e. empate A=3+2+2=7 e C=1+3+3=7: C tem 2 primeiros lugares contra 1 e vence",
          o["result"]["borda_points"]["A"] == 7 and o["result"]["borda_points"]["C"] == 7
          and o["result"]["winner"]["label"] == "C", str(o["result"]["borda_points"]))

    # f. rótulo desconhecido
    o, _ = run(tmp, [["Z", "A", "B", "C"], ["A", "B", "C"], ["A", "C", "B"]])
    pts = o["result"]["borda_points"]
    check("f. Z não entra nos pontos", "Z" not in pts, str(pts))
    check("f. o log nomeia o juiz 1 e o rótulo Z",
          any("juiz 1" in m and '"Z"' in m for m in logs(o)), str(logs(o)))
    check("f. vencedor não afetado (A)", o["result"]["winner"]["label"] == "A")

    # g. menos de 2 designs
    o, _ = run(tmp, base, null_builders=[0, 1])
    check("g. 1 design sobrevivente devolve error",
          "error" in o["result"] and "2 designs" in o["result"]["error"], str(o["result"])[:200])
    check("g. sem juízes quando não há competição", not agents(o, "judge-"))

    # h. args como string JSON
    o2, _ = run(tmp, base, as_string=True)
    check("h. args string JSON dá o mesmo resultado que objeto",
          o2 is not None and o2["result"]["borda_points"] == r["borda_points"]
          and o2["result"]["winner"] == r["winner"])

    # ciclo de ângulos: labels únicos
    ciclo = [ANGLES[0], ANGLES[1], ANGLES[0]]
    o, _ = run(tmp, base, angles=ciclo)
    rotulos = [b["label"] for b in agents(o, "builder:")]
    check("labels de builder únicos quando o ângulo se repete",
          len(set(rotulos)) == 3, str(rotulos))

    shutil.rmtree(tmp, ignore_errors=True)
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        return 1
    print("\ntudo ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
