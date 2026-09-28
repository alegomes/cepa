#!/usr/bin/env python3
"""Regression: rodada do cepa-until não herda o handoff da rodada anterior.

Cada rodada do `cepa-until` é um `claude -p` novo, na MESMA worktree e no MESMO
branch da noite. O handoff é por branch, então o SessionStart da rodada N
entregava o que a rodada N-1 escreveu, com a regra "siga de onde parou". No run
2026-09-27-0832 do wego-acessos-backend, a rodada que devia fazer o WEGO-2321
nunca reservou o item e reescreveu o relatório do WEGO-2337, da rodada anterior.

Contratos:
  - com `CEPA_UNTIL_RUN` no ambiente, o conteúdo do handoff NÃO é entregue;
    o aviso diz que o item da rodada é o que o drain-plan reservar;
  - a rodada não consome o handoff (nem `resumed_by` nem arquivo de reserva),
    para o dono ainda poder retomá-lo de manhã;
  - sem a marca, a retomada segue como antes.

Rode com `python3 tests/test_until_nao_herda_handoff.py`.
"""

import importlib.util
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "common" / "hooks"
sys.path.insert(0, str(HOOKS))
sys.path.insert(0, str(REPO / "tests"))

from _telemetria_isolada import isola  # noqa: E402

isola()

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


def cenario():
    """Handoff fresco deixado pela rodada anterior (já morta), sobre OUTRO item."""
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


def test_rodada_nao_recebe_o_handoff():
    root, path = cenario()
    out = R.resume_notice("rodada-2", root, root, env={"CEPA_UNTIL_RUN": "1"}) or ""
    check("conteúdo da rodada anterior não é entregue", "WEGO-2337" not in out, out)
    check("aviso aponta para o item reservado pelo drain-plan", "drain-plan" in out, out)


def test_rodada_nao_consome_o_handoff():
    root, path = cenario()
    R.resume_notice("rodada-2", root, root, env={"CEPA_UNTIL_RUN": "1"})
    meta, _, _ = H.parse(path)
    check("frontmatter sem resumed_by", "resumed_by" not in meta, meta)
    check("sem arquivo de reserva", not path.with_suffix(".claim").exists())


def test_sessao_normal_segue_retomando():
    root, path = cenario()
    out = R.resume_notice("dono", root, root, env={}) or ""
    check("sem a marca, o conteúdo é entregue", "WEGO-2337" in out, out)


def _session_start(marca):
    """A fiação: o SessionStart de verdade, como subprocesso, num repo git
    descartável cujo branch tem um handoff fresco de outra sessão."""
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
    if marca:
        env["CEPA_UNTIL_RUN"] = "1"
    r = subprocess.run(
        [sys.executable, str(HOOKS / "session-registry.py")],
        input=json.dumps({"hook_event_name": "SessionStart", "session_id": "rodada-2",
                          "cwd": str(repo)}),
        capture_output=True, text=True, env=env, timeout=60)
    return r, path


def test_session_start_da_rodada_nao_entrega():
    r, path = _session_start(marca=True)
    check("hook sai 0", r.returncode == 0, r.stderr[-300:])
    check("SessionStart da rodada não traz o handoff", "WEGO-2337" not in r.stdout, r.stdout[-400:])
    import json
    ctx = json.loads(r.stdout or "{}").get("hookSpecificOutput", {}).get("additionalContext", "")
    check("SessionStart da rodada avisa que não entregou", "NÃO entregue" in ctx, ctx[-400:])
    check("handoff segue sem reserva", not path.with_suffix(".claim").exists())


def test_session_start_normal_entrega():
    r, _ = _session_start(marca=False)
    check("SessionStart sem a marca traz o handoff", "WEGO-2337" in r.stdout,
          r.stdout[-400:] + r.stderr[-300:])


if __name__ == "__main__":
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            print(f"\n{nome}")
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
