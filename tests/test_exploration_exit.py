#!/usr/bin/env python3
"""The exit verdict of the exploration mode is computed from the disk.

No external dependency — run with `python3 tests/test_exploration_exit.py`.

## Why it exists

Exploration was the only mode whose exit nobody measured. The hook repeated
"Fecha quando: ..." every turn, nothing checked it, and the agent kept
proposing one more turn until the owner had to ask "is anything still
pending?" (2026-11-04). The third part of the condition — the owner's decision
on each named disagreement — had nowhere to live on disk.

Contracts guarded here (`exploration_exit` in common/hooks/_modes.py):
  - no panel report in docs/reviews/ -> 0/3, open;
  - a report whose header points to a missing document -> that part fails;
  - a report with disagreements still `_pendente_` -> 2/3, names how many;
  - every disagreement with a `**Decisão do dono:**` filled -> 3/3, closed,
    next mode is discovery;
  - both header styles (`## ... — `doc`` and `# ...: `doc``) and both section
    styles (`### DISCORDÂNCIAS NOMEADAS` and `## Discordâncias nomeadas`) count;
  - the most recent report (date prefix of the file name) is the one judged;
  - the `session-mode.py` hook injects the `Saída:` line only for exploration;
  - `cepa-modes --exit` returns 0 closed, 1 open, 2 for a mode with no verdict.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from _isolated_telemetry import isolate  # noqa: E402

isolate()

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "common" / "hooks"))
from _modes import exploration_exit, exploration_exit_line  # noqa: E402

HOOK = REPO / "common" / "hooks" / "session-mode.py"
CEPA_MODES = REPO / "common" / "bin" / "cepa-modes"

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def repo(mode="exploration"):
    d = Path(tempfile.mkdtemp(prefix="cepa-exit-"))
    subprocess.run(["git", "init", "-q", str(d)], check=True)
    (d / ".claude").mkdir()
    (d / "docs" / "reviews").mkdir(parents=True)
    if mode:
        (d / ".claude" / "session-mode").write_text(
            f"mode: {mode}\nroutine: null\nbudget: null\nopened_at: 2026-11-04T10:00:00Z\n")
    return d


def panel(d, name, artifact, disagreements, header="## Painel de advisors — `%s` (area: `x`, 5 lenses)",
          section="### DISCORDÂNCIAS NOMEADAS"):
    body = [header % artifact, "", "### Convergências", "", "- tudo bem", "", section, ""]
    for title, decision in disagreements:
        body.append(f"- **contrarian diz X** vs. **executor diz Y** — {title}")
        body.append("  **O que decide entre elas:** o critério.")
        if decision is not None:
            body.append(f"  **Decisão do dono:** {decision}")
        body.append("")
    body += ["### Propostas consolidadas priorizadas", "", "1. algo"]
    (d / "docs" / "reviews" / name).write_text("\n".join(body) + "\n", encoding="utf-8")


def hook_context(d):
    out = subprocess.run([sys.executable, str(HOOK)],
                         input=json.dumps({"cwd": str(d), "prompt": "oi", "session_id": "t1"}),
                         capture_output=True, text=True, timeout=30)
    if not out.stdout.strip():
        return ""
    return json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"]


def cepa_modes_exit(d, *args):
    return subprocess.run([sys.executable, str(CEPA_MODES), "--exit", "--no-color", *args],
                          cwd=str(d), capture_output=True, text=True, timeout=30)


def main():
    print("sem painel")
    d = repo()
    v = exploration_exit(d)
    check("aberto", not v["closed"])
    check("0/3", sum(1 for _, ok, _ in v["items"] if ok) == 0)
    check("linha do hook diz 0/3", exploration_exit_line(d).startswith("Saída: 0/3"), exploration_exit_line(d))
    c = hook_context(d)
    check("hook injeta Saída: em exploração", "Saída: 0/3" in c, c)

    print("painel aponta documento que não existe")
    d = repo()
    panel(d, "2026-11-04-painel-x.md", "docs/estrategia-x.md", [("a", "_pendente_")])
    v = exploration_exit(d)
    check("documento falha", v["items"][1][1] is False, v["items"])
    check("aberto", not v["closed"])

    print("painel com decisões pendentes")
    d = repo()
    (d / "docs" / "estrategia-x.md").write_text("# x\n")
    panel(d, "2026-11-04-painel-x.md", "docs/estrategia-x.md",
          [("a", "_pendente_"), ("b", None), ("c", "fica o caminho B")])
    v = exploration_exit(d)
    check("2/3", sum(1 for _, ok, _ in v["items"] if ok) == 2, v["items"])
    check("conta 2 de 3 pendentes", "2 de 3" in v["items"][2][2], v["items"][2])
    line = exploration_exit_line(d)
    check("linha nomeia o painel", "2026-11-04-painel-x.md" in line, line)
    r = cepa_modes_exit(d)
    check("cepa-modes --exit rc=1 aberto", r.returncode == 1, r.stdout + r.stderr)
    check("cepa-modes --exit mostra ✗", "✗ decisão do dono" in r.stdout, r.stdout)

    print("todas as decisões registradas")
    d = repo()
    (d / "docs" / "estrategia-x.md").write_text("# x\n")
    panel(d, "2026-11-04-painel-x.md", "docs/estrategia-x.md",
          [("a", "mantém A, pelo custo"), ("b", "vai de B")])
    v = exploration_exit(d)
    check("fechado", v["closed"], v["items"])
    check("próximo modo discovery", v["next_mode"] == "discovery")
    line = exploration_exit_line(d)
    check("linha diz FECHADA e aponta discovery", "FECHADA" in line and "cepa --mode discovery" in line, line)
    c = hook_context(d)
    check("hook injeta FECHADA", "FECHADA" in c, c)
    r = cepa_modes_exit(d)
    check("cepa-modes --exit rc=0 fechado", r.returncode == 0, r.stdout + r.stderr)

    print("painel sem discordâncias: nada a decidir")
    d = repo()
    (d / "docs" / "estrategia-x.md").write_text("# x\n")
    panel(d, "2026-11-04-painel-x.md", "docs/estrategia-x.md", [])
    check("fechado", exploration_exit(d)["closed"])

    print("formato antigo: `# Painel de advisors: `doc`` e `## Discordâncias nomeadas`")
    d = repo()
    (d / "docs" / "estrategia-x.md").write_text("# x\n")
    panel(d, "2026-10-07-painel-x.md", "docs/estrategia-x.md", [("a", None)],
          header="# Painel de advisors: `%s` (área: arquitetura, 7 lentes)",
          section="## Discordâncias nomeadas")
    v = exploration_exit(d)
    check("cabeçalho antigo reconhecido", v["panel"] == "docs/reviews/2026-10-07-painel-x.md", v)
    check("seção antiga reconhecida, 1 pendente", "1 de 1" in v["items"][2][2], v["items"])

    print("formato antigo: `- **O que decide:**` como bullet solto não é discordância nova")
    d = repo()
    (d / "docs" / "estrategia-x.md").write_text("# x\n")
    text = ("# Painel de advisors: `docs/estrategia-x.md`\n\n## Discordâncias nomeadas\n\n"
            "- **A vs B** sobre o corte.\n- **O que decide:** o prazo.\n\n"
            "- **C vs D** sobre o nome.\n- **O que decide:** o dono.\n\n## Recomendação\n")
    (d / "docs" / "reviews" / "2026-10-07-painel-y.md").write_text(text)
    v = exploration_exit(d)
    check("conta 2 discordâncias, não 4", "2 de 2" in v["items"][2][2], v["items"])

    print("o painel mais recente é o julgado")
    d = repo()
    (d / "docs" / "estrategia-x.md").write_text("# x\n")
    panel(d, "2026-10-01-painel-velho.md", "docs/estrategia-x.md", [("a", "decidido")])
    panel(d, "2026-11-04-painel-novo.md", "docs/estrategia-x.md", [("a", "_pendente_")])
    v = exploration_exit(d)
    check("julga o novo", v["panel"].endswith("painel-novo.md") and not v["closed"], v)
    v = exploration_exit(d, panel="docs/reviews/2026-10-01-painel-velho.md")
    check("--panel fixa o velho", v["closed"], v)

    print("outros modos não ganham a linha")
    d = repo(mode="construction")
    c = hook_context(d)
    check("hook sem Saída: em construção", "[modo]" in c and "Saída:" not in c, c)
    r = cepa_modes_exit(d)
    check("cepa-modes --exit rc=2 sem veredito", r.returncode == 2, r.stdout + r.stderr)
    d = repo(mode=None)
    r = cepa_modes_exit(d)
    check("sem modo declarado: rc=2 e pede o modo", r.returncode == 2 and "exploration" in r.stderr, r.stderr)

    print()
    if failures:
        print(f"FAIL: {len(failures)} — {failures}")
        return 1
    print("ok: exploration exit verdict")
    return 0


if __name__ == "__main__":
    sys.exit(main())
