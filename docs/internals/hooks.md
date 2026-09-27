# Hooks reference

Every hook the marketplace ships, what fires it, what it reads, what it
writes, and how to debug it.

## Hook events used

CC supports several hook events. This marketplace uses six:

| Event | Fires | Marketplace usage |
|---|---|---|
| `PreToolUse` | Before a tool call lands. Hook can exit 2 to BLOCK the call. | `path-lock.py` + `bash-path-lock.py` (every topology incl. `marketing`), plus close to 30 `common` hooks gating matchers `Bash`, `Edit\|Write\|MultiEdit\|NotebookEdit`, `Write`, `Task`, `Monitor`, and specific `mcp__...` Jira/Bitbucket tool matchers (see the full list below) |
| `PostToolUse` | After a tool call returns. Hook can observe + write to disk. Cannot block (the call already happened). | `autonomous-checkpoint.py`, `mark-build-stale.py`, `capture-build-result.py`, `session-activity.py`, `loop-budget.py`, `editorial-lint.py` (common); `push-nudge.py` (review-gate) |
| `UserPromptSubmit` | When the user submits a prompt. Hook can observe; can inject system reminders. | `session-log.py`, `session-subject.py`, `session-mode.py`, `session-routine-guard.py`, `report-style-lint.py`, `feedback-nudge.py` (common) |
| `SessionStart` | Session boot. Hook can inject context. | `session-registry.py` (common) — registry hygiene + transparent handoff resume |
| `SessionEnd` | Session teardown. | `session-registry.py` (common) — WIP-autosave + deregister |
| `Stop` | After the main agent finishes a turn. | `session-checkpoint.py`, `report-style-lint.py`, `no-background-build.py` (common) |

`Monitor` (a CC tool name, used to poll a `run_in_background` job) is a
**matcher**, not a separate event; it shows up as a `PreToolUse` matcher on
`no-background-build.py`, which also matches `Bash`. Listed here because the
matcher table above used to omit it entirely.

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

### path-lock.py × 6 (PreToolUse, matcher `Edit\|Write\|MultiEdit\|NotebookEdit`)

Owners: `build-team/hooks/`, `build-hex/hooks/`, `discovery/hooks/`,
`design/hooks/`, `docs-topology/hooks/`, `marketing/hooks/`. (`build-solo` and
`maestro` ship no path-lock: `build-solo` is deliberately hookless,
`maestro` has no agents of its own to lock.)

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

### bash-path-lock.py × 6 (PreToolUse, matcher `Bash`)

Owners: same six topologies as `path-lock.py`.

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
   install, dd of=, `git mv`, truncate. Indecidable constructs (python -c,
   heredoc-to-interpreter, ...) → fail open, but logged to
   BASH_PATHLOCK_COVERAGE_LOG.
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

