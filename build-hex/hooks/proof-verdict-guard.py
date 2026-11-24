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

import glob
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
# The plugin's own PyYAML copy goes FIRST so it wins over any installed one
# (docs/spec/cepa-roda-sem-pyyaml-instalado.md).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_vendor"))


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
    "l2_coverage.status": {"pass", "gap", "assumed", "waived"},
    "l4_adversarial_input.status": {"clean", "findings", "skipped", "n/a"},
    "bugfix_regression_red_at_base.status": {"pass", "green-at-base",
                                             "green_at_base", "n/a"},
}
KNOWN_STATUSES = set().union(*ALLOWED_STATUSES.values())

# The level names are also a closed set. Artifacts written by earlier versions
# use another spelling for the SAME levels
# (`l2_external_coverage`, `l3_diff_mutation`, `bugfix_regression_red_on_base`),
# and the two coexist on disk today. Whoever reads those files needs to know
# both or reads half of the base: the `/board-flow:decide` classifier got
# 7 of 33 cards wrong because of this, including WEGO-1698, which the
# documentation itself uses as an example. The old spelling stays accepted for
# READING and blocked for WRITING — stopping the production of new divergence
# is what makes the debt shrink by itself.
LEVEL_NAMES = {
    "l2_coverage", "l3_load_bearing", "l4_adversarial_input",
    "bugfix_regression_red_at_base",
}
LEVEL_RENAMES = {
    "l2_external_coverage": "l2_coverage",
    "l3_diff_mutation": "l3_load_bearing",
    "bugfix_regression_red_on_base": "bugfix_regression_red_at_base",
}


def unknown_levels(data) -> list:
    """(written name, canonical name or None) for each level outside the set."""
    levels = data.get("levels") if isinstance(data, dict) else None
    if not isinstance(levels, dict):
        return []
    return [(name, LEVEL_RENAMES.get(name))
            for name in levels if name not in LEVEL_NAMES]

# `n/a` on the adversarial-input level means "this diff exposes no NEW input
# surface". That is a claim the diff itself can refute: a changed class in an
# input-bearing module (controller, DTO, filter) is exactly a new input surface.
# Note this is deliberately NOT `external_observable` — that field says the
# behavior is visible from outside, not that the change accepts new input.
INPUT_MODULES = {"api-rest", "api", "rest", "api_rest"}


# Both proof directories count. `docs/proof/` is the destination the
# proof-reviewer is now locked to (see build-hex/hooks/path-lock.py), because
# `.claude/` is gitignored in the consuming projects and a verdict written there
# dies with the session's disposable worktree. `.claude/proof/` stays RECOGNIZED
# here on purpose: this hook is the gate that blocks a `verdict: proven` sitting
# next to an `assumed`/`skipped` level, and a gate that stops recognizing a path
# does not get stricter — it goes quiet. Every artifact already on disk lives
# under the old path, and anything still writing there (the ui gate, a stale
# plugin cache, a hand-written file) must keep being checked.
_PROOF_DIR_RE = re.compile(r"(?:^|/)(?:\.claude|docs)/proof/")


def is_proof_artifact(file_path: str) -> bool:
    p = file_path.replace(os.sep, "/")
    return bool(_PROOF_DIR_RE.search(p)) and p.endswith((".yaml", ".yml"))


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


# Top-level keys that say "there is a waiver on the table". A PROPOSED waiver is
# a question to the owner (board-flow/bin/waivers.py `propor`), not proof: the
# artifact that carries it cannot declare `proven`.
WAIVER_KEYS = ("waiver_proposto", "dispensa_proposta", "waiver", "dispensa")


def has_waiver(data) -> bool:
    return isinstance(data, dict) and any(data.get(k) for k in WAIVER_KEYS)


# ── L2 coverage: measured by perturbation, or covered by an owner's waiver ─────
# Without a coverage tool `l2_coverage` was always `assumed`, so 28 of 33 items of
# run all/2026-11-21-1244 came back NEEDS-HUMAN even when every deliberate break
# turned a test red and even when the owner had already signed a waiver.
#   - `status: pass` + `technique: perturbation`: a line broken on purpose that
#     turned a test red WAS executed by that test; valid only with a passing
#     L3 perturbation and no `uncovered_lines`.
#   - `status: waived` + `waivers: [...]`: the owner's signed `nada-a-provar`
#     waiver holds for the file. The agent never waives; it only CITES, and this
#     guard checks the file on disk.
#
# INLINE TWIN of board-flow/bin/waivers.py (`load`, `expired`, `matches`, `_key`,
# `applicable`): importing across plugins is fragile across versioned cache dirs
# (same reason `_t_emit` is duplicated above). tests/test_proof_coverage_by_
# perturbation.py asserts the twin agrees with waivers.py; change both together.
WAIVER_DIR = ".claude/waivers"
WAIVER_NO_EFFECT = ("proposta", "recusada")
WAIVER_REQUIRED = ("motivo", "escopo", "razao", "autor", "criado_em", "revisit_trigger")
WAIVER_REASON = "nada-a-provar"


