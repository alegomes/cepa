#!/usr/bin/env python3
"""Regression tests for common/hooks/acceptance-gate.py.

No third-party deps beyond PyYAML (already required by the hook) — run with
`python3 tests/test_acceptance_gate.py`. Exits non-zero on failure.

Guards the contracts of the acceptance gate:
  - no artifact anywhere + target == done -> BLOCK (decided 2026-09-27, item
    `acceptance-gate-barra-done-sem-auditoria`): reaching Done with zero audit
    means the completion-auditor step was skipped, not that it "hasn't run yet";
  - no artifact anywhere + target in_review, in_progress, or unresolved ->
    allow (the audit hasn't run yet; nothing to enforce before Review);
  - artifact `complete` -> allow, in any direction;
  - artifact incomplete + FORWARD transition (in_review / done) -> BLOCK;
  - artifact incomplete + BACKWARD transition (in_progress / to_do / wont_do)
    -> ALLOW. This is the 2026-07-31 defect: the gate was direction-blind and
    trapped WEGO-1782 in Review, barring the very bounce its own incomplete
    verdict called for;
  - unresolvable direction (no map, no id, unknown id, broken yaml) -> BLOCK,
    because a config problem must never silently open a gate;
  - both MCP dialects (transition.id and transition_id) are understood;
  - other tools, missing keys and unparseable payloads fail open.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "acceptance-gate.py"

FAILURES = []

CLOUD_TOOL = "mcp__claude_ai_Atlassian__transitionJiraIssue"
LOCAL_TOOL = "mcp__mcp-atlassian__jira_transition_issue"

KEY = "WEGO-1782"

BOARD_FLOW = """\
defaults:
  project_key: WEGO
  status_map:
    to_do: "To Do"
    in_progress: "In Progress"
    in_review: "In Review"
    done: "Done"
  transition_ids:
    "11": to_do
    "31": in_progress
    "41": in_review
    "51": done
    "231": wont_do
"""

AUDIT_INCOMPLETE = """\
key: WEGO-1782
status: incomplete
criteria:
  - id: AC1
    gap: "o teste de aceite roda com dublê no lugar do adapter corrigido"
