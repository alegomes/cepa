# Hook replay corpus

Zero-token way to answer "did this hook change make it deny more, deny less, or
let through something it should not?". A hand-written corpus of hook payloads is
replayed against the hooks in the working tree and against the same hooks at
any git ref, and a table compares the decisions.

## Run

    python3 tests/replay/run.py                       # working tree only
    python3 tests/replay/run.py --ref HEAD~1 --ref v1 # also compare against refs
    python3 tests/replay/run.py --hook gate-advance --json
    python3 tests/replay/run.py --repo /path/to/scratch --ref HEAD~1

Columns: calls, denials, redundant (denials marked `redundant`), holes (calls
marked `must_deny` that were allowed), mismatch (decision differs from `expect`),
tokens (estimated: denial stderr characters / 4, so a rough size, not a count),
ms (mean latency per call, includes Python start-up). Below the table: the calls
whose decision differs from the working tree.

Every hook subprocess gets `CEPA_TELEMETRY_DIR` pointed at a temp dir, so replays
never touch `~/.claude/cepa-telemetry`. The runner exits 0 even when there are
mismatches; it is a measuring instrument. `tests/test_hook_replay.py` is the
guard that fails when a decision differs from its label.

## Corpus

`tests/replay/<hook-id>/*.json`, one scenario per file:

    {
      "hook": "common/hooks/gate-advance.py",   // repo-relative hook path
      "description": "...",
      "setup": {"git": true, "files": {"rel/path": "content"}},
      "env": {"NAME": "value"},                 // extra env for the hook
      "calls": [
        {"name": "push-on-red",
         "payload": {"tool_name": "Bash", "tool_input": {"command": "..."}, "cwd": "{root}"},
         "expect": "deny",                      // "deny" (exit 2) or "allow" (exit 0)
         "redundant": false,                    // denial repeating an earlier one
         "must_deny": true,                     // allowing it would be a safety hole
         "note": "..."}
      ]
    }

- `{root}` in any string of `payload`, `env` or `setup` becomes the scenario's
  temp project directory (named `demo`).
- `setup.git: true` runs `git init` and commits all fixture files.
- Each scenario runs in a fresh temp dir; calls run in order and may share state.
- `redundant` and `must_deny` only make sense on `expect: "deny"` calls.

## Adding a hook

1. Create `tests/replay/<hook-id>/` with at least one scenario: both deny and
   allow calls, one `redundant`, one `must_deny`.
2. If the hook lives outside `common/hooks` or `build-hex/hooks`, add its
   directory to `HOOK_DIRS` in `run.py` so refs materialize it (hooks import
   siblings).
3. Run `python3 tests/test_hook_replay.py`.

## Rule R3: hand-written only

Scenarios are written by hand with neutral names (`demo`, `domain/src/main/java/Foo.java`).
Never paste a recorded session, transcript content, client names or real paths:
the repository is public. The test fails on `/Users/` and `.claude/projects` paths.

Note: denial messages that quote a baseline age ("12 day(s) ago") make the token
estimate drift by a few tokens from day to day; compare versions in one run.
