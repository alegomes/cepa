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

`problems()` is the rule of the human section, used by `cepa-queue finish`
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

# The Portuguese flag each English one replaced. Still accepted by `cepa-queue
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


# ── the item each "no-return" answer creates (docs/spec/resposta-do-decide-vira-trabalho.md, CS-1) ──
#
# A route's answer either returns the item to the queue or it does not. The ones
# that do not (the "sim" of a route on a `done` item, the "não" of any route) must
# say which queue item they create, or say "nenhum" on purpose. The declaration is
# stored in `owner_summary` under `item_se_sim` / `item_se_nao`, as the string
# "nenhum" or as {"titulo": str, "precisa_do_dono": bool}. `cepa-queue answer`
# (CS-2/CS-3) reads it; this module only validates and shapes it.
ITEM_KEYS = (
    # (key in owner_summary, title flag, needs-owner flag, answer it belongs to)
    ("item_se_sim", "--if-yes-item", "--if-yes-item-needs-owner", "sim"),
    ("item_se_nao", "--if-no-item", "--if-no-item-needs-owner", "não"),
)
NONE_WORDS = ("nenhum", "nenhuma", "none")
NONE_VALUE = "nenhum"
WORDS_PER_ITEM_TITLE = 20


def item_declaration(key, text, needs_owner=False):
    """(stored value, error) for ONE declaration. `text` is the title or "nenhum";
    `needs_owner` is the "precisa do dono" flag. (None, None) when nothing was given."""
    flag, flag_owner = next((f, o) for k, f, o, _ in ITEM_KEYS if k == key)[:2]
    title = " ".join(str(text or "").split())
    if not title:
        if needs_owner:
            return None, f"{flag_owner} sem {flag}: falta o título do item"
        return None, None
    if title.lower() in NONE_WORDS:
        if needs_owner:
            return None, f"{flag_owner} não combina com `nenhum` em {flag}"
        return NONE_VALUE, None
    found = problems(title, WORDS_PER_ITEM_TITLE)
    if found:
        return None, f"{flag}: {'; '.join(found)}"
    return {"titulo": title, "precisa_do_dono": bool(needs_owner)}, None


def item_flags(summary):
    """CLI flags that carry the declarations of an `owner_summary` into `cepa-queue`."""
    out = []
    for key, flag, flag_owner, _ in ITEM_KEYS:
        v = (summary or {}).get(key)
        if isinstance(v, dict) and str(v.get("titulo") or "").strip():
            out += [flag, str(v["titulo"])]
            if v.get("precisa_do_dono"):
                out.append(flag_owner)
        elif isinstance(v, str) and v.strip().lower() in NONE_WORDS:
            out += [flag, NONE_VALUE]
    return out


# The owner's answer that `cepa-queue answer` prepends to the evidence. Read by
# `cepa-until decide` (a route answered "no" is not asked again in the launch
# panel) and `cepa-queue waiting` (it is only counted, CS-3 of
# decisoes-de-todas-as-filas): one reader, so both agree on what "answered no" is.
OWNER_NO = re.compile(r"Resposta do dono em (\d{4})-(\d{2})-(\d{2}): n(?:ão|ao)\b",
                      re.I)


def last_owner_no(evidence):
    """The date (`YYYY-MM-DD`) of the owner's LAST answer when it was "não", else None.
    `cepa-queue answer` prepends each answer to the evidence, so the last one is the
    text's start: a later "sim" or free text, or an older "não" further down, does
    not count."""
    m = OWNER_NO.match((evidence or "").lstrip())
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
