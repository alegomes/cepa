#!/usr/bin/env python3
"""CS-3 of docs/spec/tres-portas-spec-epic.md (item 6 of O2'): the closing
step of `/common:spec` and of `/common:epic` tells the agent to repeat, in the
final report, the count the `spec-readiness-gate` showed when it let the file
through ("N decisões sem veredito neste arquivo", printed since CS-1).

The proof is by reading the command text, not a transcript (the spec's
"Decided without asking" says so): the mechanical count already lives in the
hook (CS-1); repeating it in the report is the command's instruction.

What each closing step must carry, read only inside that step (not anywhere in
the file, so an instruction parked in another section does not count):
- the literal the hook prints, "decisões sem veredito", quoted;
- the word "report" (where to repeat it);
- the zero case: the owner decided on 2026-11-06 that with no pending decision
  the closing prints "0" instead of staying quiet;
- the no-section case the hook also prints ("sem seção Decided without asking").

Run: python3 tests/test_closing_repeats_decision_count.py
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SPEC = REPO / "common" / "commands" / "spec.md"
EPIC = REPO / "common" / "commands" / "epic.md"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def section(text, heading_prefix):
    """Body of the `### <heading_prefix>...` step, up to the next `### ` or `## `."""
    lines = text.split("\n")
    start = None
    for i, line in enumerate(lines):
        if line.startswith("### ") and line[4:].startswith(heading_prefix):
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start, len(lines)):
        if lines[j].startswith("### ") or lines[j].startswith("## "):
            end = j
            break
    return "\n".join(lines[start:end])


def flat(body):
    return re.sub(r"\s+", " ", body or "")


def check_closing(label, body):
    check(f"{label}: closing step found", body is not None)
    body = flat(body)
    check(f"{label}: closing step quotes \"decisões sem veredito\"",
          "decisões sem veredito" in body, body[:120])
    check(f"{label}: closing step says to repeat it in the final report",
          re.search(r"(?i)repeat\b.{0,200}\bfinal report", body) is not None)
    check(f"{label}: closing step covers the zero case (prints 0, not silence)",
          re.search(r"\b0 decisões sem veredito\b", body) is not None)
    check(f"{label}: closing step covers the file without the section",
          "sem seção Decided without asking" in body)


def test_spec_closing():
    text = SPEC.read_text(encoding="utf-8")
    check_closing("spec.md step 5", section(text, "5. Close by the sieve"))


def test_epic_closing_ready():
    text = EPIC.read_text(encoding="utf-8")
    check_closing("epic.md step 5", section(text, "5. Close by the sieve"))


def test_epic_closing_closed():
    # `closed` is the second passage the hook counts (CS-1); its step says
    # to repeat the count too, at least by naming it.
    text = EPIC.read_text(encoding="utf-8")
    body = flat(section(text, "6. Close the Epic by its impact"))
    check("epic.md step 6: closing `closed` also repeats \"decisões sem veredito\"",
          "decisões sem veredito" in body and re.search(r"(?i)final report", body)
          is not None, body[:120])


def test_section_reader_is_scoped():
    # Sanity of the reader itself: an instruction outside the step is not seen.
    text = "### 5. Close by the sieve\nnothing\n### 6. Other\n\"decisões sem veredito\" final report"
    body = flat(section(text, "5. Close by the sieve"))
    check("reader: text of the next step is not counted as closing step",
          "decisões sem veredito" not in body)


def main():
    test_section_reader_is_scoped()
    test_spec_closing()
    test_epic_closing_ready()
    test_epic_closing_closed()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        sys.exit(1)
    print("\nall ok")


if __name__ == "__main__":
    main()
