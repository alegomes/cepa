#!/usr/bin/env python3
"""Compares each plugin's version in the REPO with the one in the installed CACHE.

Why this is a module and not a function inside whoever asks: the question
"is the harness that is running the one I think it is?" is asked from two
places with different purposes:

  - `common/bin/cepa-doctor` does the full diagnosis, on demand;
  - `common/hooks/session-registry.py` warns at session boot, unprompted
    (the voluntary trigger was exactly the failure: nobody runs the doctor
    precisely when they suspect nothing).

Two copies of the comparator would be the same disease the harness already has
in the path-locks (5 copies, fixes by discipline). One only, imported by both.

Contract: nothing here raises to the caller. A comparator that breaks the
session boot would be turned off, and then it protects nobody.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"


def semver(v: str):
    """(1, 2, 3) from "1.2.3". Anything unreadable becomes (0,)."""
    try:
        return tuple(int(x) for x in re.findall(r"\d+", str(v))[:3])
    except Exception:  # noqa: BLE001
        return (0,)


def cepa_repo_root():
    """Which clone the installed marketplace came from, according to CC itself."""
    try:
        mk = json.loads(
            (CLAUDE_DIR / "plugins" / "known_marketplaces.json").read_text(encoding="utf-8")
        )
        loc = mk.get("cepa", {}).get("installLocation")
        return Path(loc) if loc else None
    except Exception:  # noqa: BLE001
        return None


def last_install():
    """The operational record written by bin/install.sh, or None."""
    try:
        return json.loads(
            (CLAUDE_DIR / "ops" / "last-install.json").read_text(encoding="utf-8")
        )
    except Exception:  # noqa: BLE001
        return None


def age_days(iso: str):
    if not iso:
        return None
    try:
        ts = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds() / 86400


def cache_versions(name: str):
    """Versions present in the cache for a plugin, oldest to newest."""
    cdir = CLAUDE_DIR / "plugins" / "cache" / "cepa" / name
    if not cdir.is_dir():
        return []
    try:
        return sorted((d.name for d in cdir.iterdir() if d.is_dir()), key=semver)
    except OSError:
        return []


def scan(repo_root=None, enabled=None):
    """State of each repo plugin: name, version in the repo, version in the cache.

    Returns a list of dicts with the keys:
      name, repo_version, cache_version (None = nothing installed),
      drift (repo > cache), missing (nothing in the cache), enabled (None = not checked).

    `enabled` is the `enabledPlugins` dict from settings.json, when the caller
    already has it at hand; without it the field comes out None instead of a guess.
    """
    repo = Path(repo_root) if repo_root else cepa_repo_root()
    if not repo or not repo.is_dir():
        return []
    out = []
    for pj in sorted(repo.glob("*/.claude-plugin/plugin.json")):
        try:
            meta = json.loads(pj.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        # The plugin name comes from the manifest, not the directory:
        # docs-topology/ is the source of the "docs" plugin.
        name = meta.get("name") or pj.parent.parent.name
        repo_v = meta.get("version", "0")
        versions = cache_versions(name)
        cache_v = versions[-1] if versions else None
        out.append({
            "name": name,
            "repo_version": repo_v,
            "cache_version": cache_v,
            "missing": cache_v is None,
            "drift": bool(cache_v) and semver(repo_v) > semver(cache_v),
            "enabled": None if enabled is None else (enabled.get(f"{name}@cepa") is True),
        })
    return out


def drifted(repo_root=None):
    """Only the plugins whose repo edit is NOT in effect on this machine."""
    return [p for p in scan(repo_root) if p["drift"] or p["missing"]]


def loaded_now():
    """Version of each plugin that a session opened RIGHT NOW would load from the cache.

    Snapshotted at SessionStart and kept in the session's entry. Without that
    snapshot, nobody can answer the question that cost the most time in this
    harness: "is the session I am in running the hooks I just installed?".

    `scan()` compares REPO with CACHE and catches the "edited and did not
    reinstall" case. It does not catch the opposite, trickier case: I
    reinstalled DURING the session, the cache is already new, and this session
    keeps running the old hooks it read at opening. The two look the same in
    the doctor and fail differently.
    """
    out = {}
    try:
        for p in scan():
            if p["cache_version"]:
                out[p["name"]] = p["cache_version"]
    except Exception:  # noqa: BLE001
        pass
    return out


def session_stale(entry):
    """Plugins that changed in the cache AFTER this session opened.

    Takes the registry entry. Returns a list of
    (name, loaded_version, cache_version), empty when the session is up to
    date, or when it is too old to have the snapshot (then there is nothing to
    compare, and inventing an alert would be worse than staying silent).
    """
    booted = (entry or {}).get("plugin_versions") or {}
    if not booted:
        return []
    current = loaded_now()
    stale = []
    for name, v_boot in sorted(booted.items()):
        v_now = current.get(name)
        if v_now and v_now != v_boot:
            stale.append((name, v_boot, v_now))
    return stale


def boot_notice():
    """The single SessionStart line, or None when everything is up to date.

    Silence is the normal case and is deliberate: a warning that shows up every
    session becomes noise and trains the eye to skip precisely the day it matters.
    """
    try:
        bad = drifted()
        if not bad:
            return None
        rec = last_install() or {}
        a = age_days(rec.get("finished_at") or rec.get("started_at"))
        when = f", último install há {a:.0f}d" if a is not None else ""
        bits = []
        for p in bad:
            if p["missing"]:
                bits.append(f"{p['name']} {p['repo_version']} (nada instalado)")
            else:
                bits.append(f"{p['name']} {p['repo_version']} → cache {p['cache_version']}")
        return (
            "[harness] O código deste repo NÃO é o que está rodando: "
            + "; ".join(bits)
            + when
            + ". Enquanto não rodar `bin/install.sh` (e reiniciar a sessão), toda "
            "edição nesses plugins — hooks, comandos, agentes — está no disco e "
            "fora do ar. Diga isto ao usuário ANTES de afirmar que qualquer "
            "conserto recente está valendo; é a falha nº 1 registrada neste "
            "projeto (consertado, não instalado, todo mundo agindo como se "
            "estivesse). `/common:doctor` mostra o quadro completo."
        )
    except Exception:  # noqa: BLE001
        return None  # never breaks the boot


if __name__ == "__main__":
    import sys
    n = boot_notice()
    print(n or "sem divergência entre repo e cache")
    sys.exit(1 if n else 0)