def _wkey(text) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def load_waivers(dirs) -> list:
    """Valid waivers (twin of waivers.load) from each directory; never raises."""
    found = []
    try:
        import yaml
    except Exception:
        return found
    for d in dirs:
        try:
            paths = sorted(glob.glob(os.path.join(str(d), "*.yaml")))
        except Exception:
            continue
        for path in paths:
            try:
                with open(path) as fh:
                    w = yaml.safe_load(fh)
            except Exception:
                continue
            if not isinstance(w, dict) or w.get("status") in WAIVER_NO_EFFECT:
                continue
            if any(not w.get(c) for c in WAIVER_REQUIRED):
                continue
            w["_path"] = path
            found.append(w)
    return found


def _waiver_expired(w, today=None) -> bool:
    """Twin of waivers.expired: by DATE inside `revisit_trigger` only."""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(w.get("revisit_trigger") or ""))
    if not m:
        return False
    return (today or date.today()).isoformat() > m.group(0)


def applicable_waiver(waivers, scope, today=None):
    """Twin of waivers.applicable(waivers, "nada-a-provar", scope)."""
    for w in waivers:
        if (w.get("motivo") == WAIVER_REASON
                and _wkey(str(w.get("escopo"))) == _wkey(scope)
                and not _waiver_expired(w, today)):
            return w
    return None


def waiver_dirs(file_path: str, cwd: str) -> list:
    """`<root>/.claude/waivers` plus the main clone's. The root is the directory
    holding the artifact's `docs/proof` or `.claude/proof`. Consuming projects
    gitignore `.claude/`, so in a linked worktree the waivers exist only in the
    main clone. Never raises."""
    dirs = []
    try:
        p = file_path.replace(os.sep, "/")
        m = _PROOF_DIR_RE.search(p)
        root = ""
        if m:
            root = p[:m.start()]
            if not root and p.startswith("/"):
                root = "/"
        if root and not os.path.isabs(root):
            root = os.path.join(cwd, root)
        root = root or cwd
        dirs.append(Path(root) / WAIVER_DIR)
        try:
            import subprocess
            out = subprocess.run(
                ["git", "-C", root, "rev-parse", "--path-format=absolute",
                 "--git-common-dir"], capture_output=True, text=True, timeout=5)
            common = out.stdout.strip() if out.returncode == 0 else ""
            if common.endswith("/.git"):
                dirs.append(Path(common).parent / WAIVER_DIR)
        except Exception:
            pass
    except Exception:
        pass
    seen, uniq = set(), []
    for d in dirs:
        k = str(d)
        if k not in seen:
            seen.add(k)
            uniq.append(d)
    return uniq


def l2_facts(data):
    """(status, technique, uncovered, perturbation_passes, to_cover) from the
    parsed artifact, or None when there is no l2_coverage mapping."""
    levels = data.get("levels") if isinstance(data, dict) else None
    if not isinstance(levels, dict) or not isinstance(levels.get("l2_coverage"), dict):
        return None
    l2 = levels["l2_coverage"]
    status = str(l2.get("status", "")).strip().lower()
    technique = str(l2.get("technique", "")).strip().lower()
    raw = l2.get("uncovered_lines")
    if isinstance(raw, list):
        uncovered = [str(u).strip() for u in raw if str(u).strip()]
    elif raw is None or raw == "":
        uncovered = []
    else:  # a string or any other non-null value is NOT empty
        uncovered = [str(raw).strip() or str(raw)]
    l3 = levels.get("l3_load_bearing")
    pert = l3.get("perturbation") if isinstance(l3, dict) else None
    pert_ok = (isinstance(pert, dict)
               and str(pert.get("status", "")).strip().lower() == "pass")
    if uncovered:
        to_cover = sorted({u.rsplit(":", 1)[0].strip() if ":" in u else u for u in uncovered})
    else:
        scope = data.get("scope")
        classes = scope.get("changed_classes") if isinstance(scope, dict) else None
        to_cover = sorted({str(c.get("class")).strip() for c in classes
                           if isinstance(c, dict) and c.get("class")}
                          ) if isinstance(classes, list) else []
    return status, technique, uncovered, pert_ok, to_cover


