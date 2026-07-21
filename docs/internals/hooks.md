# Hooks reference

Every hook the marketplace ships, what fires it, what it reads, what it
writes, and how to debug it.

## Hook events used

CC supports several hook events. This marketplace uses six:

| Event | Fires | Marketplace usage |
|---|---|---|
| `PreToolUse` | Before a tool call lands. Hook can exit 2 to BLOCK the call. | `path-lock.py` + `bash-path-lock.py` (every topology), `gate-advance.py` + `enforcement-guard.py` + `maven-reactor-guard.py` + `lead-no-worktree.py` + `acceptance-gate.py` (common) |
| `PostToolUse` | After a tool call returns. Hook can observe + write to disk. Cannot block (the call already happened). | `autonomous-checkpoint.py`, `mark-build-stale.py`, `capture-build-result.py`, `session-activity.py` (common) |
| `UserPromptSubmit` | When the user submits a prompt. Hook can observe; can inject system reminders. | `session-log.py`, `session-subject.py` (common) |
| `SessionStart` | Session boot. Hook can inject context. | `session-registry.py` (common) — registry hygiene + transparent handoff resume |
| `SessionEnd` | Session teardown. | `session-registry.py` (common) — WIP-autosave + deregister |
| `Stop` | After the main agent finishes a turn. | `session-checkpoint.py` (common) — continuous handoff skeleton |

## Hook payload anatomy

CC pipes a JSON payload to the hook's stdin. The shape varies by event;
common keys we rely on:

```json
{
  "tool_name": "Edit",
  "tool_input": {
    "file_path": "/abs/path/to/file.java",
    "old_string": "...",
    "new_string": "..."
  },
  "tool_response": {                     // PostToolUse only
    "content": "...",
    "is_error": false,
    "exit_code": 0
  },
  "agent_type": "build-hex:domain-dev",  // Subagent caller, plugin-namespaced.
                                             // Empty string when called from main session.
                                             // BUILT-IN CC AGENTS (statusline-setup,
                                             // Explore, Plan, general-purpose) arrive
                                             // with bare name, NO colon prefix.
  "cwd": "/abs/path/to/project",
  "session_id": "...",
  "hook_event_name": "PreToolUse"
}
```

`agent_type` resolution rules (see [`path-lock.md`](path-lock.md) for
the full design):

| Form | Source | Path-lock treatment |
|---|---|---|
| `<plugin>:<agent>` matching `PLUGIN_NAME` | Our subagent | Check `ALLOWED_WRITES` |
| `<plugin>:<agent>` with foreign prefix | Another plugin's subagent | Exit 0 (foreign — not our concern) |
| `<bare-name>` (no colon) | CC built-in (statusline-setup, etc.) | Exit 0 (foreign) |
| `""` (empty) | Main session orchestrator | Exit 0 (not gated) |

## Hook exit codes

