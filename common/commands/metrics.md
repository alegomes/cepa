---
description: Telemetry report on the harness itself — sessions per repo, red build rate, gate-advance blocks by reason, proof gate verdict distribution, over-declared `proven` blocked by the guard, and the **friction at the session's ends** (how many turns you spend before you manage to launch the routine, and how many after it until you close). Reads the ledger in ~/.claude/cepa-telemetry/, fed automatically by the hooks. Use it to decide with evidence where the harness gets in the way instead of helping.
argument-hint: [--days N | --month YYYY-MM] [--repo <name>]
interaction: routine
---

# /common:metrics

## Purpose

The harness audits cards, builds and proofs — this command audits the harness.
The hooks (`gate-advance`, `capture-build-result`, `session-registry`,
`proof-verdict-guard`, `session-log`) emit fail-silent events to
`~/.claude/cepa-telemetry/events-YYYY-MM.jsonl`; the aggregator turns that into
answers: where the gate blocks too much, which repo burns the most builds, how
many over-declared `proven` the guard blocked.

Since 03/08/2026 it includes the **Formato de relatório** section (report format)
— how many done-work replies left the `plain-report` pattern and for which reason.
Since 25/08/2026 `report-style-lint` blocks and the turn rewrites, so the section
separates (06/10/2026) the first write, which the block returns, from what
persisted after the rewrite and reached the user. The second is the number that
matters.

Since 17/10/2026 it includes the **Intenção da sessão** section (session intent;
`intent.*` events): how many sessions recorded an intent, in how many the cursor
advanced, how many ended on the last step and how many times you asked "where are
we / next step", each line with the arithmetic. It is the reading of the
criterion that decides whether cycle 2 of the intent goes in
(docs/estrategia-intencao-da-sessao.md).

## Steps

1. Run the aggregator, passing the user's arguments verbatim:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-metrics" $ARGUMENTS
   ```

2. Show the report to the user **in full** (it already comes out in pt-BR and
   formatted). Do not summarize on your own — the numbers are the product.

3. If the "Leituras sugeridas" (suggested readings) section points to something
   actionable (e.g. a repo that deserves `.claude/no-build`, a slow verify loop),
   highlight the ONE highest-return action and offer to run it. Do not run it
   without confirmation.

   **Exception: session already closed.** If `/common:wrap-up` has already run in
   this same conversation ("Safe to exit" has already been said), do NOT offer
   the action: record it (a section in `BACKLOG.md` when the repo is cepa; in the
   others, `python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-feedback" add --origem comando
   --alvo metrics "<the action and the reason>"`) and say in the report where it
   was recorded. The list at the end says "Nada pendente." and `**Pra você:**`
   says "nada". `report-style-lint.py` blocks a closed question there (category
   `pergunta-pos-wrap-up`).

4. If there are no events yet, explain that telemetry started accumulating in
   this version of the plugins and suggest running it again after a few days of
   use.

## Notes

- **Where the clock of ONE session went**: the aggregator does not serve — it
  counts events, it does not measure time. What measures it is `cepa-clock`,
  which reads the session's transcript (and each subagent's) and splits the clock
  into active waiting, build, normal bash and agent generation:

  ```
  python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-clock"            # the last session of this repo
  python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-clock" --emit     # and writes it to the ledger
  ```

  With `--emit`, the split shows up here as the "Relógio medido" (measured clock)
  section. Run it after a long routine that felt slow — that is how it was
  found, on 2026-08-26, that the bottleneck was the lead probing the disk (19% to
  52% of the clock) and not the build (3% to 17%).

- **Tokens** (since 12/09/2026): at the end of each session `session-registry`
  fires `cepa-tokens` in the background, which reads the transcript and writes a
  `token_usage` event (fresh context, cache read and output, per agent type,
  plus the size of what each tool returned). The "Tokens" section answers where
  the spend is: agent, repo or file reading. Sessions from before the install
  come in with a one-off sweep:

  ```
  python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-tokens" --todas --days 30 --emit
  ```

- Commands and skills can record their own events (they show up in "Eventos
  custom") via:
  `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/_telemetry.py" emit <event> key=value ...`
- The ledger keeps no payloads or full commands — only categories, statuses and
  short labels. Deleting `~/.claude/cepa-telemetry/` resets the history without
  breaking anything.
