#!/usr/bin/env python3
"""Encadeamento de sessões para o launcher `cepa` (CS-3 do ciclo cepa-espiral-c1).

Roda DEPOIS que o `claude` lançado pelo `cepa` sai. Se a sessão que acabou de
sair deixou o próximo passo gravado em
`<raiz-principal>/.claude/sessions/<session_id>.next.json`:

    {"repo": "/abs/path", "modo": "descoberta", "brief": "<texto>"}

este script apaga o arquivo, entra em `repo` e substitui o próprio processo
pelo `cepa` de novo, com `--modo <modo>` e o brief como prompt inicial. Se o
arquivo traz `intencao` ({proposito, para_quando, plano}), vão também
`--proposito`, `--para-quando` e `--plano` (o cepa grava a intenção da sessão);
sem ela, a sessão seguinte nasce sem intenção, nunca com o brief no lugar. A
sessão seguinte abre no repo e no modo certos sem o dono digitar nada. Sem o
arquivo, sai com o código que recebeu e nada acontece.

Como o launcher sabe qual `<session_id>` é o da sessão que acabou de sair: ele
só conhece o `CEPA_LAUNCH_ID` que gerou. O hook `session-registry`, no
SessionStart, anota cada `session_id` nascido daquela abertura em
`<raiz-principal>/.claude/sessions/<launch_id>.launch`, um por linha (um
`/clear` abre outro `session_id` no mesmo processo). Aqui o mais recente que
deixou `.next.json` vence.

Uso: session-chain.py <launch_id> <cepa> <rc>
Saída: exec do `cepa` (encadeou), ou exit <rc> (nada a encadear, ou arquivo
inválido, que fica no lugar para o dono ver).
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _wtlib as L  # noqa: E402


def breadcrumb_path(root: str, launch_id: str):
    return L.sessions_dir(root) / f"{launch_id}.launch"


def next_path(root: str, session_id: str):
    return L.sessions_dir(root) / f"{session_id}.next.json"


def main() -> int:
    if len(sys.argv) != 4:
        return 0
    launch_id, cepa, rc_s = sys.argv[1:]
    try:
        rc = int(rc_s)
    except ValueError:
        rc = 0
    if os.environ.get("CEPA_ENCADEAR", "on") == "off" or not launch_id:
        return rc
    root = L.main_root(os.getcwd())
    if not root:
        return rc

    crumb = breadcrumb_path(root, launch_id)
    try:
        sids = [s.strip() for s in crumb.read_text(encoding="utf-8").splitlines() if s.strip()]
    except OSError:
        return rc
    try:
        crumb.unlink()
    except OSError:
        pass

    nxt = next((next_path(root, s) for s in reversed(sids) if next_path(root, s).exists()), None)
    if nxt is None:
        return rc

    try:
        spec = json.loads(nxt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"✗ cepa: próximo passo ilegível em {nxt} ({e}); não encadeei", file=sys.stderr)
        return rc
    repo = spec.get("repo") if isinstance(spec, dict) else None
    modo = spec.get("modo") if isinstance(spec, dict) else None
    brief = spec.get("brief") if isinstance(spec, dict) else None
    if not (isinstance(repo, str) and os.path.isdir(repo)
            and isinstance(modo, str) and modo
            and isinstance(brief, str) and brief.strip()):
        print(f"✗ cepa: próximo passo inválido em {nxt} (precisa de repo existente, "
              f"modo e brief); não encadeei", file=sys.stderr)
        return rc

    try:
        nxt.unlink()
    except OSError:
        pass
    # O registro da sessão que saiu carrega o pid do `cepa` (o claim é gravado
    # com ele), que é este processo. Sem o SessionEnd, ele pareceria uma sessão
    # viva na árvore e a próxima abertura se isolaria numa worktree à toa.
    for f, e in L.read_entries(root):
        if e.get("pid") == os.getpid() and e.get("hostname") in (None, L.host()):
            try:
                f.unlink()
            except OSError:
                pass
    print(f"↻ cepa: próxima sessão em {repo} (modo {modo}) — CEPA_ENCADEAR=off desliga",
          file=sys.stderr)
    os.chdir(repo)
    os.execv(cepa, [cepa, "--modo", modo, *intencao_args(spec.get("intencao"), nxt), brief])
    return rc  # unreachable


def intencao_args(it, nxt) -> list:
    """Flags do `cepa` que gravam a intenção da sessão seguinte. Só com as três
    partes escritas para ela; o brief fala da sessão que saiu e não vira propósito."""
    if it is None:
        return []
    plano = it.get("plano") if isinstance(it, dict) else None
    textos = [it.get(k) for k in ("proposito", "para_quando")] if isinstance(it, dict) else []
    if not (len(textos) == 2 and all(isinstance(t, str) and t.strip() for t in textos)
            and isinstance(plano, list) and plano
            and all(isinstance(i, str) and i.strip() and "\n" not in i for i in plano)):
        print(f"⚠ cepa: intenção inválida em {nxt}; a sessão seguinte abre sem ela",
              file=sys.stderr)
        return []
    return ["--proposito", textos[0], "--para-quando", textos[1], "--plano", "\n".join(plano)]


if __name__ == "__main__":
    sys.exit(main())
