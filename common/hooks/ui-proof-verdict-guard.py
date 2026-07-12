#!/usr/bin/env python3
"""PreToolUse hook (common) — UI proof-verdict integrity gate.

Sibling of build-hex/hooks/proof-verdict-guard.py, one altitude up. That guard
parses the backend proof artifact's `levels` schema; this one parses the
ui-proof-reviewer's `flows` schema (schema_version 1) written to
`.claude/proof/ui-<slug>.yaml`. The lesson is the same (WEGO-1711, WEGO-1785):
prose rules that are already clear and still get violated need enforcement,
not more prose.

Per the agent's Verdict routing (common/agents/ui-proof-reviewer.md),
`verdict: proven` is structurally unavailable when:
  - any flow's status is not literally `pass` — `fail`, `skipped`,
    `not-executable`, and the weak-evidence greens `pass-visual-only` /
    `pass-stale` all forbid it; or
  - any flow's perturbation status is `survived` or `assumed`
    (`red` and `n/a` are fine).

This hook reads the artifact the agent is about to Write, recomputes the
verdict mechanically from those statuses, and BLOCKS the write when the
declared `verdict: proven` contradicts them — telling the agent the verdict
it must write instead.

Deliberately conservative, like its sibling: it acts ONLY on a confirmed
contradiction. Anything it cannot parse, a non-ui-proof file, a missing
verdict, or a verdict already `unproven` / `needs-human` → fail OPEN (exit 0).
It never invents a block. Not agent-scoped: verdict integrity must hold no
matter who writes the artifact.

Exit codes:
  0 — allowed (not a ui-proof artifact, parse-uncertain, or verdict consistent)
  2 — blocked (stderr message reaches the agent so it can self-correct)
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def _t_emit(event: str, cwd: str = None, **fields) -> None:
    """Minimal inline mirror of common/hooks/_telemetry.py (kept inline for
    symmetry with the build-hex sibling; strictly fail-silent)."""
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


# Flow statuses: only a literal `pass` is compatible with `proven`.
FLOW_OK = {"pass"}
# A deterministic failure routes to UNPROVEN…
FLOW_UNPROVEN = {"fail"}
# Perturbation statuses compatible with `proven`.
PERTURBATION_OK = {"red", "n/a", "na", "n-a"}
PERTURBATION_UNPROVEN = {"survived"}


def is_ui_proof_artifact(file_path: str) -> bool:
    p = file_path.replace(os.sep, "/")
    return ("/.claude/proof/" in p
            and Path(p).name.startswith("ui-")
            and p.endswith((".yaml", ".yml")))


def parse_with_yaml(content: str):
    """Return (verdict, forbidding, unproven_seen) using pyyaml.
    Raises if unavailable/invalid."""
    import yaml  # noqa: deferred so absence falls back instead of crashing
    data = yaml.safe_load(content)
    if not isinstance(data, dict):
        raise ValueError("ui-proof artifact is not a YAML mapping")
    verdict = data.get("verdict")
    forbidding: list = []
    unproven_seen = False
    flows = data.get("flows")
    if isinstance(flows, dict):
        for name, flow in flows.items():
            if not isinstance(flow, dict):
                continue
            status = flow.get("status")
            s = status.strip().lower() if isinstance(status, str) else None
            if s is not None and s not in FLOW_OK:
                forbidding.append(f"flow {name}: status {s}")
                if s in FLOW_UNPROVEN:
                    fc = flow.get("failure_class")
                    fc = fc.strip().lower() if isinstance(fc, str) else None
                    # assert-failed (or unclassified fail) → UNPROVEN;
                    # selector-not-found / infra-timeout → NEEDS-HUMAN.
                    if fc in (None, "", "assert-failed"):
                        unproven_seen = True
            pert = flow.get("perturbation")
            if isinstance(pert, dict):
                ps = pert.get("status")
                p = ps.strip().lower() if isinstance(ps, str) else None
                if p is not None and p not in PERTURBATION_OK:
                    forbidding.append(f"flow {name}: perturbation {p}")
                    if p in PERTURBATION_UNPROVEN:
                        unproven_seen = True
    return verdict, forbidding, unproven_seen


def parse_with_lines(content: str):
    """Fallback parse (no pyyaml). Top-level `verdict:` plus every indented
    `status:` value (flow or perturbation — both forbid `proven` unless in
    the allowed sets). Same bias as the sibling: an over-collected status can
    only ever block an over-claimed `proven`, never mint a false one."""
    verdict = None
    forbidding: list = []
    unproven_seen = False
    allowed = FLOW_OK | PERTURBATION_OK
    for line in content.splitlines():
        m = re.match(r"^verdict:\s*([^\s#]+)", line)
        if m:
            verdict = m.group(1).strip().strip("\"'")
            continue
        for m in re.finditer(r"status:\s*([A-Za-z0-9/_-]+)", line):
            s = m.group(1).strip().lower()
            if s not in allowed:
                forbidding.append(f"status {s}")
                if s in FLOW_UNPROVEN or s in PERTURBATION_UNPROVEN:
                    unproven_seen = True
    return verdict, forbidding, unproven_seen


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        sys.exit(0)

    # Only Write carries the full artifact content needed to recompute the
    # verdict (same rationale as the build-hex sibling).
    if payload.get("tool_name") != "Write":
        sys.exit(0)

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path", "")
    if not file_path or not is_ui_proof_artifact(file_path):
        sys.exit(0)

    content = tool_input.get("content")
    if not isinstance(content, str) or not content.strip():
        sys.exit(0)

    try:
        verdict, forbidding, unproven_seen = parse_with_yaml(content)
    except Exception:
        try:
            verdict, forbidding, unproven_seen = parse_with_lines(content)
        except Exception:
            sys.exit(0)  # can't understand it → never block

    slug = Path(file_path).stem
    hook_cwd = payload.get("cwd") or os.getcwd()
    declared = verdict.strip().lower() if isinstance(verdict, str) else "?"

    if not isinstance(verdict, str) or verdict.strip().lower() != "proven":
        _t_emit("ui_proof_verdict", cwd=hook_cwd, slug=slug, verdict=declared)
        sys.exit(0)  # only `proven` can be contradicted

    if not forbidding:
        _t_emit("ui_proof_verdict", cwd=hook_cwd, slug=slug, verdict="proven")
        sys.exit(0)  # proven is consistent with the flows

    computed = "unproven" if unproven_seen else "needs-human"
    print(
        f"[common ui-proof-verdict-guard] BLOCKED: {file_path} declares "
        f"verdict: proven, but these flow statuses forbid it: "
        f"{'; '.join(sorted(set(forbidding)))}.\n"
        f"  Per the Verdict routing in ui-proof-reviewer.md, `proven` is "
        f"structurally unavailable when any flow is not `pass` (including "
        f"pass-visual-only / pass-stale) or any perturbation is "
        f"survived/assumed — weak or missing evidence is the human's to "
        f"waive, never yours.\n"
        f"  Computed verdict: {computed}. Rewrite the artifact with "
        f"`verdict: {computed}` and report THAT verdict to the orchestrator.\n"
        f"  Do NOT edit this hook or any enforcement file to bypass this. If "
        f"you believe the block is wrong, return NEEDS-HUMAN and say so.",
        file=sys.stderr,
    )
    _t_emit("ui_proof_block", cwd=hook_cwd, slug=slug,
            declared="proven", computed=computed)
    sys.exit(2)


if __name__ == "__main__":
    main()
