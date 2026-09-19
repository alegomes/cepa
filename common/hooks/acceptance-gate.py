#!/usr/bin/env python3
"""PreToolUse hook: block the In-Review Jira transition when the acceptance
audit is incomplete.

The structural teeth of the `acceptance-completeness` discipline — the same
hook+state+gate pattern as `gate-advance.py`, but the state is per-card
acceptance evidence instead of build greenness.

Mechanism — artifact presence, THEN direction:

  The `completion-auditor` writes `.claude/acceptance/<KEY>.yaml` only AFTER
  implementation, right before the flow tries to move the card to In Review.
  So an artifact on disk means "the audit has run"; its `status` says whether
  the card earned the forward move.

  That alone used to be the whole gate, on the theory that it never needed to
  know WHICH status was targeted. The theory was wrong, and 2026-07-31 showed
  how: WEGO-1782's audit was correctly `incomplete`, and the gate therefore
  blocked the card from going BACK to In Progress — it barred the exact
  movement an incomplete audit is supposed to cause. The card sat stuck in
  Review with its UNPROVEN comment already posted.

  Direction cannot be inferred from the payload: both MCP transition tools
  (`transitionJiraIssue`, `jira_transition_issue`) carry an opaque transition
  id and no status name. So the project declares the mapping once, in
  `board-flow.yaml`:

      defaults:
        transition_ids:
          "41": in_review
          "31": in_progress

  - target is an ENFORCED status (in_review / done) -> gate applies
  - target is any other declared status              -> ALLOW: a bounce is the
                                                        correct consequence of
                                                        an incomplete audit
  - id absent, unmapped, or no board-flow.yaml       -> ENFORCE (fail closed;
                                                        never lose teeth to a
                                                        missing config)

Matches the Atlassian MCP transition tool (any server prefix). Extracts the
issue key from the tool input, looks for `.claude/acceptance/<KEY>.yaml`:

  - absent                       -> allow (audit hasn't run; not gated)
  - present, status: complete    -> allow
  - present, status: <anything>  -> BLOCK, unless the target status is
                                    declared and is not an enforced one
  - key not extractable          -> allow (can't gate meaningfully; never
                                    spuriously block a Jira transition)

Exit codes:
  0 — allowed
  2 — blocked (stderr reaches the agent so it can self-correct)
"""

import json
import os
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _wtlib as L  # noqa: E402
import _jiramut as J  # noqa: E402


STATUS_RE = re.compile(r"^status:\s*([A-Za-z_-]+)", re.MULTILINE)
GAP_RE = re.compile(r"^\s*gap:\s*(?!null\b)(?!~\s*$)[\"']?(.+?)[\"']?\s*$", re.MULTILINE)
# Possible field names the MCP tool may use for the issue key.
# Both dialects: the cloud connector is camelCase, mcp-atlassian is snake_case.
# `issue_key` was missing, so even once the tool matched, the card was not
# identifiable and the gate failed open.
KEY_FIELDS = ("issueIdOrKey", "issueKey", "issue_key", "issueId", "issue_id",
              "issue", "key")

# The statuses this gate has teeth for. Everything else declared in
# transition_ids is a backward/lateral move and is never blocked here.
ENFORCED_TARGETS = {"in_review", "done"}

CONFIG_NAMES = ("board-flow.yaml", ".claude/board-flow.lifecycle.yaml")


