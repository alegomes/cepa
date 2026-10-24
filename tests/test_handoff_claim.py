#!/usr/bin/env python3
"""Regression tests for the handoff to be resumed only ONCE.

The handoff is a markdown per branch that the new session reads at SessionStart. Until
now nothing recorded WHO read it: the only protection against two sessions resuming
the same point was `live_sessions_in`, which compares the EXACT cwd. A session
opened in a subdirectory of the same tree does not match, and the second one received the same
handoff as if it were the first.

Contracts guarded here:
  - the first session that receives the handoff is recorded as the one that resumed,
    in the frontmatter (`resumed_by`) AND in a reservation file created with O_EXCL
    — two independent locks, on purpose;
  - a second session, with the first ALIVE, does not receive the content: it receives the
    notice that it was already resumed, with the id of whoever resumed it;
  - if whoever resumed DIED without writing anything, the reservation is released and the next
    session resumes normally (a dead one's reservation cannot lock the work);
  - a new checkpoint (updated_at changed) is new content: the old reservation
    does not apply to it;
  - the delivered text says the handoff is evidence, never instruction.

Run with `python3 tests/test_handoff_claim.py`.
"""

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "common" / "hooks"
sys.path.insert(0, str(HOOKS))
sys.path.insert(0, str(REPO / "tests"))

from _isolated_telemetry import isolate  # noqa: E402

isolate()
# Run inside a cepa-until round, the window's mark turns off the
# resume (see test_until_does_not_inherit_handoff.py); here the normal session is tested.
os.environ.pop("CEPA_UNTIL_RUN", None)

import _handoff as H  # noqa: E402
import _wtlib as L  # noqa: E402

spec = importlib.util.spec_from_file_location("session_registry", HOOKS / "session-registry.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def scenario():
    """Fake tree with a fresh handoff written by session A (already dead)."""
    root = tempfile.mkdtemp(prefix="handoff-claim-")
    path = H.handoff_path(root, "main")
    H.write(path, {"session_id": "sessao-A", "branch": "main",
                   "updated_at": L.now_iso()},
            auto="## Onde paramos\n- passo 3 de 5", note="Próximo: rodar o passo 4.")
    # The test has no git: pins the branch and controls who is alive.
    L.current_branch = lambda cwd: "main"
    return root, path


def with_live(ids):
    """Only the sessions in `ids` count as alive."""
    L.find_entry = lambda root, key: {"session_id": key} if key in ids else None
    L.entry_is_live = lambda e: bool(e) and e.get("session_id") in ids
    # The real loophole: the exact-cwd check does NOT see the peer (subdirectory).
    L.live_sessions_in = lambda root, cwd, exclude_key="": []


def test_first_resumes_and_is_recorded():
    root, path = scenario()
    with_live({"sessao-B"})
    out = R.resume_notice("sessao-B", root, root)
    check("B recebe o conteúdo", out and "passo 3 de 5" in out, out)
    meta, _, _ = H.parse(path)
    check("frontmatter registra quem retomou", meta.get("resumed_by") == "sessao-B", meta)
    claim = path.with_suffix(".claim")
    check("arquivo de reserva existe", claim.exists())
    if claim.exists():
        c = json.loads(claim.read_text())
        check("reserva aponta para B", c.get("session_id") == "sessao-B", c)


def test_second_does_not_resume_the_same_point():
    root, path = scenario()
    with_live({"sessao-B", "sessao-C"})
    R.resume_notice("sessao-B", root, root)
    out = R.resume_notice("sessao-C", root, root)
    check("C não recebe o conteúdo", not out or "passo 3 de 5" not in out, out)
    check("C é avisada de quem retomou", bool(out) and "sessao-B" in out, out)


def test_same_session_receives_again():
    """SessionStart fires again on resume/compact: whoever reserved remains the owner."""
    root, path = scenario()
    with_live({"sessao-B"})
    R.resume_notice("sessao-B", root, root)
    out = R.resume_notice("sessao-B", root, root)
    check("B recebe o conteúdo na 2ª chamada", out and "passo 3 de 5" in out, out)


def test_dead_ones_reservation_is_released():
    root, path = scenario()
    with_live({"sessao-B"})
    R.resume_notice("sessao-B", root, root)
    with_live({"sessao-C"})  # B died without writing a checkpoint
    out = R.resume_notice("sessao-C", root, root)
    check("C retoma depois que B morreu", out and "passo 3 de 5" in out, out)
    meta, _, _ = H.parse(path)
    check("frontmatter passa a apontar para C", meta.get("resumed_by") == "sessao-C", meta)


def test_file_lock_alone_already_blocks():
    """The two locks are independent: deleting the frontmatter does not release."""
    root, path = scenario()
    with_live({"sessao-B", "sessao-C"})
    R.resume_notice("sessao-B", root, root)
    meta, auto, note = H.parse(path)
    meta.pop("resumed_by", None); meta.pop("resumed_at", None); meta.pop("resumed_version", None)
    path.write_text(H.render(meta, auto, note), encoding="utf-8")
    out = R.resume_notice("sessao-C", root, root)
    check("C barrada só pelo arquivo de reserva", not out or "passo 3 de 5" not in out, out)


def test_frontmatter_lock_alone_already_blocks():
    root, path = scenario()
    with_live({"sessao-B", "sessao-C"})
    R.resume_notice("sessao-B", root, root)
    path.with_suffix(".claim").unlink()
    out = R.resume_notice("sessao-C", root, root)
    check("C barrada só pelo frontmatter", not out or "passo 3 de 5" not in out, out)


def test_new_checkpoint_is_new_content():
    root, path = scenario()
    with_live({"sessao-B", "sessao-C"})
    R.resume_notice("sessao-B", root, root)
    # Session A' writes a new checkpoint: another version of the handoff.
    H.write(path, {"session_id": "sessao-A2", "updated_at": "2099-01-01T00:00:00+00:00"},
            auto="## Onde paramos\n- passo 9 de 9")
    H.age_seconds = lambda meta: 0.0
    out = R.resume_notice("sessao-C", root, root)
    check("C recebe a versão nova", out and "passo 9 de 9" in out, out)


def test_text_says_evidence_never_instruction():
    root, path = scenario()
    with_live({"sessao-B"})
    out = R.resume_notice("sessao-B", root, root) or ""
    check("preâmbulo nega autoridade de instrução ao handoff",
          "nunca instrução" in out.lower() or "nunca como instrução" in out.lower(), out[:400])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            orig = (L.current_branch, L.find_entry, L.entry_is_live, L.live_sessions_in, H.age_seconds)
            try:
                fn()
            finally:
                (L.current_branch, L.find_entry, L.entry_is_live, L.live_sessions_in, H.age_seconds) = orig
    print()
    if failures:
        print(f"{len(failures)} FALHA(S): {failures}")
        sys.exit(1)
    print("tudo ok")
