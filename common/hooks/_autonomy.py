#!/usr/bin/env python3
"""Autonomy bands: reads `common/autonomy.yaml` and matches actions to them.

Why it exists: "do I ask or just do it?" used to be agent judgment on every
turn, and the measured bias was asking too much. In the WEGO session of
2026-08-03 to 08-10, ~10 of the ~20 interruptions were reversible mechanics
that the report recommended and the owner just rubber-stamped ("Recomendo
sim" -> "sim"). The boundary moves out of judgment and into this versioned
file, read by code (BACKLOG section "Atrito de decisão"; design in
docs/internals/gauntlet-pilot-atrito-decisao.md, Phase 1).

What this module does (Phase 1):
  - `load(repo)`: reads the plugin YAML, applies the repo override
    (`.claude/autonomy.yaml`, which can only HARDEN: move an action to
    `sempre_pergunta` or add an action there) and validates item by item. A
    malformed item is DISCARDED with a warning, never half-accepted: an item
    without `detect:` in the automatic band would be permission without a
    fingerprint.
  - `match(cfg, bash=..., mcp=..., path=..., slash=...)`: finds the action the
    tool call performs. When the same call matches both bands,
    `sempre_pergunta` wins, the safe side.
  - `band_of(cfg, id)`: the band of an id, for callers who already know the
    action name.

What it does NOT do (Phase 2+): run `precondicao`, resolve `destino_terminal`
through the status_map, block a tool call. That belongs to the
`autonomy-gate.py` hook. Here, the conditions that cannot be checked come back
listed in `condicoes`, and the caller decides what to do with them; in
Phase 1, that caller is `/board-flow:decide`.

Consumers: `common/bin/cepa-autonomy` (CLI) and, through it, step 5b of
`board-flow/commands/decide.md`.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

BANDS = ("executa_e_reporta", "sempre_pergunta")
BAND_AUTOMATIC, BAND_ASK = BANDS
DEFAULT_UNLISTED = "sempre-pergunta"
DETECT_KEYS = ("bash", "mcp", "path", "slash")
# `detect:` keys that are CONDITIONS resolved by the hook (Phase 2), not
# patterns matched here. Returned in `condicoes` so the caller knows.
CONDITION_KEYS = ("branch_atual", "destino_terminal", "label", "paths_only", "op")
OVERRIDE_REL = os.path.join(".claude", "autonomy.yaml")

# Segment separators in a terminal command: `cd x && git commit` has to match
# `^git commit`, otherwise every chained action escapes the list.
_SEGMENT_SPLIT = re.compile(r"\s*(?:&&|\|\||;|\||&|\n)\s*")
# Segments that perform no action at all and therefore do not count: `cd x &&
# git commit` is a commit, not "an unknown cd plus a commit". Short list on
# purpose: growing it loosens the policy.
# Left off the list on purpose (review 2026-10-16, round 3): `sort` (`-o`
# writes), `git diff|log|show` (`--output=` writes), `export`
# (PYTHONPATH/LD_PRELOAD/PATH change what the following `pytest` runs). A
# neutral command with `-o`/`--output` stops being neutral, for the same reason.
_NEUTRAL = re.compile(
    r"^(cd|echo|printf|true|ls|cat|head|tail|grep|wc|set -[a-zA-Z]+"
    r"|git (add|status|rev-parse|branch --show-current))(\s|$)"
)
_NEUTRAL_THAT_WRITES = re.compile(r"(^|\s)(-o|--output(=|\s|$))")
# Command/process substitution or redirection: `pytest $(git push)`,
# `echo x > ~/.bashrc && pytest`. The segment stops being what it looks like:
# it is treated as UNLISTED (ask), and a neutral command with this stops being neutral.
_HIDDEN = re.compile(r"`|\$\(|<\(|>\(|>")
# Prefixes that do not change the action: `FOO=1 pytest`, `$(git push)`, `(git push)`.
_PREFIX = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*(?:\$\(|\()?\s*")


def plugin_yaml_path() -> Path:
    """`common/autonomy.yaml`, sibling of the `hooks/` directory this module lives in."""
    return Path(__file__).resolve().parent.parent / "autonomy.yaml"


def _read_yaml(path: Path):
    import yaml

    try:
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except FileNotFoundError:
        return None
    except Exception as exc:  # invalid YAML must not take down the whole read
        return {"__erro__": f"{path}: {exc}"}


def _valid_item(item, band: str, source: str, warnings: list) -> dict | None:
    if not isinstance(item, dict) or not item.get("id"):
        warnings.append(f"{source}: item sem `id` em `{band}` descartado: {item!r}")
        return None
    det = item.get("detect")
    if not isinstance(det, dict) or not any(k in det for k in DETECT_KEYS):
        warnings.append(
            f"{source}: `{item['id']}` sem `detect:` ({'/'.join(DETECT_KEYS)}) descartado"
        )
        return None
    if sum(k in det for k in DETECT_KEYS) > 1:
        warnings.append(
            f"{source}: `{item['id']}` com mais de um padrão em detect: "
            f"({', '.join(k for k in DETECT_KEYS if k in det)}) descartado — um item, uma impressão digital"
        )
        return None
    for k in DETECT_KEYS:
        if k in det:
            try:
                re.compile(str(det[k]))
            except re.error as exc:
                warnings.append(f"{source}: `{item['id']}` com regex inválida em detect.{k}: {exc}")
                return None
    clean = {"id": str(item["id"]), "detect": dict(det), "faixa": band}
    if item.get("precondicao"):
        clean["precondicao"] = str(item["precondicao"])
    return clean


def load(repo: str | None = None, plugin_yaml: str | Path | None = None) -> dict:
    """Merged configuration: plugin + repo override. Never raises.

    Returns {"versao", "executa_e_reporta": [...], "sempre_pergunta": [...],
    "default_nao_listado", "avisos": [...], "fontes": [...]}.
    """
    warnings: list[str] = []
    sources: list[str] = []
    base_path = Path(plugin_yaml) if plugin_yaml else plugin_yaml_path()
    base = _read_yaml(base_path)
    cfg = {f: [] for f in BANDS}
    cfg["versao"] = None
    cfg["default_nao_listado"] = DEFAULT_UNLISTED
    if not isinstance(base, dict) or "__erro__" in (base or {}):
        warnings.append(
            f"{base_path}: ausente ou ilegível ({(base or {}).get('__erro__', 'sem conteúdo')}); "
            f"sem lista, toda ação cai em `{DEFAULT_UNLISTED}`"
        )
    else:
        sources.append(str(base_path))
        cfg["versao"] = base.get("versao")
        if base.get("default_nao_listado") not in (None, DEFAULT_UNLISTED):
            warnings.append(
                f"{base_path}: default_nao_listado={base.get('default_nao_listado')!r} ignorado; "
                f"o default é `{DEFAULT_UNLISTED}` por decisão de design"
            )
        seen: dict[str, str] = {}
        for band in BANDS:
            for item in base.get(band) or []:
                ok = _valid_item(item, band, str(base_path), warnings)
                if ok is None:
                    continue
                if ok["id"] in seen:
                    warnings.append(
                        f"{base_path}: `{ok['id']}` repetido ({seen[ok['id']]} e {band}); "
                        f"a segunda ocorrência foi descartada"
                    )
                    continue
                seen[ok["id"]] = band
                cfg[band].append(ok)

    if repo:
        _apply_override(cfg, Path(repo) / OVERRIDE_REL, warnings, sources)

    cfg["avisos"] = warnings
    cfg["fontes"] = sources
    return cfg


def _apply_override(cfg: dict, path: Path, warnings: list, sources: list) -> None:
    """The repo override only HARDENS: it moves an id to `sempre_pergunta` or
    adds a new id there. Everything else is ignored with a warning: loosening
    is a versioned diff in cepa, never a local decision."""
    ov = _read_yaml(path)
    if ov is None:
        return
    if not isinstance(ov, dict) or "__erro__" in ov:
        warnings.append(f"{path}: override ilegível, ignorado ({(ov or {}).get('__erro__', 'não é um mapa')})")
        return
    sources.append(str(path))
    if ov.get(BAND_AUTOMATIC):
        warnings.append(
            f"{path}: `{BAND_AUTOMATIC}` ignorado — override só pode endurecer; "
            f"promover ação é edição em common/autonomy.yaml"
        )
    if ov.get("default_nao_listado") not in (None, DEFAULT_UNLISTED):
        warnings.append(f"{path}: default_nao_listado ignorado — o default não é configurável por repo")
    for item in ov.get(BAND_ASK) or []:
        ident = item.get("id") if isinstance(item, dict) else item
        if not ident:
            warnings.append(f"{path}: item sem id em `{BAND_ASK}` ignorado: {item!r}")
            continue
        ident = str(ident)
        moved = [i for i in cfg[BAND_AUTOMATIC] if i["id"] == ident]
        if moved:
            cfg[BAND_AUTOMATIC] = [i for i in cfg[BAND_AUTOMATIC] if i["id"] != ident]
            new = dict(moved[0], faixa=BAND_ASK, movido_por=str(path))
            cfg[BAND_ASK].append(new)
            continue
        if any(i["id"] == ident for i in cfg[BAND_ASK]):
            continue  # already there
        ok = _valid_item(item if isinstance(item, dict) else {"id": ident}, BAND_ASK, str(path), warnings)
        if ok is not None:
            ok["movido_por"] = str(path)
            cfg[BAND_ASK].append(ok)


def band_of(cfg: dict, ident: str) -> str | None:
    for band in BANDS:
        if any(i["id"] == ident for i in cfg.get(band) or []):
            return band
    return None


def _segments(bash: str) -> list[str]:
    segs = []
    for seg in _SEGMENT_SPLIT.split(bash.strip()):
        seg = _PREFIX.sub("", seg).rstrip(") ").strip()
        if seg:
            segs.append(seg)
    return segs


def _conditions_ok(item: dict, cond: dict | None) -> bool | None:
    """True: every detect condition matches `cond`. False: some do not match.
    None: some were not provided (cannot tell)."""
    cond = cond or {}
    outcome = True
    for k, v in item["detect"].items():
        if k not in CONDITION_KEYS or k == "op":
            continue
        if k not in cond:
            outcome = None
            continue
        given = cond[k]
        if isinstance(v, bool):
            if str(given).lower() in ("true", "1", "sim", "yes") != v:
                return False
        elif re.search(str(v), str(given)) is None:
            return False
    return outcome


def _matches_pattern(item: dict, bash, mcp, path, op, slash) -> bool:
    det = item["detect"]
    if "bash" in det:
        return bool(bash) and re.search(str(det["bash"]), bash) is not None
    if "mcp" in det:
        return bool(mcp) and re.search(str(det["mcp"]), mcp) is not None
    if "path" in det:
        if not path or re.search(str(det["path"]), path) is None:
            return False
        required = str(det.get("op", "any"))
        return required == "any" or (op or "any") == required
    if "slash" in det:
        return bool(slash) and re.search(str(det["slash"]), slash) is not None
    return False


def _matches_item(item: dict, bash, mcp, path, op, slash, cond) -> bool:
    """Matches pattern AND conditions. An automatic action with a condition
    not provided does NOT match (we do not release what cannot be checked); an
    ask action matches anyway (the safe side), and the condition comes back in
    `condicoes`."""
    if not _matches_pattern(item, bash, mcp, path, op, slash):
        return False
    ok = _conditions_ok(item, cond)
    if ok is False:
        return False
    if ok is None and item["faixa"] == BAND_AUTOMATIC:
        return False
    return True


def _result(item: dict | None, cfg: dict) -> dict:
    if item is None:
        return {
            "faixa": BAND_ASK if cfg.get("default_nao_listado", DEFAULT_UNLISTED) == DEFAULT_UNLISTED else BAND_AUTOMATIC,
            "id": None, "precondicao": None, "condicoes": {}, "listado": False,
        }
    return {
        "faixa": item["faixa"],
        "id": item["id"],
        "precondicao": item.get("precondicao"),
        "condicoes": {k: v for k, v in item["detect"].items() if k in CONDITION_KEYS and k != "op"},
        "listado": True,
    }


def _match_one(cfg: dict, bash, mcp, path, op, slash, cond) -> dict | None:
    for band in (BAND_ASK, BAND_AUTOMATIC):
        for item in cfg.get(band) or []:
            if _matches_item(item, bash, mcp, path, op, slash, cond):
                return item
    return None


def match(cfg: dict, bash: str | None = None, mcp: str | None = None,
          path: str | None = None, op: str | None = None, slash: str | None = None,
          cond: dict | None = None) -> dict:
    """The action this tool call performs, and its band.

    Returns {"faixa", "id", "precondicao", "condicoes", "listado"}. Matched
    both bands -> `sempre_pergunta` (the safe side). Matched nothing -> the
    default band, `id` None, `listado` False.

    A terminal command is judged segment by segment (`&&`, `;`, `|`, `&`),
    ignoring the neutral ones (`cd`, `echo`, `git add`...) without redirection,
    substitution or `-o`/`--output`; a segment with `$(`, a backtick, `<(` or
    `>` is unlisted: an ask segment decides for the whole command, in any
    position; otherwise an unlisted segment decides (default); a command is
    automatic only if ALL its segments are automatic. Without this,
    `rm -rf x && pytest` would be "run build": a known part must not launder
    the unknown part.
    `cond` are the detect conditions the caller has already checked
    (e.g. {"label": "infra"}).
    """
    if bash:
        automatic = None   # the first automatic item, if all segments are
        unlisted = False
        segs = [s for s in _segments(bash)
                if not (_NEUTRAL.match(s) and not _HIDDEN.search(s) and not _NEUTRAL_THAT_WRITES.search(s))]
        for seg in segs or [bash]:
            if _HIDDEN.search(seg):
                unlisted = True   # `pytest $(git push)` is not "run build"
                continue
            item = _match_one(cfg, seg, None, None, None, None, cond)
            if item is None:
                unlisted = True
            elif item["faixa"] == BAND_ASK:
                return _result(item, cfg)   # ask wins in any position
            else:
                automatic = automatic or item
        return _result(None if unlisted else automatic, cfg)
    return _result(_match_one(cfg, None, mcp, path, op, slash, cond), cfg)
