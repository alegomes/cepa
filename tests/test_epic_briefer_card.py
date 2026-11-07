#!/usr/bin/env python3
"""CS-10 of docs/spec/tres-portas-spec-epic.md (item 7): the engineer-board card
the `epic-briefer` creates points at the brief's path AND the repository where
it lives, and the "Brief, not Epic" rule names both readers of the brief.

Proof by reading discovery/agents/epic-briefer.md (the discovery plugin does not
run in Cepa, R4, so there is no session to record):
- step 5 card description template: a repository line next to the
  `Delivery brief:` line, filled from `git remote get-url origin`, falling back
  to the local path only when there is no remote;
- the card template carries no literal command (`/common:epic ...`): the Epic
  `<slug>` is chosen in the interview (D6);
- the "Brief, not Epic" rule names `epic-author` (board) and `/common:epic`
  (file) as the two readers.

Run: python3 tests/test_epic_briefer_card.py
(EPIC_BRIEFER_MD=<path> points it at another copy; used for perturbation checks.)
"""

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOC = Path(os.environ.get("EPIC_BRIEFER_MD")
           or REPO / "discovery" / "agents" / "epic-briefer.md")

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def norm(s):
    return re.sub(r"\s+", " ", s)


def main():
    text = DOC.read_text(encoding="utf-8")

    # ---- Step 5: the card description template --------------------------
    sec = re.search(r"## Engineer-board card delegation \(step 5\)(.*?)(?=\n## |\Z)",
                    text, re.S)
    s5 = sec.group(1) if sec else ""
    check("step-5 delegation section exists", bool(s5))
    fence = re.search(r"```\n(.*?)\n\s*> ```", s5, re.S)
    tpl = fence.group(1) if fence else ""
    tlines = [re.sub(r"^\s*>\s?", "", l) for l in tpl.split("\n")]
    check("card template fence found", bool(tpl))

    i_brief = next((i for i, l in enumerate(tlines) if l.startswith("Delivery brief:")), -1)
    i_repo = next((i for i, l in enumerate(tlines) if l.startswith("Repository:")), -1)
    check("template keeps the Delivery brief: line with the handoff path",
          i_brief >= 0 and "docs/discovery/<discovery-key>/handoff.md" in tlines[i_brief])
    check("template has a Repository: line right next to Delivery brief:",
          i_repo >= 0 and abs(i_repo - i_brief) == 1, f"positions {i_brief},{i_repo}")
    repo_line = tlines[i_repo] if i_repo >= 0 else ""
    check("Repository: line placeholder names the remote URL",
          "<git remote get-url origin>" in repo_line, repr(repo_line))
    check("Repository: line placeholder names the local path fallback",
          "local path" in repo_line, repr(repo_line))

    s5n = norm(s5)
    check("step 5 says how to fill it: `git remote get-url origin`",
          "`git remote get-url origin`" in s5n)
    check("step 5 says the local path is used only when there is no remote",
          "only when there is no remote" in s5n)

    check("card template has no literal /common:epic command",
          "/common:epic" not in tpl, repr(tpl))
    check("card template has no slash command at all",
          not re.search(r"(^|\s)/[a-z-]+:[a-z-]+", tpl), repr(tpl))
    check("step 5: run it in the repo where the brief was written",
          "in the repo where you wrote the brief" in s5n)
    check("step 5: fallback is git rev-parse --show-toplevel",
          "`git rev-parse --show-toplevel`" in s5n)
    check("step 5 says no literal command goes on the card",
          "no literal command" in s5n)
    check("step 5 leaves the Epic slug to the interview",
          "chosen in the interview" in s5n)

    # The workflow step 5 mentions the repository too
    wf = re.search(r"## Workflow(.*?)(?=\n## )", text, re.S)
    wf5 = next((norm(l) for l in (wf.group(1) if wf else "").split("\n")
                if l.startswith("5. ")), "")
    check("workflow step 5: card links the brief path and its repository",
          "brief path" in wf5 and "repository" in wf5, repr(wf5))

    # ---- Rules: Brief, not Epic -----------------------------------------
    rule = next((norm(b) for b in text.split("\n- ")
                 if b.startswith("**Brief, not Epic.**")), "")
    check("rule Brief, not Epic exists", bool(rule))
    check("rule names epic-author as a reader (board)",
          "`epic-author`" in rule and "board" in rule, repr(rule[:300]))
    check("rule names /common:epic as a reader (file)",
          "`/common:epic`" in rule and "file" in rule, repr(rule[:300]))
    check("rule says both readers",
          "two readers" in rule, repr(rule[:300]))
    check("rule names docs/epics/<slug>.md as /common:epic's output",
          "`docs/epics/<slug>.md`" in rule, repr(rule[:300]))
    link = next((norm(b) for b in text.split("\n- ")
                 if b.startswith("**Link, don't clone")), "")
    check("Link, don't clone rule links the repository where the brief lives",
          "the repository where the brief lives" in link, repr(link[:200]))
    check("rule still forbids bypassing the boundary",
          "Don't bypass that boundary" in rule)

    if FAILURES:
        print(f"\n{len(FAILURES)} FAILED")
        sys.exit(1)
    print("\nall ok")


if __name__ == "__main__":
    main()
