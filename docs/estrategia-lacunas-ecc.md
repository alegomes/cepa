# Closing Cepa's gaps against ECC: what to take, what to leave, in what order

**Status:** strategy decided, revision 2, after the panel of 2026-11-12 (`docs/reviews/2026-11-12-painel-lacunas-ecc.md`) and the owner's six decisions · **Date:** 2026-11-12 · **Session mode:** exploration
**Sources:** the ECC repository cloned at `~/coding/floss/ECC` (version 2.2.3, last commit 2026-11-06); the GitHub API for both repositories on 2026-11-12; this repository at branch `session/ecc`; `docs/estrategia-cepa-proximo-nivel.md`; `docs/estrategia-durabilidade.md`; `docs/epics/cepa-em-espiral.md`; `BACKLOG.md`.

## 0. Context

**ECC** ("everything-claude-code", `github.com/affaan-m/ECC`) is a Claude Code plugin that ships a catalog: 71 agents, 314 skills and 98 commands, by its own `AGENTS.md`. **Cepa** is this repository: 12 plugins that put mechanical gates around an agent team so that "done" is checked, not claimed.

The owner asked two questions on 2026-11-12: is there more to take from ECC than the two items already recorded, and what does Cepa lack to reach ECC's adoption. This document answers both and proposes an order of work.

Terms used below:

- A **hook** is a script Claude Code runs before or after an agent action, which can refuse it.
- **`cepa-until`** is the supervisor that runs a repository's work queue for a window of hours, one `claude -p` subprocess (Claude Code in non-interactive mode) per item.
- The **conductor** is the not-yet-built piece (cycle 2 of the Epic `cepa-em-espiral`) that chains discovery, build, proof and landing of an Epic cycle.
- **Cycle 3** of that Epic is "learn and prune": repeated hook blocks become memory, and a scorecard shows which number each harness change moved.
- **P1-4** is the `BACKLOG.md` section "Não existe modo de saber se uma mudança no harness melhorou alguma coisa".

## 1. How ECC was read, and what was not

Four passes. The first, by the main session, covered hooks, the edit gate (GateGuard), the learning system and loop design. The other three ran in parallel, one per area, each instructed to read Cepa's equivalent before naming a gap: unattended orchestration, context and memory, install and catalog health. Every Cepa-side fact in section 2 was then checked on disk by the main session.

Not read or only skimmed: about 310 of the 314 skills; the Rust dashboard and store of `ecc2/`; `docs/ECC-2.0-GA-ROADMAP.md` (1,389 lines); `scripts/install-apply.js`, `install-guided.js`, `repair.js`; the 16 translated doc trees. No ECC test suite was run (no `cargo` on this machine, Node tests not executed). A lesson may still hide in the unread part.

## 2. The numbers

| | ECC | Cepa |
|---|---|---|
| GitHub stars | 301,698 | 2 |
| Forks | 44,507 | not checked |
| People with a commit | 557 | 1 |
| Age | 299 days (2026-01-17 to 2026-11-12) | 200 days (first commit 2026-04-26) |
| License file | MIT | none |
| Repository description on GitHub | yes | empty |

ECC gained about 1,009 stars per day (301,698 ÷ 299). Stars measure reach, not quality. The causes listed in section 4 are inference from the repository, not measurement.

## 3. Engineering gaps

ECC is ahead of Cepa in few engineering spots. Three readings out of three reported that Cepa's design is ahead in its area (handoff, session chaining, token attribution, signed reservations, quota wait, build after every item, landing bound to a commit hash). The gaps below are the complete list found.

