# green-or-revert

A structural safeguard against the "I think the test passes" failure
mode. The agent doesn't get to claim runtime correctness without proof,
and you can't commit / push / deploy while the build is broken.

## Why this exists

A common failure path:

1. Agent edits source code.
2. User asks "is it working?" (or the agent volunteers "fix is in place").
3. Agent looks at `git diff`, doesn't see changes, concludes the fix
   already landed.
4. User trusts the claim.
5. CI breaks. Hours wasted debugging from a false premise.

`git diff` empty against HEAD says nothing about runtime correctness.
It says no edits since the last commit. Tests can be red for reasons
that don't show up in diffs — dependency drift, schema changes, race
conditions, environment differences.

The skill + hooks below make this failure structurally hard.

## The state file: `.claude/last-build.json`

The authoritative record of build/test state. **The orchestrator does
not own the writes** — two hooks maintain it. It lives at the root of the
session's worktree (`session_root`), not in the Bash tool's current
directory: the cwd persists between Bash calls, so a `cd subdir` would
otherwise move the state into `subdir/.claude/` for the rest of the session.

Shape after a successful build:

```json
{
  "status": "SUCCESS",
  "at": "2026-05-13T09:22:34Z",
  "command": "./mvnw -pl bootstrap -am verify",
  "kind": "maven",
  "tail": "[INFO] BUILD SUCCESS\n[INFO] Total time: 4:15 min\n..."
}
```

Shape after a source edit invalidates a prior SUCCESS:

```json
{
  "status": "STALE",
  "since": "2026-05-13T09:30:12Z",
  "after_edit_to": "domain/src/main/java/.../X.java",
  "last_known_status": "SUCCESS",
  "last_known_at": "2026-05-13T09:22:34Z",
  "last_known_command": "./mvnw -pl bootstrap -am verify"
}
```

Shape after a failed build:

```json
{
  "status": "FAILURE",
  "at": "2026-05-13T09:35:01Z",
  "command": "./mvnw verify",
  "kind": "maven",
  "tail": "[ERROR] BUILD FAILURE\n[ERROR] tests run: 151, failures: 1..."
}
```

## State machine

```
                                edit source / build manifest / migration
                              ┌────────────────────────────────────────┐
                              │                                        │
                              │                                        ▼
   missing ──────────────► SUCCESS ◄────── verify passes ──────── STALE
   (no baseline)          ▲    │                                        ▲
                          │    │ verify fails                          │
                          │    ▼                                       │
                          └── FAILURE ────────── edit ──────────────────┘
```

| Status | Meaning | What you do |
|---|---|---|
| `SUCCESS` (recent) | Last verify ran green, no edits since. | Safe to claim "green". Safe to commit / push / advance. |
| `STALE` | Source edited since last verify. | Run verify now. Don't claim green. Don't commit / push — the gate blocks anyway. |
| `FAILURE` | Last verify failed. | Fix or revert before any other action. Read `tail` for the failure surface. |
| missing | No verify recorded yet this session. | Establish a baseline: run verify. Don't claim anything beforehand. |

Staleness has no timer — `STALE` set by an edit stays `STALE` until a
`SUCCESS` build lands. "I ran verify five minutes ago" doesn't help if
you edited something after.

## The three hooks

### `mark-build-stale.py` (PostToolUse, matches `Edit|Write|MultiEdit`)

Fires after every code edit. Marks `last-build.json` as `STALE` if the
edited path is "production code". Path classification:

