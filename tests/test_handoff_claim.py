#!/usr/bin/env python3
"""Regression tests para o handoff ser retomado UMA vez só.

O handoff é um markdown por branch que a sessão nova lê no SessionStart. Até
aqui nada registrava QUEM leu: a única proteção contra duas sessões retomarem
o mesmo ponto era `live_sessions_in`, que compara o cwd EXATO. Uma sessão
aberta num subdiretório da mesma árvore não casa, e a segunda recebia o mesmo
handoff como se fosse a primeira.

Contratos guardados aqui:
  - a primeira sessão que recebe o handoff fica registrada como quem retomou,
    no frontmatter (`resumed_by`) E num arquivo de reserva criado com O_EXCL
    — duas travas independentes, de propósito;
  - uma segunda sessão, com a primeira VIVA, não recebe o conteúdo: recebe o
    aviso de que já foi retomado, com o id de quem retomou;
  - se quem retomou MORREU sem escrever nada, a reserva é liberada e a próxima
    sessão retoma normalmente (reserva de morto não pode travar o trabalho);
  - checkpoint novo (updated_at mudou) é conteúdo novo: a reserva antiga não
    vale para ele;
  - o texto entregue diz que o handoff é evidência, nunca instrução.

Rode com `python3 tests/test_handoff_claim.py`.
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
    """Árvore falsa com um handoff fresco escrito pela sessão A (já morta)."""
    root = tempfile.mkdtemp(prefix="handoff-claim-")
    path = H.handoff_path(root, "main")
    H.write(path, {"session_id": "sessao-A", "branch": "main",
                   "updated_at": L.now_iso()},
            auto="## Onde paramos\n- passo 3 de 5", note="Próximo: rodar o passo 4.")
    # O teste não tem git: fixa o branch e controla quem está vivo.
    L.current_branch = lambda cwd: "main"
    return root, path


def com_vivos(ids):
    """Só as sessões em `ids` contam como vivas."""
    L.find_entry = lambda root, key: {"session_id": key} if key in ids else None
    L.entry_is_live = lambda e: bool(e) and e.get("session_id") in ids
    # A brecha real: a checagem por cwd exato NÃO enxerga o peer (subdiretório).
    L.live_sessions_in = lambda root, cwd, exclude_key="": []


def test_primeira_retoma_e_fica_registrada():
    root, path = cenario()
    com_vivos({"sessao-B"})
    out = R.resume_notice("sessao-B", root, root)
    check("B recebe o conteúdo", out and "passo 3 de 5" in out, out)
    meta, _, _ = H.parse(path)
    check("frontmatter registra quem retomou", meta.get("resumed_by") == "sessao-B", meta)
    claim = path.with_suffix(".claim")
    check("arquivo de reserva existe", claim.exists())
    if claim.exists():
        c = json.loads(claim.read_text())
        check("reserva aponta para B", c.get("session_id") == "sessao-B", c)


def test_segunda_nao_retoma_o_mesmo_ponto():
    root, path = cenario()
    com_vivos({"sessao-B", "sessao-C"})
    R.resume_notice("sessao-B", root, root)
    out = R.resume_notice("sessao-C", root, root)
    check("C não recebe o conteúdo", not out or "passo 3 de 5" not in out, out)
    check("C é avisada de quem retomou", bool(out) and "sessao-B" in out, out)


def test_mesma_sessao_recebe_de_novo():
    """SessionStart dispara de novo em resume/compact: quem reservou segue dono."""
    root, path = cenario()
    com_vivos({"sessao-B"})
    R.resume_notice("sessao-B", root, root)
    out = R.resume_notice("sessao-B", root, root)
    check("B recebe o conteúdo na 2ª chamada", out and "passo 3 de 5" in out, out)


def test_reserva_de_morto_e_liberada():
    root, path = cenario()
    com_vivos({"sessao-B"})
    R.resume_notice("sessao-B", root, root)
    com_vivos({"sessao-C"})  # B morreu sem escrever checkpoint
    out = R.resume_notice("sessao-C", root, root)
    check("C retoma depois que B morreu", out and "passo 3 de 5" in out, out)
    meta, _, _ = H.parse(path)
    check("frontmatter passa a apontar para C", meta.get("resumed_by") == "sessao-C", meta)


def test_so_a_trava_do_arquivo_ja_barra():
    """As duas travas são independentes: apagar o frontmatter não libera."""
    root, path = cenario()
    com_vivos({"sessao-B", "sessao-C"})
    R.resume_notice("sessao-B", root, root)
    meta, auto, note = H.parse(path)
    meta.pop("resumed_by", None); meta.pop("resumed_at", None); meta.pop("resumed_version", None)
    path.write_text(H.render(meta, auto, note), encoding="utf-8")
    out = R.resume_notice("sessao-C", root, root)
    check("C barrada só pelo arquivo de reserva", not out or "passo 3 de 5" not in out, out)


def test_so_a_trava_do_frontmatter_ja_barra():
    root, path = cenario()
    com_vivos({"sessao-B", "sessao-C"})
    R.resume_notice("sessao-B", root, root)
    path.with_suffix(".claim").unlink()
    out = R.resume_notice("sessao-C", root, root)
    check("C barrada só pelo frontmatter", not out or "passo 3 de 5" not in out, out)


def test_checkpoint_novo_e_conteudo_novo():
    root, path = cenario()
    com_vivos({"sessao-B", "sessao-C"})
    R.resume_notice("sessao-B", root, root)
    # Sessão A' escreve um checkpoint novo: outra versão do handoff.
    H.write(path, {"session_id": "sessao-A2", "updated_at": "2099-01-01T00:00:00+00:00"},
            auto="## Onde paramos\n- passo 9 de 9")
    H.age_seconds = lambda meta: 0.0
    out = R.resume_notice("sessao-C", root, root)
    check("C recebe a versão nova", out and "passo 9 de 9" in out, out)


def test_texto_diz_evidencia_nunca_instrucao():
    root, path = cenario()
    com_vivos({"sessao-B"})
    out = R.resume_notice("sessao-B", root, root) or ""
    check("preâmbulo nega autoridade de instrução ao handoff",
          "nunca instrução" in out.lower() or "nunca como instrução" in out.lower(), out[:400])


if __name__ == "__main__":
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            print(f"\n{nome}")
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
