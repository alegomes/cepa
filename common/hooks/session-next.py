#!/usr/bin/env python3
"""Records the chaining's next step from the handoff (CS-4 of the cepa-espiral-c1 cycle).

Called by step L7 of `/common:wrap-up`. Reads the handoff's NOTE zone
(`<!-- HANDOFF:NOTE -->…<!-- /HANDOFF:NOTE -->`) and looks for the line

    **Próximo:** repo=<path> mode=<mode> comando=<command and arguments>

Found: writes `<main-root>/.claude/sessions/<session_id>.next.json` with
`repo`, `mode`, `comando` and `brief`, where the brief is the paragraph of the
`## Próximo passo` section of the same zone. It is the file the `cepa` launcher
reads when the session exits (`session-chain.py`, CS-3) to open the next one
without the owner typing.

The next session's intent comes from three optional lines of the same section,
written in its voice: `**Intenção:**`, `**Meta:**` and `**Plano:** a | b | c`.
With all three, the file gains `intent` ({purpose, by_when, plan}) and `cepa`
records it before the first turn. With none, the next session is born without
intent: the brief talks about the session that left and does not serve as
purpose for the other. Only some of them is an unusable line.

Without the line, it writes nothing and says so: a handoff without `Próximo:`
remains valid, the session just does not chain. A line present but unusable
(nonexistent repo, unknown mode, empty brief) also writes nothing, and says why:
a file the launcher would refuse would erase the next step silently.

Usage: session-next.py --handoff <file> --session-id <id> [--root <root>]
Output: exit 0 wrote or there was no line; exit 2 the line exists and is no good.
The first stdout line is what goes in the wrap-up report.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _modes  # noqa: E402
import _wtlib as L  # noqa: E402

NOTE_RE = re.compile(r"<!-- HANDOFF:NOTE -->(.*?)<!-- /HANDOFF:NOTE -->", re.S)
NEXT_LINE_RE = re.compile(r"^\s*\*\*Próximo:\*\*\s*(.*)$", re.M)
KEY_RE = re.compile(r"(?:^|\s)(repo|mode|modo|comando)=")
SECTION_RE = re.compile(r"^##\s+Próximo passo\s*$", re.M)
INTENT_RE = {field: re.compile(rf"^[ \t]*\*\*{label}:\*\*[ \t]*(.*)$", re.M)
             for field, label in (("purpose", "Intenção"), ("by_when", "Meta"),
                                  ("plan", "Plano"))}


def note_zone(text: str) -> str:
    m = NOTE_RE.search(text)
    return m.group(1) if m else ""


def parse_line(rest: str) -> dict:
    """`repo=… modo=… comando=…` → dict. The command takes the rest up to the
    next key, because it carries arguments with spaces (`/common:epic contratos`)."""
    found = list(KEY_RE.finditer(rest))
    fields = {}
    for i, m in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(rest)
        fields[m.group(1)] = rest[m.end():end].strip()
    return fields


def section(note: str) -> str:
    """The body of `## Próximo passo`, up to the next section."""
    m = SECTION_RE.search(note)
    if not m:
        return ""
    body = note[m.end():]
    nxt = re.search(r"^##\s", body, re.M)
    return body[:nxt.start()] if nxt else body


def section_brief(note: str) -> str:
    """The paragraph of `## Próximo passo`, without the `**Próximo:**` line or the intent ones."""
    body = NEXT_LINE_RE.sub("", section(note))
    for r in INTENT_RE.values():
        body = r.sub("", body)
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def section_intent(note: str) -> dict:
    """The next session's intent lines that are present and non-empty."""
    body = section(note)
    found = {}
    for field, r in INTENT_RE.items():
        m = r.search(body)
        if m and m.group(1).strip():
            found[field] = m.group(1).strip()
    if "plan" in found:
        found["plan"] = [i.strip() for i in found["plan"].split("|") if i.strip()]
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--handoff", required=True)
    ap.add_argument("--session-id", required=True)
    ap.add_argument("--root")
    a = ap.parse_args()

    try:
        text = open(a.handoff, encoding="utf-8").read()
    except OSError as e:
        print(f"próximo passo não gravado: handoff ilegível ({e})")
        return 2
    note = note_zone(text)
    m = NEXT_LINE_RE.search(note)
    if not m:
        print("próximo passo não gravado: o handoff não tem a linha `**Próximo:**` "
              "na zona NOTE, então a sessão seguinte não abre sozinha")
        return 0

    fields = parse_line(m.group(1))
    # `mode=` (or the old `modo=`); the value, old or new, becomes the new name
    repo, command = fields.get("repo", ""), fields.get("comando", "")
    mode = _modes.normalize_mode(fields.get("mode") or fields.get("modo") or "")
    brief = section_brief(note)
    intent = section_intent(note)
    missing_intent = [r for c, r in (("purpose", "Intenção"), ("by_when", "Meta"),
                                     ("plan", "Plano")) if not intent.get(c)]
    missing = [k for k, v in (("repo", repo), ("mode", mode), ("comando", command)) if not v]
    if missing:
        reason = f"a linha `**Próximo:**` não traz {', '.join(missing)}"
    elif not os.path.isdir(repo):
        reason = f"repo {repo} não existe"
    elif mode not in _modes.MODES:
        reason = f"modo {mode} não é um dos modos ({' '.join(_modes.MODES)})"
    elif mode == "refactor":
        reason = "modo refactor exige --budget, que o encadeamento não passa"
    elif not brief:
        reason = "a seção `## Próximo passo` está vazia ou não existe"
    elif intent and missing_intent:
        reason = ("a intenção da sessão seguinte está pela metade: falta "
                  + ", ".join(f"`**{r}:**`" for r in missing_intent))
    else:
        reason = ""
    if reason:
        print(f"próximo passo não gravado: {reason}")
        return 2

    root = a.root or L.main_root(os.getcwd())
    if not root:
        print("próximo passo não gravado: raiz do repositório não encontrada")
        return 2
    d = L.sessions_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    target = d / f"{a.session_id}.next.json"
    spec = {"repo": repo, "mode": mode, "comando": command, "brief": brief}
    if intent:
        spec["intent"] = {"purpose": intent.get("purpose"),
                          "by_when": intent.get("by_when"),
                          "plan": intent.get("plan")}
    target.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    about = (f"com a intenção \"{intent['purpose']}\"" if intent
             else "sem intenção (o handoff não tem `**Intenção:**`)")
    print(f"próximo passo gravado em {target}: ao sair, o cepa abre {repo} "
          f"no modo {mode} ({command}), {about}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
