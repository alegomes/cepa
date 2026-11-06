"""The two sections of a queue item that went to the owner.

A blocked item carries two texts, for two readers:

- `evidence` is the AGENT section. Card keys, commit hashes, gate verdicts and
  file paths belong there, because the next agent needs them to resume.
- `owner_summary` is the HUMAN section, for someone who never opened the card:
  what was asked (`pedido`), what is ready (`pronto`), what stops it
  (`impede`), and what each answer to the question leads to (`se_sim`,
  `se_nao`). The question itself stays in `owner_question`.

Until 2026-11-01 only the first one existed. The end-of-run screen showed the
owner "travou por algo de fora do código" and, on `[e]`, a log with 8 commit
hashes and 5 gate names; the real reason (the card's rule and the final
checker's rule disagree) was in its sixth sentence (WEGO-2381, run
2026-10-31-1033). The owner: "Sua escrita é enigmática, cheia de códigos e
pressupostos de entendimento."

`problems()` is the rule of the human section, used by `cepa-plan finish`
(refuses) and by `cepa-until decide` (warns about the analysis's text).
"""
import re

# (key in owner_summary, CLI flag, label on the end-of-run screen)
FIELDS = (
    ("pedido", "--asked", "Era para"),
    ("pronto", "--ready", "Já está pronto"),
    ("impede", "--blocker", "Parou porque"),
    ("se_sim", "--if-yes", "Se sim"),
    ("se_nao", "--if-no", "Se não"),
)

# The Portuguese flag each English one replaced. Still accepted by `cepa-plan
# finish`; the keys inside `owner_summary` (column 1 above) are stored data and
# keep their Portuguese names.
OLD_FLAGS = {
    "--asked": "--pedido",
    "--ready": "--pronto",
    "--blocker": "--impede",
    "--if-yes": "--se-sim",
    "--if-no": "--se-nao",
}

WORDS_PER_FIELD = 30

# Each pattern with the reason the owner reads. The first one keeps the
# wording `cepa-until` already used for the question.
JARGON = (
    (re.compile(r"until/|session/|\b\w+Test\b"
                r"|\w+\.(?:py|java|yaml|yml|md|sh|json)\b|\(a alternativa"),
     "nome de branch, classe de teste ou arquivo"),
    (re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b"
                r"|\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b"),
     "código de card ou de commit"),
    (re.compile(r"\b(?:validation-lead|proof-reviewer|completion-auditor"
                r"|acceptance-gate|security-reviewer|code-reviewer"
                r"|engineering-lead|atlassian-expert|ui-proof-reviewer)\b"
                r"|\b(?:READY-WITH-CAVEATS|READY-TO-SHIP|CLEAN-WITH-NOTES"
                r"|PROVEN|UNPROVEN|NEEDS-HUMAN|INCOMPLETE|COMPLETE|APPROVE"
                r"|REJECT)\b"),
     "nome de verificador ou veredito interno"),
    (re.compile(r"`"), "trecho de código entre crases"),
)


def jargon(text):
    """The reasons the text is not lay, in the order of JARGON."""
    text = " ".join(str(text or "").split())
    return [reason for rx, reason in JARGON if rx.search(text)]


def problems(text, limit=WORDS_PER_FIELD):
    """What the text breaks of the human-section rule, or [] when it is fine."""
    text = " ".join(str(text or "").split())
    out = []
    n = len(text.split())
    if n > limit:
        out.append(f"{n} palavras, o limite é {limit}")
    return out + jargon(text)
