#!/usr/bin/env python3
"""PreToolUse hook for the build-hex topology — proof-verdict integrity gate.

The proof-reviewer's own routing already forbids it (proof-reviewer.md,
"Verdict routing"): a proof artifact whose `verdict: proven` sits next to a
level with status `skipped` / `assumed` / `survived` / `gap`, or an
`l4_adversarial_input` with `findings`, is a protocol violation, never a
"waiver." Yet it has happened more than once (WEGO-1711, WEGO-1785): the agent
recorded the gap honestly in the levels but stamped `verdict: proven` anyway.

Prose rules that are already clear and still get violated need enforcement, not
more prose. This hook reads the `.claude/proof/<KEY>.yaml` the agent is about to
Write, recomputes the verdict mechanically from the level statuses, and BLOCKS
the write when the declared `verdict: proven` contradicts them — telling the
agent the verdict it must write instead.

It is deliberately conservative: it acts ONLY on a confirmed contradiction
(verdict is literally `proven` AND a forbidding status is present). Anything it
cannot parse, a non-proof file, a missing verdict, or a verdict that is already
`unproven` / `needs-human` → fail OPEN (exit 0). It never invents a block.

This is NOT agent-scoped: verdict integrity must hold no matter who writes the
artifact, so there is no agent allowlist here.

Exit codes:
  0 — allowed (not a proof artifact, parse-uncertain, or verdict consistent)
  2 — blocked (stderr message reaches the agent so it can self-correct)
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def _t_emit(event: str, cwd: str = None, **fields) -> None:
    """Minimal inline mirror of common/hooks/_telemetry.py (cross-plugin import
    is fragile across versioned cache dirs, so the ~20 lines are duplicated).
    Same ledger, same shape: ~/.claude/cepa-telemetry/events-YYYY-MM.jsonl.
    Strictly fail-silent."""
    try:
        import subprocess
        repo = ""
        try:
            out = subprocess.run(
                ["git", "-C", cwd or os.getcwd(), "rev-parse",
                 "--path-format=absolute", "--git-common-dir"],
                capture_output=True, text=True, timeout=5)
            if out.returncode == 0:
                common = out.stdout.strip()
                repo = Path(common).parent.name if common.endswith("/.git") else Path(common).name
        except Exception:
            pass
        entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "event": event, "repo": repo}
        entry.update(fields)
        tdir = Path(os.environ.get("CEPA_TELEMETRY_DIR") or (Path.home() / ".claude" / "cepa-telemetry"))
        tdir.mkdir(parents=True, exist_ok=True)
        with open(tdir / f"events-{entry['ts'][:7]}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass

# A level whose status is in UNPROVEN_STATUSES routes the card to UNPROVEN;
# anything else forbidding `proven` routes to NEEDS-HUMAN. Both forbid `proven`.
# Mirrors the "Verdict routing" section of build-hex/agents/proof-reviewer.md.
UNPROVEN_STATUSES = {"survived", "green-at-base", "green_at_base"}
NEEDS_HUMAN_STATUSES = {"skipped", "assumed", "gap", "findings"}
FORBIDDING_STATUSES = UNPROVEN_STATUSES | NEEDS_HUMAN_STATUSES


def is_proof_artifact(file_path: str) -> bool:
    p = file_path.replace(os.sep, "/")
    return "/.claude/proof/" in p and p.endswith((".yaml", ".yml"))


def collect_statuses(node, out):
    """Recursively gather every value bound to a `status:` key. Using a real
    parse (when pyyaml is present) means block-scalar prose that merely mentions
    'status: skipped' inside a results string is a STRING value, never traversed
    as a status key — so it can't cause a false block."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "status" and isinstance(v, str):
                out.append(v.strip().lower())
            else:
                collect_statuses(v, out)
    elif isinstance(node, list):
        for item in node:
            collect_statuses(item, out)


def double_offenders(data) -> list:
    """Changed classes whose covering test replaces THEM with a test double.

    The dominant false-green in this repo, found across four cards on
    2026-08-01: the test presented as end-to-end proof substitutes a double for
    the very class the card fixed, so production could be broken on purpose and
    the test stayed green. A double at the far boundary (the vendor) is normal
    and correct; a double standing in for the changed class means the proof
    measures the double.

    Returns a list of (class, double) for offenders, plus (class, None) for a
    changed class that never declared the field at all — explicit-null
    discipline, same as summary-nulls-gate: silence is not an answer.
    """
    scope = data.get("scope") if isinstance(data, dict) else None
    classes = (scope or {}).get("changed_classes") if isinstance(scope, dict) else None
    if not isinstance(classes, list):
        return []
    out = []
    for c in classes:
        if not isinstance(c, dict):
            continue
        name = str(c.get("class", "?"))
        if "substituted_by_double" not in c:
            out.append((name, None))
            continue
        v = c.get("substituted_by_double")
        if v is None:
            continue  # explicit null → declared clean
        s = str(v).strip().lower()
        if s in ("none", "no", "false", "n/a", "na", "~", ""):
            continue
        out.append((name, str(c.get("substituted_by_double")).strip()))
    return out


