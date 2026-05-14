# Build-state machine

The `.claude/last-build.json` state file and the three hooks that
maintain it. For user-facing usage docs see
[`../green-or-revert.md`](../green-or-revert.md); this page is for
extending or debugging the state machine itself.

## States

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

Four states; transitions all triggered by hooks (orchestrator never
writes the file directly):

| From | Trigger | To | Hook |
|---|---|---|---|
| (missing) | Edit on source path | `STALE` (with `last_known_status: UNKNOWN`) | `mark-build-stale` |
| (missing) | `mvnw verify` returns BUILD SUCCESS | `SUCCESS` | `capture-build-result` |
| (missing) | `mvnw verify` returns BUILD FAILURE | `FAILURE` | `capture-build-result` |
| `SUCCESS` | Edit on source path | `STALE` | `mark-build-stale` |
| `SUCCESS` | `mvnw verify` returns BUILD SUCCESS | `SUCCESS` (refresh timestamp) | `capture-build-result` |
| `SUCCESS` | `mvnw verify` returns BUILD FAILURE | `FAILURE` | `capture-build-result` |
| `STALE` | Edit on source path | `STALE` (newer timestamp, new `after_edit_to`) | `mark-build-stale` |
| `STALE` | `mvnw verify` returns BUILD SUCCESS | `SUCCESS` | `capture-build-result` |
| `STALE` | `mvnw verify` returns BUILD FAILURE | `FAILURE` | `capture-build-result` |
| `FAILURE` | Edit on source path | `STALE` | `mark-build-stale` |
| `FAILURE` | `mvnw verify` returns BUILD SUCCESS | `SUCCESS` | `capture-build-result` |
| `FAILURE` | `mvnw verify` returns BUILD FAILURE | `FAILURE` (refresh timestamp) | `capture-build-result` |

Note: editing while FAILURE returns to STALE, not directly to a fixed
state. The fix is unproven until a new verify lands.

## Schema

### SUCCESS

```json
{
  "status": "SUCCESS",
  "at": "2026-05-13T09:22:34Z",
  "command": "./mvnw -pl bootstrap -am verify",
  "kind": "maven",
  "tail": "[INFO] BUILD SUCCESS\n[INFO] Total time: 4:15 min\n..."
}
```

| Field | Source |
|---|---|
| `status` | Always `SUCCESS` |
| `at` | UTC ISO-8601, second precision, written by `capture-build-result` at hook time |
| `command` | First 200 chars of the Bash command that triggered |
| `kind` | One of: `maven`, `gradle`, `npm`, `yarn`, `pytest`, `cargo`, `go-test` |
| `tail` | Last ~12 lines of the response text |

### FAILURE

Same shape as SUCCESS, with `status: FAILURE`. `tail` will include the
failure surface.

### STALE

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

| Field | Source |
|---|---|
| `status` | Always `STALE` |
| `since` | UTC ISO-8601 of the edit that triggered |
| `after_edit_to` | Project-relative path that was edited |
| `last_known_status` | The status of the previous record (SUCCESS / FAILURE / UNKNOWN if no prior state) |
| `last_known_at` | Timestamp from the previous record |
| `last_known_command` | Command from the previous record |

The `last_known_*` fields preserve context across staleness. A `STALE`
state with `last_known_status: FAILURE` is more concerning than one
with `last_known_status: SUCCESS` — the edit might or might not have
fixed the prior failure, but you can't claim either way.

## Hook interactions

### mark-build-stale (PostToolUse on Edit/Write/MultiEdit)

Source-path classification via allowlist:

