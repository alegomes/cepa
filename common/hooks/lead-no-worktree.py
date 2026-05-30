#!/usr/bin/env python3
"""PreToolUse hook: leads must never run worktree-isolated.

Topology-agnostic guardrail shared by every alegomes topology. CC 2.1.x
strips the `Task` tool from any subagent invoked with
`isolation: "worktree"` (empirically verified — see
`cc_plugin_quirks.md`). A lead's entire job is to delegate via `Task`;
a worktreed lead therefore silently loses its ability to fan out to
workers. The symptom is nasty and indirect: the lead does as much as it
can by itself (burning a huge token budget solo), can't apply code
because it's write-locked out of the workers' lanes, and returns a
spec instead of a result. Stalls at ARCHITECT on plan-build-validate;
collapses into a 190k-token solo run on reproduce-fix-verify.

The "never worktree a lead" rule already exists as prose in the command
docs (`reproduce-fix-verify.md`, `fix.md`, `plan-build-validate.md`).
Prose is not a hard guarantee — an orchestrator that improvises its
delegation (rather than executing the command step-by-step) can reach
the anti-pattern with nothing stopping it. This hook converts the prose
into enforcement: it inspects every `Task` call and blocks the spawn
when the target agent is a delegating lead AND worktree isolation is
requested.

Scope by construction, not by plugin prefix: any agent whose name ends
in `-lead` (engineering-lead, planning-lead, validation-lead,
writing-lead, discovery-lead) is a delegator, plus a small explicit set
of delegating non-lead agents (e.g. book-architect). Built-in CC agents
and leaf workers never match, so they pass untouched.

Lives in `common` (installed with every topology) rather than in each
topology plugin — one hook, no multi-plugin collision.

Exit codes:
  0 — allowed
  2 — blocked (stderr message reaches the orchestrator so it re-issues
      the Task without worktree)
"""

import json
import os
import sys

# Delegating agents that lose their reason to exist when worktreed.
# The `-lead` suffix is the primary rule (covers every topology's leads);
# this set catches delegators that don't carry the suffix.
EXTRA_DELEGATORS = {"book-architect"}


def resolve_target_agent(tool_input: dict) -> str:
    """The agent being spawned by this Task call. CC's Task tool carries it
    as `subagent_type`, plugin-namespaced (`<plugin>:<agent>`); strip the
    prefix. Fall back across plausible key names for version drift."""
    for key in ("subagent_type", "agent_type", "subagent_name", "agent"):
        val = tool_input.get(key)
        if val and isinstance(val, str):
            return val.split(":", 1)[1] if ":" in val else val
    return ""


def wants_worktree(tool_input: dict) -> bool:
    """True if this Task call requests worktree isolation. Primary key is
    `isolation: "worktree"`; we also scan defensively for param-name drift
    across CC versions (mirroring capture-build-result's shape-tolerance)."""
    iso = tool_input.get("isolation")
    if isinstance(iso, str) and iso.strip().lower() == "worktree":
        return True
    if tool_input.get("worktree") in (True, "true", "True", 1):
        return True
    # Last-resort: any top-level scalar literally equal to "worktree".
    for v in tool_input.values():
        if isinstance(v, str) and v.strip().lower() == "worktree":
            return True
    return False


def is_delegating_lead(agent: str) -> bool:
    return agent.endswith("-lead") or agent in EXTRA_DELEGATORS


def debug_log(payload: dict, agent: str, worktree: bool) -> None:
    """Gated behind LEAD_WORKTREE_DEBUG=1 — dumps the payload shape so future
    Task-param drift is diagnosable rather than a guessing game."""
    if os.environ.get("LEAD_WORKTREE_DEBUG") != "1":
        return
    log_path = os.environ.get("LEAD_WORKTREE_DEBUG_LOG", "/tmp/lead-no-worktree-debug.log")
    snapshot = {
        "top_level_keys": sorted(payload.keys()),
        "tool_name": payload.get("tool_name"),
        "tool_input_keys": sorted((payload.get("tool_input") or {}).keys()),
        "resolved_target_agent": agent,
        "wants_worktree": worktree,
    }
    try:
        with open(log_path, "a") as f:
            f.write(json.dumps(snapshot) + "\n")
    except OSError:
        pass


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[lead-no-worktree] could not parse hook payload; allowing", file=sys.stderr)
        sys.exit(0)

    if payload.get("tool_name", "") != "Task":
        sys.exit(0)

    tool_input = payload.get("tool_input") or {}
    agent = resolve_target_agent(tool_input)
    worktree = wants_worktree(tool_input)
    debug_log(payload, agent, worktree)

    if not agent or not is_delegating_lead(agent) or not worktree:
        sys.exit(0)

    print(
        f"[lead-no-worktree] BLOCKED: refusing to spawn {agent!r} with "
        f"isolation=\"worktree\".\n"
        f"  CC 2.1.x strips the `Task` tool from worktree-isolated subagents, "
        f"so a worktreed lead cannot delegate to its workers — it stalls or "
        f"silently does the whole job solo.\n"
        f"  Re-issue this Task WITHOUT isolation (leads run in the main "
        f"session). Only leaf workers (dev / qa / reviewer) may be worktreed, "
        f"and only for genuine parallelism.\n"
        f"  See cc_plugin_quirks.md and the command's \"Worktree policy\" section.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