| Marks STALE | Doesn't mark STALE |
|---|---|
| `.java`, `.kt`, `.ts`, `.tsx`, `.js`, `.py`, `.go`, `.rs`, `.rb`, `.cs`, `.cpp`, `.h`, etc. | `.md`, `.rst`, `.txt` |
| `pom.xml`, `build.gradle`, `package.json`, `Cargo.toml`, `go.mod`, `requirements.txt` | `docs/**`, `spec/**`, `specs/**` |
| `.sql` (migrations affect runtime) | `*/src/test/**` (changing tests extends coverage, doesn't invalidate production code state) |
| | `.claude/**` (plumbing) |

Out-of-band: the orchestrator does not own this write.

### `capture-build-result.py` (PostToolUse, matches `Bash`)

Fires after every Bash invocation. Recognizes common build/test
commands. Claude Code's Bash result omits the exit code when a command
succeeds, so a green run can only be recognized by text in the output.
Failure markers are checked first; when no marker matches, the hook falls
back to the exit code, which is present on failures only.

| Pattern | Kind | Detected via |
|---|---|---|
| `./mvnw verify`, `./mvnw test`, `mvn ...` | `maven` | `BUILD SUCCESS` / `BUILD FAILURE` in output |
| `./gradlew test`, `gradle ...` | `gradle` | `BUILD SUCCESSFUL` / `BUILD FAILED` |
| `npm test`, `npm run build` | `npm` | text markers: success `Compiled successfully`, `built in`, `build completed`, `Done in `; failure `npm error`, `npm ERR!`, `ELIFECYCLE`, `Failed to compile`, `error TS`, etc. Exit code as fallback. |
| `yarn test`, `pnpm test`, `yarn build` | `yarn` | same text markers as `npm` |
| `docker build`, `docker buildx build` | `docker-build` | text markers: success `writing image`, `naming to`, `Successfully built`; failure `failed to solve`, `executor failed`, `returned a non-zero code` |
| `pytest` | `pytest` | exit code only (no markers): a failure is recorded, a green run is not |
| `cargo test`, `cargo build` | `cargo` | exit code only, same limit |
| `go test` | `go-test` | exit code only, same limit |

Other commands are skipped (better to leave stale than misclassify).
Records the command, kind, and last ~12 lines of output.

The hook follows a leading `cd X &&` (or `cd X;`) prefix to find where the
build actually ran. A build inside the session tree, including
`cd subdir && ...` in a monorepo, is recorded at the session root. A build
outside it (for example a proof reviewer's throwaway worktree under `/tmp`)
is recorded in that directory's own `.claude/last-build.json`, so a
deliberate RED there never touches this session's baseline.

### `gate-advance.py` (PreToolUse, matches `Bash`)

Hard gate. Refuses Bash commands that signal "I'm done, push it out"
when `last-build.json` is `STALE` or `FAILURE`. Gated commands split
into two tiers based on recoverability:

**Local tier** (recoverable via `git reset`):
- `git commit`

**Sharing tier** (broadcasts to others / deploys; unrecoverable):
- `git push`
- `gh pr create`, `gh pr merge`, `gh release`
- `kubectl apply`, `terraform apply`, `docker push`
- `aws|gcloud|az` with `deploy` or `push`

Exempted (won't be blocked even when state is STALE/FAILURE — these are
the recovery path):

- `./mvnw`, `gradle`, `npm`, `yarn`, `pnpm`, `pytest`, `cargo test`,
  `go test`
- Read-only `git`: `status`, `log`, `diff`, `show`, `stash`, `checkout`,
  `restore`, `reset`, `add`, `rm`, `mv`, `fetch`, `pull`, `merge`,
  `rebase`, `branch`, `tag`, `worktree`, `config`, `remote`

When the command mixes exempt + gated portions (e.g., `git add foo
&& git commit -m bar`), the gated portion still applies; the strictest
tier wins (sharing > local > exempt).

### Behavior by tier and state

| `last-build.json` state | local tier (`git commit`) | sharing tier (`push` / PR / deploy) |
|---|---|---|
| `SUCCESS` | ALLOW | ALLOW |
| `STALE` | BLOCK | BLOCK |
| `FAILURE` | BLOCK | BLOCK |
| missing (no baseline yet) | **ALLOW** with loud stderr warning | **BLOCK** with clear message |
| missing, and no build manifest at the root | **ALLOW** with loud stderr warning | **ALLOW** with warning asking for `.claude/no-build` |
| any state, but `.claude/no-build` present | **ALLOW** | **ALLOW** |

The asymmetry on "missing baseline" is intentional:

- A bad local commit is cheap to undo (`git reset`); blocking it just
  to force `./mvnw verify` would add friction to greenfield projects
  and to projects whose build tool isn't recognized by
  `capture-build-result.py`. So we ALLOW with a warning loud enough
  that nobody can miss it (boxed ⚠ banner in stderr).
- A bad `git push` / `gh pr create` / `kubectl apply` crosses out of
  your machine — unrecoverable. Forcing a baseline before that is
  worth the friction.

This split (H1 + H2 in the design discussion) replaces the older
behavior of fail-open-with-stderr-warning for both tiers. The old
behavior let unverified commits ship silently because nobody reads
plain stderr lines mid-session.

**The `.claude/no-build` opt-out.** For a repo that has no build to verify —
docs-only, content, config — a baseline can never exist, so the sharing tier
would block `push` forever. Create `.claude/no-build` (commit it to apply for
the team) and the gate allows both tiers: there is nothing to verify, so it
does not apply. This is an **explicit, human-placed** marker. Without it, the gate has one
narrow fallback: when there is no baseline *and* no recognizable build
manifest at the root (`pom.xml`, `mvnw`, `gradlew`, `package.json`,
`pyproject.toml`, `Cargo.toml`, `go.mod`, `Makefile` and a few more), it
allows the sharing tier with a warning that asks for the marker instead of
blocking. A project that has a manifest but hasn't run verify yet stays
blocked. Faking `last-build.json` with a
`SUCCESS` you never ran is the dishonest alternative this exists to replace.

When the gate fires, the block message names:

- The current status (`STALE` or `FAILURE`).
- The path that triggered STALE (or the failing command for FAILURE).
- The suggested recovery (run verify; fix or revert).
- The state file path.

## The skill: `green-or-revert`

Codifies the rule for the agent to read. Activates whenever the agent
is about to make a claim about runtime state — "test is green", "fix
is in place", "build succeeded", "it's working", "está funcionando" —
or after a meaningful code change.

Key rules:

1. **Verify is the next action after meaningful edits**, before
   reporting back or claiming done. Don't wait to be asked.
2. **Never claim runtime state without consulting `last-build.json`.**
   Read the file before answering.
3. **"No diff against HEAD" is NOT evidence of correctness.**
4. **On FAILURE, fix or revert.** Don't proceed with broken state. The
   gate enforces this for commits/pushes; the skill teaches it for the
   broader workflow.
5. **Commit / push / advance is gated.** The agent can't work around
   the gate by editing the state file directly — the recovery is to
   re-establish green, not to fake it.
6. **If the user asks "is X working?"** — verify before answering,
   don't guess.

## When you'll see the gate fire

```
$ git commit -m "fix WEGO-1234"
[gate-advance] BLOCKED: cannot run advancement command — build is STALE
since edit to domain/src/main/java/.../X.java at 2026-05-13T09:30:12Z.
  Command: git commit -m "fix WEGO-1234"
  Suggestion: Run your project's verify command (e.g. `./mvnw <scope>
  verify`) before this operation. The hook will clear STALE on a green
  run.
  State file: /path/to/project/.claude/last-build.json
  Override by re-establishing green build, not by editing the state file.
```

Recovery:

```
$ ./mvnw -pl bootstrap -am verify
# ... runs ...
# BUILD SUCCESS  ← capture-build-result.py writes status: SUCCESS

$ git commit -m "fix WEGO-1234"
# Allowed — gate passes.
```

If verify FAILED:

```
$ ./mvnw -pl bootstrap -am verify
# ... runs ...
# BUILD FAILURE  ← last-build.json gets status: FAILURE

$ git commit -m "fix WEGO-1234"
[gate-advance] BLOCKED: build is FAILURE since 2026-05-13T09:36:00Z
(command: ./mvnw -pl bootstrap -am verify)
  Suggestion: Fix the failing tests / build errors, re-run the verify
  command, and try again. Don't proceed with broken state.
```

Either fix the failure and re-verify, or revert the offending edit:

```
$ git checkout -- domain/src/main/java/.../X.java
# Note: this doesn't clear FAILURE — only a fresh SUCCESS run does.
$ ./mvnw -pl bootstrap -am verify
# BUILD SUCCESS → last-build.json: SUCCESS → gate clears.
```

## What this doesn't protect against

- **Build tool bugs.** If `./mvnw verify` falsely reports BUILD SUCCESS
  when tests are actually broken, the hook trusts the marker.
- **Flaky tests.** A test that intermittently passes will sometimes
  show SUCCESS and sometimes FAILURE; the gate reflects whatever the
  last run showed.
- **Environment drift between local and CI.** If local builds green
  but CI breaks, the hook can't catch that.
- **Untested code paths.** SUCCESS means the tests you have pass — not
  that they cover the right cases. That's `qa-engineer`'s job (and
  `code-reviewer`'s).

The gate eliminates the simplest, most-common failure: agent claiming
green without proof. Everything else is still on the team.

## Disabling temporarily

Don't. The recovery path is to re-establish green, not to silence the
gate. If you genuinely need to bypass (one-off rescue commit on a
known-broken state), edit the state file by hand — but the skill will
flag that you cheated.

In a real emergency where you must push broken state intentionally:

```sh
echo '{"status": "SUCCESS", "at": "<now>", "command": "<override>", "kind": "manual", "tail": "manually overridden"}' \
  > .claude/last-build.json
```

But really — fix the build instead.
