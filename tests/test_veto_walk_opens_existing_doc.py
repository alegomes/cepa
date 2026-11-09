#!/usr/bin/env python3
"""CS-7 of docs/spec/tres-portas-spec-epic.md (item 4 of O2'): `/common:spec
--continuar`/`--fechar` and `/common:epic` on an existing document open with the
"caminhada do veto" (veto walk) before resuming the interview or the sieve.

Proof by reading the command text. Read only inside step 1 (the step that opens
an existing document), which must come before the interview step:
- the call to `cepa-plan decisions` (lists the decisions without a verdict);
- the call to `cepa-plan verdict` (the only writer of the marker; the agent never
  writes the marker by hand);
- the pace: up to four per round in spec.md, one per turn in epic.md;
- a skipped decision does not block ("pular não trava") and stays without marker.

Run: python3 tests/test_veto_walk_opens_existing_doc.py
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
    lines = text.split("\n")
    start = None
    for i, line in enumerate(lines):
        if line.startswith("### ") and line[4:].startswith(heading_prefix):
            start = i
            break
    if start is None:
        return None, None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("### ") or lines[j].startswith("## "):
            end = j
            break
    return start, re.sub(r"\s+", " ", "\n".join(lines[start + 1:end]))


def check_common(label, text, open_prefix, interview_prefix):
    o_pos, body = section(text, open_prefix)
    i_pos, _ = section(text, interview_prefix)
    check(f"{label}: opening step found", body is not None)
    check(f"{label}: interview step found", i_pos is not None)
    check(f"{label}: opening step comes before the interview step",
          o_pos is not None and i_pos is not None and o_pos < i_pos)
    body = body or ""
    check(f"{label}: names the veto walk", "caminhada do veto" in body)
    check(f"{label}: calls `cepa-plan decisions`", "cepa-plan decisions" in body)
    check(f"{label}: calls `cepa-plan verdict`", "cepa-plan verdict" in body)
    check(f"{label}: the three verdicts are named",
          all(w in body for w in ("mantida", "vetada", "refinada")))
    check(f"{label}: agent never writes the marker by hand",
          re.search(r"(?i)never\b.{0,80}\bby hand", body) is not None)
    check(f"{label}: skipped decision does not block",
          re.search(r"(?i)skipped decision.{0,80}does not block", body) is not None)
    check(f"{label}: skipped decision stays without a marker",
          re.search(r"(?i)without (a )?marker", body) is not None)
    check(f"{label}: Status does not change by veto",
          re.search(r"(?i)\bStatus\b.{0,60}(does not|doesn't) change", body) is not None)
    check(f"{label}: passes on the R2 warning of verdict",
          "já virou código na fila" in body)
    return body


def check_order(label, path, walk, later):
    text = re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))
    i, j = text.find(walk), text.find(later)
    check(f"{label}: walk paragraph comes before {later!r}",
          i != -1 and j != -1 and i < j, f"{i} {j}")


def check_numbers(label, body):
    check(f"{label}: use the number as `cepa-plan decisions` prints it, never renumber",
          "exactly as `cepa-plan decisions` prints it" in body and "never renumber" in body)


def check_pins(label, body, doc):
    check(f"{label}: the call line runs `cepa-plan decisions {doc}`",
          f"run `cepa-plan decisions {doc}`" in body)
    check(f"{label}: the record line is `cepa-plan verdict {doc} <n> mantida|vetada|refinada`",
          f"`cepa-plan verdict {doc} <n> mantida|vetada|refinada`" in body)
    check(f"{label}: walks only the decisions without a verdict",
          "Walk only the ones without" in body)
    check(f"{label}: a skipped decision is offered again next time",
          re.search(r"(?i)\bit is offered again\b|\boffers it again\b", body) is not None)
    check(f"{label}: `vetada` needs `--reason`",
          re.search(r"`vetada`\s+needs\s+`--reason`", body) is not None)
    check(f"{label}: `refinada` needs `--text`",
          re.search(r"`refinada`\s+needs\s+`--text`", body) is not None)


def test_spec():
    text = SPEC.read_text(encoding="utf-8")
    body = check_common("spec.md", text, "1. Locate or open", "3. Interrogate")
    check("spec.md: limit of four per round",
          re.search(r"(?i)up to four\b.{0,60}\bper round", body) is not None)
    check_numbers("spec.md", body)
    check_order("spec.md", SPEC, "The veto walk (caminhada do veto).", "write the skeleton with")
    check_pins("spec.md", body, "docs/spec/<slug>.md")
    check("spec.md: --continuar/--fechar bullet routes through the walk first",
          re.search(r"`--continuar <slug>` or `--fechar <slug>`: read the file, open with the "
                    r"veto walk below, and only then go to step 4 \(continue\) or 5 \(close\)", body)
          is not None)
    check("spec.md: covers --continuar and --fechar",
          "--continuar" in body and "--fechar" in body)


def test_epic():
    text = EPIC.read_text(encoding="utf-8")
    body = check_common("epic.md", text, "1. Open or resume", "3. Ask")
    check_numbers("epic.md", body)
    check_order("epic.md", EPIC, "The veto walk (caminhada do veto).", "Otherwise (the file does not exist)")
    check_pins("epic.md", body, "docs/epics/<name>.md")
    check("epic.md: walk comes before the first gap and before the sieve",
          "Before the first gap and before the sieve, run `cepa-plan decisions" in body)
    check("epic.md: limit of one per turn",
          re.search(r"(?i)\bone\b.{0,30}\bper turn\b", body) is not None)


def walk_paragraph(text):
    """The veto walk paragraph, whitespace-normalized (from its bold lead to the next blank line)."""
    m = re.search(r"\*\*The veto walk \(caminhada do veto\)\.\*\*.*?(?:\n\s*\n|\Z)", text, re.S)
    return re.sub(r"\s+", " ", m.group(0)).strip() if m else ""


MARKER = "`· mantida em` / `· vetada em` / `· refinada em`"
R2 = ('If `cepa-plan verdict` prints "já virou código na fila" (the file is the `source:` of a '
      "derived queue), pass the warning on to the owner as it came.")


def check_sentences(label, walk, sentences):
    check(f"{label}: walk paragraph found", walk != "")
    for name, lit in sentences:
        check(f"{label}: {name}", lit in walk, lit)


def test_walk_sentences():
    spec = walk_paragraph(SPEC.read_text(encoding="utf-8"))
    epic = walk_paragraph(EPIC.read_text(encoding="utf-8"))
    common = [
        ("R2 warning is passed on to the owner, as it came", R2),
        ("`Never write the marker by hand` is its own sentence",
         "never renumber. Never write the " + MARKER + " marker by hand:"),
        ("`Record ... in the same turn`", "in the same turn with `cepa-plan verdict"),
        ("a vetoed decision becomes an open question only if the owner says so",
         "`Status` does not change by veto; a vetoed decision becomes an open question "
         "only if the owner says so in the same turn."),
        ("with no decision without a verdict, say so in one line",
         "With no decision without a verdict, say so in one line and go on."),
    ]
    check_sentences("spec.md", spec, common + [
        ("asks the owner for one answer per decision",
         "and ask the owner for one answer per decision: keep it (`mantida`), veto it "
         "(`vetada`, with the reason) or refine it (`refinada`, with the new text)."),
        ("applies `On an existing file`", "On an existing file (`--continuar`, `--fechar`, "
         'or the "continue that one" answer), before resuming the interview or the sieve, '
         "run `cepa-plan decisions docs/spec/<slug>.md`."),
        ("offers `mantida` in the walk itself (three verdicts)",
         "keep it (`mantida`), veto it (`vetada`, with the reason) or refine it (`refinada`"),
    ])
    check_sentences("epic.md", epic, common + [
        ("offers `mantida` in the walk itself (three verdicts)",
         "ask the owner to keep it (`mantida`), veto it (`vetada`, with the reason) or refine it "
         "(`refinada`, with the new text)."),
    ])
    spec_text = re.sub(r"\s+", " ", SPEC.read_text(encoding="utf-8"))
    check("spec.md: `When creating a new file` is its own paragraph after the walk",
          "With no decision without a verdict, say so in one line and go on. "
          "When creating a new file, write the skeleton with" in spec_text)
    raw = SPEC.read_text(encoding="utf-8")
    w = raw.find("**The veto walk (caminhada do veto).**")
    h3 = raw.find("### 3. Interrogate")
    sieve = raw.find("do two different answers")
    check("spec.md: walk paragraph comes before the step 3 heading and the sieve text",
          w != -1 and h3 != -1 and sieve != -1 and w < h3 and w < sieve, f"{w} {h3} {sieve}")
    epic_text = re.sub(r"\s+", " ", EPIC.read_text(encoding="utf-8"))
    check("epic.md: routing sentence opens with the veto walk and then resumes",
          "read it whole, open with the veto walk below, and then resume from the first gap"
          in epic_text)


if __name__ == "__main__":
    test_spec()
    test_epic()
    test_walk_sentences()
    if FAILURES:
        print(f"\n{len(FAILURES)} failed")
        sys.exit(1)
    print("\nall passed")
