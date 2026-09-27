# Build-state machine

The `.claude/last-build.json` state file and the three hooks that
maintain it. For user-facing usage docs see
[`../green-or-revert.md`](../green-or-revert.md); this page is for
extending or debugging the state machine itself.

## States

For the state machine diagram, the tier behavior (LOCAL vs SHARING),
the `.claude/no-build` opt-out, the no-manifest warning path, and how
`UNKNOWN` is treated, see [`../green-or-revert.md`](../green-or-revert.md),
which is now the single description of all of that. This page covers
only what's internal to the three hooks: file schema and per-tool
detection.

Five states in the file (`SUCCESS`, `FAILURE`, `EMPTY`, `STALE`, and
`UNKNOWN`/missing); transitions all triggered by hooks (orchestrator
never writes the file directly). `UNKNOWN` is any `status` value
`gate-advance.py` doesn't recognize, treated the same as `FAILURE`.
Editing while `FAILURE` returns to `STALE`, not directly to a fixed
state, since the fix is unproven until a new verify lands.

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
| `kind` | One of: `maven`, `gradle`, `npm`, `yarn`, `pytest`, `cargo`, `go-test`, `docker-build` |
| `tail` | Last ~12 lines of the response text |

### FAILURE

Same shape as SUCCESS, with `status: FAILURE`. `tail` will include the
failure surface.

### EMPTY

Same shape as SUCCESS, with `status: EMPTY`, `tests_run: 0` and a `reason`.
Written when the command carries a **test filter** (`-Dtest=`/`-Dit.test=`,
`pytest -k`, `go test -run`, jest `-t`/`--testNamePattern`), the run would
classify SUCCESS, and the output shows zero tests executed (or no count at
all). Origin: with `surefire.failIfNoSpecifiedTests=false`, a mistyped
`-Dtest=` prints BUILD SUCCESS with no `Tests run:` line. EMPTY is never
green: gate-advance blocks on it like FAILURE, and the two places that
declare a card/item done refuse it too: `acceptance-gate.py` blocks a
forward Jira transition (in_review/done or unresolved target, bounces
allowed) even with a `complete` audit, and `cepa-plan finish --status done`
exits 2 (blocked/pending still accepted). Both also refuse `STALE` with `last_known_status: EMPTY` (edited after the empty run, no new build; mark-build-stale carries `last_known_*` through STALE→STALE so a second edit keeps it), reading the baseline of the session's own worktree root, never the main clone. Unfiltered builds are not
checked (a module with no tests is legitimate). A filtered SUCCESS also
records `tests_run: N`.

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
    # docker build emits no exit code the hook can read; classified on
    # output text only. BuildKit prints "writing image" + "naming to";
    # the classic builder prints "Successfully built". Failures:
    # BuildKit "failed to solve" / "executor failed"; classic "returned
    # a non-zero code".
    (re.compile(r"(?:^|\s)docker\s+(?:buildx\s+)?build\b"),
     "docker-build",
     ["writing image", "naming to", "Successfully built"],
     ["failed to solve", "executor failed", "returned a non-zero code"]),
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

**Where the build actually ran (`effective_build_dir`).** The Bash `cwd`
CC reports persists across calls within a session, so a project script
that does `cd subdir && ./mvnw verify` needs the hook to know it ran in
`subdir`, not at the session root. `effective_build_dir` follows a
leading `cd X &&` / `cd X;` prefix (quoted or bare, chained) to resolve
where the build actually executed. When that resolved directory is
OUTSIDE the session's worktree (the case that matters is a
`proof-reviewer` perturbation running in a throwaway `/tmp` worktree),
the result is written to THAT directory's own
`.claude/last-build.json`, never poisoning the session's own baseline
with a deliberate RED from somewhere else.

### gate-advance (PreToolUse on Bash)

The full tier behavior (LOCAL vs SHARING), the `.claude/no-build`
opt-out, the no-manifest warning, and how `UNKNOWN` is treated are
described once, for both internals and usage, in
[`../green-or-revert.md`](../green-or-revert.md)#the-three-hooks. What's
internal here: the three pattern lists (`LOCAL_PATTERNS`,
`SHARING_PATTERNS`, `EXEMPT_PATTERNS`) live in `gate-advance.py`, each a
list of regexes with the separator-aware prefix `(?:^|\s|&&\s|;\s)` so
compound shells (`git add foo && git commit -m bar`) match correctly.
`classify()` returns the highest tier that matched, precedence SHARING
> LOCAL > EXEMPT, so a compound command that includes a commit needs
the gate even if most of it is exempt.

To add a new advancement command:
- New local operation (rare; almost everything that isn't a build is
  sharing-tier) → add regex to `LOCAL_PATTERNS`.
- New sharing operation (e.g., `helm install` for k8s deploys) → add
  regex to `SHARING_PATTERNS`.
- New recovery command (e.g., a project-specific test runner) → add to
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

## Recovery flows and what the gate doesn't catch

Both now live in [`../green-or-revert.md`](../green-or-revert.md): the
`After STALE` / `After FAILURE` / missing-baseline recovery steps
(green-or-revert's "When you'll see the gate fire" + "Recovery" section)
and the "What this doesn't protect against" list (flaky tests, build
tool lies, coverage gaps, environment drift). One correction that used
to live here and contradicted the tier table above: a **missing**
baseline does NOT uniformly "exit 0 with a warning"; that's only true
for the LOCAL tier (`git commit`) and for the no-manifest fallback.
SHARING-tier commands (`push`, PR, deploy) fail CLOSED on a missing
baseline. And `UNKNOWN` (a `status` value the gate doesn't recognize) is
treated as `FAILURE`, not as a missing baseline, so it always blocks.

**Manual override (emergency only):**

```sh
echo '{"status": "SUCCESS", "at": "2026-05-13T10:00:00Z", "command": "manual override", "kind": "manual", "tail": "manually overridden"}' \
  > .claude/last-build.json
```

This is cheating. The `green-or-revert` skill should flag it. The
recovery path is to re-establish a real green build, not to fake the
state file.

## When to extend

- **New language with non-standard markers:** add to
  `capture-build-result.py`'s `PATTERNS` list.
- **New file type that should mark STALE:** extend `SOURCE_EXTENSIONS`
  or `BUILD_FILES` in `mark-build-stale.py`.
- **New advancement command:** add regex to `gate-advance.py`'s
  `LOCAL_PATTERNS` (recoverable; fail-open on missing baseline) or
  `SHARING_PATTERNS` (broadcasts/deploys; fail-closed on missing
  baseline). Almost everything new lands in SHARING.
- **Project layout where source lives outside `src/main/`:** the
  exclusions are path-fragment based; tighten or loosen as needed.

After any change: `bin/install.sh --clean` to refresh the cache.
