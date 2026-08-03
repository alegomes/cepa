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

It acts ONLY on an artifact that declares `verdict: proven`. A non-proof file,
an unparseable one, a missing verdict, or a verdict already `unproven` /
`needs-human` → fail OPEN (exit 0).

Within a `proven`, though, it fails CLOSED: statuses are checked against a
closed enum PER LEVEL, so an unrecognized value blocks instead of passing. The
first version used a denylist of forbidden statuses, and WEGO-1779/1793 walked
straight through it with an `l4_adversarial_input.status: n/a` the schema never
offered — while WEGO-1962 encoded the same situation as `skipped` and was routed
to NEEDS-HUMAN. Honest encoding punished, invented value rewarded; `banana`
would have passed too.

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

# The closed enum per level. A denylist let ANY unrecognized string through:
# WEGO-1779 and WEGO-1793 reached `proven` with `l4_adversarial_input.status:
# n/a` — a value the schema never offered — while WEGO-1962 encoded the same
# situation as `skipped` and was routed to NEEDS-HUMAN. Same scenario, opposite
# verdict, and a typo like `banana` would have passed just as easily. A gate
# must fail CLOSED: a status this table does not know is a block, not a pass.
ALLOWED_STATUSES = {
    "l3_load_bearing.pit.status": {"ran", "absent", "n/a"},
    "l3_load_bearing.perturbation.status": {"pass", "survived", "skipped"},
    "l2_coverage.status": {"pass", "gap", "assumed"},
    "l4_adversarial_input.status": {"clean", "findings", "skipped", "n/a"},
    "bugfix_regression_red_at_base.status": {"pass", "green-at-base",
                                             "green_at_base", "n/a"},
}
KNOWN_STATUSES = set().union(*ALLOWED_STATUSES.values())

# `n/a` on the adversarial-input level means "this diff exposes no NEW input
# surface". That is a claim the diff itself can refute: a changed class in an
# input-bearing module (controller, DTO, filter) is exactly a new input surface.
# Note this is deliberately NOT `external_observable` — that field says the
# behavior is visible from outside, not that the change accepts new input.
INPUT_MODULES = {"api-rest", "api", "rest", "api_rest"}


def is_proof_artifact(file_path: str) -> bool:
    p = file_path.replace(os.sep, "/")
    return "/.claude/proof/" in p and p.endswith((".yaml", ".yml"))


