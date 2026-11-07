#!/usr/bin/env python3
"""CS-9 of docs/spec/tres-portas-spec-epic.md (items 1 and 2): `/common:epic`
does what CS-8 made `/common:spec` do, in prose: names the sources it read,
puts the label and the path of a proposal taken from a file before the turn's
only question, challenges that proposal once before recording it, and never
marks `- [x]` without an owner utterance.

Proof by reading the command text common/commands/epic.md (the recorded
transcript lives in docs/proof/tres-portas-c1-CS-9-transcricao.md):
- step 2 names the three sources with their paths (discovery brief, planning-lead
  spec, "Decided without asking" of other specs/Epics), and the `**Fontes lidas:**`
  line rule;
- step 3: the label (`evidência` / `proposta de agente`) and the path go in the
  proposal, BEFORE the turn's only question, in prose (no menu); a file that
  answers a gap does not close it;
- step 3: an inherited decision goes to "Decided without asking" with its origin;
- step 4: an accepted labeled proposal is challenged once like any answer; no
  `- [x]` without an owner utterance;
- step 7: template header carries `**Fontes lidas:**` on its own line after the
  Status line, and the verbatim-labels sentence lists it;
- Constraints mirror the rule.

Run: python3 tests/test_epic_reads_sources.py
(EPIC_MD=<path> points it at another copy of epic.md; used for perturbation checks.)
"""

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EPIC = Path(os.environ.get("EPIC_MD") or REPO / "common" / "commands" / "epic.md")

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


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
    text = EPIC.read_text()

    # ---- Step 2: the three named sources -------------------------------
    p2 = step_paragraphs(text, "2. ")
    check("step 2 exists", bool(p2))
    intro = para(p2, "Before the first question")
    check("step 2 intro: three sources named, looked up by path",
          "Three sources are named, and you look for each by path" in intro,
          repr(intro[:160]))
    bullets = para(p2, "- the `discovery` delivery brief")
    b_brief = bullets.split("- the `planning-lead`", 1)[0]
    b_pl = bullets.split("- the `planning-lead`", 1)[-1].split("- the \"Decided", 1)[0] \
        if "- the `planning-lead`" in bullets else ""
    b_dec = ("Decided" + bullets.split("- the \"Decided", 1)[1]) if "- the \"Decided" in bullets else ""
    check("brief bullet: path docs/discovery/<card>/handoff.md, by epic-briefer",
          "`docs/discovery/<card>/handoff.md`" in b_brief and "`epic-briefer`" in b_brief)
    check("brief bullet: carries the audit, so it is **evidence**",
          "It carries the audit, so it is **evidence**" in b_brief)
    check("planning-lead bullet: spec/<slug>.md or specs/<slug>.md at the repo root",
          "`spec/<slug>.md`" in b_pl and "`specs/<slug>.md`" in b_pl
          and "at the repo root" in b_pl)
    check("planning-lead bullet: decision taken by an agent, not by the owner",
          "taken in another interview by an agent, not by the owner" in b_pl)
    check("third bullet: Decided without asking in docs/spec/ and docs/epics/",
          "Decided without asking\" section" in b_dec
          and "`docs/spec/`" in b_dec and "`docs/epics/`" in b_dec)

    fontes_p = para(p2, "Write the paths")
    check("Fontes paragraph: paths actually read, that informed the Epic",
          "paths you actually read, and that informed the Epic" in fontes_p,
          repr(fontes_p[:160]))
    check("Fontes paragraph: on the **Fontes lidas:** line of the header, once",
          "`**Fontes lidas:**` line of the header: once" in fontes_p)
    check("Fontes paragraph: updated when another file is read",
          "updated when another file is read" in fontes_p)
    check("Fontes paragraph: never a label suffix on a ladder cell or a heading",
          "Never a label suffix on a ladder cell or a heading" in fontes_p)

    # ---- Step 3: label + path before the only question ------------------
    p3 = step_paragraphs(text, "3. ")
    lab = para(p3, "**A proposal taken from one of these files")
    check("step 3 labels paragraph exists", bool(lab))
    check("labels paragraph: carries its label and its path",
          "**A proposal taken from one of these files carries its label and its path**"
          in lab)
    check("labels paragraph: before the turn's only question",
          "in the proposal sentence, before the turn's only question" in lab)
    check("labels paragraph: evidência (brief) / proposta de agente (planning-lead)",
          "`evidência` (from the discovery brief) or `proposta de agente` (from the "
          "`planning-lead` spec)" in lab)
    check("labels paragraph: prose example with label and path before the question",
          re.search(r"Minha proposta \(`evidência`, docs/discovery/<card>/handoff\.md\)"
                    r"[^?]*\. [^?]*\?", lab) is not None)
    check("labels paragraph: in prose, never a list of options nor a ladder cell",
          "The label goes in the prose, never as a list of options and never in a "
          "ladder cell" in lab)
    check("labels paragraph: a file that answers a gap does not close it",
          "A file that answers a gap does not close it: the question is still asked, "
          "with the file's answer as the proposal" in lab)
    check("labels paragraph: the rule holds in every turn, the challenge turn included",
          "The rule holds in every turn, the challenge turn of step 4 included: any "
          "proposal or argument drawn from one of these files names the label and the path"
          in lab)
    check("labels paragraph: even when the file was already cited earlier",
          "even when the file was already cited in an earlier turn" in lab)
    check("labels paragraph: what a file settles goes to Decided without asking, labeled",
          "is never announced as \"não vou perguntar o que eles já respondem\"" in lab
          and "as a line of \"Decided without asking\" with the label and the path" in lab)
    check("labels paragraph: the answer is challenged once like any other",
          "challenged once like any other (step 4)" in lab)

    # the labels paragraph comes after the generic proposal paragraph
    i_prop = next((i for i, p in enumerate(p3)
                   if p.startswith("**Propose the answer along with the question**")), -1)
    i_lab = next((i for i, p in enumerate(p3)
                  if p.startswith("**A proposal taken from one of these files")), -1)
    check("labels paragraph follows 'Propose the answer along with the question'",
          0 <= i_prop < i_lab, f"positions {i_prop},{i_lab}")

    dec = para(p3, "The test for whether something becomes a question")
    i_rec = dec.find('record it in "Decided without asking"')
    i_inh = dec.find("A decision inherited from the `planning-lead` spec")
    i_there = dec.find("goes there with its origin, never as an answered `- [x]` question")
    check("inherited decision: goes to Decided without asking with its origin",
          0 <= i_rec < i_inh < i_there, f"positions {i_rec},{i_inh},{i_there}")
    check("inherited decision: model line with proposta de agente and Vete aqui",
          "`- <decision> — proposta de agente, specs/<slug>.md. Vete aqui se discordar.`"
          in dec)

    # ---- Step 4: challenge the accepted proposal, [x] only after owner ---
    p4 = step_paragraphs(text, "4. ")
    acc = para(p4, "A proposal the owner accepts")
    check("step 4: an accepted proposal is an answer, challenged once too",
          "A proposal the owner accepts" in acc
          and "is an answer like any other, and is challenged once too" in acc,
          repr(acc[:160]))
    check("step 4: a labeled proposal is never written down without the challenge",
          "a labeled proposal is never written down without having gone through "
          "the challenge" in acc)
    check("step 4: the file agreeing with the owner is not the challenge",
          "The file agreeing with the owner is not the challenge." in acc)
    i_one = next((i for i, p in enumerate(p4) if p.startswith("When the owner answers")), -1)
    i_acc = next((i for i, p in enumerate(p4) if p.startswith("A proposal the owner accepts")), -1)
    check("step 4: accepted-proposal rule follows 'When the owner answers'",
          0 <= i_one < i_acc, f"positions {i_one},{i_acc}")
    line_p = para(p4, "A line turns")
    check("step 4: [x] only after an owner utterance that answers it",
          "A line turns `- [x]` only after an owner utterance in the conversation "
          "that answers it" in line_p, repr(line_p[:160]))
    check("step 4: what files said is a proposal, never an answer",
          "What the files said is a proposal, never an answer" in line_p)
    check("step 4: no hook enforces it",
          "No hook enforces this" in line_p)

    # ---- Step 7: template and verbatim labels ---------------------------
    m = re.search(r"### 7\. .*?(?=\n## Constraints)", text, re.S)
    s7 = m.group(0) if m else ""
    fence = re.search(r"```markdown\n(.*?)\n```", s7, re.S)
    tpl = fence.group(1) if fence else ""
    tlines = tpl.split("\n")
    i_status = next((i for i, l in enumerate(tlines) if l.startswith("**Status:**")), -1)
    i_fontes = next((i for i, l in enumerate(tlines) if l.startswith("**Fontes lidas:**")), -1)
    i_int = next((i for i, l in enumerate(tlines) if l.startswith("## Intenção")), -1)
    check("template: Fontes lidas on its own line right after Status, before Intenção",
          i_status >= 0 and i_fontes == i_status + 1 and i_fontes < i_int,
          f"positions {i_status},{i_fontes},{i_int}")
    check("template: Status line itself carries no Fontes lidas",
          i_status >= 0 and "Fontes lidas" not in tlines[i_status])
    check("template Fontes lidas placeholder: paths actually read",
          i_fontes >= 0 and "paths actually read" in tlines[i_fontes])
    verb = para(step_paragraphs(text, "7. "), "The document is written in pt-BR")
    check("step 7 verbatim sentence keeps the **Fontes lidas:** label",
          "the `**Status:**` and `**Fontes lidas:**` labels" in verb, repr(verb[:220]))

    # ---- Constraints ----------------------------------------------------
    cons = text.split("## Constraints", 1)[-1]
    cb = next((norm(b) for b in cons.split("\n- ")
               if b.startswith("**Proposals from files are labeled")), "")
    check("constraint: Proposals from files are labeled, answers come from the owner",
          cb.startswith("**Proposals from files are labeled, answers come from the owner.**"))
    check("constraint: label + path before the turn's question",
          "`evidência` or `proposta de agente` plus the path, before the turn's question"
          in cb, repr(cb[:200]))
    check("constraint: challenged once like any answer",
          "is challenged once like any answer" in cb)
    check("constraint: nothing becomes [x] without an owner utterance",
          "nothing becomes `- [x]` without an owner utterance" in cb)

    # The epic still forbids AskUserQuestion (CS-9 is "in prose")
    check("still no AskUserQuestion allowed",
          "never `AskUserQuestion`" in norm(cons))

    if FAILURES:
        print(f"\n{len(FAILURES)} FAILED")
        sys.exit(1)
    print("\nall ok")


if __name__ == "__main__":
    main()
