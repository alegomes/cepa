# Internals

Documentation for people extending, debugging, or maintaining the
marketplace. For "I want to use the agents" docs, see the parent
[`../`](../) directory and the top-level [`../../README.md`](../../README.md).

## When to read each page

| Page | Read it for |
|---|---|
| [`architecture.md`](architecture.md) | Three-tier model (orchestrator/leads/workers). What's hard-enforced (tool allowlists, path-lock, gate-advance) vs. convention (prompts, topology snippets). Plugin anatomy and per-plugin layout. |
| [`hooks.md`](hooks.md) | Full reference for every hook the marketplace ships. Lifecycle events, payload shapes, exit codes, ordering, debugging. |
| [`path-lock.md`](path-lock.md) | Deep dive on the path-lock PreToolUse hook. Prefix scoping (the multi-plugin collision fix), agent detection, allowlist conventions, foreign-prefix and no-prefix early-exits, expertise-file structural check. Plus its two companions: `bash-path-lock.py` (the shell-write bypass) and `enforcement-guard.py` (the lock can't protect its own out-of-root files). |
| [`build-state.md`](build-state.md) | The `.claude/last-build.json` state machine: `mark-build-stale` writes STALE, `capture-build-result` writes SUCCESS/FAILURE, `gate-advance` reads to block. Edge cases and patterns to handle. |
| [`agent-anatomy.md`](agent-anatomy.md) | System prompt conventions: YAML frontmatter, the table header (Reports to / Delegates to / Skills / Reads / Writes / Output), Rules section, Output shape, expertise file reference. The shape every agent in the marketplace follows. |
| [`expertise.md`](expertise.md) | `common/expertise/<agent>-mental-model.yaml` shape, the centralized-via-symlink trick that makes agent learnings persist across projects, the `mental-model` skill that reads on boot, the `debrief` command that writes feedback, the 20-entry cap with `principle` exemption. |
| [`extending.md`](extending.md) | Cookbook: add a new agent / skill / command / hook / plugin. Each comes with a checklist and a path-lock entry (when applicable). |
| [`cc-quirks.md`](cc-quirks.md) | Empirical findings about Claude Code's plugin system. Mirrors the `cc_plugin_quirks` memory in `~/.claude/projects/.../memory/`. The "wish I'd known this before building" list. |

## House conventions

- **Edit centrally, install locally.** The marketplace is local-only.
  No public publishing, no CI/CD, no release automation. Everything
  ships via `bin/install.sh` from a local clone (private GitHub remote
  for personal infra is fine; see `user_preferences` memory).
- **Per-Story / per-PR commits.** Split commits along feature/doc lines
  rather than mega-commits. Naming and scope decisions get explicit
  push-back before landing.
- **Multi-layer enforcement over prompt-only conventions.** When
  proposing a new rule, ask "where does this fail closed?". Order of
  preference: (a) tool allowlist (CC enforces hard), (b) hook-level
  refusal, (c) agent-spec rule, (d) command-level prompt.
- **Read the memory.** `~/.claude/projects/.../memory/` has
  `project_state`, `cc_plugin_quirks`, `user_preferences` — read them
  before assuming.
