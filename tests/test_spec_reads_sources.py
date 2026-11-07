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
(SPEC_MD=<path> points it at another copy of spec.md; used for perturbation checks.)
"""

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SPEC = Path(os.environ.get("SPEC_MD") or REPO / "common" / "commands" / "spec.md")

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


def norm(s):
    return re.sub(r"\s+", " ", s)


def step_paragraphs(text, heading_prefix):
    """Blank-line separated blocks of one `### ` step, whitespace-flattened."""
    lines = text.split("\n")
    start = next((i for i, l in enumerate(lines)
                  if l.startswith("### ") and l[4:].startswith(heading_prefix)), None)
    if start is None:
        return []
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("### ") or lines[j].startswith("## "):
            end = j
            break
    blocks = "\n".join(lines[start + 1:end]).split("\n\n")
    return [norm(b).strip() for b in blocks if b.strip()]


def para(paras, starts):
    for p in paras:
        if p.startswith(starts):
            return p
    return ""


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

    # Step 2, scoped to its paragraphs
    paras2 = step_paragraphs(text, "2. ")
    intro = para(paras2, "Before the first round")
    bullets = para(paras2, "- the `discovery` delivery brief")
    fontes_p = para(paras2, "Write the paths")
    labels_p = para(paras2, "Every proposal taken from one of these files")
    bullet_brief = bullets.split("- the `planning-lead`", 1)[0]
    bullet_pl = bullets.split("- the `planning-lead`", 1)[-1].split("- the \"Decided", 1)[0]
    check("step 2 intro: three sources named, looked up by path",
          "Three sources are named, and you look for each by path" in intro)
    bullet_pl_full = "- the `planning-lead`" + bullet_pl
    bullet_dec = "Decided" + bullets.split("- the \"Decided", 1)[1] if "- the \"Decided" in bullets else ""
    check("step 2 planning-lead bullet: names planning-lead",
          "- the `planning-lead` spec," in bullet_pl_full and "`planning-lead`" in bullet_pl_full)
    check("step 2 planning-lead bullet: both spec/<slug>.md and specs/<slug>.md",
          "`spec/<slug>.md`" in bullet_pl and "`specs/<slug>.md`" in bullet_pl)
    check("step 2 planning-lead bullet: at the repo root",
          "at the repo root" in bullet_pl)
    check("step 2 third bullet: Decided without asking in docs/spec/ and docs/epics/",
          "Decided without asking" in bullet_dec
          and "`docs/spec/`" in bullet_dec and "`docs/epics/`" in bullet_dec)
    check("step 2 brief bullet: path docs/discovery/<card>/handoff.md",
          "`docs/discovery/<card>/handoff.md`" in bullet_brief)
    check("step 2 brief bullet: carries the audit, so it is **evidence**",
          "It carries the audit, so it is **evidence**" in bullet_brief)
    check("step 2 planning-lead bullet: decision taken by an agent, not by the owner",
          "taken in another interview by an agent, not by the owner" in bullet_pl)
    check("step 2 Fontes paragraph: paths actually read, that informed the specification",
          "paths you actually read, and that informed the specification" in fontes_p)
    check("step 2 Fontes paragraph: updated when another file is read",
          "updated when another file is read" in fontes_p)
    check("step 2 labels paragraph: evidência and proposta de agente",
          "with a label and the file path: `evidência` (from the discovery brief)"
          in labels_p
          and "or `proposta de agente` (from the `planning-lead` spec)" in labels_p)
    check("step 2 labels paragraph: proposal becomes the RECOMMENDED option",
          "The proposal becomes the RECOMMENDED option" in labels_p)
    check("step 2 labels paragraph: AskUserQuestion description carries label and path",
          "in `AskUserQuestion`, the recommended option's description carries "
          "the label and the path" in labels_p)

    # Template header
    check("step 6 exists", step6_raw is not None)
    fence = re.search(r"```markdown\n(.*?)\n```", step6_raw or "", re.S)
    check("step 6 has the fenced markdown template", fence is not None)
    tpl = fence.group(1) if fence else ""
    i_aberta = tpl.find("**Aberta em:**")
    i_fontes = tpl.find("**Fontes lidas:**")
    i_como = tpl.find("## Como chegamos aqui", i_aberta if i_aberta >= 0 else 0)
    check("template has Fontes lidas between Aberta em and Como chegamos aqui",
          0 <= i_aberta < i_fontes < i_como,
          f"positions {i_aberta},{i_fontes},{i_como}")

    # Step 6: the verbatim-labels sentence lists Fontes lidas
    verbatim_p = para(step_paragraphs(text, "6. "), "The document is written in pt-BR")
    vm = re.search(r"Keep the headings and the (.*?) labels verbatim", verbatim_p)
    check("step 6 verbatim-labels sentence lists **Fontes lidas:**",
          vm is not None and "`**Fontes lidas:**`" in vm.group(1),
          "sentence not found" if vm is None else "")
    fline = next((l for l in tpl.split("\n") if l.startswith("**Fontes lidas:**")), "")
    check("template Fontes lidas line: placeholder says paths actually read",
          "paths actually read" in fline, repr(fline))

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
    line_p = para(step_paragraphs(text, "4. "), "A line turns")
    check("step 4 'A line turns' paragraph: only after an owner utterance",
          "only after an owner utterance in the conversation that answers it"
          in line_p, repr(line_p[:120]))
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
    dec_p = para(step_paragraphs(text, "3. "), "The test for whether something")
    i_rec = dec_p.find('record the decision in the "Decided without asking" section')
    i_inh = dec_p.find("A decision inherited from the `planning-lead` spec")
    i_there = dec_p.find("goes there with its origin, never as an answered `- [x]` question")
    check("inherited decision: 'there' resolves to Decided without asking, with its origin",
          0 <= i_rec < i_inh < i_there, f"positions {i_rec},{i_inh},{i_there}")
    check("inherited decision: 'with its origin'", "with its origin" in dec_p)
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