```python
SOURCE_EXTENSIONS = {
    ".java", ".kt", ".kts", ".scala", ".groovy", ".clj",
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
    ".py", ".pyx",
    ".go", ".rs",
    ".rb", ".php", ".cs", ".swift", ".m", ".mm",
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hxx",
    ".ex", ".exs",
    ".sql",
}

BUILD_FILES = {
    "pom.xml",
    "build.gradle", "build.gradle.kts",
    "settings.gradle", "settings.gradle.kts",
    "package.json", "package-lock.json",
    "yarn.lock", "pnpm-lock.yaml",
    "Cargo.toml", "Cargo.lock",
    "go.mod", "go.sum",
    "requirements.txt", "Pipfile", "Pipfile.lock",
    "pyproject.toml", "poetry.lock",
    "Gemfile", "Gemfile.lock",
}

EXCLUDED_PATH_FRAGMENTS = (
    ".claude/",
    "docs/",
    "/spec/", "/specs/",
    "/src/test/", "/test/", "/tests/", "/__tests__/",
)
```

The exclusions are deliberate: edits to docs, specs, or test sources
don't invalidate the production build state. (Changing tests might
make them pass — but that's `capture-build-result`'s job to detect, not
this hook's.)

To add support for a new language, extend `SOURCE_EXTENSIONS` and
`BUILD_FILES`. Conservative bias: false positives (marking STALE for
a non-source edit) are acceptable; false negatives (missing a real
source edit) are the failure mode that defeats the purpose.

### capture-build-result (PostToolUse on Bash)

Pattern matching against known build tools:

```python
PATTERNS = [
    (re.compile(r"(?:^|\s)(?:\./)?mvnw?\b.*\b(?:verify|test|package|install)\b"),
     "maven", "BUILD SUCCESS", "BUILD FAILURE"),
    (re.compile(r"(?:^|\s)(?:\./)?gradlew?\b.*\b(?:build|test|check|verify)\b"),
     "gradle", "BUILD SUCCESSFUL", "BUILD FAILED"),
    (re.compile(r"(?:^|\s)npm\b.*\b(?:test|run\s+test|run\s+build)\b"),
     "npm", None, None),
    (re.compile(r"(?:^|\s)(?:yarn|pnpm)\b.*\b(?:test|build)\b"),
     "yarn", None, None),
    (re.compile(r"(?:^|\s)pytest\b"),
     "pytest", None, None),
    (re.compile(r"(?:^|\s)cargo\b.*\b(?:test|build|check)\b"),
     "cargo", None, None),
    (re.compile(r"(?:^|\s)go\s+test\b"),
     "go-test", None, None),
]
```

For each pattern: regex matches the command; `kind` labels the tool;
`success_marker` / `failure_marker` strings are searched in the response
text. `None` markers mean "trust exit code only."

**Ambiguity policy:** if no marker matches AND exit code is unknown,
the hook returns `(None, kind)` from `classify()` and exits 0 without
writing. Better to leave the previous state than to misclassify.

To support a new build tool: add a tuple. Keep the regex precise — too
broad and it'll fire on commands that aren't builds.

### gate-advance (PreToolUse on Bash)

Two pattern lists:

```python
ADVANCE_PATTERNS = [
    re.compile(r"(?:^|\s|&&\s|;\s)git\s+commit\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)git\s+push\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)gh\s+pr\s+(?:create|merge|review\s+--approve)\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)gh\s+release\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)kubectl\s+apply\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)terraform\s+apply\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)docker\s+push\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)(?:aws|gcloud|az)\s+(?:.*\b)?(?:deploy|push)\b"),
]

EXEMPT_PATTERNS = [
    # Build / test commands — recovery path, never gate.
    re.compile(r"(?:^|\s|&&\s|;\s)(?:\./)?mvnw?\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)(?:\./)?gradlew?\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)gradle\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)npm\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)(?:yarn|pnpm)\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)pytest\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)cargo\s+(?:test|build|check)\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)go\s+test\b"),
    # Read-only git — fine to run while STALE/FAILURE.
    re.compile(r"(?:^|\s|&&\s|;\s)git\s+(?:status|log|diff|show|stash|checkout|restore|reset|add|rm|mv|fetch|pull|merge|rebase|branch|tag|worktree|config|remote)\b"),
]
```

