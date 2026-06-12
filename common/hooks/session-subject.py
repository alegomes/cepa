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

It also carries the wrap-up nudge: when the session looks like a good cut point
— a subject pivot AFTER the prior work closed (recent commits), or simply a long
session — it suggests cutting. If the session is landable (its own `session/*`
worktree with commits ahead of base) it points at `/common:wrap-up` (the whole
commit→handoff→merge→push→prune chain); otherwise at `/common:handoff` alone.
The bar to suggest ENDING is deliberately higher than the bar to suggest worktree
isolation, because a noisy signal that nags is worse than one that stays quiet.

Config (env):
  CLAUDE_WT_SUBJECT=off                 disable subject detection entirely
  CLAUDE_WT_SUBJECT_THRESHOLD=0.20      relevance below this = candidate shift
  CLAUDE_WT_SUBJECT_MINPROMPTS=3        need this many prior prompts as baseline
  CLAUDE_WT_NUDGE=off                   disable the wrap-up/handoff nudge only
  CLAUDE_WT_SESSION_SOFTCAP=45          prompts past which "long session" nudges

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


def recent_commit_close(cwd: str, within_secs: int = 900) -> bool:
    """True if HEAD's last commit is recent — a cheap 'the prior work just
    closed' signal. Commit is the most honest marker that a chunk finished."""
    rc, out, _ = L.git(["log", "-1", "--format=%ct"], cwd=cwd)
    if rc != 0 or not out.strip():
        return False
    try:
        import time
        return (time.time() - int(out.strip())) <= within_secs
    except (ValueError, OSError):
        return False


def wrap_action(cwd: str, root: str, entry: dict) -> str:
    """The action clause for a wrap-up nudge — a complete, capitalized sentence.

    When the session is genuinely *landable* (an own `session/*` worktree with
    commits ahead of its base), point at `/common:wrap-up`: it does the whole
    chain (commit + handoff + merge/push/prune) in one confirmed step, which is
    exactly what a good cut point wants. Otherwise there's nothing to land —
    fall back to the narrative-only `/common:handoff`.
    """
    branch = L.current_branch(cwd)
    if branch.startswith("session/"):
        base = entry.get("base_branch") or L.default_base(root)
        if L.commits_ahead(cwd, base, branch) > 0:
            return (
                f"Como este worktree (`{branch}`) tem commits à frente de "
                f"`{base}`, a sessão inteira pode aterrissar de uma vez: ofereça "
                "`/common:wrap-up` (commit + handoff + merge/push/prune numa "
                "tacada, atrás de uma confirmação). Se ele só quiser registrar e "
                "parar sem aterrissar, `/common:handoff`."
            )
    return (
        "Ofereça ao usuário salvar um handoff e seguir numa sessão nova; se ele "
        "concordar, rode `/common:handoff` na hora."
    )


def label_offer(cwd: str, root: str) -> str:
    """Suffix nudging the model to label THIS worktree, but only when it's an
    unlabeled session/* worktree — the exact case that strands timestamp names.
    """
    branch = L.current_branch(cwd)
    if not branch.startswith("session/") or L.branch_description(root, branch):
        return ""
    return (
        f" Além disso, este worktree (`{branch}`) ainda não tem rótulo: ofereça "
        "batizá-lo com `/common:worktree-label <propósito>` pra ele não virar "
        "mais um worktree timestamp órfão na lista. O usuário pode recusar e "
        "rotular depois."
    )


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

        nudge_on = os.environ.get("CLAUDE_WT_NUDGE", "").lower() != "off"
        try:
            soft_cap = int(os.environ.get("CLAUDE_WT_SESSION_SOFTCAP", "45"))
        except ValueError:
            soft_cap = 45

        subj = entry.setdefault("subject", {"centroid": {}, "prompts": 0, "last_flag": -10})
        centroid = subj.get("centroid", {})
        seen = set(centroid)
        new = terms(prompt)

        msg = None

        # ── Trigger 1: subject divergence (with enough baseline + cooldown) ──
        if subj["prompts"] >= min_prompts and len(new) >= 4:
            rel = relevance(new, seen)
            since_last = subj["prompts"] - subj.get("last_flag", -10)
            if rel < threshold and since_last >= 3:
                subj["last_flag"] = subj["prompts"]
                old_top = sorted(centroid, key=lambda k: -centroid[k])[:6]
                fresh = sorted(new - seen)[:6]
                # Higher bar to suggest ENDING: pivot AND the prior work closed
                # (recent commit). Otherwise fall back to the gentle isolate hint.
                if nudge_on and recent_commit_close(cwd):
                    msg = (
                        "[wrap-up] O assunto mudou (sobreposição de termos "
                        f"{rel:.0%}) E o trabalho anterior parece fechado — houve "
                        "commit há pouco. Bom ponto de corte. "
                        + wrap_action(cwd, root, entry) +
                        " Se ele quiser continuar aqui, siga sem insistir — é "
                        "sugestão, não bloqueio. (Desliga com CLAUDE_WT_NUDGE=off.)"
                    ) + label_offer(cwd, root)
                else:
                    msg = (
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
                    )

        # ── Trigger 2: long session (independent; only if 1 didn't fire) ──
        if msg is None and nudge_on and subj["prompts"] >= soft_cap:
            since_len = subj["prompts"] - subj.get("last_len_flag", -100)
            if since_len >= 20:
                subj["last_len_flag"] = subj["prompts"]
                msg = (
                    f"[wrap-up] Sessão longa ({subj['prompts']} interações) — o "
                    "contexto tende a poluir e ficar caro. Se estamos num ponto "
                    "estável, é um bom momento pra cortar. "
                    + wrap_action(cwd, root, entry) +
                    " Sugestão, não bloqueio. (Desliga com CLAUDE_WT_NUDGE=off.)"
                ) + label_offer(cwd, root)

        if msg is not None:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit", "additionalContext": msg}}))

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