"""

AUDIT_COMPLETE = """\
key: WEGO-1782
status: complete
"""


def make_project(audit=None, board_flow=None):
    d = Path(tempfile.mkdtemp(prefix="acceptance-gate-test-"))
    if audit is not None:
        acc = d / ".claude" / "acceptance"
        acc.mkdir(parents=True)
        (acc / f"{KEY}.yaml").write_text(audit, encoding="utf-8")
    if board_flow is not None:
        (d / "board-flow.yaml").write_text(board_flow, encoding="utf-8")
    return d


def run_hook(cwd, tool_name=CLOUD_TOOL, tool_input=None):
    payload = json.dumps({
        "tool_name": tool_name,
        "tool_input": tool_input if tool_input is not None else {},
        "cwd": str(cwd),
    })
    return subprocess.run(
        [sys.executable, str(HOOK)], input=payload, capture_output=True, text=True
    )


def cloud(tid):
    return {"issueIdOrKey": KEY, "transition": {"id": tid}}


def local(tid):
    return {"issue_key": KEY, "transition_id": tid}


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


# ── the reported defect: an incomplete audit must not trap the card ─────────
proj = make_project(audit=AUDIT_INCOMPLETE, board_flow=BOARD_FLOW)

for tid, label in (("31", "In Progress"), ("11", "To Do"), ("231", "Won't Do")):
    r = run_hook(proj, tool_input=cloud(tid))
    check(f"auditoria incompleta → devolução para {label} PASSA",
          r.returncode == 0, f"rc={r.returncode} {r.stderr[:200]}")

# ── …without losing the teeth it exists for ────────────────────────────────
for tid, label in (("41", "In Review"), ("51", "Done")):
    r = run_hook(proj, tool_input=cloud(tid))
    check(f"auditoria incompleta → avanço para {label} BLOQUEIA",
          r.returncode == 2, f"rc={r.returncode}")

# ── the other MCP dialect ──────────────────────────────────────────────────
r = run_hook(proj, tool_name=LOCAL_TOOL, tool_input=local("31"))
check("mcp-atlassian: transition_id de volta PASSA", r.returncode == 0, r.stderr[:200])

r = run_hook(proj, tool_name=LOCAL_TOOL, tool_input=local("41"))
check("mcp-atlassian: transition_id de ida BLOQUEIA", r.returncode == 2)

# ── unresolvable direction fails CLOSED ────────────────────────────────────
no_cfg = make_project(audit=AUDIT_INCOMPLETE)
r = run_hook(no_cfg, tool_input=cloud("31"))
check("sem board-flow.yaml → BLOQUEIA (fail closed)", r.returncode == 2)
check("…e a mensagem ensina a declarar transition_ids",
      "transition_ids" in r.stderr, r.stderr[:200])

r = run_hook(proj, tool_input=cloud("999"))
check("id fora do mapa → BLOQUEIA", r.returncode == 2)

r = run_hook(proj, tool_input={"issueIdOrKey": KEY})
check("sem id de transição → BLOQUEIA", r.returncode == 2)

broken = make_project(audit=AUDIT_INCOMPLETE, board_flow="defaults: [not, a, mapping\n")
r = run_hook(broken, tool_input=cloud("31"))
check("yaml quebrado → BLOQUEIA (config ruim não abre portão)", r.returncode == 2)

empty_map = make_project(audit=AUDIT_INCOMPLETE,
                         board_flow="defaults:\n  project_key: WEGO\n")
r = run_hook(empty_map, tool_input=cloud("31"))
check("board-flow.yaml sem transition_ids → BLOQUEIA", r.returncode == 2)

# ── worktree nova: o artefato mora no clone principal (WEGO-2218, 2026-09-16) ─
def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def make_worktree_pair(audit, where=Path(".claude") / "acceptance"):
    """Clone principal com o artefato em `where` e uma worktree ligada sem ele,
    como deixa o seed-worktree (que não copia `.claude/acceptance/`)."""
    main = Path(tempfile.mkdtemp(prefix="acceptance-gate-main-"))
    git("init", "-q", "-b", "main", cwd=main)
    (main / "board-flow.yaml").write_text(BOARD_FLOW, encoding="utf-8")
    (main / ".gitignore").write_text(".claude/\n", encoding="utf-8")
    git("add", "-A", cwd=main)
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init", cwd=main)
    wt = Path(tempfile.mkdtemp(prefix="acceptance-gate-wt-")) / "wt"
    git("worktree", "add", "-q", "-b", "session/x", str(wt), cwd=main)
    if audit is not None:
        (main / where).mkdir(parents=True, exist_ok=True)
        (main / where / f"{KEY}.yaml").write_text(audit, encoding="utf-8")
    return main, wt


main, wt = make_worktree_pair(AUDIT_INCOMPLETE)
check("pré-condição: a worktree não tem o artefato",
      not (wt / ".claude" / "acceptance" / f"{KEY}.yaml").exists())
for tid, label in (("41", "In Review"), ("51", "Done")):
    r = run_hook(wt, tool_input=cloud(tid))
    check(f"worktree + artefato incompleto no clone principal → {label} BLOQUEIA",
          r.returncode == 2, f"rc={r.returncode} {r.stderr[:200]}")
check("…e a mensagem aponta o artefato do clone principal",
      str(main.resolve()) in r.stderr, r.stderr[:300])
(wt / "sub").mkdir()
r = run_hook(wt / "sub", tool_input=cloud("51"))
check("worktree, cwd num subdiretório → Done BLOQUEIA", r.returncode == 2, r.stderr[:200])
r = run_hook(wt, tool_input=cloud("31"))
check("worktree + artefato incompleto no principal → devolução PASSA", r.returncode == 0)

(wt / ".claude" / "acceptance").mkdir(parents=True)
(wt / ".claude" / "acceptance" / f"{KEY}.yaml").write_text(AUDIT_COMPLETE, encoding="utf-8")
r = run_hook(wt, tool_input=cloud("51"))
check("auditoria nova da worktree (complete) vence a antiga do principal",
      r.returncode == 0, r.stderr[:200])

main, wt = make_worktree_pair(AUDIT_INCOMPLETE, where=Path("docs") / "acceptance")
r = run_hook(wt, tool_input=cloud("51"))
check("artefato em docs/acceptance/ do principal → Done BLOQUEIA",
      r.returncode == 2, r.stderr[:200])

docs_proj = make_project(board_flow=BOARD_FLOW)
(docs_proj / "docs" / "acceptance").mkdir(parents=True)
(docs_proj / "docs" / "acceptance" / f"{KEY}.yaml").write_text(AUDIT_INCOMPLETE, encoding="utf-8")
r = run_hook(docs_proj, tool_input=cloud("41"))
check("artefato em docs/acceptance/ da própria árvore → In Review BLOQUEIA",
      r.returncode == 2, r.stderr[:200])

# Fora de git o main_root é "", e Path("") seria o diretório do PROCESSO. Com
# o processo parado numa árvore que tem artefato incompleto, um projeto limpo
# fora de git não pode herdar esse artefato.
# Alvo In Review (não done) para não confundir com a regra nova de "ausente +
# done bloqueia" — o que este teste verifica é só o vazamento entre árvores.
alheio = make_project(audit=AUDIT_INCOMPLETE)
limpo = make_project(board_flow=BOARD_FLOW)
r = subprocess.run(
    [sys.executable, str(HOOK)], cwd=alheio, capture_output=True, text=True,
    input=json.dumps({"tool_name": CLOUD_TOOL, "tool_input": cloud("41"),
                      "cwd": str(limpo)}))
check("fora de git, artefato no diretório do processo não conta → In Review PASSA",
      r.returncode == 0, r.stderr[:200])

main, wt = make_worktree_pair(None)
r = run_hook(wt, tool_input=cloud("51"))
check("nenhuma árvore tem artefato → Done BLOQUEIA (decisão do dono, 2026-09-27)",
      r.returncode == 2, f"rc={r.returncode} {r.stderr[:200]}")
check("…e a mensagem cita .claude/acceptance e o clone principal",
      ".claude/acceptance" in r.stderr and str(main.resolve()) in r.stderr,
      r.stderr[:400])

r = run_hook(wt, tool_name=LOCAL_TOOL, tool_input=local("51"))
check("nenhuma árvore tem artefato, dialeto mcp-atlassian → Done BLOQUEIA",
      r.returncode == 2, f"rc={r.returncode} {r.stderr[:200]}")

r = run_hook(wt, tool_input=cloud("41"))
check("nenhuma árvore tem artefato → In Review PASSA", r.returncode == 0, r.stderr[:200])

r = run_hook(wt, tool_input=cloud("31"))
check("nenhuma árvore tem artefato → In Progress PASSA", r.returncode == 0, r.stderr[:200])

no_flow = make_project()
r = run_hook(no_flow, tool_input=cloud("51"))
check("nenhuma árvore tem artefato, sem board-flow.yaml (alvo não resolvido) → PASSA",
      r.returncode == 0, r.stderr[:200])

r = run_hook(no_flow, tool_name="Bash", tool_input={
    "command": f'twg jira workitem transition --id {KEY} --transition-id "Done"'})
check("twg Bash, sem artefato, transição por nome 'Done' → BLOQUEIA",
      r.returncode == 2, f"rc={r.returncode} {r.stderr[:200]}")

# ── unchanged contracts ────────────────────────────────────────────────────
clean = make_project(board_flow=BOARD_FLOW)
r = run_hook(clean, tool_input=cloud("41"))
check("sem artefato de auditoria → PASSA", r.returncode == 0, r.stderr[:200])

done_proj = make_project(audit=AUDIT_COMPLETE, board_flow=BOARD_FLOW)
for tid in ("41", "31"):
    r = run_hook(done_proj, tool_input=cloud(tid))
    check(f"auditoria complete → PASSA (id {tid})", r.returncode == 0, r.stderr[:200])

r = run_hook(proj, tool_name="mcp__claude_ai_Atlassian__addCommentToJiraIssue",
             tool_input=cloud("41"))
check("outra tool é ignorada", r.returncode == 0)

r = run_hook(proj, tool_input={"transition": {"id": "41"}})
check("sem chave do card → fail open", r.returncode == 0)

r = subprocess.run([sys.executable, str(HOOK)], input="{not json",
                   capture_output=True, text=True)
check("payload ilegível → fail open", r.returncode == 0)

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {FAILURES}")
    sys.exit(1)
print("all acceptance-gate tests passed")
