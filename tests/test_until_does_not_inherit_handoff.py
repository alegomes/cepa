#!/usr/bin/env python3
"""Regression: a cepa-until round does not inherit the previous round's handoff.

Each `cepa-until` round is a fresh `claude -p`, in the SAME worktree and the SAME
branch of the run. The handoff is per branch, so the SessionStart of round N
delivered what round N-1 wrote, with the rule "continue from where you left off". In run
2026-09-27-0832 of wego-acessos-backend, the round that should have done WEGO-2321
never reserved the item and rewrote the report of WEGO-2337, from the previous round.

Contracts:
  - with `CEPA_UNTIL_RUN` in the environment, the handoff content is NOT delivered;
    the notice says that the round's item is whatever the drain-plan reserves;
  - the round does not consume the handoff (neither `resumed_by` nor a reservation file),
    so the owner can still resume it in the morning;
  - without the marker, resuming goes on as before.

Run with `python3 tests/test_until_does_not_inherit_handoff.py`.
"""

import importlib.util
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "common" / "hooks"
sys.path.insert(0, str(HOOKS))
sys.path.insert(0, str(REPO / "tests"))

from _isolated_telemetry import isolate  # noqa: E402

isolate()

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
    """Fresh handoff left by the previous round (already dead), about ANOTHER item."""
    root = tempfile.mkdtemp(prefix="until-handoff-")
    path = H.handoff_path(root, "until/2026-09-27-0832")
    H.write(path, {"session_id": "rodada-1", "branch": "until/2026-09-27-0832",
                   "updated_at": L.now_iso()},
            auto="## Onde paramos\n- relatorio do WEGO-2337", note="Próximo: fechar o WEGO-2337.")
    L.current_branch = lambda cwd: "until/2026-09-27-0832"
    L.find_entry = lambda root, key: None
    L.entry_is_live = lambda e: False
    L.live_sessions_in = lambda root, cwd, exclude_key="": []
    return root, path


def test_round_does_not_receive_the_handoff():
    root, path = scenario()
    out = R.resume_notice("rodada-2", root, root, env={"CEPA_UNTIL_RUN": "1"}) or ""
    check("conteúdo da rodada anterior não é entregue", "WEGO-2337" not in out, out)
    check("aviso aponta para o item reservado pelo drain-plan", "drain-plan" in out, out)


def test_round_does_not_consume_the_handoff():
    root, path = scenario()
    R.resume_notice("rodada-2", root, root, env={"CEPA_UNTIL_RUN": "1"})
    meta, _, _ = H.parse(path)
    check("frontmatter sem resumed_by", "resumed_by" not in meta, meta)
    check("sem arquivo de reserva", not path.with_suffix(".claim").exists())


def test_normal_session_keeps_resuming():
    root, path = scenario()
    out = R.resume_notice("dono", root, root, env={}) or ""
    check("sem a marca, o conteúdo é entregue", "WEGO-2337" in out, out)


def _session_start(marker):
    """The wiring: the real SessionStart, as a subprocess, in a disposable git
    repo whose branch has a fresh handoff from another session.
    """
    import json
    import os
    import subprocess
    repo = Path(tempfile.mkdtemp(prefix="until-handoff-repo-")).resolve()
    subprocess.run(["git", "init", "-q", "-b", "until/noite", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "--no-gpg-sign", "-m", "x"], check=True)
    path = H.handoff_path(str(repo), "until/noite")
    H.write(path, {"session_id": "rodada-1", "branch": "until/noite",
                   "updated_at": L.now_iso()}, auto="- relatorio do WEGO-2337")
    env = {k: v for k, v in os.environ.items() if k != "CEPA_UNTIL_RUN"}
    if marker:
        env["CEPA_UNTIL_RUN"] = "1"
    r = subprocess.run(
        [sys.executable, str(HOOKS / "session-registry.py")],
        input=json.dumps({"hook_event_name": "SessionStart", "session_id": "rodada-2",
                          "cwd": str(repo)}),
        capture_output=True, text=True, env=env, timeout=60)
    return r, path


def test_round_session_start_does_not_deliver():
    r, path = _session_start(marker=True)
    check("hook sai 0", r.returncode == 0, r.stderr[-300:])
    check("SessionStart da rodada não traz o handoff", "WEGO-2337" not in r.stdout, r.stdout[-400:])
    import json
    ctx = json.loads(r.stdout or "{}").get("hookSpecificOutput", {}).get("additionalContext", "")
    check("SessionStart da rodada avisa que não entregou", "NÃO entregue" in ctx, ctx[-400:])
    check("handoff segue sem reserva", not path.with_suffix(".claim").exists())


def test_normal_session_start_delivers():
    r, _ = _session_start(marker=False)
    check("SessionStart sem a marca traz o handoff", "WEGO-2337" in r.stdout,
          r.stdout[-400:] + r.stderr[-300:])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            orig = (L.current_branch, L.find_entry, L.entry_is_live, L.live_sessions_in)
            try:
                fn()
            finally:
                (L.current_branch, L.find_entry, L.entry_is_live, L.live_sessions_in) = orig
    print()
    if failures:
        print(f"{len(failures)} FALHA(S): {failures}")
        sys.exit(1)
    print("tudo ok")
