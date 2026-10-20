---
description: Periodic consolidation of the mental-models (common/expertise/*.yaml) — merges redundant entries, retires the ones the current code contradicts (ALWAYS checking against the repo first) and leaves untouched what is still valid. Produces a before/after diff with the evidence for each retirement and ONLY writes after explicit approval from the user. Complements expertise-append.py's count-based prune, which prevents growth but never re-checks facts.
argument-hint: [agent | --all]   (e.g.: proof-reviewer, backend-dev; --all sweeps every *-mental-model.yaml)
interaction: routine
---

# /common:consolidate

## Purpose

Expertise entries accumulate via `common/hooks/expertise-append.py` with a
prune by COUNT (cap of 20 in `feedback:`, except `tag: principle`) — never by
VALIDITY. A fact written in February may be contradicted by July's code and
still be read on every boot of the agent. It is the same defect as the handoffs
before the "handoff is a hypothesis" discipline: memory treated as settled fact.

This command closes that hole: it rereads each entry of the target
mental-model(s), checks the ones that cite concrete artifacts against the
current state of the repo, merges redundancies and proposes a reviewable diff.
**Nothing is written without the user's explicit approval** — this is the
flow's human gate.

## Variables

- `$ARGUMENTS`:
  - `<agent>` — consolidates only `common/expertise/<agent>-mental-model.yaml`
    (also accept the file name or the full path).
  - `--all` — sweeps every `common/expertise/*-mental-model.yaml`.
  - empty — list the available files with the entry count per section and ask
    which one to consolidate (suggest the fattest).

The files live in `common/expertise/` in the plugin repo; in host projects,
`.claude/expertise/` is a symlink to that same directory (see
`common/skills/mental-model/SKILL.md`). Resolve through the symlink if you are
in a host; there is only one physical file.

## Steps

### 1. Read and inventory

For each target file, read it in full and inventory the sections with a schema
(`feedback:`, `heuristics:`, `ecosystem_gotchas:`) and the free keys.
Keep in mind three things the final write must NOT lose:

- the comment header (`# Mental model — <agent>` etc.) and
  `last_updated:`;
- the chronological order of the entries within each section (oldest-first —
  it is what the append's prune assumes);
- the hand formatting (block scalars `|`, blank line between items).

### 2. Classify each entry — by verification, not by opinion

Classify each entry into exactly one category:

- **(a) redundant** — says the same as another entry (or a subset of it).
  Proposal: merge, keeping the richest entry as the base and incorporating any
  unique detail from the absorbed one(s); in the resulting entry, note the
  absorbed `run_id`s/ids (e.g. `merged_from: [<run_id>, ...]` in a feedback
  entry, or a parenthesis in the text of a short heuristic).
- **(b) contradicted** — the repo's current code/state says the opposite of
  what the entry states. Proposal: retire (remove), with evidence.
- **(c) stale** — references something renamed, removed or replaced (a hook
  that no longer exists, an extinct flag, a renamed command). Proposal: retire
  OR rewrite pointing at the successor, if the rule itself still holds.
- **(d) valid** — still correct. Keep it **untouched**: do not rewrite it, do
  not "improve" the wording. Consolidation is not editing.

**Verification rule (proof-reviewer rigor): a retirement without cited
evidence is a violation.** Before classifying any entry as (b) or (c):

- If the entry cites a **file or path**, check that it exists (Glob/Read)
  and — when the entry describes behavior — that the relevant snippet still
  behaves as described (read the code, not the file name).
- If it cites a **flag, allowlist, config or constant**, open the source and
  cite the current line that confirms or contradicts it.
- If it cites a **command/CLI**, confirm it exists (`command -v`, `--help`, or
  the script in the repo); run it only if it is read-only and cheap.
- Record the evidence in the format `evidence: <file:line or command> — <what
  was observed>`. "Looks obsolete", "probably changed" or memory from a previous
  session **are not evidence** — without mechanical verification, the entry is
  (d) by default.
- **Not verifiable ≠ contradicted.** Expertise is agent-global and
  cross-project: an entry may cite an artifact from ANOTHER repo that is not on
  your disk. In that case mark it `not verifiable in this repo` and keep it as
  (d) — at most list it in a "could not verify" section of the report for the
  user to decide.

**`tag: principle` entries never go into (b)/(c) automatically.** They are the
agent's disciplinary memory (the append never prunes them; this command does
not either). If verification suggests a principle has aged, present it as a
**separate, highlighted proposal**, requiring explicit individual approval —
never inside an "approve all".

### 3. Produce the proposed diff and present it to the user

Build, per file, a before/after report. The rendered report is in Brazilian
Portuguese (pt-BR):

```
## <agent>-mental-model.yaml — consolidation proposal

Entries: N → M  (merged: x · retired: y · kept: z)

### Merges
- [feedback] <run_id A> + <run_id B> → keeps A (richer), absorbs the detail
  "<...>" from B.
  BEFORE: <the two entries, verbatim>
  AFTER: <merged entry>

### Retirements  (each with evidence — mandatory)
- [heuristics] "<entry text>"
  reason: contradicted
  evidence: common/hooks/gate-advance.py:41 — the cited flag was removed;
  the gate now reads `.claude/last-build.json` directly.

### Proposals about `tag: principle` (individual approval)
- <if any>

### Could not verify (kept)
- <cross-project entries or ones without a citable artifact>

### Kept untouched
- <short list, identifiers only>
```

Present and **stop**. Accept full approval, partial approval ("approve the
merges, not retirement 2") or rejection. **Never write without an explicit
"yes" from the user in this session** — silence, "looks good, keep analysing"
or autonomous-mode do NOT count; in autonomous-mode this command stops here and
reports the diff as a pending human item.

### 4. Write (only after approval)

Apply exactly what was approved, by Edit/Write directly on the file
(consolidation is a rewrite of existing entries — the `expertise-append.py`
helper only appends; it does not fit here). Preserve:

- the comment header and every free key not touched;
- `tag: principle` entries (intact, unless individually approved in step 3);
- the chronological order of the remaining entries (a merged entry stays in the
  position of the kept base entry);
- the formatting (block scalars `|`, two-space indent, blank line between
  feedback items) — no round-trip through `yaml.dump`.

Update `last_updated:` to today's date. Mind concurrency: the helper's flock
only protects appends; this direct rewrite can collide with another session
writing the same file. Consolidate with the other sessions stopped (or warn the
user about the risk).

Reread the written file and validate that it is parseable YAML
(`python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" <file>`).
If it does not parse, revert and report.

### 5. Telemetry

At the end, one event per consolidated agent:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/_telemetry.py" emit mm_consolidation \
  agent=<name> merged=<n> retired=<n> kept=<n>
```

(`merged` = entries absorbed in merges; `retired` = retired; `kept` =
entries in the final file. If the user rejected everything, emit anyway with
`merged=0 retired=0` — the attempt is also a signal.) If `${CLAUDE_PLUGIN_ROOT}`
is not in the environment, use the absolute path of `common/hooks/_telemetry.py`.

### 6. Final report

Write it in Brazilian Portuguese (pt-BR):

- Per file: N → M entries, what was merged/retired/kept, and what was left
  pending (rejections, unapproved principles, unverifiable entries).
- It shows up in `/common:metrics` as the custom event `mm_consolidation`.

## Notes

- **Slice acceptance (BACKLOG P4):** running it on the fattest expertise file
  reduces entries without losing any still-valid rule — the reviewable diff of
  step 3 is what guarantees that.
- `feedback:` is normally written only by `/common:debrief`
  (`common/commands/debrief.md`); this command is the second sanctioned
  exception, and only under human approval.
- Consolidation is about VALIDITY, not size. A file with 6 entries, all valid,
  comes out untouched — that is success, not a failure of the command.
- Suggested cadence: when a file hits the cap of 20 in `feedback:`, or every
  few weeks of heavy autonomous-mode + debrief use.
