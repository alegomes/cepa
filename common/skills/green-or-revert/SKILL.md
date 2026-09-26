---
name: green-or-revert
description: Use whenever you are about to make a claim about runtime state — "build is green", "tests pass", "the fix works", "this is ready to commit / push / merge", "está funcionando" — or whenever you've just finished a chunk of code edits. The harness's job is to take safe steps, not to be asked whether each step was safe. Consult `.claude/last-build.json` before any such claim and treat its status as authoritative.
---

# green-or-revert

The harness must always be in a known-good state, or moving toward one. After every meaningful code change, verification is the next action — not a question to ask the user, not an inference from "the file didn't change," not a guess from prior context.

## Authoritative state file: `.claude/last-build.json`

Maintained by two hooks out of your control:

- `mark-build-stale.py` writes `status: STALE` after every `Edit` / `Write` / `MultiEdit` on production code (source files, build manifests, migrations). Records the edited path + previous known-good status.
- `capture-build-result.py` writes `status: SUCCESS`, `status: FAILURE` or `status: EMPTY` (filtered run, zero tests executed) after every `Bash` invocation of a recognized build/test command (Maven, Gradle, npm, yarn, pytest, cargo, go test). Records the command + tail of output.

You **cannot** write this file. The orchestrator does not own its content. The file reflects reality, not optimism.

Possible states:

| `status` | Meaning | Your reaction |
|---|---|---|
| `SUCCESS` (recent) | Last verify ran green, no edits since. | Safe to claim "green". Safe to commit / push / advance. |
| `STALE` | Source edited since last verify. | **Run verify now.** Then re-check the file. Do not claim green. Do not commit / push / advance — the `gate-advance` hook blocks those anyway. |
| `FAILURE` | Last verify failed. | **Fix or revert before any other action.** Read the `tail` field for the failure surface. If the fix is small, fix and re-verify. If you don't immediately see the cause, `git checkout -- <files>` to revert the failing edit, then re-verify, then approach the problem fresh. |
| `EMPTY` | A **filtered** test run (`-Dtest=`, `pytest -k`, `go test -run`, jest `-t`) exited green but executed **zero** tests — usually a mistyped test name. | **Not green.** Fix the name in the filter and re-run, or make the build fail on it (Maven: `-Dsurefire.failIfNoSpecifiedTests=true`). Never cite it as "the test passed". |
| Missing | No verify recorded yet this session. | Run verify to establish a baseline. Don't claim anything before the first verify lands. |

Staleness has no expiry timer — `STALE` set by an edit stays `STALE` until a `SUCCESS` build lands. "I ran verify five minutes ago" doesn't matter if you edited something after. The hook will have already moved the file to `STALE`.

## Rules

### 1. Verify is the next action after meaningful edits.

When you finish a logical change (a fix, a refactor section, a feature increment), running the project's verify command is the next step — before reporting back, before claiming "done", before delegating to the next stage. Don't wait to be asked. Don't say "should I run the tests?" — run them.

The scope matters: a domain-only change verifies with `./mvnw -pl domain,application -am verify`; a fix that crosses adapter + api-rest needs `bootstrap` to confirm wiring. When in doubt, run the broader scope.

### 2. Never claim runtime state without consulting `last-build.json`.

Claims that require evidence include but aren't limited to:

- "Test is green" / "tests pass" / "build is green"
- "Fix is in place" / "fix landed" / "regression is closed"
- "Safe to commit / push / merge"
- "It's working" / "está funcionando" / "deploy-ready"

For each, the answer's truth is in `.claude/last-build.json`, not in your memory of what you did. **Read the file** before answering. If it says `STALE` or `FAILURE`, the honest answer is the file's actual status — followed by the recovery action (verify or revert).

### 3. "No diff against HEAD" is NOT evidence of correctness.

It's evidence of the absence of recent edits. Tests can be red for reasons that don't show up in `git diff` — dependency drift, environment changes, schema/seed updates, race conditions in CI vs local. "I committed the fix earlier" is not a substitute for "I just ran verify."

### 4. On `FAILURE`, fix or revert. Don't proceed.

Failure is not a state to work around. Two valid responses:

- **Fix forward**: if the failure is small and well-understood, apply the fix, re-run verify. Repeat until green.
- **Revert**: if you don't immediately see the cause, `git checkout -- <changed files>` (or `git stash`) and start the change over with a clearer plan. Better to redo a small chunk than to compound mystery failures.

What you do NOT do: continue editing other files while the build is red. Each new edit adds a confound to the failure surface and makes the eventual diagnosis harder.

### 5. Commit / push / advance is gated.

The `gate-advance.py` PreToolUse hook refuses Bash commands matching `git commit`, `git push`, `gh pr create`, `kubectl apply`, etc. when `last-build.json` is `STALE`, `FAILURE` or `EMPTY`. This is structural — you literally cannot proceed without green. The block message names the suggested recovery.

Don't try to work around the gate (e.g., by editing the state file directly). The fix is to re-establish green, not to fake it.

### 6. If the user asks "is X working?" — verify before answering.

The skill's whole point is that the user shouldn't have to ask. But when they do, the answer is not "I think so" or "the file didn't change so probably yes." The answer is:

- If `last-build.json` is `SUCCESS` and the timestamp predates the question: "Last verify (`<command>` at `<time>`) passed: `<tail>`. No edits since, so still green."
- If `STALE`: "Build is STALE since edit to `<path>` at `<time>`. Running verify now." Then run it.
- If `FAILURE`: "Build is FAILURE since `<time>`: `<command>`. Tail: `<tail>`. Fixing now." Then start the fix or revert.

Never answer the question optimistically when the state file disagrees.

## What the harness protects against

This skill exists because, without it, the failure mode is consistent: model says "test is green / fix is in place" → user trusts the claim → ships → discovers the test was never run or never passed → debugs from a false premise → wastes hours. The hooks + skill make that path structurally hard.

It does not protect against: build tool bugs, flaky tests, environment differences between local and CI. Those require their own fixes. But it does eliminate the simplest, most-common failure: the agent claiming green without proof.