def _warn_no_yaml(exc) -> None:
    """One stderr line when the plugin's vendored PyYAML cannot load
    (docs/spec/cepa-roda-sem-pyyaml-instalado.md, CS-4). Never raises."""
    try:
        name = os.path.splitext(os.path.basename(sys.argv[0] or ""))[0] or "proof-verdict-guard"
        vendor = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "_vendor", "yaml")
        why = " ".join(f"{type(exc).__name__}: {exc}".split())
        print(f"[{name}] could not load PyYAML ({why}); expected the plugin's copy at "
              f"{vendor}. Carrying on the way it always does.", file=sys.stderr)
    except Exception:  # noqa: BLE001
        pass


def parse_with_yaml(content: str):
    """Return (verdict, [(path, status)], [doubles], [l4 n/a violations],
    [levels with a name outside the closed set], proposed waiver?).
    Raises if invalid."""
    try:
        import yaml  # noqa: deferred so absence falls back instead of crashing
    except ImportError as exc:
        _warn_no_yaml(exc)
        raise
    data = yaml.safe_load(content)
    if not isinstance(data, dict):
        raise ValueError("proof artifact is not a YAML mapping")
    verdict = data.get("verdict")
    statuses: list = []
    collect_statuses(data.get("levels", {}), statuses)
    return (verdict, statuses, double_offenders(data),
            l4_na_violations(data), unknown_levels(data), has_waiver(data))


