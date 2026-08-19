#!/usr/bin/env python3
"""Compara a versão de cada plugin no REPO com a que está no CACHE instalado.

Por que isto é um módulo e não uma função dentro de quem pergunta: a pergunta
"o harness que está rodando é o que eu acho que está?" é feita de dois lugares
com propósitos diferentes —

  - `common/bin/cepa-doctor` faz o diagnóstico completo, sob demanda;
  - `common/hooks/session-registry.py` avisa no boot da sessão, sem ser
    perguntado (o gatilho voluntário era exatamente a falha: ninguém roda o
    doctor justamente quando não suspeita de nada).

Duas cópias do comparador seriam a mesma doença que o harness já tem nos
path-locks (5 cópias, correção por disciplina). Uma só, importada pelos dois.

Contrato: nada aqui levanta exceção para quem chama. Um comparador que quebra
o boot da sessão seria desligado, e aí não protege ninguém.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"


def semver(v: str):
    """(1, 2, 3) a partir de "1.2.3". Qualquer coisa ilegível vira (0,)."""
    try:
        return tuple(int(x) for x in re.findall(r"\d+", str(v))[:3])
    except Exception:  # noqa: BLE001
        return (0,)


def cepa_repo_root():
    """De qual clone veio o marketplace instalado, segundo o próprio CC."""
    try:
        mk = json.loads(
            (CLAUDE_DIR / "plugins" / "known_marketplaces.json").read_text(encoding="utf-8")
        )
        loc = mk.get("cepa", {}).get("installLocation")
        return Path(loc) if loc else None
    except Exception:  # noqa: BLE001
        return None


def last_install():
    """O registro operacional escrito por bin/install.sh, ou None."""
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
    """Versões presentes no cache para um plugin, da mais velha para a mais nova."""
    cdir = CLAUDE_DIR / "plugins" / "cache" / "cepa" / name
    if not cdir.is_dir():
        return []
    try:
        return sorted((d.name for d in cdir.iterdir() if d.is_dir()), key=semver)
    except OSError:
        return []


def scan(repo_root=None, enabled=None):
    """Estado de cada plugin do repo: nome, versão no repo, versão no cache.

    Retorna uma lista de dicts com as chaves:
      name, repo_version, cache_version (None = nada instalado),
      drift (repo > cache), missing (nada no cache), enabled (None = não checado).

    `enabled` é o dict `enabledPlugins` do settings.json, quando o chamador já
    o tem em mãos; sem ele o campo sai None em vez de um palpite.
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
        # O nome do plugin vem do manifest, não do diretório: docs-topology/ é
        # a fonte do plugin "docs".
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
    """Só os plugins cuja edição no repo NÃO está valendo na máquina."""
    return [p for p in scan(repo_root) if p["drift"] or p["missing"]]


def loaded_now():
    """Versão de cada plugin que uma sessão aberta AGORA carregaria do cache.

    Fotografada no SessionStart e guardada na entrada da sessão. Sem essa foto,
    ninguém consegue responder a pergunta que mais custou tempo neste harness:
    "a sessão em que estou está rodando os hooks que acabei de instalar?".

    `scan()` compara REPO com CACHE e pega o caso "editei e não reinstalei".
    Ele não pega o caso oposto e mais traiçoeiro: reinstalei DURANTE a sessão,
    o cache já está novo, e esta sessão segue executando os hooks velhos que
    leu na abertura. Os dois parecem iguais no doctor e falham diferente.
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
    """Plugins que mudaram no cache DEPOIS que esta sessão abriu.

    Recebe a entrada do registry. Devolve uma lista de
    (nome, versão_carregada, versão_no_cache) — vazia quando a sessão está em
    dia, ou quando ela é antiga demais para ter a foto (aí não há o que
    comparar, e inventar um alerta seria pior que ficar calado).
    """
    booted = (entry or {}).get("plugin_versions") or {}
    if not booted:
        return []
    agora = loaded_now()
    fora = []
    for nome, v_boot in sorted(booted.items()):
        v_agora = agora.get(nome)
        if v_agora and v_agora != v_boot:
            fora.append((nome, v_boot, v_agora))
    return fora


def boot_notice():
    """A linha única do SessionStart, ou None quando está tudo em dia.

    Silêncio é o caso normal e é deliberado: aviso que aparece toda sessão vira
    ruído e treina o olho a pular justamente o dia em que ele importa.
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
        return None  # nunca quebra o boot


if __name__ == "__main__":
    import sys
    n = boot_notice()
    print(n or "sem divergência entre repo e cache")
    sys.exit(1 if n else 0)
