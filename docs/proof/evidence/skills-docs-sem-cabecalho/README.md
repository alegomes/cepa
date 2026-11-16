# skills-docs-sem-cabecalho — what a real Claude Code session lists

Precondition of the item (finding CR10 of docs/reviews/2026-11-12-painel-lacunas-ecc.md):
a test showing Claude Code does not load the 2 skills before the fix.

Probe, run from /tmp on 2026-11-16 with Claude Code 2.1.325:

    claude -p "Reply with the single word: ok" --plugin-dir <docs-topology dir> \
        --model haiku --max-turns 1 --output-format stream-json --verbose

and the `system`/`init` event filtered to the `docs:` entries.

- `session-init-before.json`: `<dir>` = `git archive 24da38f^ docs-topology`
  (docs 0.3.3, no header block). `skills` has no `docs:` entry; the two names
  show up only under `slash_commands`, that is, typable by a person but not
  offered to the model as skills.
- `session-init-after.json`: `<dir>` = the tree at 24da38f (docs 0.3.4).
  `skills` lists `docs:diataxis-discipline` and `docs:how-why-boundary`.