def parse_with_lines(content: str):
    """Fallback parse (no pyyaml). Top-level `verdict:` and any indented
    `status:`. Caveat: an indented `status:` buried inside a block scalar would
    be picked up too — but that only ever ADDS a forbidding status, and the hook
    acts only when the verdict is already `proven`, so the bias is toward
    blocking an over-claimed artifact, never toward a false `proven`."""
    verdict = None
    waiver = False
    statuses: list = []
    for line in content.splitlines():
        if re.match(r"^(waiver_proposto|dispensa_proposta|waiver|dispensa):\s*\S",
                    line):
            waiver = True
            continue
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
    # without pyyaml the level names cannot be seen: fail open, like the rest
    # of this fallback.
    return verdict, statuses, [], violations, [], waiver


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

    fallback = False
    try:
        verdict, statuses, doubles, na_violations, bad_levels, waiver = parse_with_yaml(content)
    except Exception:
        fallback = True
        try:
            verdict, statuses, doubles, na_violations, bad_levels, waiver = parse_with_lines(content)
        except Exception:
            sys.exit(0)  # can't understand it → never block

    card = Path(file_path).stem
    hook_cwd = payload.get("cwd") or os.getcwd()
    declared = verdict.strip().lower() if isinstance(verdict, str) else "?"

    # A level name outside the closed set blocks under ANY verdict: the point is
    # to stop generating new divergent spelling, and a `needs-human` written
    # with the old spelling poisons the reading just the same.
    if bad_levels:
        lines = "".join(
            f"    - {written}" + (f"  → escreva `{canonical}`\n" if canonical
                                  else "  (nível que o esquema não conhece)\n")
            for written, canonical in bad_levels)
        print(
            f"[build-hex proof-verdict-guard] BLOCKED: {file_path} usa nome de "
            f"nível fora do conjunto fechado:\n{lines}"
            f"  Os níveis são: {', '.join(sorted(LEVEL_NAMES))}.\n"
            f"  A grafia antiga segue LIDA por quem consome os artefatos, mas não\n"
            f"  pode ser escrita de novo: duas grafias para o mesmo nível fizeram o\n"
            f"  classificador de motivos errar 7 de 33 cards, entre eles o WEGO-1698.",
            file=sys.stderr,
        )
        _t_emit("proof_verdict", cwd=hook_cwd, card=card, verdict=declared,
                blocked="unknown_level_name")
        sys.exit(2)

    # L2 coverage rules (perturbation / waiver). Under ANY verdict, like the level
    # names: they stop the same question from being asked again.
    facts = None
    if not fallback:
        try:
            import yaml
            facts = l2_facts(yaml.safe_load(content))
        except Exception:
            facts = None
    if facts:
        l2_status, technique, uncovered, pert_ok, to_cover = facts
        wvs = []
        if l2_status in ("assumed", "waived") and to_cover:
            wvs = load_waivers(waiver_dirs(file_path, hook_cwd))
        missing = [f for f in to_cover if not applicable_waiver(wvs, f)]

        def l2_block(tag, body):
            print(f"[build-hex proof-verdict-guard] BLOCKED: {file_path} "
                  f"(verdict: {declared}) l2_coverage: {body}", file=sys.stderr)
            _t_emit("proof_verdict", cwd=hook_cwd, card=card, verdict=declared,
                    blocked=tag)
            sys.exit(2)

        if l2_status == "assumed" and pert_ok and not uncovered:
            l2_block("l2_assumed_but_perturbed",
                     "`status: assumed` sits next to a passing "
                     "l3_load_bearing.perturbation and an empty `uncovered_lines`. "
                     "The perturbation already measured coverage: a changed line "
                     "broken on purpose that turned a test red was executed by it.\n"
                     "  Write `status: pass` + `technique: perturbation` with the "
                     "killed perturbations in `run:`, OR list in `uncovered_lines` "
                     "(\"<file>:<lines>\") the changed hunks no perturbation broke "
                     "and keep `assumed`.")
        if l2_status == "assumed" and to_cover and not missing:
            l2_block("l2_assumed_but_waived",
                     "`status: assumed`, but the owner already signed a "
                     "`nada-a-provar` waiver for every file concerned ("
                     + ", ".join(to_cover) + ").\n"
                     "  Write `status: waived` and cite the waiver paths in "
                     "`waivers:` (e.g. `.claude/waivers/nada-a-provar--<scope>.yaml`). "
                     "The owner already answered for these files; do not ask again.")
        if l2_status == "waived" and not to_cover:
            l2_block("l2_waived_unbacked",
                     "`status: waived` but there is no file to cover (no "
                     "`uncovered_lines`, no `scope.changed_classes`). Nothing to "
                     "waive: write `pass` (technique: perturbation) or `assumed`.")
        if l2_status == "waived" and uncovered and not pert_ok:
            l2_block("l2_waived_unbacked",
                     "`status: waived` with a non-empty `uncovered_lines`, but "
                     "l3_load_bearing.perturbation.status is not `pass`. The files "
                     "outside `uncovered_lines` are claimed covered by perturbation, "
                     "but the perturbation did not pass.\n"
                     "  Either leave `uncovered_lines` empty so every changed class "
                     "needs a signed waiver, or write `status: assumed`.")
        if l2_status == "waived" and missing:
            l2_block("l2_waived_unbacked",
                     "`status: waived` but no owner-signed waiver covers: "
                     + ", ".join(missing) + ".\n"
                     "  A waiver needs `motivo: nada-a-provar`, an `escopo` matching "
                     "the file, every required field (autor, criado_em, "
                     "revisit_trigger, ...), no `status: proposta`/`recusada` and an "
                     "unexpired date in `.claude/waivers/`. A proposal or a refusal "
                     "does not count; a `waived` with no signed waiver is the agent "
                     "waiving on its own. Write `status: assumed` (and propose with "
                     "`waivers.propose` in an autonomous run).")


    if not isinstance(verdict, str) or verdict.strip().lower() != "proven":
        _t_emit("proof_verdict", cwd=hook_cwd, card=card, verdict=declared)
        sys.exit(0)  # only `proven` can be contradicted

    if waiver:
        print(
            f"[build-hex proof-verdict-guard] BLOCKED: {file_path} declares "
            f"verdict: proven ao lado de uma dispensa (waiver_proposto / "
            f"dispensa_proposta / waiver / dispensa).\n"
            f"  Uma dispensa proposta é uma pergunta ao dono, não prova; "
            f"veredito computado: needs-human.\n"
            f"  Grave `verdict: needs-human` e deixe o `waiver_proposto` "
            f"apontando para o arquivo em `.claude/waivers/`. Só o "
            f"`cepa-plan answer` do dono converte a proposta em dispensa.",
            file=sys.stderr,
        )
        _t_emit("proof_verdict", cwd=hook_cwd, card=card, verdict="proven",
                blocked="waiver_proposto")
        sys.exit(2)

    if fallback and any(v == "waived" for _, v in statuses):
        print(
            f"[build-hex proof-verdict-guard] BLOCKED: {file_path} declares "
            f"verdict: proven with `waived`, but the artifact could not be read "
            f"as YAML, so the waiver could not be verified.\n"
            f"  Fix the YAML so the guard can check `.claude/waivers/`, or write "
            f"`verdict: needs-human`.",
            file=sys.stderr,
        )
        _t_emit("proof_verdict", cwd=hook_cwd, card=card, verdict="proven",
                blocked="l2_waived_unverifiable")
        sys.exit(2)

    if facts and facts[1] == "perturbation" and facts[0] == "pass" \
            and (not facts[3] or facts[2]):
        why = ("l3_load_bearing.perturbation.status is not `pass`" if not facts[3]
               else "`uncovered_lines` is not empty: " + ", ".join(facts[2]))
        print(
            f"[build-hex proof-verdict-guard] BLOCKED: {file_path} declares "
            f"verdict: proven with `l2_coverage` `technique: perturbation`, but "
            f"{why}.\n"
            f"  Coverage by perturbation holds only when every changed behavior "
            f"hunk was broken on purpose and went red. Write `status: assumed` "
            f"(or `gap`) listing the unbroken hunks in `uncovered_lines`, and "
            f"verdict needs-human.",
            file=sys.stderr,
        )
        _t_emit("proof_verdict", cwd=hook_cwd, card=card, verdict="proven",
                blocked="l2_perturbation_unbacked")
        sys.exit(2)

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