def parse_with_yaml(content: str):
    """Return (verdict, [statuses], [double offenders]). Raises if invalid."""
    import yaml  # noqa: deferred so absence falls back instead of crashing
    data = yaml.safe_load(content)
    if not isinstance(data, dict):
        raise ValueError("proof artifact is not a YAML mapping")
    verdict = data.get("verdict")
    statuses: list = []
    collect_statuses(data.get("levels", {}), statuses)
    return verdict, statuses, double_offenders(data)


def parse_with_lines(content: str):
    """Fallback parse (no pyyaml). Top-level `verdict:` and any indented
    `status:`. Caveat: an indented `status:` buried inside a block scalar would
    be picked up too — but that only ever ADDS a forbidding status, and the hook
    acts only when the verdict is already `proven`, so the bias is toward
    blocking an over-claimed artifact, never toward a false `proven`."""
    verdict = None
    statuses: list = []
    for line in content.splitlines():
        m = re.match(r"^verdict:\s*([^\s#]+)", line)
        if m:
            verdict = m.group(1).strip().strip("\"'")
            continue
        m = re.match(r"^\s+status:\s*([A-Za-z0-9_-]+)", line)
        if m:
            statuses.append(m.group(1).strip().lower())
    # The line parser cannot see `scope.changed_classes` structure, so it
    # reports no double offenders — biased toward allowing, like the rest
    # of this fallback.
    return verdict, statuses, []


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        sys.exit(0)

    # Only Write carries the full artifact content needed to recompute the
    # verdict. An Edit/MultiEdit fragment can't be validated in isolation —
    # fail open; the agent's authoring path writes the whole file via Write.
    if payload.get("tool_name") != "Write":
        sys.exit(0)

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path", "")
    if not file_path or not is_proof_artifact(file_path):
        sys.exit(0)

    content = tool_input.get("content")
    if not isinstance(content, str) or not content.strip():
        sys.exit(0)

    try:
        verdict, statuses, doubles = parse_with_yaml(content)
    except Exception:
        try:
            verdict, statuses, doubles = parse_with_lines(content)
        except Exception:
            sys.exit(0)  # can't understand it → never block

    card = Path(file_path).stem
    hook_cwd = payload.get("cwd") or os.getcwd()
    declared = verdict.strip().lower() if isinstance(verdict, str) else "?"

    if not isinstance(verdict, str) or verdict.strip().lower() != "proven":
        _t_emit("proof_verdict", cwd=hook_cwd, card=card, verdict=declared)
        sys.exit(0)  # only `proven` can be contradicted

    if doubles:
        undeclared = [c for c, d in doubles if d is None]
        substituted = [(c, d) for c, d in doubles if d is not None]
        lines = "".join(f"    - {c}  ← substituído por {d}\n" for c, d in substituted)
        lines += "".join(f"    - {c}  ← `substituted_by_double` não declarado\n"
                         for c in undeclared)
        print(
            f"[build-hex proof-verdict-guard] BLOCKED: {file_path} declares "
            f"verdict: proven, but the covering test does not exercise the changed "
            f"code:\n{lines}"
            f"  Um dublê no lugar da classe que o card corrigiu faz o teste medir o\n"
            f"  DUBLÊ, não a correção — quebrar produção de propósito deixa o teste\n"
            f"  verde. Foi o padrao dominante em quatro cards (1726, 1770, 1779, 1783).\n"
            f"  Dublê na fronteira do fornecedor (WireMock no lugar da PlugSign) é\n"
            f"  correto; dublê no lugar do adapter alterado invalida a prova.\n"
            f"  Rode o teste de aceite com o adapter REAL (mock.enabled=false) e o\n"
            f"  WireMock no lugar do fornecedor, perturbe a classe alterada e exija\n"
            f"  VERMELHO. Depois declare `substituted_by_double: none` em cada classe.\n"
            f"  Um campo ausente é bloqueio igual: silêncio nao e resposta.",
            file=sys.stderr,
        )
        _t_emit("proof_verdict", cwd=hook_cwd, card=card, verdict="proven",
                blocked="double_substitution")
        sys.exit(2)

    forbidding = sorted({s for s in statuses if s in FORBIDDING_STATUSES})
    if not forbidding:
        _t_emit("proof_verdict", cwd=hook_cwd, card=card, verdict="proven")
        sys.exit(0)  # proven is consistent with the levels

    computed = "unproven" if any(s in UNPROVEN_STATUSES for s in forbidding) else "needs-human"
    print(
        f"[build-hex proof-verdict-guard] BLOCKED: {file_path} declares "
        f"verdict: proven, but these level statuses forbid it: "
        f"{', '.join(forbidding)}.\n"
        f"  Per the Verdict routing in proof-reviewer.md, `proven` is "
        f"structurally unavailable when any level is "
        f"skipped/assumed/survived/gap or L4 has findings — a skipped or "
        f"assumed check is the human's to waive, never yours.\n"
        f"  Computed verdict: {computed}. Rewrite the artifact with "
        f"`verdict: {computed}` and report THAT verdict to the orchestrator.\n"
        f"  Do NOT edit this hook or any enforcement file to bypass this. If "
        f"you believe the block is wrong, return NEEDS-HUMAN and say so.",
        file=sys.stderr,
    )
    _t_emit("proof_block", cwd=hook_cwd, card=card,
            declared="proven", computed=computed)
    sys.exit(2)


if __name__ == "__main__":
    main()
