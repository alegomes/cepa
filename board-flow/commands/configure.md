---
description: Interactive setup for board-flow.yaml at project root. Walks the user through site, project_key, board_id, issue_types, and default_topology. Validates site against the user's actually-accessible Atlassian sites via atlassian-expert (no guessing). Use after `bin/install.sh --topology=NAME` to replace the placeholder values, or anytime atlassian-expert is refusing operations because of missing config.
argument-hint: [--migrate]   (optional: detect legacy .claude/board-flow.lifecycle.yaml and offer to migrate it to project root)
---

# /board-flow:configure

## Purpose

`bin/install.sh` seeds `board-flow.yaml` with placeholder values (`example.atlassian.net`, `EXAMPLE`, etc.) — those have to be replaced before any `/board-flow:*` command will work. This command does that interactively: asks for each value, validates the site against your actual Atlassian sites (so you can't typo it), and writes the file.

This is one of the few commands where **asking the user questions is the point**. The autonomous-mode skill, if active, does NOT apply here — configuration values come from the user, not inference.

## Variables

- `$ARGUMENTS` — `--migrate` (optional). If set, also looks for legacy `.claude/board-flow.lifecycle.yaml` and offers to move its contents into the new file at project root.

## Instructions

You are the orchestrator. Drive the user through each value. Don't fabricate any value — every field comes from the user's answer or from `atlassian-expert`'s validated lookup.

`atlassian-expert` is the only Jira read path. If it isn't installed, abort: "board-flow's atlassian-expert is required for site validation; install board-flow@cepa."

## Workflow

### 1. Locate and read existing config

Check for these files in order:

- `board-flow.yaml` at project root → "current config" (canonical location).
- `.claude/board-flow.lifecycle.yaml` → "legacy config".

Branches:

- **Neither exists** → fresh setup. Skip to step 2.
- **Canonical exists, legacy doesn't** → re-configuration. Read current values; in step 2, present them as defaults (user can press enter to keep).
- **Legacy exists, canonical doesn't** → migration case.
  - If `--migrate` was passed: read legacy values, offer to move them into the new location at project root. Ask user to confirm: "Found legacy `.claude/board-flow.lifecycle.yaml`. Migrate its contents to `board-flow.yaml` (project root) and delete the legacy file? (yes / no / keep both)"
  - If `--migrate` not passed: tell user "Legacy config found at `.claude/board-flow.lifecycle.yaml`. Re-run with `/board-flow:configure --migrate` to move it, or I'll create a fresh `board-flow.yaml` ignoring it. Continue with fresh setup? (yes / cancel)"
- **Both exist** → conflict. Tell user: "Both `board-flow.yaml` and `.claude/board-flow.lifecycle.yaml` exist. The new file wins (commands prefer it). Want me to delete the legacy file? (yes / no — leave alone)" Then proceed using the canonical as the source.

### 2. Resolve site (validated)

Delegate to `atlassian-expert`:

> Call `getAccessibleAtlassianResources` and reply with the list of sites the current Atlassian session can access — name + URL for each.

If the call fails (auth dropout, MCP unavailable): tell user "Couldn't reach Jira to list sites. You can either: (a) reauthorize the Atlassian connector and re-run this command, or (b) type the site URL manually and skip validation. Which?" Don't proceed silently with an unvalidated value.

If the call succeeds:

- One site → confirm with user: "Found one site: `<url>`. Use it? (yes / no — type a different one)".
- Multiple sites → numbered list, user picks: "Which site? 1) `wego.atlassian.net`  2) `other.atlassian.net`  ..."

Whatever the user picks (or types if validation skipped) → `site = <chosen-value>`. Don't accept partial URLs ("wego" → "wego.atlassian.net" is forbidden inference); require the full host.

### 3. Resolve project_key

Ask: "Project key (e.g., `WEGO`, `ENG`)? Current: `<value or none>`. Enter to keep, or type new:"

Optional validation: if the user wants, delegate to `atlassian-expert` to call `getVisibleJiraProjects` and confirm the key exists in their accessible sites. Recommended on first setup, optional on re-run.

### 4. Resolve board_id

Ask: "Board ID (numeric, e.g., `766`)? Current: `<value or none>`. Find this in Jira's URL when viewing the board (`/jira/software/projects/<KEY>/boards/<ID>`). Enter to keep, or type new:"

Don't try to enumerate boards via API — many users have hundreds. Trust the user-provided value but require it to be numeric.

### 5. Resolve status_map

These are the literal Jira status names for the four states the canonical flow uses. `/board-flow:drain` pulls cards from `to_do`. `/board-flow:execute` and `/common:autonomous-start` move cards through `to_do` → `in_progress` → `in_review`. Blocked cards stay in `in_progress` unless `blocked` is set.

Show current values (or defaults): `to_do: "To Do"`, `in_progress: "In Progress"`, `in_review: "In Review"`, `blocked: "Blocked"`.

Ask: "Use standard status names (To Do / In Progress / In Review / Blocked) or customize? Many projects use 'Doing' / 'Code Review' / 'Done' or different names. (standard / customize)".

If customize:
- Walk through each: "What's the literal name in your Jira for `<purpose>`? (e.g., `<default>`)".
- For `blocked`: also offer "null" — meaning "my project doesn't have a Blocked status; commands should leave blocked cards in In Progress with a comment instead."

Optional validation: delegate to `atlassian-expert` to call `getJiraIssue` on a known card and read the available statuses from its `getTransitionsForJiraIssue` output. If a name the user gave isn't reachable from your typical entry points, warn — don't auto-correct.

### 6. Resolve issue_types

Show current values (or defaults): `story: "Story"`, `bug: "Bug"`, `epic: "Epic"`, `task: "Task"`.

Ask: "Use standard issue type names (Story / Bug / Epic / Task) or customize? (standard / customize)". If customize: walk through each and ask. Most projects use the defaults.

### 7. Resolve default_topology

Read `.claude/topology` if present. If found: confirm with user: "Default topology for `/board-flow:execute` and `/board-flow:plan-track-build-validate`: `<value from .claude/topology>` (matches `.claude/topology`). Keep? (yes / type different)".

If `.claude/topology` is missing: ask "Default topology? Options: `build-hex`, `build-team`, `discovery`. Type one:". Don't write a value the user didn't give.

### Optional keys (not walked through)

Some `defaults` keys are optional and hand-edited rather than asked here: `status_map.done` (auto-advance target for `/board-flow:prove`), a discard status (`wont_do` / `cancelled`), and `sibling_link_type` — the issue link type used to tie sibling cards of the same work across repos (default `"Relates"`; see "Cascata multi-repo" in `agents/atlassian-expert.md`). Mention they exist if the user asks; don't prompt for them.

### 8. Show the proposed file and confirm

Display the assembled `board-flow.yaml` exactly as it'll be written. Ask: "Write this to `<path>`? (yes / cancel / edit field <name>)".

If "edit field <name>" → loop back to that step.

### 9. Write the file

Write `board-flow.yaml` at project root. Preserve any existing `lifecycles:` block from the prior config (don't overwrite lifecycles — those are advance-command schema, separate concern). If migrating from legacy AND user confirmed deletion, delete `.claude/board-flow.lifecycle.yaml` after the new file is written and verified readable.

### 10. Verify

Delegate to `atlassian-expert`:

> Read the just-written `board-flow.yaml`. Try a no-op operation: `getJiraIssue` for any one issue in `defaults.project_key` (e.g., search for one card via `searchJiraIssuesUsingJql` with `project = <KEY> ORDER BY created DESC` and limit 1). If it succeeds, the config works end-to-end. If it fails, report the error.

This is the smoke test — proves the site + project + auth all line up.

### 11. Final report

A single concise message:

- **File:** `<path>` written.
- **Site:** `<site>` (validated).
- **Project / board:** `<key>` / `<board_id>`.
- **Default topology:** `<topology>`.
- **Smoke test:** PASS (found issue `<sample-key>`) / FAIL (`<error>`).
- **Migration:** "Legacy file deleted" / "Legacy file kept" / "No migration".

If smoke test FAILed: name the likely cause (auth, project key, site mismatch) and suggest the fix.

## Constraints

- **Never infer values from context.** If the user doesn't answer or gives an empty answer, re-ask. Don't fall back to placeholders, don't construct from repo name (forbidden by `atlassian-expert`'s anti-hallucination rule and the same forbidden here).
- **Validate the site against the user's actual access.** A site URL the user can't authenticate to is useless. The `getAccessibleAtlassianResources` step prevents typos and stale config.
- **Don't preserve placeholder values.** If the existing file has `site: example.atlassian.net` (the install.sh placeholder), treat the field as unset — don't offer it as "current value to keep".
- **One re-run is cheap.** If the user wants to change one field later, just re-run this command. Don't try to invent a granular `/configure --field=site` — the full walk is short.
