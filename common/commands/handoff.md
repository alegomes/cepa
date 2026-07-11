---
description: Save a rich session handoff so a new session can pick up seamlessly. Writes the narrative (decisions, current state, next concrete step, caveats, open threads) into this branch's handoff file at .claude/handoffs/<branch-slug>.md, on top of the mechanical skeleton the checkpoint hook maintains. Replaces typing "salve a memória de handoff" by hand. The next session's SessionStart surfaces it automatically.
argument-hint: (none) — captures the current session
---

# /common:handoff

## Purpose

End-of-session (or good-stopping-point) capture, in one word. The checkpoint
hook already keeps a mechanical skeleton current every turn (commits, dirs
touched, last intents) — this command adds the part only a model can write: the
*story*. Decisions and why, where things stand, and the single most important
next step. A fresh session reads it automatically at startup and just continues.

## How the handoff file works

- Lives at `<repo-root>/.claude/handoffs/<branch-slug>.md`, keyed by **branch**
  (not session id), so resume is a direct lookup and parallel worktrees stay
  separate.
- Two zones, independently owned:
  - `<!-- HANDOFF:AUTO -->…<!-- /HANDOFF:AUTO -->` — the checkpoint hook owns
    this. **Preserve it byte-for-byte.**
  - `<!-- HANDOFF:NOTE -->…<!-- /HANDOFF:NOTE -->` — **you write this.**

## Workflow

### 1. Locate the file

- Branch: `git rev-parse --abbrev-ref HEAD`.
- `branch-slug` = the branch with every run of non-`[A-Za-z0-9._-]` characters
  replaced by `-` (e.g. `session/0611-1430` → `session-0611-1430`).
- Repo root: `git rev-parse --show-toplevel` (in a linked worktree, use the
  parent of `git rev-parse --git-common-dir` with the trailing `/.git` removed —
  the handoff lives in the MAIN worktree's `.claude/handoffs/`).
- File: `<root>/.claude/handoffs/<branch-slug>.md`.

### 2. Gather material (same sources as `/common:recap`)

- `.claude/session-log.md` — the intent trail (what the user asked, in order).
- `git log` for this session (the AUTO zone already lists the commits; trust it).
- The live conversation — for the decisions, rationale, and what's left, which
  the log can't capture.

### 3. Compose the NOTE zone

Write tight, scannable Markdown — a handoff, not a transcript. Structure:

```markdown
## Onde estamos
<1–3 frases: o estado atual de verdade>

## Decisões desta sessão
- **<decisão>** — <por quê, em uma linha>
- …  (só as que importam para retomar — escolhas de escopo, contrato, design)

## Próximo passo
<a ÚNICA coisa mais importante a fazer a seguir — concreta, acionável>

## ⚠ Cuidados / pendências
- <armadilhas, "não-live até reinstall", coisas a não esquecer>

## Threads abertas
- <o que foi começado e não terminou, se houver>
```

Rules:
- **Concrete over vague.** "Fix the bug" is useless; "rodar `bin/install.sh
  --clean` + restart para os hooks novos valerem" is useful. Cite commits /
  `file:line` where it helps.
- **Convert relative dates to absolute** ("amanhã" → the actual date).
- **Don't fabricate.** If a thread's state is unclear, say so rather than guess.
- **Mark perishable facts.** Anything the next session could state as fact but
  that another session/person can change in the meantime — remotes, sibling
  repos existing or not, branch positions, build state, "X ainda não foi
  implementado" — gets a `(verificar)` suffix. The reader re-checks before
  repeating it; a handoff fact repeated without verification is the top-1
  user-reported failure of this system.
- If there's genuinely nothing strategic to record (a trivial session), write a
  one-line NOTE and say so — don't pad.

### 4. Write the file

- If the file **exists**: Read it, then Write it back with the frontmatter and
  the entire AUTO zone **unchanged**, replacing only the text between the NOTE
  markers. Also refresh the frontmatter `updated_at:` line to now (UTC ISO,
  seconds) so resume treats this as the freshest state.
- If the file **does not exist** (checkpoint hook not installed yet / fresh
  branch): create it with this exact shape, filling the AUTO zone from `git log`
  + `git status` yourself:

```markdown
---
session_id: (unknown — written by /handoff)
branch: <branch>
branch_slug: <slug>
cwd: <repo root>
updated_at: <now ISO>
turns: ?
---

<!-- HANDOFF:AUTO -->
## Onde paramos (checkpoint automático)
<commits desta sessão + git status, montados por você>
<!-- /HANDOFF:AUTO -->

<!-- HANDOFF:NOTE -->
<a narrativa do passo 3>
<!-- /HANDOFF:NOTE -->
```

### 5. Confirm

Reply with one line: the path written and the one-line next step you recorded —
so the user knows the handoff is saved and what it points at. Don't dump the
whole file back.

## Constraints

- **Only write the handoff file.** No code edits, no commits, no Jira.
- **Never touch the AUTO zone** when the file already exists — that's the hook's.
- This is invoked either directly by the user (`/common:handoff`) or by you after
  the wrap-up nudge when the user agrees. Same behavior either way.
