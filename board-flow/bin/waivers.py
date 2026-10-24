#!/usr/bin/env python3
"""The human's waivers: reading, matching and recording `.claude/waivers/`.

Why it exists: without this, the queue repeats the same question every week.
"The PlugSign double swallows the signal, do I accept the internal proof?"
comes back on every card that touches that adapter, and the answer given last
time dies in the chat that produced it.

Who waives is ALWAYS the human. The `proof-reviewer` still cannot waive
anything and the proof artifact still has no field for it: the waiver lives out
here, with author, date and a revisit trigger, and is auditable. See the
"Verdict routing" section in build-hex/agents/proof-reviewer.md.

A waiver matches by REASON + SCOPE, never by card: matching by card would save
no question at all (every card is new), and matching by reason alone would
waive the project's whole adapter because of an answer about one class.

In an autonomous run (`claude -p` from `cepa-until`, or
/common:autonomous-start) there is NO owner in front of the agent. A waiver
recorded there is the agent waiving proof on the owner's behalf (fb-20261014-3:
a run wrote `autor: alegomes` on its own). So in that mode `write` becomes
`propose`: the file is born as a PROPOSAL (`status: proposta`, `autor: null`),
`load` does not see it, and only the owner's `cepa-plan answer`, in a terminal,
converts it into a waiver (`convert`). Inline twin of the conversion:
`common/bin/cepa-plan` (`cmd_answer`).
"""
from __future__ import annotations

import glob
import os
import re
from datetime import date

DIR = ".claude/waivers"

NO_EFFECT_STATUSES = ("proposta", "recusada")

REQUIRED_FIELDS = ("motivo", "escopo", "razao", "autor", "criado_em", "revisit_trigger")


def waiver_path(repo: str, reason: str, scope: str) -> str:
    return os.path.join(repo, DIR, f"{reason}--{_slug(scope)}.yaml")