Hard gate against advancement commands (`git commit`/`push`, `gh pr
create/merge`, deploys) when `.claude/last-build.json` is unsafe. Two
tiers: LOCAL (`git commit`, recoverable, fails open on a missing
baseline with a loud warning) and SHARING (push/PR/deploy,
unrecoverable, fails closed on a missing baseline), plus a
`.claude/no-build` opt-out and a warning-only path for repos with no
recognizable build manifest. `UNKNOWN` status is treated as `FAILURE`.
This is one of three hooks (with `mark-build-stale.py` and
`capture-build-result.py`) behind the `last-build.json` state machine;
the full behavior table, states, and recovery flows live in
[`../green-or-revert.md`](../green-or-revert.md); this entry just
says where the gate sits in the hook lifecycle. Internal file format
and per-tool detection detail: [`build-state.md`](build-state.md).

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
   cargo, go-test, docker-build). If no match: exit 0 (don't classify).
4. For matched kind:
     - Extract response text from tool_response (handles dict shape
       variants: stdout/output/result/content/stderr)
     - Check for kind-specific marker: BUILD SUCCESS / BUILD SUCCESSFUL
       in success path; BUILD FAILURE / BUILD FAILED in failure path
       (docker-build uses its own text markers, no exit code to read)
     - Fallback: exit_code 0 → SUCCESS; non-zero → FAILURE
     - Ambiguous (marker missing, exit code unknown): exit 0
5. Follow a leading `cd X &&`/`cd X;` prefix (effective_build_dir) to
   find where the build actually ran; a build outside the session tree
   (e.g. a proof-reviewer throwaway worktree) is recorded in THAT
   directory's own .claude/last-build.json, never the session's.
6. Write { status: SUCCESS|FAILURE, at: now, command, kind,
   tail: last ~12 lines of response_text }
```

Pattern list is extensible — add a `(regex, kind, success_marker,
failure_marker)` tuple to `PATTERNS`. `None` markers fall back to exit
code only. Full behavior table: [`../green-or-revert.md`](../green-or-revert.md).

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

### feedback-nudge.py (UserPromptSubmit)

Owner: `common/hooks/`.

Notices when a prompt is a complaint **about the harness** and injects one line
telling the agent to record it (`common:feedback-capture` skill →
`cepa-feedback add`) before getting on with the turn's actual work.

**Logic:**

```python
1. CEPA_FEEDBACK_NUDGE=off → silent (kill switch).
2. Require BOTH regexes on the prompt:
   - QUEIXA: complaint shape ("me irrita", "para de", "não devia", ...)
   - ALVO:   a harness target (cepa|hook|gate|comando|skill|agente|
             worktree|plugin|/plugin:command|...)
   Either one alone → silent. "That vendor API is broken" is a project
   card, not harness feedback.
3. Once per session: marker file `.claude/feedback-nudge` (anchored with
   _wtlib.session_root, never the raw cwd) holds the session_id.
4. Inject additionalContext. Never blocks, never answers the complaint.
```

Why a hook and not just the skill: the same lesson this repo has catalogued
three times — a control that depends on the agent remembering is not a control.
The skill says *how* to record; the hook makes sure the moment gets noticed.
Once per session, because a line repeated every turn is how you teach an agent
to ignore it.

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
`start_commit`), prunes dead entries, **warns when the repo's plugin code isn't
what's installed** (see below), warns on same-tree overlap, auto-cleans
finished worktrees, and — via a direct branch-keyed lookup — injects the
previous session's handoff as background with a "don't announce, just continue"
rule (suppressed when a live peer shares the tree or the handoff is >48h old).
On end: WIP-autosaves a dirty `session/*` worktree and deregisters.

**The version notice (`_pluginver.py`).** The most recurring failure in this
project's history is epistemic, not technical: a fix is committed, never
installed, and everyone — owner and agent — keeps operating as if it were live.
`cepa-doctor` has always detected this, but only when someone chose to ask,
which is never the moment you suspect anything. `_pluginver.boot_notice()`
compares every repo `plugin.json` against the newest version in the cache and
returns **one line** naming what isn't live — or `None`, which is the normal
case and deliberate: a notice that fires every session trains the eye to skip
it. It is the **first** notice in the list, because a version drift contaminates
how you should read every other conclusion in that session.

`cepa-doctor` and this hook share the comparator through `_pluginver.py` rather
than each carrying a copy — the same single-source discipline the path-locks
still owe. Cache *ahead* of the repo is silent (another clone installed newer;
that's the doctor's business, not an alarm). Tests:
`tests/test_pluginver_boot.py` (17 checks; perturbation: dropping the call from
`session-registry.py` turns 2 red).

**The handoff claim (`_handoff.py`).** A handoff is resumed by one session.
Delivery records who took it, in the frontmatter (`resumed_by`) and in a
sibling `.claim` file created with `O_EXCL`, both tied to the handoff's
`updated_at`. The live-peer check compares the exact `cwd` and missed a session
opened in a subdirectory; the claim does not guess. A dead claimer's claim is
released. `tests/test_handoff_claim.py` (13 checks; perturbation: making
`holder()` return nothing turns 4 red). See [`../handoff.md`](../handoff.md).

**The memory validity sweep (`_memval.py`).** A Claude Code memory that asserts
a *state* ("not installed yet", "not run on a real repo") carries
`validade: YYYY-MM-DD` under `metadata:` in its frontmatter. Past that date the
sweep prefixes its line in `MEMORY.md` with `[VENCIDA desde D, reconfira antes
de afirmar]` and the session gets a notice naming it. The mark lands for the
*next* session (this one already loaded the index); the notice covers this one.
A memory without the field never expires, and extending the date removes the
mark. The memory directory is derived from the main clone's path, the way
Claude Code names it. By hand: `python3 common/hooks/_memval.py sweep`.
`tests/test_memoria_validade.py` (21 checks, one drives the real hook as a
subprocess; perturbation: dropping the call turns 2 red).

### session-checkpoint.py (Stop)

Owner: `common/hooks/`. Every turn, rewrites the AUTO zone of
`<main-root>/.claude/handoffs/<branch-slug>.md` with mechanical facts (commits
this session, dirs touched, last intents from `session-log.md`). Crash-proof:
the skeleton is always current, so a token-limit kill never loses the thread.
The narrative (NOTE zone) is written separately by `/common:handoff`; the two
zones are marker-delimited and never clobber each other (`_handoff.py`).

### loop-budget.py (PreToolUse + PostToolUse, matcher `Task`)

Owner: `common/hooks/`.

Separates **iterating** (each round carries new information) from **repeating**
(the same round, the same red). `engineering-lead` is told to "iterate until
APPROVED" and `till-done` says not to stop early; neither has a ceiling, so a
card whose failure the worker can't see can burn a whole session cycling
dev→qa→dev.

The signal that the loop started is available without guessing: **the failure is
the same**. The fingerprint comes from the delegation's *result*, not its prompt
— the prompt changes every round (it carries the feedback), the failure doesn't.

```python
PostToolUse: extract a failure signature from the result → count it in
             .claude/loop-state.json. Volatile noise (timestamps, durations,
             SHAs, /tmp paths) is normalized away first, or the same failure
             would look new every round and the ceiling would never fire.
             A SUCCESS in last-build.json clears the table.
PreToolUse:  any signature at CEPA_LOOP_LIMIT (default 3) → exit 2, naming the
             repeated failure and the three ways out (diagnose / go green /
             declare BLOCKED with the diagnosis).
```

The counter lives outside the agent's reach for the same reason as
`last-build.json`: whoever is being judged doesn't write the number that judges
them. A signature absent for 6 delegations is forgotten (a red already fixed
must not keep counting). Turning it off is an explicit decision
(`CEPA_LOOP_BUDGET=off`), never an accident — same discipline as the
`.claude/no-build` marker.

`loop-state.json` is in `_wtlib.RESCUE_SKIP`: it describes the session that
produced it, so carrying it into another tree would block a delegation over
someone else's red.

Tests: `tests/test_loop_budget.py` (16 checks). Half of them exist to prove it
does **not** bite legitimate iteration — alternating failures, a green build, a
clean run: all pass. A ceiling that bites real work gets switched off on day
one, and then protects nothing.

### lead-no-worktree.py (PreToolUse, matcher `Task`)

Owner: `common/hooks/`. Blocks spawning a lead agent with worktree isolation —
leads are write-locked out of the workers' lanes, so isolating them is a
mistake. Exit 2 with a re-issue suggestion.

### acceptance-gate.py (PreToolUse, matchers `Bash` and `mcp__.*(transitionJiraIssue|jira_transition_issue)`)

Owner: `common/hooks/`. Blocks the In-Review transition while the per-card
acceptance audit (`.claude/acceptance/<KEY>.yaml`, written by
`completion-auditor`) is absent or incomplete. Also matches `Bash`: the
`twg` CLI transitions a card the same way the MCP tool does, and used to slip
past this gate uncaught because it never showed up as an `mcp__...` call. See
[`../acceptance-completeness.md`](../acceptance-completeness.md).

### no-busy-wait.py (PreToolUse, matcher `Bash`)

Owner: `common/hooks/`. Blocks active-waiting Bash (`sleep`-in-a-loop,
polling a marker file, `wait` on a backgrounded PID), measured as the
single biggest wall-clock cost in the harness's own transcripts
(2026-08-26 measurement). Steers the agent toward `run_in_background` +
being re-invoked on completion instead of burning a turn in a spin-loop.

### no-background-build.py (PreToolUse, matchers `Bash` and `Monitor`; also `Stop`)

Owner: `common/hooks/`. Scoped to `cepa-until` runs only (`CEPA_UNTIL_RUN`
env var set; outside that mode, backgrounding a build is the right move
and the hook is a no-op). Under `claude -p` (what `cepa-until` uses per
queue item), there is no next turn to be woken up by a background job's
completion notification: a build sent to the background is never
collected, the item rots `in_progress`, and the next window finds an
orphaned reservation. Blocks a build/test command from backgrounding via
either `run_in_background: true` or shell-level detachment (trailing `&`,
`nohup`, `disown`, `setsid`) outside quotes, and blocks polling it back via
the `Monitor` tool. The `Stop` registration catches a session that ends
mid-build.

Exception since 2026-09-27: a build that declares its own end
(`...; echo EXIT=$? >> <file>`) may go to the background, because a build
longer than 10 minutes has no foreground option (the Bash tool moves it to
the background anyway). The turn must then wait for that file in the
foreground with a loop that exits on its own before the 10-minute cap
(`for i in $(seq 27); do grep -q EXIT= <file> && break; sleep 20; done
# espera-ok`), repeated until `EXIT=` shows up (a full 10-minute wait is
itself moved to the background), and `Stop` is blocked while the file
lacks `EXIT=`. Measured the same day
on claude 2.1.283: `claude -p` kills background tasks when the turn ends
whatever `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` says (0, unset or 120000),
and an armed `Monitor` does not keep the turn alive.

### reforma-gate.py (PreToolUse, matchers `Bash` and `Edit\|Write\|MultiEdit\|NotebookEdit`)

Owner: `common/hooks/`. Blocks editing an EXTERNAL test while the
"Reforma" work mode is active (`docs/modos-de-trabalho.md`). Reforma's exit
condition has three parts (declared budget exhausted, build green, no
external test edited), and the third is the only one this hook can check
mechanically, so it's the one enforced.

### modo-escrita-gate.py (PreToolUse, matchers `Bash` and `Edit\|Write\|MultiEdit\|NotebookEdit`)

Owner: `common/hooks/`. Each session mode (set via `session-mode.py`) only
writes what it PRODUCES: a mode announced in prose was routinely ignored
under pressure; this closes that gap mechanically instead of re-teaching it
every session.

### merge-truth-gate.py (PreToolUse, matchers `Bash` and `mcp__.*(transitionJiraIssue|jira_transition_issue)`)

Owner: `common/hooks/`. Blocks a card's forward transition while its code
sits unmerged. The Implementation Summary is written the moment the work
is done, necessarily before the merge exists, so it says "pending merge"
and nobody revisits it; a 2026-08-01 board review found six cards closed
this way. Recomputes merge state instead of trusting the comment.

### summary-nulls-gate.py (PreToolUse, matcher `mcp__.*(addCommentToJiraIssue|jira_add_comment)`)

Owner: `common/hooks/`. Blocks posting an Implementation Summary that
omits the explicit-null fields ("new debt introduced: none", "release
needed: no") instead of stating them outright: the structural teeth of
the "explicit nulls" discipline (imported from the Ariad method).

### bounce-reason-gate.py (PreToolUse, matcher `mcp__.*(addCommentToJiraIssue|jira_add_comment)`)

Owner: `common/hooks/`. Sibling of `summary-nulls-gate.py`, one seam
later: blocks bouncing a card back from Review without a structured
reason, so the next session doesn't have to re-derive WHY from the diff.

### bitbucket-decision-lock.py (PreToolUse, matcher `Bash`)

Owner: `common/hooks/`. Only `bitbucket-expert` decides a pull request's
fate (approve, merge, decline, request changes); this hook is the same
"one decider" invariant `review-gate` enforces, applied to Bitbucket
instead of a direct `git push`/merge.

### jira-write-lock.py (PreToolUse, matcher `Bash`)

Owner: `common/hooks/`. Only `board-flow:atlassian-expert` writes to Jira
via the `twg` CLI. Via MCP the "one agent writes Jira" rule holds through
the `tools:` frontmatter allowlist (only `atlassian-expert` has the
write-scoped Jira MCP tools); the CLI path has no such allowlist, so this
hook is the CLI's equivalent gate.

### jira-create-fields-gate.py (PreToolUse, matcher `Bash` and `mcp__.*(createJiraIssue|jira_create_issue|jira_batch_create_issues)`)

Owner: `common/hooks/`. A new Jira card must carry the `required_fields`
declared in the project's `board-flow.yaml` (e.g. Team, Módulo do
sistema); Jira itself doesn't enforce a per-project required-field list,
so this hook does.

### handoff-seeds-gate.py (PreToolUse, matcher `Edit\|Write\|MultiEdit\|NotebookEdit`)

Owner: `common/hooks/`. Blocks writing a discovery handoff that omits the
forward-carrying fields (validation seeds, etc.), the fields exploration
routinely drops at the seam into delivery.

### decision-altitude-gate.py (PreToolUse, matcher `Edit\|Write\|MultiEdit\|NotebookEdit`)

Owner: `common/hooks/`. Blocks a `### Decision:` block whose `**Altitude:**`
field isn't one of `strategic` / `tactical` / `implementation`, the field
that routes the decision to the right reviewer at `/common:debrief` time
(owner for strategic, lead for tactical, `--all`-only for implementation).

### spec-readiness-gate.py (PreToolUse, matcher `Edit\|Write\|MultiEdit\|NotebookEdit`)

Owner: `common/hooks/`. Blocks a specification declaring itself
build-ready (`Status: ready`) while some success criterion still has no
surface + red test: the failure mode is the `/common:spec` interrogation
ending from agent fatigue rather than actual readiness.

### ui-proof-verdict-guard.py (PreToolUse, matcher `Write`)

Owner: `common/hooks/`. Sibling of `build-hex/hooks/proof-verdict-guard.py`,
one altitude up: parses the `ui-proof-reviewer`'s `flows` schema (written
to `docs/proof/ui-<slug>.yaml`) and blocks a declared `verdict: proven`
that the recorded flow statuses don't support.

### reflexao-gate.py (PreToolUse, matcher `Write`)

Owner: `common/hooks/`. Integrity gate for the "Reflexão" report, sibling
of `ui-proof-verdict-guard.py`: the verdict is a value recalculated from
the report's own content, not an opinion the agent writes, and is blocked
when it doesn't match. Reflexão's exit condition is "no finding without a
destination," checked mechanically here.

### editorial-lint.py (PostToolUse, matcher `Edit\|Write\|MultiEdit`)

Owner: `common/hooks/`. Opt-in per-project lint for pt-BR editorial style
(zero em dash, not sounding LinkedIn-ish, niche-specific hashtags), rules
that were being re-taught every session and still getting violated.

### session-mode.py (UserPromptSubmit)

Owner: `common/hooks/`. Injects the active work mode (set via `cepa
--modo <x>`, stored in `.claude/session-mode`) into context every turn:
a session-long STATE, distinct from a routine (a task that ends). Full
design: `docs/modos-de-trabalho.md`.

### session-routine-guard.py (UserPromptSubmit)

Owner: `common/hooks/`. Refuses, at the start, a conversational routine
handed to `/common:session`. That command's own rule is "no questions
between launch and report," and a routine that isn't ready to run
straight through breaks it.

### report-style-lint.py (UserPromptSubmit and Stop)

Owner: `common/hooks/`. Measures the turn's final report against the
`plain-report` skill's format (2 plain-language sentences, explicit
default recommendation, technical detail last), added after the user
reported having to read reports more than once to understand them.

### proof-verdict-guard.py (PreToolUse, matcher `Edit\|Write\|MultiEdit\|NotebookEdit`)

Owner: `build-hex/hooks/`. Reads the `.claude/proof/<KEY>.yaml` /
`docs/proof/<KEY>.yaml` the `proof-reviewer` is about to write, recomputes
the verdict mechanically from the level statuses, and blocks the write
when a declared `verdict: proven` contradicts a level marked `skipped` /
`assumed` / `survived` / `gap` (or an `l4_adversarial_input` with
findings), the same integrity gap `ui-proof-verdict-guard.py` closes for
UI proofs, one topology down.

### no-direct-main.py (PreToolUse, matcher `Bash`)

Owner: `review-gate/hooks/`. THE FENCE: blocks a direct `git merge` /
`git push` to the protected branch in a repo that opted into `review-gate`
(a `review-gate.yaml` at root), redirecting to the PR flow
(`/review-gate:open`, `/review-gate:merge`) instead. Silent (self-scoped
exit 0) in repos without that config.

### push-nudge.py (PostToolUse, matcher `Bash`)

Owner: `review-gate/hooks/`. THE NUDGE, never a block: after a feature-branch
push, suggests `/review-gate:open` ("lexical proposes, model disposes,"
same discretion pattern as `session-subject.py`).

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

`docs-topology/hooks/path-lock.py` has the equivalent
`DOCS_PATHLOCK_DEBUG` (log at `/tmp/docs-pathlock-debug.log` by default,
overridable via `DOCS_PATHLOCK_DEBUG_LOG`). `build-team`, `discovery`,
`design`, and `marketing` ship no debug env var today; if you need one
there, mirror `HEX_PATHLOCK_DEBUG`'s pattern rather than inventing a new
shape.

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
