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
from pathlib import Path

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


def parse_with_yaml(content: str):
    """Return (verdict, [statuses]) using pyyaml. Raises if unavailable/invalid."""
    import yaml  # noqa: deferred so absence falls back instead of crashing
    data = yaml.safe_load(content)
    if not isinstance(data, dict):
        raise ValueError("proof artifact is not a YAML mapping")
    verdict = data.get("verdict")
    statuses: list = []
    collect_statuses(data.get("levels", {}), statuses)
    return verdict, statuses


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
    return verdict, statuses


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
        verdict, statuses = parse_with_yaml(content)
    except Exception:
        try:
            verdict, statuses = parse_with_lines(content)
        except Exception:
            sys.exit(0)  # can't understand it → never block

    if not isinstance(verdict, str) or verdict.strip().lower() != "proven":
        sys.exit(0)  # only `proven` can be contradicted

    forbidding = sorted({s for s in statuses if s in FORBIDDING_STATUSES})
    if not forbidding:
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
    sys.exit(2)


if __name__ == "__main__":
    main()
