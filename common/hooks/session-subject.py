#!/usr/bin/env python3
"""UserPromptSubmit hook: experimental Tier-2 subject-shift detection.

Watches the vocabulary of a session's prompts and flags when a new prompt
diverges sharply from the running subject — a cheap, dependency-free signal
that the session may have pivoted to a new task (which is a reason to isolate
it in its own worktree).

The design is "lexical proposes, model disposes": this hook is the always-on
cheap trigger (so the check is consistent), and it injects a discreet note into
context rather than acting — the model, which actually understands the live
conversation, decides whether to surface it to the user (so the call is
accurate). That pairing is the only honest way to use a noisy signal: neither
half is trustworthy alone.

Signal (default backend): relevance = |new_terms ∩ seen_terms| / |new_terms|.
A low value means most of this prompt's vocabulary is unseen → likely a new
subject. Tunable; an embedding backend can replace `relevance()` later.

Config (env):
  CLAUDE_WT_SUBJECT=off                 disable entirely
  CLAUDE_WT_SUBJECT_THRESHOLD=0.20      relevance below this = candidate shift
  CLAUDE_WT_SUBJECT_MINPROMPTS=3        need this many prior prompts as baseline

Never blocks; exit 0 always.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _wtlib as L  # noqa: E402

STOPWORDS = {
    "the", "and", "for", "you", "with", "this", "that", "have", "was", "are",
    "can", "but", "not", "all", "any", "from", "your", "what", "when", "how",
    "why", "who", "will", "would", "should", "could", "make", "made", "use",
    "using", "used", "now", "then", "let", "lets", "please", "want", "need",
    "into", "out", "get", "got", "set", "add", "added", "fix", "fixed", "also",
    "like", "just", "some", "more", "less", "see", "look", "run", "running",
    "ran", "they", "them", "their", "there", "here", "about", "which", "where",
    "been", "being", "does", "did", "doing", "still", "even", "only", "very",
    "much", "many", "one", "two", "new", "old", "yes", "code", "file", "files",
}
WORD = re.compile(r"[a-z][a-z0-9_]{2,}")
TOP = 80  # cap stored vocabulary


def terms(text: str) -> set:
    return {w for w in WORD.findall(text.lower()) if w not in STOPWORDS}


def relevance(new: set, seen: set) -> float:
    """Fraction of the new prompt's terms already seen in the session."""
    if not new:
        return 1.0
    return len(new & seen) / len(new)


def main():
    if os.environ.get("CLAUDE_WT_SUBJECT", "").lower() == "off":
        sys.exit(0)
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        sys.exit(0)

    prompt = payload.get("prompt") or ""
    if isinstance(prompt, dict):
        prompt = prompt.get("content", "") or ""
    session_id = payload.get("session_id") or ""
    if not session_id or not isinstance(prompt, str) or not prompt.strip():
        sys.exit(0)
    cwd = os.path.abspath(payload.get("cwd") or os.getcwd())

    try:
        threshold = float(os.environ.get("CLAUDE_WT_SUBJECT_THRESHOLD", "0.20"))
        min_prompts = int(os.environ.get("CLAUDE_WT_SUBJECT_MINPROMPTS", "3"))
    except ValueError:
        threshold, min_prompts = 0.20, 3

    try:
        root = L.main_root(cwd)
        entry = L.find_entry(root, session_id)
        if entry is None:
            sys.exit(0)

        subj = entry.setdefault("subject", {"centroid": {}, "prompts": 0, "last_flag": -10})
        centroid = subj.get("centroid", {})
        seen = set(centroid)
        new = terms(prompt)

        flag = False
        if subj["prompts"] >= min_prompts and len(new) >= 4:
            rel = relevance(new, seen)
            since_last = subj["prompts"] - subj.get("last_flag", -10)
            if rel < threshold and since_last >= 3:
                flag = True
                old_top = sorted(centroid, key=lambda k: -centroid[k])[:6]
                fresh = sorted(new - seen)[:6]
                subj["last_flag"] = subj["prompts"]
                print(json.dumps({"hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": (
                        "[subject-watch] Lexical signal: this prompt's vocabulary "
                        f"diverges from the session so far (seen-term overlap "
                        f"{rel:.0%}). Earlier focus: {', '.join(old_top) or '—'}. "
                        f"New terms now: {', '.join(fresh) or '—'}. "
                        "This is a heuristic, not a verdict — judge it against the "
                        "actual conversation. If the user has genuinely pivoted to a "
                        "NEW task, briefly suggest isolating it (a fresh `ccw` session "
                        "/ `/common:worktree-start <slice>`) so the two land "
                        "separately. If it's the same thread of work, ignore this "
                        "silently."
                    )}}))

        # Update running subject regardless of flag.
        for w in new:
            centroid[w] = centroid.get(w, 0) + 1
        if len(centroid) > TOP:
            centroid = dict(sorted(centroid.items(), key=lambda kv: -kv[1])[:TOP])
        subj["centroid"] = centroid
        subj["prompts"] += 1
        entry["subject"] = subj
        entry["last_seen"] = L.now_iso()
        L.write_entry(root, session_id, entry)
    except Exception as e:  # noqa: BLE001
        print(f"[session-subject] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
