"""_queuepath — onde mora a fila single-track de um repo, nos dois layouts.

A fila saiu de `.claude/programs/<nome>/plan.yaml` (chave `program:`, escrita
pelo /common:plan) para `.claude/queues/<nome>/queue.yaml` (chave `queue:`,
escrita pelo /common:queue), para casar com o vocabulário de
docs/how-it-fits.md. Durante a transição todo consumidor LÊ OS DOIS layouts; o
`cepa-plan migrate` move as filas existentes. Plano de ondas do maestro
(`parallel-waves`) continua em `.claude/programs/<nome>/plan.yaml`: é um
programa, não uma fila.

Este módulo é a única cópia da regra de resolução — os binários o importam.
"""
from pathlib import Path

NEW_DIR = ".claude/queues"
NEW_FILE = "queue.yaml"
LEGACY_DIR = ".claude/programs"
LEGACY_FILE = "plan.yaml"


def _novo(root, name):
    return Path(root) / NEW_DIR / name / NEW_FILE


def _legado(root, name):
    return Path(root) / LEGACY_DIR / name / LEGACY_FILE


def queue_file(root, name):
    """O arquivo da fila: novo se existe; senão o legado se existe; senão o
    caminho NOVO (fila nova nasce no layout novo)."""
    novo = _novo(root, name)
    if novo.exists():
        return novo
    legado = _legado(root, name)
    if legado.exists():
        return legado
    return novo


def queue_dir(root, name):
    """O diretório da fila (onde moram `until/` e o `.bak`)."""
    return queue_file(root, name).parent


def queue_files(root):
    """[(nome, caminho)] de todo candidato nos dois layouts, por nome.

    Quando o mesmo nome existe nos dois, o novo ganha. Quem chama ainda filtra
    por `mode: single-track` (o legado também guarda planos de ondas)."""
    achados = {}
    for base, arq in ((LEGACY_DIR, LEGACY_FILE), (NEW_DIR, NEW_FILE)):
        for p in (Path(root) / base).glob(f"*/{arq}"):
            achados[p.parent.name] = p  # o novo vem depois e sobrescreve
    return sorted(achados.items())


def queue_name_of(plan, fallback=None):
    """O nome gravado no cabeçalho: `queue:` (novo) ou `program:` (legado)."""
    if not isinstance(plan, dict):
        return fallback
    return plan.get("queue") or plan.get("program") or fallback


def both_layouts(root, name):
    """True se o mesmo nome existe nos dois layouts (o novo esconde o legado)."""
    return _novo(root, name).exists() and _legado(root, name).exists()