| Exit | Meaning |
|---|---|
| `0` | Allow / observe / no-op |
| `1` | Generic error (CC may log; doesn't block) |
| `2` | **Block** (PreToolUse only). Stderr message reaches the calling agent so it can self-correct. |

## Every hook the marketplace ships

### path-lock.py × 5 (PreToolUse, matcher `Edit\|Write\|MultiEdit\|NotebookEdit`)

Owners: `build-team/hooks/`, `build-hex/hooks/`, `discovery/hooks/`,
`design/hooks/`, `docs-topology/hooks/`.

Enforces per-agent write allowlists. Each instance has a `PLUGIN_NAME`
constant and an `ALLOWED_WRITES` dict keyed by agent name.

**Logic (post-fix flow):**

```python
1. Parse stdin JSON; fail-open on parse error.
2. If tool_name not in {Edit, Write, MultiEdit, NotebookEdit}: exit 0.
3. If file_path missing: exit 0.
4. raw_agent_type = payload["agent_type"]
   If has colon:
     prefix = raw_agent_type.split(":")[0]
     If prefix != PLUGIN_NAME: exit 0  (foreign plugin)
   Else: exit 0  (main session, built-in CC agent, or no agent info)
5. agent = detect_agent(payload)  (strips prefix; falls back to legacy keys)
6. If is_own_expertise_file(file_path, agent): exit 0
7. allowed = ALLOWED_WRITES.get(agent)
   If allowed is None: BLOCK ("unknown agent X")
8. If path_matches(file_path, allowed, project_root): exit 0
   Else: BLOCK with allowlist contents.
```

See [`path-lock.md`](path-lock.md) for design rationale, the
multi-plugin collision fix (`PLUGIN_NAME` prefix scoping), the
built-in-agent fail-open fix, and debugging via
`HEX_PATHLOCK_DEBUG=1`.

### bash-path-lock.py × 5 (PreToolUse, matcher `Bash`)

Owners: same five topologies as `path-lock.py`.

The Bash half of the path-lock. `path-lock.py` only gates
`Edit/Write/MultiEdit` — so an agent blocked from a `Write` could land the
same write through the shell (`sed -i`, `cat > file`, `tee`, a heredoc). This
hook closes that bypass: it detects **shell-level writes** to an **in-project**
path outside the agent's allowlist and exits 2.

**Logic:**

```python
1. tool_name must be Bash; act only on this plugin's prefixed subagents.
2. Reuse the sibling path-lock.py's allowlist (build_allowed_writes /
   ALLOWED_WRITES, imported via importlib — single source of truth).
3. extract_write_targets(command): redirections (>, >>), tee, sed -i, cp, mv,
   install, dd of=, truncate. Indecidable constructs (python -c, heredoc-to-
   interpreter, ...) → fail open, but logged to BASH_PATHLOCK_COVERAGE_LOG.
4. For each target inside project_root and outside the agent's allowlist
   (own expertise file exempt): BLOCK. Out-of-root targets (/tmp, $HOME,
   build caches) are out of scope — allowed.
```

Deliberately narrow to keep false positives near zero: subprocess-internal
writes (`mvn`, `git`, `npm`) are invisible — only explicit shell redirection/
file-mutation commands are caught. It is a guardrail, not a sandbox; see
[`path-lock.md`](path-lock.md)#the-bash-half-and-the-enforcement-surface.

### enforcement-guard.py (PreToolUse, matcher `Bash` + `Edit\|Write\|MultiEdit\|NotebookEdit`)

Owner: `common/hooks/`.

The path-locks protect in-project paths; they cannot protect the files that
DEFINE the rules, which live out of root: installed plugin code under
`~/.claude/plugins/`, the global `~/.claude/settings.json` (which declares the
hooks), and a project's own `.claude/hooks/`. A subagent once edited the cached
`path-lock.py` via Bash to whitelist itself — a silent privilege escalation
both locks allowed (out-of-root blind spot). This guard is the missing
invariant: **no plugin subagent writes the enforcement surface, anywhere.**

**Logic:**

```python
1. Only gate plugin-prefixed subagents (main session / built-in agents
   fail open — you can still reinstall + edit settings).
2. Collect targets: file_path (Edit/Write) or shell-write targets (Bash).
3. BLOCK if a target resolves under any `.claude/` segment whose child is
   `plugins`, `hooks`, or one of {settings.json, settings.local.json,
   keybindings.json} — home OR project.
4. Carve-out: the agent's own <agent>-mental-model.yaml in an expertise/
   dir stays writable (its legitimate mental-model home, even in the cache).
```

### maven-reactor-guard.py (PreToolUse, matcher `Bash`)

Owner: `common/hooks/`.

`./mvnw test -pl <modulo>` **sem** `-am` resolve os módulos irmãos pelos jars do
`~/.m2` em vez de recompilar o reator. Cache defasado ⇒ os testes rodam contra
código antigo e o vermelho é **falso**: determinístico, reproduzível e irreal —
o que faz ele se disfarçar de bug funcional. Em 2026-07-21 (WEGO-1949) isso
custou uma investigação inteira e um card acusando indevidamente uma feature
entregue: o jar de `application` era de 16/jul e sequer tinha o método que o
teste exercitava. Já estava documentado no README do projeto e na memória, e
reincidiu — daí a barreira ser mecânica e bloquear, não avisar.

**Logic:**

```python
1. Só tool Bash; comando contendo `stale-ok` fail-open (escape hatch para
   quem ACABOU de rodar `./mvnw install -DskipTests`).
2. cwd precisa ser raiz de reator multi-módulo (`<modules>` no pom.xml).
   Single-module e sem-pom fail-open — o problema não existe lá.
3. Por segmento (split em ; | && ||): achar uma invocação REAL do Maven.
   Prefixo de env (`FOO=bar ./mvnw`) e wrapper (`timeout 600 mvn`) contam;
   `echo`/`grep`/`cat` + amigos não — ali o `mvn` é texto citado.
4. BLOCK se houver `-pl`/`--projects` (inclusive `-pl=x`) sem `-am`/
   `--also-make`. `-amd`/`--also-make-dependents` NÃO conta: constrói os
   dependentes, não as dependências, então o buraco continua aberto.
```

Testes: `tests/test_maven_reactor_guard.py` (25 casos, sem deps).

### gate-advance.py (PreToolUse, matcher `Bash`)

Owner: `common/hooks/`.

Hard gate against advancement commands when build state is unsafe.

**Logic:**

```python
1. Parse stdin; tool_name must be Bash; fail-open on parse error.
2. command = tool_input["command"]
3. If command matches any EXEMPT_PATTERN (mvnw, gradle, npm, pytest,
   cargo, go test, read-only git): exit 0  (recovery path; never gate)
4. If command does NOT match any ADVANCE_PATTERN (git commit, git push,
   gh pr create, gh pr merge, gh release, kubectl apply, terraform
   apply, docker push, aws/gcloud/az deploy): exit 0
5. Read .claude/last-build.json
   If missing: exit 0 with stderr warning (no baseline)
   If parse error: exit 0 with stderr warning
   If status == SUCCESS: exit 0
   If status == STALE: BLOCK with edit path + suggestion
   If status == FAILURE: BLOCK with failure tail + suggestion
```

ADVANCE_PATTERNS use regex with separator-aware lookahead
(`(?:^|\s|&&\s|;\s)`) so compound shells (`git add foo && git commit
-m bar`) match correctly.

### mark-build-stale.py (PostToolUse, matcher `Edit|Write|MultiEdit`)

Owner: `common/hooks/`.

Marks `last-build.json` as STALE after source edits.

**Logic:**

```python
1. Parse stdin; tool_name must be Edit/Write/MultiEdit.
2. file_path = tool_input["file_path"]
3. If is_source(file_path):
     - Read current .claude/last-build.json (if present) for last_known_*
     - Write new state: { status: STALE, since: now, after_edit_to,
       last_known_status, last_known_at, last_known_command }
4. Else: exit 0 (not production code; docs/specs/tests don't invalidate)
```

`is_source` allowlist: source-language extensions (`.java`, `.ts`,
`.py`, `.go`, etc.), build manifests (`pom.xml`, `package.json`,
`Cargo.toml`, etc.), SQL migrations. Path exclusions: `.claude/`,
`docs/`, `spec/`, `specs/`, `*/src/test/`, `/test/`, `/tests/`,
`/__tests__/`.

### capture-build-result.py (PostToolUse, matcher `Bash`)

Owner: `common/hooks/`.

Detects build/test invocations and writes SUCCESS or FAILURE to
`last-build.json`.

**Logic:**

```python
1. Parse stdin; tool_name must be Bash.
2. command = tool_input["command"]
3. Match against PATTERNS list (maven, gradle, npm, yarn, pytest,
   cargo, go-test). If no match: exit 0 (don't classify).
4. For matched kind:
     - Extract response text from tool_response (handles dict shape
       variants: stdout/output/result/content/stderr)
     - Check for kind-specific marker: BUILD SUCCESS / BUILD SUCCESSFUL
       in success path; BUILD FAILURE / BUILD FAILED in failure path
     - Fallback: exit_code 0 → SUCCESS; non-zero → FAILURE
     - Ambiguous (marker missing, exit code unknown): exit 0
5. Write { status: SUCCESS|FAILURE, at: now, command, kind,
   tail: last ~12 lines of response_text }
```

Pattern list is extensible — add a `(regex, kind, success_marker,
failure_marker)` tuple to `PATTERNS`. `None` markers fall back to exit
code only.

### autonomous-checkpoint.py (PostToolUse, matcher `Task`)

Owner: `common/hooks/`.

Out-of-band state writes during autonomous runs. Active only when
`CLAUDE_AUTONOMOUS_RUN_ID` is set in env.

**Logic:**

```python
1. Read CLAUDE_AUTONOMOUS_RUN_ID env. If unset: fast no-op.
2. Parse stdin; tool_name must be Task.
3. Extract subagent_type, prompt summary (description or first ~200
   chars of prompt), result text (handles list-of-blocks shape).
4. Append YAML list item to docs/autonomous/<run-id>/state.yaml's
   "log:" section: { timestamp, subagent, prompt_summary,
   result_summary, exit_status }.
5. Failures stderr-only; never break the workflow.
```

Append uses raw file manipulation (not PyYAML — no external deps).
Trusts the file ends with a `log:` list created by
`/common:autonomous-start`.

### session-log.py (UserPromptSubmit)

Owner: `common/hooks/`.

Captures every user prompt to `.claude/session-log.md` with date and
UTC time headers.

**Logic:**

```python
1. Parse stdin.
2. prompt = payload["prompt"] or payload["message"] (handles dict
   content shape).
3. Skip empty/whitespace prompts (CC sometimes fires on internal
   events).
4. Append to .claude/session-log.md:
   - First write to file → "# Session log\n\n## YYYY-MM-DD\n\n"
   - New date → "\n## YYYY-MM-DD\n\n"
   - Entry → "### HH:MM:SS UTC\n\n<prompt>\n\n"
```

`/common:recap` reads this file to render its "Asked / Status /
Delivered" table.

### session-subject.py (UserPromptSubmit)

Owner: `common/hooks/`.

Lexical subject-shift detection plus the wrap-up/handoff nudge. Tracks a
per-session vocabulary centroid in the registry entry. "Lexical proposes, model
disposes": the hook injects a discreet note; the model, which understands the
live conversation, decides whether to surface it.

- **Subject divergence** (overlap below `CLAUDE_WT_SUBJECT_THRESHOLD`, after a
  baseline of `CLAUDE_WT_SUBJECT_MINPROMPTS`): a gentle hint to isolate a new
  task in its own worktree.
- **Wrap-up nudge** (a divergence AND a recent commit = prior work closed, OR a
  long session past `CLAUDE_WT_SESSION_SOFTCAP=45` prompts): suggest saving a
  handoff and starting fresh; on agreement the model runs `/common:handoff`.
  Higher bar than the isolate-hint to avoid nagging.

Off-switches: `CLAUDE_WT_SUBJECT=off` (whole detector), `CLAUDE_WT_NUDGE=off`
(just the wrap-up nudge).

### session-activity.py (PostToolUse, matcher `Edit|Write|MultiEdit`)

Owner: `common/hooks/`. Records which top-level dirs a session touches into its
registry entry (`touched_dirs`), feeding the worktree "multi-area" flag and the
handoff checkpoint's "areas touched" line.

### session-registry.py (SessionStart / SessionEnd)

Owner: `common/hooks/`. The live-session registry + worktree hygiene, plus
**transparent handoff resume**. On start: registers the session (capturing
`start_commit`), prunes dead entries, warns on same-tree overlap, auto-cleans
finished worktrees, and — via a direct branch-keyed lookup — injects the
previous session's handoff as background with a "don't announce, just continue"
rule (suppressed when a live peer shares the tree or the handoff is >48h old).
On end: WIP-autosaves a dirty `session/*` worktree and deregisters.

### session-checkpoint.py (Stop)

Owner: `common/hooks/`. Every turn, rewrites the AUTO zone of
`<main-root>/.claude/handoffs/<branch-slug>.md` with mechanical facts (commits
this session, dirs touched, last intents from `session-log.md`). Crash-proof:
the skeleton is always current, so a token-limit kill never loses the thread.
The narrative (NOTE zone) is written separately by `/common:handoff`; the two
zones are marker-delimited and never clobber each other (`_handoff.py`).

### lead-no-worktree.py (PreToolUse, matcher `Task`)

Owner: `common/hooks/`. Blocks spawning a lead agent with worktree isolation —
leads are write-locked out of the workers' lanes, so isolating them is a
mistake. Exit 2 with a re-issue suggestion.

### acceptance-gate.py (PreToolUse, matcher `mcp__.*transitionJiraIssue`)

Owner: `common/hooks/`. Blocks the In-Review transition while the per-card
acceptance audit (`.claude/acceptance/<KEY>.yaml`, written by
`completion-auditor`) is absent or incomplete. See
[`../acceptance-completeness.md`](../acceptance-completeness.md).

## Hook ordering when multiple match

CC fires hooks in the order they appear in `plugin.json`. When multiple
plugins each register hooks on the same event + matcher, **all of them
fire**. Order across plugins is unspecified.

Practical implication: every hook that returns exit 2 on the same call
short-circuits the rest. The strictest verdict wins.

This was the bug behind the multi-plugin path-lock collision (commit
`0284825`). Every path-lock fires on every gated tool call; without
prefix scoping, plugin A would block plugin B's agents. Fix: each hook
exits 0 early when the calling agent isn't from its plugin.

## Debugging hooks

### Verbose CC debug mode

```sh
claude --debug
```

Hooks print stderr; messages surface in the debug log.

### Hook-specific debug logs

`build-hex/hooks/path-lock.py` has a `HEX_PATHLOCK_DEBUG` env var:

```sh
export HEX_PATHLOCK_DEBUG=1
# Re-run the operation. Log lands at /tmp/hex-pathlock-debug.log.
```

Each entry: payload top-level keys, identity fields probed,
env-agent vars, resolved agent name, tool, file path.

Useful when CC version changes (the `agent_type` payload field might
move; debug log shows what's actually arriving).

### Adding your own debug print

Insert `print(payload, file=sys.stderr)` at the top of `main()` and
re-run. The payload goes to CC's debug output.

### Hook didn't fire

Three common causes:

1. **Plugin disabled.** `claude plugin list` should show enabled.
2. **Cache stale.** Edited the hook source but CC is using the cached
   copy. Run `bin/install.sh --clean`.
3. **Matcher mismatch.** The `"matcher"` field in `plugin.json`'s hook
   declaration uses a regex against `tool_name`. Common matchers:
   `Edit|Write|MultiEdit|NotebookEdit`, `Bash`, `Task`. Typo
   silently skips the hook.

### Hook fires but is wrong

```sh
HEX_PATHLOCK_DEBUG=1 claude --debug
```

Then read `/tmp/hex-pathlock-debug.log`. If `resolved_agent` is wrong,
check `detect_agent`'s fallback list — CC might be using a different
payload field in your version.

## Adding a new hook

See [`extending.md`](extending.md). Short version:

1. Write `<plugin>/hooks/<name>.py` (make executable: `chmod +x`).
2. Register in `<plugin>/.claude-plugin/plugin.json` under `hooks.<event>`:

   ```json
   {
     "hooks": {
       "PreToolUse": [
         {
           "matcher": "Bash",
           "hooks": [
             { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/<name>.py\"" }
           ]
         }
       ]
     }
   }
   ```

3. `bin/install.sh --clean` (refreshes cache).
4. Test in a fresh CC session in a host project.

## Memory of past gotchas

These are documented in `cc_plugin_quirks` memory and in
[`cc-quirks.md`](cc-quirks.md). Read those before adding a new hook —
the failure modes are predictable.