def extract_key(tool_input: dict) -> str | None:
    for f in KEY_FIELDS:
        v = tool_input.get(f)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def extract_transition_id(tool_input: dict) -> str | None:
    """The transition id, from either MCP dialect.

    cloud connector: {"transition": {"id": "41"}}   mcp-atlassian: {"transition_id": "41"}
    """
    t = tool_input.get("transition")
    if isinstance(t, dict):
        v = t.get("id")
        if v is not None and str(v).strip():
            return str(v).strip()
    for f in ("transition_id", "transitionId"):
        v = tool_input.get(f)
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def transition_map(cwd: Path) -> dict:
    """`defaults.transition_ids` from the project's board-flow config.

    Absent file, absent key, or unreadable YAML all yield {} — which makes
    every id unresolvable and therefore keeps the gate enforcing. A config
    problem must never silently open the gate.
    """
    for name in CONFIG_NAMES:
        path = cwd / name
        if not path.is_file():
            continue
        try:
            import yaml  # noqa: deferred so absence falls back instead of crashing

            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        defaults = data.get("defaults")
        raw = (defaults or {}).get("transition_ids") if isinstance(defaults, dict) else None
        if not isinstance(raw, dict):
            return {}
        return {str(k).strip(): str(v).strip().lower() for k, v in raw.items()}
    return {}


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[acceptance-gate] could not parse hook payload; allowing", file=sys.stderr)
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    # BOTH dialects. Matching only the cloud connector's `transitionJiraIssue`
    # left this gate with zero teeth on `mcp-atlassian`, which is the server
    # the local Jira runs use — every transition there sailed through
    # regardless of the audit. Found by the direction tests, 2026-08-01.
    # Reconhecimento por EFEITO, nao por nome de ferramenta. O nome MCP so
    # cobria MCP; a CLI `twg` chega como Bash e passava calada por aqui.
    _mut = J.classify(payload)
    if _mut is None:
        sys.exit(0)
    # A opacidade se checa ANTES de filtrar por tipo: uma mutacao que nao da
    # para ler pode ser justamente a que este gate guarda. Filtrar primeiro
    # deixava `twg api ... -X POST` escapar por nao ser classificavel.
    if _mut["opaque"]:
        J.block(_mut, "acceptance-gate")
    if _mut["kind"] != "transition":
        sys.exit(0)

    tool_input = _mut["tool_input"]
    key = extract_key(tool_input)
    if not key:
        # Can't identify the card -> can't gate. Never spuriously block.
        sys.exit(0)

    # RAIZ da worktree, não o diretório corrente: o cwd do Bash persiste
    # entre chamadas, e um `cd subdir` desviaria o estado desta sessão
    # para `subdir/.claude/` pelo resto dela (ver _wtlib.session_root).
    cwd = Path(L.session_root(payload.get("cwd") or os.getcwd())).resolve()
    artifact = cwd / ".claude" / "acceptance" / f"{key}.yaml"

    if not artifact.exists():
        # No audit on disk yet (e.g. the To Do -> In Progress transition).
        # Nothing to enforce. The completion-auditor writes this file right
        # before the In-Review transition; that's when teeth appear.
        sys.exit(0)

    try:
        text = artifact.read_text(encoding="utf-8")
    except OSError as e:
        print(f"[acceptance-gate] could not read {artifact}: {e}; allowing", file=sys.stderr)
        sys.exit(0)

    m = STATUS_RE.search(text)
    status = (m.group(1).lower() if m else "unparseable")

    if status == "complete":
        sys.exit(0)

    # The audit is incomplete. Which way is this card moving?
    tid = extract_transition_id(tool_input)
    tmap = transition_map(cwd)
    # Nome de status vindo da `twg` precisa virar chave lógica: "In Review"
    # baixado de caixa dava `in review` e passava como movimento lateral.
    if _mut["target_status"]:
        target = J.logical_status(_mut["target_status"], cwd)
    else:
        target = tmap.get(tid) if tid else None

    if target is not None and target not in ENFORCED_TARGETS:
        # Backward / lateral move (In Progress, To Do, Won't Do). Sending the
        # card back is precisely what an incomplete audit should cause — the
        # gate exists to stop it going FORWARD on unproven work, not to trap it.
        sys.exit(0)

    unresolved_note = ""
    if target is None:
        unresolved_note = (
            f"\n  NOTE: the target status could not be resolved"
            f"{f' (transition id {tid})' if tid else ' (no transition id in the payload)'},"
            f" so this gate\n"
            f"  enforced by default. If you are BOUNCING the card back, that is legitimate and\n"
            f"  the gate should not be in the way — declare the mapping once in board-flow.yaml:\n"
            f"      defaults:\n"
            f"        transition_ids:\n"
            f"          \"<id>\": in_progress   # and in_review / to_do / done\n"
            f"  Get the ids from getTransitionsForJiraIssue. Never work around this by editing\n"
            f"  the acceptance artifact."
        )

    # Present but not complete -> BLOCK. Surface the gaps so the agent can route
    # the fix instead of guessing.
    gaps = GAP_RE.findall(text)
    gap_lines = "".join(f"\n    - {g.strip()}" for g in gaps[:8]) or "\n    - (see the artifact for per-criterion gaps)"

    print(
        f"[acceptance-gate] BLOCKED: cannot move {key} to review — acceptance audit is "
        f"'{status}', not 'complete'.\n"
        f"  Artifact: {artifact}\n"
        f"  Open gaps (criterion not demonstrated at its stated altitude):{gap_lines}\n"
        f"  An acceptance criterion is only 'complete' when a test exercises its literal\n"
        f"  surface end-to-end and was run green — not when the parts are covered in\n"
        f"  isolation. Close the gap (add the missing altitude test), re-run the\n"
        f"  completion-auditor, and retry. Override by demonstrating the criterion, not\n"
        f"  by editing the artifact."
        f"{unresolved_note}",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
