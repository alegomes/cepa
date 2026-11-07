#!/usr/bin/env python3
"""CS-8 of docs/spec/tres-portas-spec-epic.md (items 1 and 2): `/common:spec`
names the sources it read, labels every proposal taken from them, and never marks
`- [x]` without an owner utterance.

Proof by reading the command text common/commands/spec.md:
- step 2 names the three sources with their paths (discovery brief, planning-lead
  spec, "Decided without asking" of other specs/Epics);
- the step-6 template header carries `**Fontes lidas:**` after `**Aberta em:**`;
- the two labels `evidência` / `proposta de agente`, the proposal as the
  RECOMMENDED option with the path;
- step 4: no `- [x]` without an owner answer;
- an inherited decision goes to "Decided without asking" with its origin;
- the criterion line (`### CS-<n>:`) carries no label.

Run: python3 tests/test_spec_reads_sources.py
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SPEC = REPO / "common" / "commands" / "spec.md"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def section(text, heading_prefix):
    lines = text.split("\n")
    start = None
    for i, line in enumerate(lines):
        if line.startswith("### ") and line[4:].startswith(heading_prefix):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("### ") or lines[j].startswith("## "):
            end = j
            break
    return re.sub(r"\s+", " ", "\n".join(lines[start + 1:end]))


def main():
    text = SPEC.read_text()
    flat = re.sub(r"\s+", " ", text)

    step2 = section(text, "2. ")
    step3 = section(text, "3. ")
    step4 = section(text, "4. ")
    step6_raw = None
    m = re.search(r"### 6\. .*?(?=\n### 7\.)", text, re.S)
    if m:
        step6_raw = m.group(0)

    check("step 2 exists", step2 is not None)
    s2 = step2 or ""
    for needle in ("docs/discovery/", "handoff.md", "specs/", "spec/",
                   "docs/epics/", "Decided without asking"):
        check(f"step 2 names {needle}", needle in s2)
    check("step 2 names epic-briefer and planning-lead",
          "epic-briefer" in s2 and "planning-lead" in s2)

    # Template header
    check("step 6 exists", step6_raw is not None)
    tpl = step6_raw or ""
    i_aberta = tpl.find("**Aberta em:**")
    i_fontes = tpl.find("**Fontes lidas:**")
    i_como = tpl.find("## Como chegamos aqui", i_aberta if i_aberta >= 0 else 0)
    check("template has Fontes lidas between Aberta em and Como chegamos aqui",
          0 <= i_aberta < i_fontes < i_como,
          f"positions {i_aberta},{i_fontes},{i_como}")

    # Fontes lidas rule: once, header, paths actually read
    check("Fontes lidas rule: once, in the header",
          re.search(r"Fontes lidas:\*\*[^.]*", flat) is not None
          and "once" in flat.split("Fontes lidas:**", 1)[-1][:600])

    # Labels
    check("label evidência", "`evidência`" in flat)
    check("label proposta de agente", "`proposta de agente`" in flat)
    check("proposal is the RECOMMENDED option with the path",
          re.search(r"recommended option", flat, re.I) is not None
          and re.search(r"(label|rotulo).{0,80}path|path.{0,80}label", flat, re.I)
          is not None)
    check("prose form: Recomendo X (`evidência`, path)",
          re.search(r"Recomendo X \(`evidência`, docs/discovery/", flat) is not None)
    check("a file answering does not close the question",
          re.search(r"does not close|not close the question|still asked", flat, re.I)
          is not None)

    # Step 4: no [x] without owner answer
    s4 = step4 or ""
    check("step 4 exists", step4 is not None)
    check("step 4: [x] only after an owner utterance",
          "- [x]" in s4 and re.search(r"owner", s4) is not None
          and re.search(r"only after|never .{0,40}- \[x\]|nothing becomes", s4, re.I)
          is not None)
    check("step 4: files are recommendation, never an answer",
          re.search(r"recommendation, never an answer", s4) is not None)
    check("step 4: no hook enforces it",
          re.search(r"no hook", s4, re.I) is not None)

    # Inherited decision
    scope = (step3 or "") + " " + s4
    check("inherited decision goes to Decided without asking with origin",
          "Decided without asking" in scope
          and "proposta de agente, specs/" in scope
          and "Vete aqui se discordar" in scope)
    check("inherited decision is never an answered [x]",
          re.search(r"never as an answered", scope, re.I) is not None)

    # Criterion line carries no label
    check("criterion line carries no label",
          re.search(r"never a (label )?suffix on a criterion line", flat, re.I)
          is not None and "### CS-<n>:" in flat)
    check("template criterion line has no label",
          re.search(r"### CS-1: <[^>]*>\s*$", tpl, re.M) is not None)

    # Constraint
    cons = text.split("## Constraints", 1)[-1]
    check("constraint mirrors labels and no [x] without owner answer",
          "`evidência`" in cons and "- [x]" in cons)

    if FAILURES:
        print(f"\n{len(FAILURES)} FAILED")
        sys.exit(1)
    print("\nall ok")


if __name__ == "__main__":
    main()
