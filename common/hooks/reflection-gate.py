#!/usr/bin/env python3
"""PreToolUse hook (common) — integrity of the Reflection report.

Sibling of ui-proof-verdict-guard: the verdict is not an opinion the agent
writes, it is a value recomputed from the content and blocked when it does not
match.

The exit condition of Reflection is **no finding without a destination**: each
finding either became a card or was discarded with a written reason
(docs/modos-de-trabalho.md). The reason is the symptom that originated the
modes — a loose finding does not go away, it comes back as a micro-adjustment
in the middle of the next construction. The report is the right place to
enforce this, because it is where the finding is born.

Blocks the Write of `.claude/reflection/*.yaml` (legacy `.claude/reflexao/`) that declares `fechado: true`
with any finding lacking `destino`, or with a discard whose reason is empty or
decorative ("n/a", "-", "ok"). A reason that is too short is the same as no
reason: it exists so you can find the decision again three months from now.
(The report's field names — `fechado`, `achados`, `destino`, `descartado`,
`o_que`, `titulo` — are the on-disk format and stay as they are.)

Conservative on purpose, like its sibling: acts only on a confirmed
contradiction. A file that is not a reflection report, YAML that does not
parse, or `fechado` absent/false -> lets it through. Never invents a block.
Turned off with CEPA_MODO=off.
"""

import json
import os
import re
import sys

MIN_REASON_LEN = 12
DECORATIVE = {"n/a", "na", "-", "--", "ok", "nao", "não", "sim", "ja", "já",
              "nada", "none", "tbd", "?", "x"}


def is_report(file_path):
    p = file_path.replace(os.sep, "/")
    full = f"/{p.lstrip('/')}"
    # `/.claude/reflexao/` is the legacy name, still used by client repos.
    in_dir = "/.claude/reflection/" in full or "/.claude/reflexao/" in full
    return in_dir and p.endswith((".yaml", ".yml"))


def load(text):
    try:
        import yaml  # noqa: PLC0415
        return yaml.safe_load(text)
    except Exception:  # noqa: BLE001
        return None


def reason_is_empty(reason):
    if reason is None:
        return True
    m = str(reason).strip()
    return (not m) or m.lower() in DECORATIVE or len(m) < MIN_REASON_LEN


def without_destination(findings):
    """Returns (index, finding, why) of the first finding that does not close."""
    for i, a in enumerate(findings, 1):
        if not isinstance(a, dict):
            return i, a, "the finding is not a map with fields"
        destination = a.get("destino")
        discarded = a.get("descartado")
        if destination not in (None, "", "null"):
            continue
        if discarded is None:
            return i, a, "it has neither `destino:` nor `descartado:`"
        if reason_is_empty(discarded):
            return i, a, (f"the discard reason is empty or decorative "
                          f"({discarded!r}) — it needs at least "
                          f"{MIN_REASON_LEN} characters saying why")
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        sys.exit(0)

    try:
        if os.environ.get("CEPA_MODO", "on") == "off":
            sys.exit(0)

        ti = payload.get("tool_input") or {}
        fp = ti.get("file_path", "")
        if not fp or not is_report(fp):
            sys.exit(0)

        content = ti.get("content")
        if not isinstance(content, str):
            sys.exit(0)

        doc = load(content)
        if not isinstance(doc, dict):
            sys.exit(0)
        if doc.get("fechado") is not True:
            sys.exit(0)

        findings = doc.get("achados")
        if not isinstance(findings, list) or not findings:
            sys.exit(0)

        failure = without_destination(findings)
        if not failure:
            sys.exit(0)

        i, a, why = failure
        label = (a.get("o_que") or a.get("titulo") or f"finding #{i}") \
            if isinstance(a, dict) else f"finding #{i}"
        print(
            f"[reflection-gate] BLOCKED: {fp} declares `fechado: true`, but "
            f"finding #{i} has no destination.\n"
            f"  Finding: {str(label)[:120]}\n"
            f"  Problem: {why}.\n"
            f"  Reflection closes when NO finding was left loose. A loose "
            f"finding does not go away — it comes back as a micro-adjustment "
            f"in the middle of the next construction, which is the leak the "
            f"modes exist to prevent.\n"
            f"  Write one of the two things on this finding:\n"
            f"    destino: WEGO-1234        (or the line in .claude/deviations.md)\n"
            f"    descartado: <why it is not worth it, in one sentence>\n"
            f"  Or save the report with `fechado: false` while you are still "
            f"triaging.",
            file=sys.stderr,
        )
        sys.exit(2)
    except Exception as e:  # noqa: BLE001
        print(f"[reflection-gate] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
