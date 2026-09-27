#!/usr/bin/env python3
"""Testes: o `cepa-until` grava a versão da CLI `twg` em cada `item_start`.

Rode com `python3 tests/test_cepa_until_twg_version.py` (precisa de PyYAML).

## Por que este registro existe

A `twg` (Atlassian) instala um agendador `launchd`
(`com.atlassian.twg.upkeep.plist`) que checa atualização sozinho a cada 12
minutos — a versão pode trocar ENTRE dois cards do MESMO run desatendido, sem
sinal nenhum. O `cepa-until` lê a versão instalada a CADA item (nunca em
cache no `run_start`) e grava no evento `item_start` do `.jsonl` do run — é a
prova concreta de qual ferramenta produziu qual item.

O teste que mais importa aqui é o de troca NO MEIO do run: o `claude` falso
reescreve o script do `twg` falso durante o processamento do primeiro item, e
os dois `item_start` do ledger têm de trazer versões diferentes.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    print("✗ precisa de PyYAML (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

REPO = Path(__file__).resolve().parent.parent
CEPA_UNTIL = REPO / "common" / "bin" / "cepa-until"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def monta_repo(tmp, itens):
    raiz = Path(tmp) / "repo"
    raiz.mkdir(parents=True, exist_ok=True)
    d = raiz / ".claude" / "programs" / "fila"
    d.mkdir(parents=True)
    plano = {"schema_version": 2, "mode": "single-track", "program": "fila",
             "source": "teste", "items": itens}
    (d / "plan.yaml").write_text(yaml.safe_dump(plano, allow_unicode=True),
                                 encoding="utf-8")
    subprocess.run(["git", "init", "-q", "."], cwd=raiz, check=True)
    subprocess.run(["git", "add", "-A"], cwd=raiz, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=raiz, check=True)
    return raiz


def item(ident, status="pending", human_pending=None):
    return {"id": ident, "title": f"item {ident}", "why": "porque",
            "status": status, "blocked_by": [], "human_pending": human_pending,
            "evidence": None}


def fake_claude(tmp, corpo):
    """Idêntico ao ajudante de test_cepa_until.py: um `claude` falso no PATH."""
    binv = Path(tmp) / "bin"
    binv.mkdir(exist_ok=True)
    script = binv / "claude"
    script.write_text(
        f"#!{sys.executable}\n"
        "import os, sys, yaml, json, time\n"
        "PLANO = os.environ['FAKE_PLANO']\n"
        "ARGS = sys.argv[1:]\n"
        "def carrega():\n"
        "    return yaml.safe_load(open(PLANO, encoding='utf-8'))\n"
        "def grava(p):\n"
        "    open(PLANO, 'w', encoding='utf-8').write("
        "yaml.safe_dump(p, allow_unicode=True))\n"
        "def marca(ident, **campos):\n"
        "    p = carrega()\n"
        "    for it in p['items']:\n"
        "        if it['id'] == ident:\n"
        "            it.update(campos)\n"
        "    grava(p)\n"
        "def primeiro_pendente():\n"
        "    for it in carrega()['items']:\n"
        "        if it['status'] == 'pending' and not it.get('human_pending'):\n"
        "            return it['id']\n"
        "    return None\n"
        "with open(os.environ['FAKE_CHAMADAS'], 'a') as f:\n"
        "    f.write(json.dumps(ARGS) + '\\n')\n"
        + corpo + "\n",
        encoding="utf-8")
    script.chmod(0o755)
    return binv


def fake_twg(binv, versao):
    """`twg` falso: script sh que ecoa `versao` em texto livre (a mesma forma
    livre da CLI real, que o regex do doctor/until extrai)."""
    script = binv / "twg"
    script.write_text(f"#!/bin/sh\necho 'twg version {versao}'\n", encoding="utf-8")
    script.chmod(0o755)
    return script


def path_essenciais(tmp):
    """Diretório só com symlinks para git/python3 — usado quando o teste quer
    garantir que NENHUM `twg` real da máquina de quem roda o teste entre no
    PATH (esta máquina tem uma instalação real, ver docs/env-manifest.md)."""
    d = Path(tmp) / "minpath"
    d.mkdir(exist_ok=True)
    for nome in ("git", "python3"):
        real = shutil.which(nome)
        if real:
            alvo = d / nome
            if not alvo.exists():
                alvo.symlink_to(real)
    return d


def roda(raiz, binv, plano, args, timeout=120, extra_env=None, path=None):
    env = dict(os.environ)
    env.update(extra_env or {})
    env["PATH"] = f"{binv}:{path}" if path is not None else f"{binv}:{env['PATH']}"
    env["FAKE_PLANO"] = str(plano)
    env.setdefault("CEPA_WORKTREE_HOME", str(Path(raiz).parent / "worktrees"))
    chamadas = Path(raiz).parent / "chamadas.jsonl"
    env["FAKE_CHAMADAS"] = str(chamadas)
    args = list(args)
    if "--verify" not in args and "--sem-verify" not in args:
        args.append("--sem-verify")
    if "--sem-analise" not in args:
        args.append("--sem-analise")
    p = subprocess.run([sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(raiz)]
                       + args, capture_output=True, text=True, env=env,
                       timeout=timeout)
    linhas = []
    if chamadas.exists():
        linhas = [json.loads(l) for l in chamadas.read_text().splitlines() if l.strip()]
    return p, linhas


def ledger_de(raiz):
    d = Path(raiz) / ".claude" / "programs" / "fila" / "until"
    eventos = []
    for f in sorted(d.glob("*.jsonl")):
        eventos += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return eventos


def item_starts(raiz):
    return [e for e in ledger_de(raiz) if e.get("evento") == "item_start"]


def test_item_start_traz_a_versao_do_twg_instalado():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        fake_twg(binv, "1.3.1")
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        roda(raiz, binv, plano, ["--for", "2h"])
        starts = item_starts(raiz)
        check("houve 1 item_start", len(starts) == 1, json.dumps(starts))
        check("...com twg_version 1.3.1",
              starts and starts[0].get("twg_version") == "1.3.1",
              json.dumps(starts))


def test_sem_twg_no_path_grava_null():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        # nenhum `twg` fake criado, e o PATH é restrito a git/python3 — a CLI
        # simplesmente não existe (nem a real da máquina que roda o teste).
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        roda(raiz, binv, plano, ["--for", "2h"], path=str(path_essenciais(tmp)))
        starts = item_starts(raiz)
        check("houve 1 item_start", len(starts) == 1, json.dumps(starts))
        check("...com twg_version null (twg ausente do PATH)",
              starts and starts[0].get("twg_version") is None,
              json.dumps(starts))


def test_versao_trocando_no_meio_do_run_aparece_nos_dois_item_start():
    """O caso que importa: o `claude` falso reescreve o `twg` falso durante o
    processamento do PRIMEIRO item (simulando o agendador `upkeep` atualizando
    a CLI sozinho no meio da noite). Os dois `item_start` têm de trazer
    versões DIFERENTES — a versão é lida a cada item, nunca em cache."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(
            tmp,
            "if primeiro_pendente() == 'a1':\n"
            "    open(os.environ['FAKE_TWG'], 'w').write("
            "\"#!/bin/sh\\necho 'twg version 1.4.0'\\n\")\n"
            "marca(primeiro_pendente(), status='done')")
        twg_path = fake_twg(binv, "1.3.1")
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        roda(raiz, binv, plano, ["--for", "2h"],
             extra_env={"FAKE_TWG": str(twg_path)})
        starts = item_starts(raiz)
        check("houve 2 item_start", len(starts) == 2, json.dumps(starts))
        if len(starts) == 2:
            v1 = starts[0].get("twg_version")
            v2 = starts[1].get("twg_version")
            check("1º item_start com a versão de ANTES da troca (1.3.1)",
                  v1 == "1.3.1", json.dumps(starts))
            check("2º item_start com a versão de DEPOIS da troca (1.4.0)",
                  v2 == "1.4.0", json.dumps(starts))
            check("as duas versões são diferentes entre si",
                  v1 != v2, json.dumps(starts))


def main():
    print("cepa-until — twg_version em cada item_start\n")
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            print(f"{nome}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
