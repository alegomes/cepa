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
issue key from the tool input, looks for `<KEY>.yaml` (see `find_artifact` for
where — this worktree first, then the main clone, `.claude/acceptance/` and
`docs/acceptance/` in each):

  - absent, target == done       -> BLOCK: reaching Done with no audit in any
                                    of the four places means the completion-
                                    auditor step was skipped, not that it
                                    hasn't run yet (item
                                    `acceptance-gate-barra-done-sem-auditoria`,
                                    decided 2026-09-27)
  - absent, target unresolved or
    anything else                -> allow (audit hasn't run yet; not gated)
  - present, status: complete    -> allow
  - present, status: <anything>  -> BLOCK, unless the target status is
                                    declared and is not an enforced one
  - key not extractable          -> allow (can't gate meaningfully; never
                                    spuriously block a Jira transition)

Build EMPTY (item `gate-verde-sem-teste`, 2026-09-25): before the artifact
check, a forward move (enforced or unresolved target) is BLOCKED when the
session root's `.claude/last-build.json` is `EMPTY` — a filtered test run that
exited green with zero tests executed. That is the half of "a green with no
test is not green" that gate-advance cannot see: gate-advance stops the
commit, this stops the card being declared done. Independent of the artifact
(a `complete` audit does not unlock it); bounces stay allowed.

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


def resolve_target(mut: dict, tid: str | None, cwd: Path) -> str | None:
    """Logical target status of the transition, or None when unresolvable."""
    # A status name coming from `twg` must become a logical key: a lowercased
    # "In Review" gave `in review` and passed as a lateral move.
    if mut["target_status"]:
        return J.logical_status(mut["target_status"], cwd)
    return transition_map(cwd).get(tid) if tid else None


ACCEPTANCE_DIRS = (Path(".claude") / "acceptance", Path("docs") / "acceptance")


def candidate_paths(key: str, session: Path, main: Path) -> list[Path]:
    """The (up to four) artifact paths this gate looks at, in lookup order.

    Session root's `.claude/acceptance/` and `docs/acceptance/`, then the same
    two under the MAIN clone — deduped to two when `session == main` (no
    worktree involved). Shared by `find_artifact` and by the block message for
    a missing artifact, so the two never drift apart.
    """
    roots = [session] if session == main else [session, main]
    return [root / d / f"{key}.yaml" for root in roots for d in ACCEPTANCE_DIRS]


def find_artifact(key: str, session: Path, main: Path) -> Path | None:
    """The acceptance artifact for `key`, or None when no tree has one.

    Order: this worktree's `.claude/acceptance/`, its `docs/acceptance/`, then
    the same two under the MAIN clone. The first found wins, so a fresh audit
    written in this worktree outranks an older one left in the main clone.

    Looking only at `<session root>/.claude/acceptance/` made the gate blind in
    every new worktree: `.claude/` is not versioned and `seed-worktree.py` does
    not copy `acceptance/`, so the file was "absent" and the transition passed.
    On 2026-09-16 the prove-drain, running in the `session/decide` worktree,
    moved WEGO-2218 to Done while the main clone's artifact said `incomplete`.
    `docs/acceptance/` is where wego-acesso-backend versions its artifacts.

    This is a deliberate exception to `session_root` (item `session-root`,
    2026-08-25), which keeps per-worktree state per worktree. The build
    baseline describes the CODE in one tree, so reading another tree's is
    wrong. The acceptance audit describes a CARD, and a card is the same card
    whichever tree moves it on the board.
    """
    for p in candidate_paths(key, session, main):
        if p.is_file():
            return p
    return None


def empty_build(cwd: Path) -> dict | None:
    """The session's `.claude/last-build.json` when its status is EMPTY, or
    STALE with `last_known_status: EMPTY` (edited after the empty run).

    Unreadable or absent state is None: build greenness is gate-advance's job;
    this gate only refuses the one state that LOOKS green and is not.
    """
    p = cwd / ".claude" / "last-build.json"
    try:
        state = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(state, dict):
        return None
    status = str(state.get("status", "")).upper()
    if status == "EMPTY":
        return state
    # EMPTY followed by a source edit: mark-build-stale writes STALE and keeps
    # the EMPTY in `last_known_status`. No new build ran, so the card still has
    # no executed test, and now not even the code is the same.
    if status == "STALE" and str(state.get("last_known_status", "")).upper() == "EMPTY":
        return dict(state, _stale=True,
                    command=state.get("last_known_command"),
                    at=state.get("last_known_at"))
    return None


def block_empty(key: str, target: str | None, state: dict, cwd: Path):
    target_label = target or "a forward status (target unresolved, enforced by default)"
    stale = (
        f"  The code changed since (last edit: {state.get('after_edit_to', '<unknown>')}),\n"
        f"  and no build ran after it: the baseline is STALE on top of that EMPTY run.\n"
        if state.get("_stale") else ""
    )
    print(
        f"[acceptance-gate] BLOCKED: cannot move {key} to {target_label} — the last real build "
        f"is EMPTY: the test filter in `{state.get('command') or '<unknown>'}` matched zero "
        f"tests (recorded {state.get('at') or '<unknown time>'} in "
        f"{cwd / '.claude' / 'last-build.json'}).\n"
        f"{stale}"
        f"  It exited green, but no test ran, so it proves nothing, and a card is not\n"
        f"  done on it — whatever the acceptance artifact says.\n"
        f"  Fix the test name in the filter (-Dtest= / -k / -run / -t) so it matches the\n"
        f"  tests you mean and re-run it, or make the build fail on an empty filter\n"
        f"  (Maven: -Dsurefire.failIfNoSpecifiedTests=true). A green run with N > 0 tests\n"
        f"  clears this. Bouncing the card back (e.g. to in_progress) stays allowed.",
        file=sys.stderr,
    )
    sys.exit(2)


def block_no_artifact(key: str, session: Path, main: Path):
    paths = candidate_paths(key, session, main)
    paths_str = "\n".join(f"    - {p}" for p in paths)
    print(
        f"[acceptance-gate] BLOCKED: cannot move {key} to done — no acceptance audit found\n"
        f"  Searched:\n{paths_str}\n"
        f"  Every harness flow runs the completion-auditor before Review, so reaching Done\n"
        f"  with no audit anywhere means the flow was skipped, not that the audit hasn't\n"
        f"  run yet — WEGO-1891, 2202 and 2218 all reached Done this way.\n"
        f"  Fix: run the completion-auditor (it writes `.claude/acceptance/{key}.yaml`) and\n"
        f"  get `status: complete`. Never create the artifact by hand. Bouncing the card\n"
        f"  back (e.g. to in_progress) stays allowed.",
        file=sys.stderr,
    )
    sys.exit(2)


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
    # Recognition by EFFECT, not by tool name. The MCP name only covered MCP;
    # the `twg` CLI arrives as Bash and used to pass silently through here.
    _mut = J.classify(payload)
    if _mut is None:
        sys.exit(0)
    # Opacity is checked BEFORE filtering by kind: a mutation that cannot be
    # read may be exactly the one this gate guards. Filtering first let
    # `twg api ... -X POST` escape for not being classifiable.
    if _mut["opaque"]:
        J.block(_mut, "acceptance-gate")
    if _mut["kind"] != "transition":
        sys.exit(0)

    tool_input = _mut["tool_input"]
    key = extract_key(tool_input)
    if not key:
        # Can't identify the card -> can't gate. Never spuriously block.
        sys.exit(0)

    # The worktree ROOT, not the current directory: Bash's cwd persists
    # between calls, and a `cd subdir` would divert this session's state
    # to `subdir/.claude/` for the rest of it (see _wtlib.session_root).
    here = payload.get("cwd") or os.getcwd()
    cwd = Path(L.session_root(here)).resolve()
    # Outside a git repo `main_root` is "", and `Path("")` would be the
    # process directory: with no main clone, only the own root counts.
    main = L.main_root(here)
    artifact = find_artifact(key, cwd, Path(main).resolve() if main else cwd)

    tid = extract_transition_id(tool_input)
    target = resolve_target(_mut, tid, cwd)

    # A filtered build that matched zero tests (EMPTY, written by
    # capture-build-result) declares no card done, with or without an audit
    # artifact. Only the forward move is blocked; sending the card back stays
    # free, for the same reason as the direction below.
    if target is None or target in ENFORCED_TARGETS:
        empty = empty_build(cwd)
        if empty is not None:
            block_empty(key, target, empty, cwd)

    if artifact is None:
        # Absent + target == done: BLOCK (owner's decision, 2026-09-27, item
        # `acceptance-gate-barra-done-sem-auditoria`, question 6 of the review of
        # run 2026-09-26-2203). Every harness pipeline runs the
        # completion-auditor before Review; reaching Done with NO artifact
        # in the four trees means the flow was skipped, not that the audit
        # "has not run yet": WEGO-1891, 2202 and 2218
        # reached Done that way.
        if target == "done":
            block_no_artifact(key, cwd, Path(main).resolve() if main else cwd)
        # Absent + target NOT resolved (None): still allows, on purpose.
        # Failing closed here would block every To Do -> In Progress
        # transition in repos without `transition_ids`, since no audit exists
        # at that point of the flow (the completion-auditor only runs after
        # implementation). Failing closed is the right behavior when there IS
        # a `target` resolved to `done`; with no resolved target, it would be
        # just noise.
        # Absent + target in_review or anything else: nothing to do yet, the
        # completion-auditor writes this file well before the transition to
        # In Review; that is where the teeth show up.
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

    # The audit is incomplete. Which way is this card moving? (`target`,
    # resolved above.)
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