| Code | Gap in Cepa | What ECC does | Evidence in ECC that it works | Cepa fact, checked |
|---|---|---|---|---|
| E1 | No fixed set of recorded sessions to compare a hook's decisions before and after a change | `scripts/dev/gateguard-eval.js` replays 20 sessions (184 tool calls) against the hook at the working tree and at a git ref | Results table in `docs/gateguard/evaluation.md`: denials 157 to 132, repeated denials 38 to 0, bypasses 8 to 0 | Recorded in `BACKLOG.md` on 2026-11-12 |
| E2 | Hooks have no stable identifier and no switch | `ECC_HOOK_PROFILE` and `ECC_DISABLED_HOOKS`, read by `scripts/lib/hook-flags.js` | `tests/hooks/hook-flags.test.js` | 53 hook commands in `common/.claude-plugin/plugin.json`, no switch found. Recorded in `BACKLOG.md` on 2026-11-12 |
| E3 | No validator over every component | `scripts/ci/validate-skills.js`, `validate-agents.js`, `validate-commands.js` check the header block and dangling references | Run in CI, tested in `tests/ci/validators.test.js` | **Live defect:** 2 of 21 `SKILL.md` files have no header block (`docs-topology/skills/diataxis-discipline`, `how-why-boundary`), so Claude Code does not load them, while two agents of that plugin tell the agent to apply them |
| E4 | The test suite does not run on every commit | `.github/workflows/ci.yml` runs the suite on every push | CI | No `.github/` directory. `.claude/no-build` exempts the repo from the green-build rule. Only `cepa-until` requires `tests/run-all.sh` |
| E5 | The plugin list drifts between documents | `scripts/ci/catalog.js` compares counts with the README and can rewrite them | `tests/ci/catalog.test.js` | `.claude-plugin/marketplace.json` has 12 plugins, the installer's final summary prints 11, `docs/getting-started.md` lists 10 |
| E6 | `cepa-until` watches the clock, not the child | `scripts/loop-status.js` reads the session transcript and flags a tool call with no result for 1,800 seconds | About 27 unit tests. It only reports, never kills | `wait_for_child` (`common/bin/cepa-until:719`) waits on wall clock. 4 of 530 item runs were killed at the end of the slack (0.75%, `docs/estrategia-durabilidade.md`) |
| E7 | No ceiling on the text that is always loaded | A check rejects the lean profile above 8,000 estimated tokens | Tested, savings unmeasured | 145 descriptions of commands, agents and skills total 54,664 characters, about 13,666 tokens (54,664 ÷ 4). This is repo-wide, not what one install loads |
| E8 | The "long session" nudge counts prompts | `scripts/hooks/suggest-compact.js` reads the real context size from the transcript | Unit tests only | `common/hooks/session-subject.py` nudges at 45 prompts, then every 20. `cepa-tokens` already has the parser |
| E9 | Context compaction leaves no trace | `scripts/hooks/pre-compact.js` logs each compaction | Trivial | No PreCompact hook registered. The strategy of 2026-10-08 cites a session with 2 compactions found by hand |
| E10 | Finished sibling branches are not compared with each other before landing | `ecc2/src/worktree/mod.rs` runs `git merge-tree` between siblings and queues the conflicting one | Rust tests, not run here | `_wtlib.py:215` predicts conflict against the base only. Matters only when the conductor runs parallel branches |
| E11 | The handoff does not record what failed | `commands/save-session.md` has "What Did NOT Work" and "What Has NOT Been Tried Yet" | Prose | The narrative zone of `common/commands/handoff.md` has neither |

One finding is a design disagreement, not a gap. Cycle 3 plans that a repeated hook block becomes a memory line **injected** into the next child. ECC's memory store refuses automatic injection: every entry starts as `trust: unreviewed`, recall is on request only, and a secret scan runs before any write (`docs/design/ecc-memory-vault.md`). ECC's own doc says the retrieval evaluation is still pending, so this is a caution, not a proven result. The owner decided in Q3 that the memory waits (section 10).

One method is worth keeping without building anything now. ECC measured its edit gate with real sessions, with and without the gate, hypotheses written beforehand and a placebo arm. Result on 96 sessions: 25 of 48 passed with the gate against 18 of 48 without, p = 0.210, not confirmed, while the cost was stable at 37% more turns (8.2 against 6.0) and 40% more spend (US$ 0.151 against US$ 0.108). The lesson for Cepa is to report a gate's cost next to its effect. It needs E1 and E2 first.

## 4. Adoption gaps

