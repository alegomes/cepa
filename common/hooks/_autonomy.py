#!/usr/bin/env python3
"""Faixas de autonomia: leitura de `common/autonomy.yaml` e casamento de ações.

Por que existe: "pergunto ou faço?" era julgamento do agente a cada turno, e o
viés medido foi perguntar demais — na sessão WEGO de 2026-08-03 a 08-10, ~10
das ~20 interrupções eram mecânica reversível que o relatório recomendava e o
dono só carimbava ("Recomendo sim" → "sim"). A fronteira sai do julgamento e
vira este arquivo versionado, lido por código (BACKLOG § "Atrito de decisão";
design em docs/internals/gauntlet-pilot-atrito-decisao.md, Fase 1).

O que este módulo faz (Fase 1):
  - `carregar(repo)`: lê o YAML do plugin, aplica o override do repo
    (`.claude/autonomy.yaml`, que só pode ENDURECER — mover ação para
    `sempre_pergunta` ou acrescentar ação lá) e valida item a item. Item
    malformado é DESCARTADO com aviso, nunca aceito pela metade: um item sem
    `detect:` na faixa automática seria permissão sem impressão digital.
  - `casar(cfg, bash=..., mcp=..., path=..., slash=...)`: encontra a ação que
    o tool-call realiza. Quando o mesmo call casa as duas faixas,
    `sempre_pergunta` vence — o lado seguro.
  - `faixa_de(cfg, id)`: a faixa de um id, para quem já sabe o nome da ação.

O que ele NÃO faz (Fase 2+): rodar `precondicao`, resolver `destino_terminal`
pelo status_map, bloquear tool-call. Isso é do hook `autonomy-gate.py`. Aqui as
condições que não dão para conferir voltam listadas em `condicoes`, e quem
chama decide o que fazer com elas — na Fase 1, o `/board-flow:decide`.

Consumidores: `common/bin/cepa-autonomy` (CLI) e, por ele, o passo 5b do
`board-flow/commands/decide.md`.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

FAIXAS = ("executa_e_reporta", "sempre_pergunta")
FAIXA_AUTOMATICA, FAIXA_PERGUNTA = FAIXAS
DEFAULT_NAO_LISTADO = "sempre-pergunta"
CHAVES_DETECT = ("bash", "mcp", "path", "slash")
# Chaves de `detect:` que são CONDIÇÕES resolvidas pelo hook (Fase 2), não
# padrões casados aqui. Devolvidas em `condicoes` para o chamador saber.
CHAVES_CONDICAO = ("branch_atual", "destino_terminal", "label", "paths_only", "op")
OVERRIDE_REL = os.path.join(".claude", "autonomy.yaml")

# Separadores de segmento num comando de terminal: `cd x && git commit` tem
# que casar `^git commit`, senão toda ação encadeada escapa da lista.
_SEGMENTOS = re.compile(r"\s*(?:&&|\|\||;|\||&|\n)\s*")
# Prefixos que não mudam a ação: `FOO=1 pytest`, `$(git push)`, `(git push)`.
# Segmentos que não realizam ação nenhuma e por isso não contam: `cd x &&
# git commit` é um commit, não "um cd desconhecido mais um commit". Lista
# curta de propósito — crescer aqui é afrouxar.
# Fora da lista de propósito (revisão 2026-10-16, rodada 3): `sort` (`-o` grava),
# `git diff|log|show` (`--output=` grava), `export` (PYTHONPATH/LD_PRELOAD/PATH
# mudam o que o `pytest` seguinte executa). Neutro com `-o`/`--output` deixa de
# ser neutro, pelo mesmo motivo.
_NEUTROS = re.compile(
    r"^(cd|echo|printf|true|ls|cat|head|tail|grep|wc|set -[a-zA-Z]+"
    r"|git (add|status|rev-parse|branch --show-current))(\s|$)"
)
_NEUTRO_QUE_GRAVA = re.compile(r"(^|\s)(-o|--output(=|\s|$))")
# Substituição de comando/processo ou redirecionamento: `pytest $(git push)`,
# `echo x > ~/.bashrc && pytest`. O segmento deixa de ser o que parece — é
# tratado como NÃO LISTADO (pergunta), e um neutro com isso deixa de ser neutro.
_ESCONDIDO = re.compile(r"`|\$\(|<\(|>\(|>")
_PREFIXO = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*(?:\$\(|\()?\s*")


def yaml_do_plugin() -> Path:
    """`common/autonomy.yaml`, irmão do diretório `hooks/` em que este módulo vive."""
    return Path(__file__).resolve().parent.parent / "autonomy.yaml"


def _ler_yaml(path: Path):
    import yaml

    try:
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except FileNotFoundError:
        return None
    except Exception as exc:  # YAML inválido não pode derrubar a leitura toda
        return {"__erro__": f"{path}: {exc}"}


def _item_valido(item, faixa: str, origem: str, avisos: list) -> dict | None:
    if not isinstance(item, dict) or not item.get("id"):
        avisos.append(f"{origem}: item sem `id` em `{faixa}` descartado: {item!r}")
        return None
    det = item.get("detect")
    if not isinstance(det, dict) or not any(k in det for k in CHAVES_DETECT):
        avisos.append(
            f"{origem}: `{item['id']}` sem `detect:` ({'/'.join(CHAVES_DETECT)}) descartado"
        )
        return None
    if sum(k in det for k in CHAVES_DETECT) > 1:
        avisos.append(
            f"{origem}: `{item['id']}` com mais de um padrão em detect: "
            f"({', '.join(k for k in CHAVES_DETECT if k in det)}) descartado — um item, uma impressão digital"
        )
        return None
    for k in CHAVES_DETECT:
        if k in det:
            try:
                re.compile(str(det[k]))
            except re.error as exc:
                avisos.append(f"{origem}: `{item['id']}` com regex inválida em detect.{k}: {exc}")
                return None
    limpo = {"id": str(item["id"]), "detect": dict(det), "faixa": faixa}
    if item.get("precondicao"):
        limpo["precondicao"] = str(item["precondicao"])
    return limpo


def carregar(repo: str | None = None, plugin_yaml: str | Path | None = None) -> dict:
    """Configuração mesclada: plugin + override do repo. Nunca levanta exceção.

    Devolve {"versao", "executa_e_reporta": [...], "sempre_pergunta": [...],
    "default_nao_listado", "avisos": [...], "fontes": [...]}.
    """
    avisos: list[str] = []
    fontes: list[str] = []
    base_path = Path(plugin_yaml) if plugin_yaml else yaml_do_plugin()
    base = _ler_yaml(base_path)
    cfg = {f: [] for f in FAIXAS}
    cfg["versao"] = None
    cfg["default_nao_listado"] = DEFAULT_NAO_LISTADO
    if not isinstance(base, dict) or "__erro__" in (base or {}):
        avisos.append(
            f"{base_path}: ausente ou ilegível ({(base or {}).get('__erro__', 'sem conteúdo')}); "
            f"sem lista, toda ação cai em `{DEFAULT_NAO_LISTADO}`"
        )
    else:
        fontes.append(str(base_path))
        cfg["versao"] = base.get("versao")
        if base.get("default_nao_listado") not in (None, DEFAULT_NAO_LISTADO):
            avisos.append(
                f"{base_path}: default_nao_listado={base.get('default_nao_listado')!r} ignorado; "
                f"o default é `{DEFAULT_NAO_LISTADO}` por decisão de design"
            )
        vistos: dict[str, str] = {}
        for faixa in FAIXAS:
            for item in base.get(faixa) or []:
                ok = _item_valido(item, faixa, str(base_path), avisos)
                if ok is None:
                    continue
                if ok["id"] in vistos:
                    avisos.append(
                        f"{base_path}: `{ok['id']}` repetido ({vistos[ok['id']]} e {faixa}); "
                        f"a segunda ocorrência foi descartada"
                    )
                    continue
                vistos[ok["id"]] = faixa
                cfg[faixa].append(ok)

    if repo:
        _aplicar_override(cfg, Path(repo) / OVERRIDE_REL, avisos, fontes)

    cfg["avisos"] = avisos
    cfg["fontes"] = fontes
    return cfg


def _aplicar_override(cfg: dict, path: Path, avisos: list, fontes: list) -> None:
    """O override do repo só ENDURECE: move id para `sempre_pergunta` ou
    acrescenta id novo lá. Tudo o mais é ignorado com aviso — afrouxar é diff
    versionado no cepa, nunca decisão local."""
    ov = _ler_yaml(path)
    if ov is None:
        return
    if not isinstance(ov, dict) or "__erro__" in ov:
        avisos.append(f"{path}: override ilegível, ignorado ({(ov or {}).get('__erro__', 'não é um mapa')})")
        return
    fontes.append(str(path))
    if ov.get(FAIXA_AUTOMATICA):
        avisos.append(
            f"{path}: `{FAIXA_AUTOMATICA}` ignorado — override só pode endurecer; "
            f"promover ação é edição em common/autonomy.yaml"
        )
    if ov.get("default_nao_listado") not in (None, DEFAULT_NAO_LISTADO):
        avisos.append(f"{path}: default_nao_listado ignorado — o default não é configurável por repo")
    for item in ov.get(FAIXA_PERGUNTA) or []:
        ident = item.get("id") if isinstance(item, dict) else item
        if not ident:
            avisos.append(f"{path}: item sem id em `{FAIXA_PERGUNTA}` ignorado: {item!r}")
            continue
        ident = str(ident)
        movido = [i for i in cfg[FAIXA_AUTOMATICA] if i["id"] == ident]
        if movido:
            cfg[FAIXA_AUTOMATICA] = [i for i in cfg[FAIXA_AUTOMATICA] if i["id"] != ident]
            novo = dict(movido[0], faixa=FAIXA_PERGUNTA, movido_por=str(path))
            cfg[FAIXA_PERGUNTA].append(novo)
            continue
        if any(i["id"] == ident for i in cfg[FAIXA_PERGUNTA]):
            continue  # já está lá
        ok = _item_valido(item if isinstance(item, dict) else {"id": ident}, FAIXA_PERGUNTA, str(path), avisos)
        if ok is not None:
            ok["movido_por"] = str(path)
            cfg[FAIXA_PERGUNTA].append(ok)


def faixa_de(cfg: dict, ident: str) -> str | None:
    for faixa in FAIXAS:
        if any(i["id"] == ident for i in cfg.get(faixa) or []):
            return faixa
    return None


def _segmentos(bash: str) -> list[str]:
    segs = []
    for seg in _SEGMENTOS.split(bash.strip()):
        seg = _PREFIXO.sub("", seg).rstrip(") ").strip()
        if seg:
            segs.append(seg)
    return segs


def _condicoes_ok(item: dict, cond: dict | None) -> bool | None:
    """True: toda condição do detect bate com `cond`. False: alguma não bate.
    None: alguma não foi informada (não dá para saber)."""
    cond = cond or {}
    resultado = True
    for k, v in item["detect"].items():
        if k not in CHAVES_CONDICAO or k == "op":
            continue
        if k not in cond:
            resultado = None
            continue
        dado = cond[k]
        if isinstance(v, bool):
            if str(dado).lower() in ("true", "1", "sim", "yes") != v:
                return False
        elif re.search(str(v), str(dado)) is None:
            return False
    return resultado


def _casa_padrao(item: dict, bash, mcp, path, op, slash) -> bool:
    det = item["detect"]
    if "bash" in det:
        return bool(bash) and re.search(str(det["bash"]), bash) is not None
    if "mcp" in det:
        return bool(mcp) and re.search(str(det["mcp"]), mcp) is not None
    if "path" in det:
        if not path or re.search(str(det["path"]), path) is None:
            return False
        exigido = str(det.get("op", "any"))
        return exigido == "any" or (op or "any") == exigido
    if "slash" in det:
        return bool(slash) and re.search(str(det["slash"]), slash) is not None
    return False


def _casa_item(item: dict, bash, mcp, path, op, slash, cond) -> bool:
    """Casa padrão E condições. Ação automática com condição não informada
    NÃO casa (não se libera o que não dá para conferir); ação de pergunta
    casa mesmo assim (o lado seguro), e a condição volta em `condicoes`."""
    if not _casa_padrao(item, bash, mcp, path, op, slash):
        return False
    ok = _condicoes_ok(item, cond)
    if ok is False:
        return False
    if ok is None and item["faixa"] == FAIXA_AUTOMATICA:
        return False
    return True


def _resultado(item: dict | None, cfg: dict) -> dict:
    if item is None:
        return {
            "faixa": FAIXA_PERGUNTA if cfg.get("default_nao_listado", DEFAULT_NAO_LISTADO) == DEFAULT_NAO_LISTADO else FAIXA_AUTOMATICA,
            "id": None, "precondicao": None, "condicoes": {}, "listado": False,
        }
    return {
        "faixa": item["faixa"],
        "id": item["id"],
        "precondicao": item.get("precondicao"),
        "condicoes": {k: v for k, v in item["detect"].items() if k in CHAVES_CONDICAO and k != "op"},
        "listado": True,
    }


def _casar_um(cfg: dict, bash, mcp, path, op, slash, cond) -> dict | None:
    for faixa in (FAIXA_PERGUNTA, FAIXA_AUTOMATICA):
        for item in cfg.get(faixa) or []:
            if _casa_item(item, bash, mcp, path, op, slash, cond):
                return item
    return None


def casar(cfg: dict, bash: str | None = None, mcp: str | None = None,
          path: str | None = None, op: str | None = None, slash: str | None = None,
          cond: dict | None = None) -> dict:
    """A ação que este tool-call realiza, e a faixa dela.

    Devolve {"faixa", "id", "precondicao", "condicoes", "listado"}. Casou as
    duas faixas → `sempre_pergunta` (o lado seguro). Não casou nada → faixa do
    default, `id` None, `listado` False.

    Comando de terminal é julgado segmento a segmento (`&&`, `;`, `|`, `&`),
    ignorando os neutros (`cd`, `echo`, `git add`...) sem redirecionamento,
    substituição nem `-o`/`--output`; segmento com `$(`, crase, `<(` ou `>` é não listado: um segmento de pergunta decide
    pelo comando inteiro, em qualquer posição; senão um segmento não listado
    decide (default); só é automático o comando em que TODOS os segmentos
    são automáticos. Sem isso `rm -rf x && pytest` seria "rodar
    build" — uma parte conhecida não pode lavar a parte desconhecida.
    `cond` são as condições do detect que o chamador já conferiu
    (ex.: {"label": "infra"}).
    """
    if bash:
        automatico = None   # o primeiro item automático, se todos os segmentos forem
        nao_listado = False
        segs = [s for s in _segmentos(bash)
                if not (_NEUTROS.match(s) and not _ESCONDIDO.search(s) and not _NEUTRO_QUE_GRAVA.search(s))]
        for seg in segs or [bash]:
            if _ESCONDIDO.search(seg):
                nao_listado = True   # `pytest $(git push)` não é "rodar build"
                continue
            item = _casar_um(cfg, seg, None, None, None, None, cond)
            if item is None:
                nao_listado = True
            elif item["faixa"] == FAIXA_PERGUNTA:
                return _resultado(item, cfg)   # pergunta vence em qualquer posição
            else:
                automatico = automatico or item
        return _resultado(None if nao_listado else automatico, cfg)
    return _resultado(_casar_um(cfg, None, mcp, path, op, slash, cond), cfg)