The separator prefix `(?:^|\s|&&\s|;\s)` lets the regex match commands
inside compound shells (e.g., `git add foo && git commit -m bar`).

**Exempt list precedence over advance:** the hook checks exempt first.
If the command matches any exempt pattern AND no advance pattern, it
exits 0. If it matches BOTH (e.g., a one-liner that runs tests then
commits), the advance pattern still triggers and the gate fires.

This is conservative: a compound command that includes a commit needs
the gate. The user splits it into two commands if they want
finer-grained control.

To add a new advancement command (e.g., `helm install` for k8s
deploys): add a regex to `ADVANCE_PATTERNS`. To add a new
recovery command (e.g., a project-specific test runner): add to
`EXEMPT_PATTERNS`.

## State file race conditions

The hooks are simple file overwrites — no locking. Three potential
race scenarios:

1. **Two PostToolUse hooks fire concurrently** on different events.
   Not possible in practice — CC fires hooks sequentially per tool
   call.
2. **A user's `cat .claude/last-build.json` racing with a write.**
   Worst case the user reads a partial file. Unlikely to cause harm
   (the user re-reads).
3. **CC summarization mid-write.** The hook completes its write in a
   single `write_text` call; partial writes wouldn't survive a process
   exit anyway. Safe in practice.

Race-condition-safety isn't a hard guarantee; if it became an issue,
the right fix is `os.replace()` (atomic) for the write.

## Recovery flows

### After STALE

Run any of: `./mvnw verify`, `./gradlew test`, `npm test`, `pytest`,
etc. If green: state becomes SUCCESS. If red: state becomes FAILURE.

### After FAILURE

Two paths:

1. **Fix forward** — apply the fix, re-run verify, watch FAILURE → STALE
   → SUCCESS.
2. **Revert** — `git checkout -- <files>` to discard the edit. State is
   still FAILURE (the file write doesn't reset state); run verify again
   to confirm green and update to SUCCESS.

### After UNKNOWN (or missing file)

No baseline. The gate exits 0 with stderr warning. Run a verify to
establish the baseline; subsequent edits will then properly mark STALE.

### Manual override (emergency only)

```sh
echo '{"status": "SUCCESS", "at": "2026-05-13T10:00:00Z", "command": "manual override", "kind": "manual", "tail": "manually overridden"}' \
  > .claude/last-build.json
```

This is cheating. The `green-or-revert` skill should flag it. The
recovery path is to re-establish a real green build, not to fake the
state file.

## What this doesn't catch

- **Flaky tests.** A test that intermittently passes will move state
  between SUCCESS and FAILURE on consecutive runs. The state always
  reflects the last run, not aggregate confidence.
- **Build tool lies.** If `./mvnw verify` reports BUILD SUCCESS while
  tests are silently broken, the hook trusts the marker.
- **Coverage gaps.** SUCCESS means the tests that exist pass. It
  doesn't mean coverage is meaningful. That's `qa-engineer`'s gap
  scan (within the per-Task quality loop), separate concern.
- **Pre-existing FAILURE on session start.** If you start a session
  with `.claude/last-build.json` already in FAILURE from a previous
  session, the gate immediately blocks pushes. Correct behavior — run
  verify to confirm or revert prior broken state.

## When to extend

- **New language with non-standard markers:** add to
  `capture-build-result.py`'s `PATTERNS` list.
- **New file type that should mark STALE:** extend `SOURCE_EXTENSIONS`
  or `BUILD_FILES` in `mark-build-stale.py`.
- **New advancement command:** add regex to `gate-advance.py`'s
  `ADVANCE_PATTERNS`.
- **Project layout where source lives outside `src/main/`:** the
  exclusions are path-fragment based; tighten or loosen as needed.

After any change: `bin/install.sh --clean` to refresh the cache.