| Code | What ECC does | Cepa today, checked |
|---|---|---|
| A1 | MIT license, repository description, topics | No `LICENSE`, empty description. Without a license nobody may legally use the code |
| A2 | Install without cloning: `npx ecc-universal setup`, or `/plugin marketplace add` plus `/plugin install` | Documented path is clone, then `bin/install.sh --topology=...` inside the host project |
| A3 | First value in 3 steps and 2 decisions that have a default | About 7 steps and 3 to 4 decisions (topology, shell alias, session mode, build baseline). Without `--topology` the installer ends in manual copy instructions |
| A4 | Uninstall, dry run and repair, driven by a record of every file written | `install.sh` writes into the host project (symlink, `CLAUDE.md` line, `.claude/topology`, `board-flow.yaml`). There is a rollback of the plugin cache, no uninstall and no dry run |
| A5 | `CHANGELOG.md` and signed tags | 0 git tags, no changelog, 12 independent plugin versions |
| A6 | A "what are you doing, start here" table | The README explains Epic, cycle, queue, item, mode and intent before the first command |
| A7 | Something for every stack, 16 README translations, several agent tools, Discord, sponsors | Java with Quarkus in `build-hex`, Claude Code only, one owner |
| A8 | The author had an audience first: two long guides and a hackathon win | None |

## 5. What not to copy

- **The catalog breadth and the multi-tool support (A7).** They are what a star count rewards and what a single owner cannot maintain. The strategy of 2026-10-08 already records 19.5% of sessions spent on Cepa itself.
- **The background learning observer** ("instincts"): an agent reads every tool call and writes rules with a confidence score. Costly, and ECC shows no measured effect.
- **The question gate before every edit:** the cost is certain and the benefit was not confirmed by ECC's own experiment.
- **The SQLite store and resident daemon of `ecc2/`:** against Cepa's rule of no new state store, and its lock needs manual removal after a crash.
- **Automatic merge without verification, and dependency directories symlinked into worktrees:** Cepa verifies after each merge and copies on purpose.
- **The context-profile machinery** (about 2,500 lines): it solves a problem of a 300-skill catalog.
- **Release gates for npm, supply-chain scans, limits on bursts of issues and pull requests:** they solve a crowd problem Cepa does not have.

## 6. Paths considered

### P1. Engineering only

Close E1 to E11 in the order of section 7 and do nothing about adoption. Cepa stays the owner's tool.

- Gain: every item serves a need the owner already recorded (P1-4, cycle 3, the unattended window).
- What it leaves: A1 stays, so the public repository remains unusable by anyone else.

### P2. Adoption first

Go after outside users: A1 to A6 first, then breadth (A7) and content (A8).

- Gain: the only path that could move the star count.
- Risk: every outside user is support work, and the count of sessions spent on the harness rises. Breadth contradicts the pruning of cycle 3. Stars depend on A8, which no repository change produces.

### P3. Engineering, plus an open door without a crowd

P1, plus the adoption items that are cheap and also good for the owner: A1, A2, A3 with one default topology, A5 and A6. No A7, no community machinery, no promise of support.

- Gain: a stranger can try Cepa in a few minutes, and the owner gets a changelog and a simpler install on a new machine.
- Risk: A3 changes the installer, which is the piece every host project depends on.

## 7. Recommendation (revision 2, after the panel)

Revision 1 recommended P3 in five lots. The panel of 2026-11-12 (`docs/reviews/2026-11-12-painel-lacunas-ecc.md`, 7 lenses, 81 findings) accepted the direction and rejected the order. The owner decided the six named disagreements the same day. This section replaces the lots of revision 1.

**The admission rule.** `docs/estrategia-cepa-proximo-nivel.md` line 82 says a harness change that moves none of the four scorecard numbers does not enter. The four numbers are: turns after the routine per session, red builds, needs-human per cycle, and the fraction of sessions spent in the cepa repository. The column "Number it moves" applies that rule. An item that moves none is listed as an exception with its reason.

| Lot | Items | Number it moves | Precondition |
|---|---|---|---|
| 0. Defects, through the single-item route | Fix the 2 `SKILL.md` files without a header block. Add the MIT `LICENSE` | None. Exception: the first is a defect, the second is the legal precondition of Q1 | For the skills: a test showing Claude Code does not load them today. For the license: holder name and year |
| 1. One source for the plugin list | The installer's final summary and the list in `docs/getting-started.md` are derived from `.claude-plugin/marketplace.json`. This replaces the list check E5 | Fraction of sessions in cepa (one place to edit instead of three) | The owner says which of the 12 plugins a newcomer should see |
| 2. Cepa checks itself | E3 validator as a test in the suite. A repository tag each time a queue lands | None. Exception: E3 stops the defect of lot 0 from recurring. The tag is the point to return to before any lot touches a hook | None |
| 3. Compare a hook before and after (E1) | Runner plus hand-written hook inputs for the three hooks that block the most | It is the instrument that shows which number a hook change moved (P1-4) | None. Brought forward out of cycle 3 by the owner |
| 4. Open door | Repository description, topics, one README line with `claude plugin marketplace add` and `claude plugin install`. A "start here" table (A6) | None. Exception: decided by the owner in Q1 | A read of the repository for content not meant for strangers (client names, tracker addresses) before description and topics |