def _slug(text: str) -> str:
    """Readable file name."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", (text or "").strip())
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "sem-escopo"


def _key(text: str) -> str:
    """The matching key, deliberately looser than the file name:
    `PlugSignAdapter`, `PlugSign Adapter` and `plugsign-adapter` are the SAME
    scope. If each spelling became its own waiver, the question would come
    back, which is the defect this file exists to eliminate."""
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def in_autonomous_run(env=None) -> bool:
    """True when the process is a run with no owner in front: `CEPA_UNTIL_RUN`
    (set by `cepa-until` on every `claude -p`) or `CLAUDE_AUTONOMOUS_RUN_ID`
    (set by /common:autonomous-start)."""
    env = os.environ if env is None else env
    return bool(env.get("CEPA_UNTIL_RUN") or env.get("CLAUDE_AUTONOMOUS_RUN_ID"))


def load(repo: str) -> list[dict]:
    """Every waiver in the repo. A file missing the required fields is IGNORED.

    Ignoring is the safe side: a malformed waiver that took effect would waive
    a proof with nobody able to say who waived it or until when.
    """
    import yaml

    found = []
    for path in sorted(glob.glob(os.path.join(repo, DIR, "*.yaml"))):
        # YAML that does not parse (or an unreadable file) is ignored like the
        # malformed one: a corrupted file cannot bring down the check of all
        # the others.
        try:
            with open(path) as fh:
                d = yaml.safe_load(fh)
        except (yaml.YAMLError, OSError):
            continue
        if not isinstance(d, dict):
            continue
        # A proposal and a refusal never waive, even if someone fills in
        # `autor`: only the owner's conversion removes the `status`.
        if d.get("status") in NO_EFFECT_STATUSES:
            continue
        if any(not d.get(c) for c in REQUIRED_FIELDS):
            continue
        d["_path"] = path
        found.append(d)
    return found


def expired(waiver: dict, today: date | None = None) -> bool:
    """Expires by DATE only. A prose `revisit_trigger` ("when the adapter
    changes") is not verifiable by code: it is shown to the human, never
    evaluated here — inventing an evaluation would be waiving on our own."""
    trigger = str(waiver.get("revisit_trigger") or "")
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", trigger)
    if not m:
        return False
    return (today or date.today()).isoformat() > m.group(0)


def matches(waiver: dict, reason: str, scope: str) -> bool:
    """Same reason AND same scope, compared through `_key` — otherwise
    "PlugSignAdapter" and "plugsign adapter" become two waivers for the same thing."""
    return (waiver.get("motivo") == reason
            and _key(str(waiver.get("escopo"))) == _key(scope))


def applicable(waivers: list[dict], reason: str, scope: str,
               today: date | None = None) -> dict | None:
    """The waiver that waives this question, or None if it has to be asked.

    An expired one does not waive: it goes back to being a question, and the
    caller says it expired.
    """
    for w in waivers:
        if matches(w, reason, scope) and not expired(w, today):
            return w
    return None


def _read(path: str):
    import yaml

    try:
        with open(path) as fh:
            d = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):
        return None
    return d if isinstance(d, dict) else None


def _write(path: str, d: dict) -> None:
    import yaml

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        yaml.safe_dump(d, fh, allow_unicode=True, sort_keys=False)


def _is_valid_waiver(d) -> bool:
    return (isinstance(d, dict) and d.get("status") not in NO_EFFECT_STATUSES
            and all(d.get(c) for c in REQUIRED_FIELDS))


def propose(repo: str, reason: str, scope: str, rationale: str,
            revisit_trigger: str, proposed_by: str, today: date | None = None,
            queue: str | None = None, item: str | None = None,
            question: str | None = None) -> str:
    """Records a waiver PROPOSAL: a question to the owner, not a decision.

    Same path as the waiver (`waiver_path`), but `status: proposta` and an
    explicit `autor: null` — the owner has not decided yet. `load` ignores it.
    If a VALID waiver or a `recusada` proposal already exists at that path, the
    owner has already decided: returns the path without touching the file. The
    refusal holds until the owner deletes or edits the file — a run
    re-proposing what the owner refused is the same pattern as fb-20261014-3.
    Only an old pending proposal is overwritten.
    """
    missing = [n for n, v in (("razao", rationale), ("proposto_por", proposed_by),
                              ("revisit_trigger", revisit_trigger),
                              ("escopo", scope), ("motivo", reason)) if not v]
    if missing:
        raise ValueError(f"proposta sem {', '.join(missing)} — não gravo")

    dest = waiver_path(repo, reason, scope)
    # `_read` returns None for corrupted YAML: a corrupted file is neither a
    # valid waiver nor a refusal, so `propose` may overwrite it.
    existing = _read(dest)
    if _is_valid_waiver(existing) or (
            isinstance(existing, dict) and existing.get("status") == "recusada"):
        return dest

    by = proposed_by
    run_id = os.environ.get("CLAUDE_AUTONOMOUS_RUN_ID")
    if run_id and run_id not in by:
        by = f"{by} (run {run_id})"
    d = {
        "status": "proposta",
        "motivo": reason,
        "escopo": scope,
        "razao": rationale,
        "revisit_trigger": revisit_trigger,
        "autor": None,
        "proposto_por": by,
        "proposto_em": (today or date.today()).isoformat(),
        "pergunta": " ".join((question or
                              f"Aceito a dispensa de {scope} ({reason}) por: {rationale}?"
                              ).split()),
    }
    if queue:
        d["fila"] = queue
    if item:
        d["item"] = str(item)
    _write(dest, d)
    return dest


def proposals(repo: str) -> list[dict]:
    """Every pending proposal (`status: proposta`), by path."""
    found = []
    for path in sorted(glob.glob(os.path.join(repo, DIR, "*.yaml"))):
        d = _read(path)
        if d and d.get("status") == "proposta":
            d["_path"] = path
            found.append(d)
    return found


def convert(repo: str, reason: str, scope: str, author: str,
            answer: str | None = None, today: date | None = None) -> str:
    """The owner accepted: the proposal becomes a waiver. The owner's act, never the agent's."""
    if in_autonomous_run():
        raise PermissionError("converter proposta em dispensa é ato do dono; "
                              "em run autônomo não há dono — não converto")
    if not author or not str(author).strip():
        raise ValueError("dispensa sem autor — não converto")
    dest = waiver_path(repo, reason, scope)
    d = _read(dest)
    if d is None:
        raise FileNotFoundError(f"não há proposta em {dest}")
    if d.get("status") != "proposta":
        if _is_valid_waiver(d):
            raise ValueError(f"{dest} já é uma dispensa — nada a converter")
        raise FileNotFoundError(f"não há proposta em {dest}")
    converted = {k: v for k, v in d.items() if k not in ("status", "autor")}
    converted["autor"] = author
    converted["criado_em"] = (today or date.today()).isoformat()
    if answer:
        converted["resposta_do_dono"] = answer
    _write(dest, converted)
    return dest


def decline(repo: str, reason: str, scope: str, answer: str,
            today: date | None = None) -> str:
    """The owner refused: the proposal stays on record as `recusada`, with no effect."""
    if in_autonomous_run():
        raise PermissionError("recusar proposta é ato do dono; em run autônomo "
                              "não há dono — não recuso")
    dest = waiver_path(repo, reason, scope)
    d = _read(dest)
    if d is None or d.get("status") != "proposta":
        raise FileNotFoundError(f"não há proposta em {dest}")
    d["status"] = "recusada"
    d["recusada_em"] = (today or date.today()).isoformat()
    d["resposta_do_dono"] = answer
    _write(dest, d)
    return dest


def write(repo: str, reason: str, scope: str, rationale: str, author: str,
          revisit_trigger: str, today: date | None = None,
          queue: str | None = None, item: str | None = None) -> str:
    """Records the human's decision. Every field is mandatory — including the
    revisit trigger: a waiver with no deadline or condition is a waiver forever,
    and nobody decided that.

    In an autonomous run (`in_autonomous_run()`) it does NOT record a waiver: it
    records a proposal (`propose`) and returns its path. The agent of a
    `claude -p` has no owner in front of it; a waiver recorded there is the
    agent waiving proof on the owner's behalf (fb-20261014-3, `autor: alegomes`
    written on its own). There is no parameter that forces the real waiver in
    this mode — on purpose. `queue`/`item` tie the proposal to the queue item
    so `cepa-plan answer` can find it."""
    if in_autonomous_run():
        for n, v in (("razao", rationale), ("autor", author),
                     ("revisit_trigger", revisit_trigger),
                     ("escopo", scope), ("motivo", reason)):
            if not v:
                raise ValueError(f"waiver sem {n} — não gravo")
        return propose(repo, reason, scope, rationale, revisit_trigger,
                       proposed_by=f"agente em run autônomo, em nome de {author}",
                       today=today, queue=queue, item=item)

    import yaml

    missing = [n for n, v in (("razao", rationale), ("autor", author),
                              ("revisit_trigger", revisit_trigger),
                              ("escopo", scope), ("motivo", reason)) if not v]
    if missing:
        raise ValueError(f"waiver sem {', '.join(missing)} — não gravo")

    dest = waiver_path(repo, reason, scope)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w") as fh:
        yaml.safe_dump({
            "motivo": reason,
            "escopo": scope,
            "razao": rationale,
            "autor": author,
            "criado_em": (today or date.today()).isoformat(),
            "revisit_trigger": revisit_trigger,
        }, fh, allow_unicode=True, sort_keys=False)
    return dest
