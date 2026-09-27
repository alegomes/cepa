#!/usr/bin/env python3
"""A topologia marketing existe, está registrada e o path-lock funciona.

Sem dependências — rode com `python3 tests/test_topologia_marketing.py`.
Sai não-zero na primeira leva de falhas.

Cobre comportamento, não só existência:

  - `plugin.json` e a entrada no `marketplace.json` fazem parse e apontam
    para o diretório certo;
  - todo agente tem frontmatter válido; o lead tem `Task` nas tools, os
    workers/gates não têm;
  - o path-lock GERADO (`marketing/hooks/path-lock.py`) permite um agente da
    topologia escrever `docs/marketing/x/pecas/a.md` e nega a mesma escrita
    para fora da árvore, e.g. `common/hooks/x.py`.

Espelha o estilo de `tests/test_path_lock_out_of_root.py` (invoca o hook via
subprocess com um payload JSON no stdin) e `tests/test_catalogo_comandos.py`
(nome do plugin vem do manifest, não da pasta).
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN_DIR = REPO / "marketing"

FAILURES = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok  {label}")
    else:
        FAILURES.append(label)
        print(f"FAIL  {label}  {detail}")


# ── plugin.json + marketplace entry ─────────────────────────────────────────

def test_plugin_json():
    manifesto = PLUGIN_DIR / ".claude-plugin" / "plugin.json"
    check("marketing/.claude-plugin/plugin.json existe", manifesto.is_file())
    if not manifesto.is_file():
        return
    data = json.loads(manifesto.read_text(encoding="utf-8"))
    check("plugin.json: name == 'marketing'", data.get("name") == "marketing")
    check("plugin.json: description menciona os 5 agentes",
          all(a in data.get("description", "") for a in
              ("content-lead", "content-strategist", "copywriter",
               "brand-style-critic", "fact-checker")),
          data.get("description", "")[:120])
    hooks = data.get("hooks", {}).get("PreToolUse", [])
    matchers = {h.get("matcher") for h in hooks}
    check("plugin.json: hook de Edit/Write/MultiEdit/NotebookEdit declarado",
          "Edit|Write|MultiEdit|NotebookEdit" in matchers)
    check("plugin.json: hook de Bash declarado", "Bash" in matchers)


def test_marketplace_entry():
    mp = REPO / ".claude-plugin" / "marketplace.json"
    check("marketplace.json existe e faz parse", mp.is_file())
    if not mp.is_file():
        return
    data = json.loads(mp.read_text(encoding="utf-8"))
    entradas = [p for p in data.get("plugins", []) if p.get("name") == "marketing"]
    check("marketplace.json tem exatamente uma entrada 'marketing'",
          len(entradas) == 1, f"achei {len(entradas)}")
    if len(entradas) == 1:
        check("marketplace.json: source aponta para ./marketing",
              entradas[0].get("source") == "./marketing",
              entradas[0].get("source"))


# ── agentes: frontmatter e tools ────────────────────────────────────────────

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)

AGENTS = {
    "content-lead":          {"lead": True},
    "content-strategist":    {"lead": False},
    "copywriter":            {"lead": False},
    "brand-style-critic":    {"lead": False},
    "fact-checker":          {"lead": False},
}


def frontmatter_of(path: Path) -> dict:
    texto = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(texto)
    if not m:
        return {}
    out = {}
    for linha in m.group(1).splitlines():
        if ":" not in linha:
            continue
        chave, _, valor = linha.partition(":")
        out[chave.strip()] = valor.strip()
    return out


def test_agentes_frontmatter():
    for nome, meta in AGENTS.items():
        arq = PLUGIN_DIR / "agents" / f"{nome}.md"
        check(f"{nome}.md existe", arq.is_file())
        if not arq.is_file():
            continue
        fm = frontmatter_of(arq)
        check(f"{nome}: frontmatter declara name == {nome!r}",
              fm.get("name") == nome, fm.get("name"))
        check(f"{nome}: frontmatter declara description",
              bool(fm.get("description")))
        check(f"{nome}: frontmatter declara tools",
              bool(fm.get("tools")))
        tools = fm.get("tools", "")
        tem_task = "Task" in [t.strip() for t in tools.split(",")]
        if meta["lead"]:
            check(f"{nome} (lead): tools inclui Task", tem_task, tools)
        else:
            check(f"{nome} (worker/gate): tools NÃO inclui Task",
                  not tem_task, tools)
            check(f"{nome}: descrição diz que é worker sem delegar",
                  "never delegates" in arq.read_text(encoding="utf-8"))


def test_content_lead_nunca_produz():
    """O lead delega; a única escrita permitida é a própria expertise."""
    arq = PLUGIN_DIR / "agents" / "content-lead.md"
    check("content-lead.md existe", arq.is_file())
    if not arq.is_file():
        return
    texto = arq.read_text(encoding="utf-8")
    check("content-lead: Writes declara 'nothing except own expertise'",
          "nothing except own expertise" in texto)


# ── path-lock: comportamento, não só presença ───────────────────────────────

PATH_LOCK = PLUGIN_DIR / "hooks" / "path-lock.py"


def run_pathlock(agent_type, file_path, cwd):
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(file_path)},
        "agent_type": agent_type,
        "cwd": str(cwd),
    }
    p = subprocess.run(
        [sys.executable, str(PATH_LOCK)],
        input=json.dumps(payload), capture_output=True, text=True, timeout=30,
    )
    return p.returncode, p.stderr


def test_pathlock_existe_e_e_valido_python():
    check("marketing/hooks/path-lock.py existe", PATH_LOCK.is_file())
    check("marketing/hooks/bash-path-lock.py existe",
          (PLUGIN_DIR / "hooks" / "bash-path-lock.py").is_file())
    if not PATH_LOCK.is_file():
        return
    compilado = subprocess.run(
        [sys.executable, "-m", "py_compile", str(PATH_LOCK)],
        capture_output=True, text=True,
    )
    check("marketing/hooks/path-lock.py compila", compilado.returncode == 0,
          compilado.stderr)


def test_pathlock_permite_peca_dentro_da_pista():
    if not PATH_LOCK.is_file():
        check("path-lock permite peça dentro da pista", False, "hook ausente")
        return
    proj = Path(tempfile.mkdtemp(prefix="mkt-proj-"))
    rc, err = run_pathlock(
        "marketing:copywriter", proj / "docs/marketing/x/pecas/a.md", proj)
    check("copywriter pode escrever docs/marketing/x/pecas/a.md",
          rc == 0, err)


def test_pathlock_nega_fora_da_arvore():
    if not PATH_LOCK.is_file():
        check("path-lock nega escrita fora da árvore", False, "hook ausente")
        return
    proj = Path(tempfile.mkdtemp(prefix="mkt-proj-"))
    rc, err = run_pathlock(
        "marketing:copywriter", proj / "common/hooks/x.py", proj)
    check("copywriter NÃO pode escrever common/hooks/x.py", rc == 2, err)


def test_pathlock_content_strategist_e_o_unico_dono_do_brief():
    if not PATH_LOCK.is_file():
        check("só content-strategist escreve BRIEF.md", False, "hook ausente")
        return
    proj = Path(tempfile.mkdtemp(prefix="mkt-proj-"))
    rc_ok, err_ok = run_pathlock(
        "marketing:content-strategist", proj / "docs/marketing/x/BRIEF.md", proj)
    check("content-strategist pode escrever BRIEF.md", rc_ok == 0, err_ok)

    rc_bloq, err_bloq = run_pathlock(
        "marketing:copywriter", proj / "docs/marketing/x/BRIEF.md", proj)
    check("copywriter NÃO pode escrever BRIEF.md (só lê)", rc_bloq == 2, err_bloq)


def test_pathlock_gates_so_escrevem_reviews():
    if not PATH_LOCK.is_file():
        check("gates só escrevem em reviews/", False, "hook ausente")
        return
    proj = Path(tempfile.mkdtemp(prefix="mkt-proj-"))
    for agente in ("brand-style-critic", "fact-checker"):
        rc_ok, err_ok = run_pathlock(
            f"marketing:{agente}", proj / "docs/marketing/reviews/x-brand.md", proj)
        check(f"{agente} pode escrever docs/marketing/reviews/**", rc_ok == 0, err_ok)

        rc_bloq, err_bloq = run_pathlock(
            f"marketing:{agente}", proj / "docs/marketing/x/pecas/a.md", proj)
        check(f"{agente} NÃO pode escrever peças (é read-only sobre elas)",
              rc_bloq == 2, err_bloq)


def test_pathlock_lead_nao_produz_nada():
    if not PATH_LOCK.is_file():
        check("content-lead não escreve artefatos", False, "hook ausente")
        return
    proj = Path(tempfile.mkdtemp(prefix="mkt-proj-"))
    rc, err = run_pathlock(
        "marketing:content-lead", proj / "docs/marketing/x/BRIEF.md", proj)
    check("content-lead NÃO pode escrever BRIEF.md (delega, não produz)",
          rc == 2, err)


def test_pathlock_expertise_propria_sempre_liberada():
    if not PATH_LOCK.is_file():
        check("expertise própria é sempre liberada", False, "hook ausente")
        return
    proj = Path(tempfile.mkdtemp(prefix="mkt-proj-"))
    rc, err = run_pathlock(
        "marketing:copywriter",
        proj / ".claude/expertise/copywriter-mental-model.yaml", proj)
    check("copywriter pode sempre escrever a própria expertise", rc == 0, err)


# ── comando ──────────────────────────────────────────────────────────────

def test_comando_brief_write_review():
    cmd = PLUGIN_DIR / "commands" / "brief-write-review.md"
    check("marketing/commands/brief-write-review.md existe", cmd.is_file())
    if not cmd.is_file():
        return
    texto = cmd.read_text(encoding="utf-8")
    fm = frontmatter_of(cmd)
    check("comando declara interaction: routine ou conversational",
          fm.get("interaction") in ("routine", "conversational"),
          fm.get("interaction"))
    check("comando declara argument-hint", bool(fm.get("argument-hint")))
    check("comando cita content-lead", "content-lead" in texto)
    check("comando cita o teto de 2 rodadas de revise",
          "2" in texto and "REVISE" in texto)


def test_catalogo_cita_o_comando():
    catalogo = (REPO / "docs" / "commands.md").read_text(encoding="utf-8")
    check("docs/commands.md tem a linha do /marketing:brief-write-review",
          bool(re.search(r"^\|\s*`/marketing:brief-write-review`\s*\|",
                          catalogo, re.M)))


def main():
    test_plugin_json()
    test_marketplace_entry()
    test_agentes_frontmatter()
    test_content_lead_nunca_produz()
    test_pathlock_existe_e_e_valido_python()
    test_pathlock_permite_peca_dentro_da_pista()
    test_pathlock_nega_fora_da_arvore()
    test_pathlock_content_strategist_e_o_unico_dono_do_brief()
    test_pathlock_gates_so_escrevem_reviews()
    test_pathlock_lead_nao_produz_nada()
    test_pathlock_expertise_propria_sempre_liberada()
    test_comando_brief_write_review()
    test_catalogo_cita_o_comando()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} falha(s):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("all green")


if __name__ == "__main__":
    main()