def collect_statuses(node, out, path=""):
    """Recursively gather every `status:` value as a (dotted-path, value) pair.
    Using a real parse (when pyyaml is present) means block-scalar prose that
    merely mentions 'status: skipped' inside a results string is a STRING value,
    never traversed as a status key — so it can't cause a false block.

    The path is what lets the enum be checked PER LEVEL instead of globally:
    `n/a` is legitimate for the PIT and regression levels and, since this
    change, for L4 — but never for coverage or perturbation."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "status" and isinstance(v, str):
                out.append((path, v.strip().lower()))
            else:
                collect_statuses(v, out, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for item in node:
            collect_statuses(item, out, path)


def unknown_statuses(pairs) -> list:
    """(path, value) pairs whose value is outside the level's closed enum.

    A path this table doesn't know falls back to the union of every legal
    status — so an invented level can't smuggle an invented value either.
    """
    bad = []
    for path, value in pairs:
        allowed = ALLOWED_STATUSES.get(f"{path}.status", KNOWN_STATUSES)
        if value not in allowed:
            bad.append((path or "levels", value, sorted(allowed)))
    return bad


def l4_na_violations(data) -> list:
    """Reasons an `l4_adversarial_input.status: n/a` must not stand.

    `n/a` is the honest encoding of "this diff opens no new input surface"
    (WEGO-1779, WEGO-1793), which is why the enum now offers it. But a
    self-declared n/a with nothing behind it is the same hole by another name,
    so it carries two mechanical conditions: a written justification, and a diff
    that doesn't contradict it.
    """
    levels = data.get("levels") if isinstance(data, dict) else None
    l4 = (levels or {}).get("l4_adversarial_input") if isinstance(levels, dict) else None
    if not isinstance(l4, dict):
        return []
    if str(l4.get("status", "")).strip().lower() != "n/a":
        return []

    out = []
    reason = l4.get("reason")
    if not isinstance(reason, str) or len(reason.strip()) < 15:
        out.append("falta `reason:` — n/a sem justificativa escrita não vale "
                   "(mínimo: por que o diff não abre superfície de entrada)")

    scope = data.get("scope") if isinstance(data, dict) else None
    classes = (scope or {}).get("changed_classes") if isinstance(scope, dict) else []
    if isinstance(classes, list):
        offenders = [str(c.get("class", "?")) for c in classes
                     if isinstance(c, dict)
                     and str(c.get("module", "")).strip().lower() in INPUT_MODULES]
        if offenders:
            out.append("o diff toca módulo de entrada (" + ", ".join(offenders) +
                       ") — isso É superfície de entrada nova; use clean/findings")
    return out


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
    """Return (verdict, [(path, status)], [doubles], [l4 n/a violations]).
    Raises if invalid."""
    import yaml  # noqa: deferred so absence falls back instead of crashing
    data = yaml.safe_load(content)
    if not isinstance(data, dict):
        raise ValueError("proof artifact is not a YAML mapping")
    verdict = data.get("verdict")
    statuses: list = []
    collect_statuses(data.get("levels", {}), statuses)
    return verdict, statuses, double_offenders(data), l4_na_violations(data)


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
        m = re.match(r"^\s+status:\s*([^\s#]+)", line)
        if m:
            statuses.append(("", m.group(1).strip().strip("\"'").lower()))
    # The line parser cannot see `scope.changed_classes` structure, so it
    # reports no double offenders — biased toward allowing, like the rest
    # of this fallback. The one thing it must NOT wave through is an `n/a`,
    # whose justification lives in exactly the structure it can't read.
    na = [p for p, v in statuses if v == "n/a"] if statuses else []
    violations = (["o artefato não pôde ser lido como YAML, então a "
                   "justificativa do `n/a` não pôde ser verificada"]
                  if na else [])
    return verdict, statuses, [], violations


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
        verdict, statuses, doubles, na_violations = parse_with_yaml(content)
    except Exception:
        try:
            verdict, statuses, doubles, na_violations = parse_with_lines(content)
        except Exception:
            sys.exit(0)  # can't understand it → never block

    card = Path(file_path).stem
    hook_cwd = payload.get("cwd") or os.getcwd()
    declared = verdict.strip().lower() if isinstance(verdict, str) else "?"

    if not isinstance(verdict, str) or verdict.strip().lower() != "proven":
        _t_emit("proof_verdict", cwd=hook_cwd, card=card, verdict=declared)
        sys.exit(0)  # only `proven` can be contradicted

    unknown = unknown_statuses(statuses)
    if unknown:
        lines = "".join(
            f"    - {p}.status: {v!r} — legítimos: {', '.join(allowed)}\n"
            for p, v, allowed in unknown)
        print(
            f"[build-hex proof-verdict-guard] BLOCKED: {file_path} declares "
            f"verdict: proven with a status outside the level's closed enum:\n{lines}"
            f"  O portão compara contra o enum FECHADO de cada nível, não contra\n"
            f"  uma lista de proibidos — valor desconhecido bloqueia. Foi assim que\n"
            f"  WEGO-1779 e 1793 chegaram a `proven` com um `n/a` que o esquema do L4\n"
            f"  não oferecia, enquanto o 1962 codificou o MESMO cenário como\n"
            f"  `skipped` e foi para NEEDS-HUMAN. Um typo não pode virar aprovação.\n"
            f"  Escolha um valor do enum ou devolva NEEDS-HUMAN dizendo o que falta.",
            file=sys.stderr,
        )
        _t_emit("proof_verdict", cwd=hook_cwd, card=card, verdict="proven",
                blocked="unknown_status")
        sys.exit(2)

    if na_violations:
        lines = "".join(f"    - {v}\n" for v in na_violations)
        print(
            f"[build-hex proof-verdict-guard] BLOCKED: {file_path} declares "
            f"verdict: proven with `l4_adversarial_input.status: n/a`, but the "
            f"n/a doesn't hold up:\n{lines}"
            f"  `n/a` no L4 significa \"este diff não abre superfície de entrada\"\n"
            f"  — é uma afirmação sobre o diff, não uma dispensa. Ela exige um\n"
            f"  `reason:` escrito e um diff que não a contradiga.\n"
            f"  Se a superfície existe, rode a checagem e declare clean/findings.\n"
            f"  Se não consegue rodar, `skipped` → NEEDS-HUMAN é a saída honesta.",
            file=sys.stderr,
        )
        _t_emit("proof_verdict", cwd=hook_cwd, card=card, verdict="proven",
                blocked="l4_na_unjustified")
        sys.exit(2)

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

    forbidding = sorted({v for _, v in statuses if v in FORBIDDING_STATUSES})
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