**Out of the plan, by decision of the owner on 2026-11-12:**

- **E2, the hook switch.** Not built now. It returns only when the with-and-without experiment has a queue. Then the switch is obeyed only by the experiment's runner, records an event on each use, and never turns off an invariant of the Epic `cepa-em-espiral`, such as the write gate by mode.
- **A hand-written `CHANGELOG.md` (part of A5).** Versions stay per plugin as `docs/versionamento.md` defines.
- **A3 (default topology) and A4 (uninstaller, dry run).** The install without cloning does not go through `bin/install.sh`, so the installer does not change and R5 holds by construction.

**Out of the plan, by the panel's convergence:**

- **E6, the stuck-child detector, becomes a condition.** The 4 cases of `docs/estrategia-durabilidade.md` are children killed at the end of the slack ("3 without progress + 1 with progress"), with no evidence they were stuck in a tool call. That document reopens the subject only above 5% of item ends, and the measured rate is 0.75% (4 ÷ 530). E6 enters only if the cause of those cases is checked and is a hanging tool call.
- **E4, the suite on every push, waits for three measurements:** whether `tests/run-all.sh` passes today, how long it takes, and whether it runs on Linux. The fate of `.claude/no-build` is decided with it.
- **E7, the ceiling on always-loaded text, waits** for the number of one real install. The 13,666 tokens are repository-wide.

**In cycle 3, recorded in `docs/epics/cepa-em-espiral.md`:** E9 (compaction log), E8 (long-session nudge by real context size), E7 once measured. E8 and E9 share the transcript reader that `cepa-tokens` already has.

**Recorded without a queue:** E10 (until the conductor runs parallel branches), E11 (the "what did not work" section of the handoff), the with-and-without experiment.

**Queue.** Lots 1, 2 and 3 form the queue `lacunas-ecc`. Lot 0 goes through the single-item route and does not wait for the queue. Lot 4 is owner work plus one documentation item.

## 8. The test of the install without cloning (2026-11-12)

With an empty configuration folder (`CLAUDE_CONFIG_DIR` pointing to a scratch directory), these three commands succeeded: `claude plugin marketplace add <path of this repository>`, `claude plugin install common@cepa`, `claude plugin install build-solo@cepa`. `claude plugin list` then showed `common` 3.6.0 and `build-solo` 0.2.0 enabled.

Not tested: adding the marketplace from GitHub instead of a local folder, and opening a session in a host project that has no `.claude/topology` file, which `bin/install.sh` normally writes. The second one decides what the README line must say after the two commands.

## 9. Risks every lot must respect

- **R1.** No lot adds a hook that blocks, and no lot adds a hook at all. E3 is a test in the suite.
- **R2.** No lot creates a way to turn a gate off.
- **R3.** E1 scenarios contain no recorded session and no client data. The repository is public.
- **R4.** Lot 4 does not change `bin/install.sh`.

## 10. Questions answered by the owner (2026-11-12)

Q1 to Q3 were answered before the panel ran, against the rule of `docs/advisors.md` that the panel comes first. The panel's synthesis then adjusted Q1 and Q3, and the owner confirmed.

- **Q1.** Should anyone besides the owner be able to use Cepa? **Yes, in the minimal form** described in lot 4.
- **Q2.** Which license? **MIT.**
- **Q3.** Does the memory of cycle 3 inject itself into the next child, or wait for a review? **It waits.** The candidate line appears as a closed question in the report at the end of each unattended run (`/common:until-review`) and expires if unanswered. The cycle 3 row of the Epic was corrected on 2026-11-12.

The six decisions on the panel's disagreements are recorded line by line in `docs/reviews/2026-11-12-painel-lacunas-ecc.md`.
