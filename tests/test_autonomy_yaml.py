#!/usr/bin/env python3
"""Aceite da Fase 1 do "Atrito de decisão": `common/autonomy.yaml` lido por código.

Sem pytest — rode com `python3 tests/test_autonomy_yaml.py`. Sai não-zero na
primeira falha.

O que está em jogo: "pergunto ou faço?" deixou de ser julgamento do agente no
turno e virou um arquivo versionado com duas listas (executa e reporta /
sempre pergunta), cada ação com um `detect:` que casa o tool-call. Estes testes
pinam (1) a forma do arquivo e as ações que a sessão WEGO de 08-03/08-10 provou
necessárias, (2) o casamento mecânico, com `sempre_pergunta` vencendo quando
um call casa as duas faixas, (3) o override por repo que só pode endurecer,
(4) o CLI e o atalho do board-flow, e (5) a prosa do `/board-flow:decide` que
consome a lista (BACKLOG § "Atrito de decisão";
docs/internals/gauntlet-pilot-atrito-decisao.md).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
YAML_PATH = REPO / "common" / "autonomy.yaml"
CLI = REPO / "common" / "bin" / "cepa-autonomy"
SHIM = REPO / "board-flow" / "bin" / "cepa-autonomy"
SHIM_PLAN = REPO / "board-flow" / "bin" / "cepa-plan"
DECIDE = REPO / "board-flow" / "commands" / "decide.md"

sys.path.insert(0, str(REPO / "common" / "hooks"))
import _autonomy as aut  # noqa: E402

AUTOMATICAS_EXIGIDAS = {
    "rodar-build", "commit-local", "criar-card", "apagar-branch-contida",
    "apagar-handoff-vencido", "mover-arquivo", "atualizar-plano",
}
PERGUNTA_EXIGIDAS = {
    "push-remoto", "merge-integracao", "descartar-trabalho",
    "transicao-terminal", "segredo", "terceiros",
}

FALHAS = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        FALHAS.append(msg)


def ids(cfg, faixa):
    return [i["id"] for i in cfg[faixa]]


def test_arquivo_tem_as_duas_faixas_com_detect_e_default_pergunta():
    import yaml

    check(YAML_PATH.is_file(), "common/autonomy.yaml existe")
    bruto = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    check(bruto.get("default_nao_listado") == "sempre-pergunta",
          "ação não listada cai em sempre-pergunta, declarado no arquivo")
    cfg = aut.carregar(None)
    check(cfg["avisos"] == [], f"o arquivo do plugin carrega sem aviso: {cfg['avisos']}")
    todos = ids(cfg, "executa_e_reporta") + ids(cfg, "sempre_pergunta")
    check(len(todos) == len(set(todos)), "nenhum id repetido entre as faixas")
    for faixa in aut.FAIXAS:
        for item in bruto[faixa]:
            check(any(k in item["detect"] for k in aut.CHAVES_DETECT),
                  f"{item['id']} tem detect: com bash/mcp/path/slash")
    check(AUTOMATICAS_EXIGIDAS <= set(ids(cfg, "executa_e_reporta")),
          f"as mecânicas carimbadas de 08-03/08-10 estão na faixa automática: "
          f"faltam {AUTOMATICAS_EXIGIDAS - set(ids(cfg, 'executa_e_reporta'))}")
    check(PERGUNTA_EXIGIDAS <= set(ids(cfg, "sempre_pergunta")),
          f"as irreversíveis estão na faixa de pergunta: "
          f"faltam {PERGUNTA_EXIGIDAS - set(ids(cfg, 'sempre_pergunta'))}")
    check(len(cfg["executa_e_reporta"]) == 10 and len(cfg["sempre_pergunta"]) == 6,
          "10 ações automáticas e 6 de pergunta, como no design")


def test_casamento_mecanico_dos_tool_calls():
    cfg = aut.carregar(None)
    casos = [
        (dict(bash="./mvnw verify -pl api"), "executa_e_reporta", "rodar-build"),
        (dict(bash="cd /x && git commit -m 'docs'"), "executa_e_reporta", "commit-local"),
        (dict(bash="git mv a.md docs/a.md"), "executa_e_reporta", "mover-arquivo"),
        (dict(bash="git push origin feature"), "sempre_pergunta", "push-remoto"),
        (dict(bash="git commit -m x && git push"), "sempre_pergunta", "push-remoto"),
        (dict(bash="git reset --hard HEAD~1"), "sempre_pergunta", "descartar-trabalho"),
        (dict(bash="git worktree remove ../x"), "sempre_pergunta", "descartar-trabalho"),
        (dict(bash="git merge session/x"), "sempre_pergunta", "merge-integracao"),
        (dict(mcp="mcp__Atlassian__createJiraIssue"), "executa_e_reporta", "criar-card"),
        (dict(mcp="mcp__mcp-atlassian__jira_add_comment"), "executa_e_reporta", "comentar-card"),
        (dict(mcp="mcp__Atlassian__transitionJiraIssue"), "sempre_pergunta", "transicao-terminal"),
        (dict(mcp="mcp__instagram__send_dm"), "sempre_pergunta", "terceiros"),
        (dict(path=".claude/handoffs/until-x.md", op="delete"), "executa_e_reporta", "apagar-handoff-vencido"),
        (dict(path=".claude/programs/cepa/plan.yaml", op="edit"), "executa_e_reporta", "atualizar-plano"),
        (dict(path="/Users/a/.zsecrets", op="edit"), "sempre_pergunta", "segredo"),
        (dict(path="apps/web/.env.local", op="edit"), "sempre_pergunta", "segredo"),
        (dict(slash="/board-flow:prove-drain --max 5"), "executa_e_reporta", "rerodar-prove"),
        # revisão do par (2026-10-16): regex solta de build e comando composto lavado
        (dict(bash="mvn deploy"), "sempre_pergunta", None),
        (dict(bash="gradle publish"), "sempre_pergunta", None),
        (dict(bash="mvn verify deploy"), "sempre_pergunta", None),
        (dict(bash="./mvnw -Dskip=1 deploy"), "sempre_pergunta", None),
        (dict(bash="rm -rf data pytest"), "sempre_pergunta", None),
        (dict(bash="comando-desconhecido && pytest"), "sempre_pergunta", None),
        (dict(bash="pytest; rm -rf x"), "sempre_pergunta", None),
        (dict(bash="FOO=1 pytest -k x"), "executa_e_reporta", "rodar-build"),
        (dict(bash="python3 -m pytest tests/x.py"), "executa_e_reporta", "rodar-build"),
        (dict(bash="cd a && ./mvnw -q -pl api verify && git commit -m x"), "executa_e_reporta", "rodar-build"),
        (dict(bash="echo ok | git push"), "sempre_pergunta", "push-remoto"),
        (dict(bash="$(git push origin x)"), "sempre_pergunta", "push-remoto"),
        (dict(bash="(git push)"), "sempre_pergunta", "push-remoto"),
        (dict(bash="pytest && echo fim && git push"), "sempre_pergunta", "push-remoto"),
        # prova (2026-10-16): a pergunta vence em QUALQUER posição, não só na última
        (dict(bash="git push && pytest"), "sempre_pergunta", "push-remoto"),
        (dict(bash="git push; pytest"), "sempre_pergunta", "push-remoto"),
        (dict(bash="pytest && git push && echo x"), "sempre_pergunta", "push-remoto"),
        (dict(bash="git reset --hard && git commit -m x && pytest"), "sempre_pergunta", "descartar-trabalho"),
        (dict(bash="git commit -m 'fix (x)'"), "executa_e_reporta", "commit-local"),
        (dict(bash="git merge x", cond={"branch_atual": "main"}), "sempre_pergunta", "merge-integracao"),
        (dict(bash="git merge x", cond={"branch_atual": "feature/y"}), "sempre_pergunta", None),
        (dict(mcp="mcp__Atlassian__createJiraIssue"), "executa_e_reporta", "criar-card"),
        (dict(mcp="mcp__Atlassian__createJiraIssue", cond={"label": "infra"}), "executa_e_reporta", "card-infra-agregado"),
        # revisão do par, rodada 2: substituição no meio dos argumentos e neutro com redirecionamento
        (dict(bash="pytest `git push`"), "sempre_pergunta", None),
        (dict(bash="pytest $(rm -rf x)"), "sempre_pergunta", None),
        (dict(bash="mvn test $(git push)"), "sempre_pergunta", None),
        (dict(bash="pytest <(git push)"), "sempre_pergunta", None),
        (dict(bash="printf x > ~/.bashrc && pytest"), "sempre_pergunta", None),
        (dict(bash="echo x > important.py && pytest"), "sempre_pergunta", None),
        (dict(bash="echo x >(git push) && pytest"), "sempre_pergunta", None),
        # e o que NÃO pode virar pergunta à toa
        (dict(bash="git add . && git commit -m x"), "executa_e_reporta", "commit-local"),
        (dict(bash="pytest -q 2>&1 | tail -5"), "sempre_pergunta", None),  # `2>&1` é redirecionamento: fica como está, pergunta
        (dict(bash="pytest -q | tail -5"), "executa_e_reporta", "rodar-build"),
        (dict(bash="X=1 mvn test"), "executa_e_reporta", "rodar-build"),
        (dict(bash="git status && git add -A && git commit -m x"), "executa_e_reporta", "commit-local"),
        # rodada 3: neutro que grava sem `>` e export que muda o que o pytest executa
        (dict(bash="sort -o important.py x && pytest"), "sempre_pergunta", None),
        (dict(bash="git diff --output=important.py && pytest"), "sempre_pergunta", None),
        (dict(bash="git log --output=a.py && pytest"), "sempre_pergunta", None),
        (dict(bash="export PYTHONPATH=/tmp/evil && pytest"), "sempre_pergunta", None),
        (dict(bash="export LD_PRELOAD=/tmp/x.so && pytest"), "sempre_pergunta", None),
        (dict(bash="tail -o x f && pytest"), "sempre_pergunta", None),
        (dict(bash="grep --output=x f && pytest"), "sempre_pergunta", None),
    ]
    for entrada, faixa, ident in casos:
        r = aut.casar(cfg, **entrada)
        check((r["faixa"], r["id"]) == (faixa, ident),
              f"{entrada} → {faixa}/{ident} (veio {r['faixa']}/{r['id']})")

    r = aut.casar(cfg, bash="git branch -D feature/x")
    check(r["id"] == "apagar-branch-contida" and "merge-base --is-ancestor" in (r["precondicao"] or ""),
          "apagar branch casa a ação automática E devolve a precondição que o hook confere")

    r = aut.casar(cfg, path=".claude/handoffs/x.md", op="edit")
    check(r["id"] is None and r["faixa"] == "sempre_pergunta" and r["listado"] is False,
          "editar um handoff NÃO é apagar handoff: cai no default (não listado)")

    r = aut.casar(cfg, bash="rm -rf /tmp/qualquer")
    check(r["listado"] is False and r["faixa"] == "sempre_pergunta",
          "comando fora da lista → não listado → sempre pergunta")

    r = aut.casar(cfg, mcp="mcp__Atlassian__transitionJiraIssue")
    check(r["condicoes"].get("destino_terminal") is True,
          "a condição que o hook da Fase 2 resolve volta em `condicoes`")


def test_override_do_repo_so_endurece(tmp):
    repo = Path(tmp) / "repo"
    (repo / ".claude").mkdir(parents=True)
    (repo / ".claude" / "autonomy.yaml").write_text(
        "executa_e_reporta:\n"
        "  - {id: push-remoto, detect: {bash: '^git push'}}\n"   # afrouxar: ignorado
        "sempre_pergunta:\n"
        "  - commit-local\n"                                      # mover: aplicado
        "  - {id: apagar-tag, detect: {bash: '^git tag -d'}}\n"   # acrescentar: aplicado
        "  - {id: sem-detect}\n"                                  # malformado: descartado
        "default_nao_listado: executa-e-reporta\n",               # ignorado
        encoding="utf-8",
    )
    cfg = aut.carregar(str(repo))
    check("commit-local" in ids(cfg, "sempre_pergunta") and "commit-local" not in ids(cfg, "executa_e_reporta"),
          "override MOVE commit-local para sempre_pergunta")
    check(aut.casar(cfg, bash="git commit -m x")["faixa"] == "sempre_pergunta",
          "e o casamento respeita a movida")
    check("apagar-tag" in ids(cfg, "sempre_pergunta"), "override ACRESCENTA ação nova à faixa de pergunta")
    check("push-remoto" in ids(cfg, "sempre_pergunta") and "push-remoto" not in ids(cfg, "executa_e_reporta"),
          "override NÃO promove push-remoto para a faixa automática")
    check(cfg["default_nao_listado"] == "sempre-pergunta", "override não muda o default")
    check("sem-detect" not in ids(cfg, "sempre_pergunta"), "item sem detect: do override é descartado")
    avisos = " ".join(cfg["avisos"])
    check("executa_e_reporta" in avisos and "default_nao_listado" in avisos and "sem-detect" in avisos,
          f"cada coisa ignorada vira aviso nomeado: {cfg['avisos']}")
    check(len(cfg["fontes"]) == 2, "as duas fontes (plugin + override) ficam registradas")

    sem_override = aut.carregar(str(Path(tmp) / "nao-existe"))
    check(sem_override["avisos"] == [] and "commit-local" in ids(sem_override, "executa_e_reporta"),
          "repo sem .claude/autonomy.yaml usa só o plugin, sem aviso")


def test_plugin_yaml_malformado_cai_tudo_em_pergunta(tmp):
    ruim = Path(tmp) / "autonomy.yaml"
    ruim.write_text(
        "versao: 2\n"
        "executa_e_reporta:\n"
        "  - {id: sem-detect}\n"
        "  - {id: regex-ruim, detect: {bash: '('}}\n"
        "  - {id: dois-padroes, detect: {bash: '^x', mcp: 'y'}}\n"
        "sempre_pergunta: []\n",
        encoding="utf-8",
    )
    cfg = aut.carregar(None, plugin_yaml=ruim)
    check(cfg["executa_e_reporta"] == [], "item sem detect, regex inválida e dois padrões num detect são descartados")
    check(len(cfg["avisos"]) == 3, f"um aviso por item descartado: {cfg['avisos']}")
    check(aut.casar(cfg, bash="git commit")["faixa"] == "sempre_pergunta",
          "sem lista válida, tudo cai em pergunta (o lado seguro)")
    cfg2 = aut.carregar(None, plugin_yaml=Path(tmp) / "inexistente.yaml")
    check(cfg2["executa_e_reporta"] == [] and cfg2["avisos"], "arquivo ausente: lista vazia + aviso, sem exceção")


def test_cli_classificar_e_listar():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, str(CLI), "classificar", "--bash", "git push origin x", "--json"],
                       capture_output=True, text=True, env=env, cwd=REPO)
    check(r.returncode == 0, f"cli classificar sai 0: {r.stderr}")
    j = json.loads(r.stdout)
    check(j["faixa"] == "sempre_pergunta" and j["id"] == "push-remoto", "cli --json devolve faixa e id")

    r = subprocess.run([sys.executable, str(CLI), "classificar", "--mcp", "mcp__Atlassian__createJiraIssue"],
                       capture_output=True, text=True, env=env, cwd=REPO)
    check("executa e reporta (criar-card)" in r.stdout and "linha de informação" in r.stdout,
          "saída humana diz a faixa, o id e o que fazer")

    r = subprocess.run([sys.executable, str(CLI), "classificar", "--bash", "rm -rf x"],
                       capture_output=True, text=True, env=env, cwd=REPO)
    check("não listado" in r.stdout and "common/autonomy.yaml" in r.stdout,
          "não listado: manda perguntar e propor o id no arquivo")

    r = subprocess.run([sys.executable, str(CLI), "classificar", "--mcp", "mcp__Atlassian__createJiraIssue",
                        "--cond", "label=infra", "--json"], capture_output=True, text=True, env=env, cwd=REPO)
    check(json.loads(r.stdout)["id"] == "card-infra-agregado", "cli --cond chave=valor libera a condição do detect")

    r = subprocess.run([sys.executable, str(CLI), "classificar", "--id", "transicao-terminal"],
                       capture_output=True, text=True, env=env, cwd=REPO)
    check("sempre pergunta (transicao-terminal)" in r.stdout, "classificar --id responde pelo nome da ação")

    r = subprocess.run([sys.executable, str(CLI), "listar"], capture_output=True, text=True, env=env, cwd=REPO)
    check(r.returncode == 0 and all(i in r.stdout for i in AUTOMATICAS_EXIGIDAS | PERGUNTA_EXIGIDAS),
          "listar mostra todas as ações")


def test_atalho_do_board_flow_resolve_o_cepa_autonomy_do_common(tmp):
    check(SHIM.read_bytes() == SHIM_PLAN.read_bytes(),
          "board-flow/bin/cepa-autonomy é cópia byte a byte do shim cepa-plan (o alvo vem do nome)")
    check(os.access(SHIM, os.X_OK), "o atalho é executável")
    # layout falso de repo: o shim deve achar <repo>/common/bin/cepa-autonomy, não o cepa-plan
    repo = Path(tmp) / "repo"
    (repo / "board-flow" / "bin").mkdir(parents=True)
    (repo / "common" / "bin").mkdir(parents=True)
    shim = repo / "board-flow" / "bin" / "cepa-autonomy"
    shim.write_bytes(SHIM.read_bytes())
    fake = repo / "common" / "bin" / "cepa-autonomy"
    fake.write_text("import sys; print('fake-autonomy', *sys.argv[1:]); sys.exit(11)\n")
    (repo / "common" / "bin" / "cepa-plan").write_text("import sys; print('ERRADO'); sys.exit(99)\n")
    r = subprocess.run([sys.executable, str(shim), "listar", "--json"], capture_output=True, text=True)
    check(r.returncode == 11 and "fake-autonomy listar --json" in r.stdout,
          f"o atalho executa o homônimo do common e repassa argv e exit (veio {r.returncode}: {r.stdout!r})")


def test_decide_le_a_lista():
    s = DECIDE.read_text(encoding="utf-8")
    check("cepa-autonomy" in s and "classificar" in s, "decide.md consulta o cepa-autonomy classificar")
    check("### 5b." in s and s.index("### 5b.") < s.index("### 6."),
          "a consulta vem antes de agrupar e perguntar (passo 5b, antes do 6)")
    check("executa_e_reporta" in s and "sempre_pergunta" in s, "decide.md nomeia as duas faixas")
    check("**Never** a numbered item of" in s,
          "ação automática nunca vira item numerado de Decisões e próximos passos")
    check("proponho adicionar" in s, "ação não listada termina propondo o id ao arquivo")
    check("Re-run `/board-flow:prove`" in s and "create\n  **one** infra card" in s,
          "passo 4 passou de propor para fazer (rerodar-prove e card-infra-agregado)")
    check("--dry-run" in s and "nor executes" in s, "--dry-run continua sem executar nada")
    check("before you answer — except what" in s and "`executa_e_reporta` (step 5b" in s,
          "o bloco 'O que ele NÃO faz' declara a exceção da faixa automática (não contradiz as Constraints)")
    check("`git branch -D` without that check is forbidden" in s,
          "apagar branch sem rodar a precondição é proibido na Fase 1")


def main():
    with tempfile.TemporaryDirectory() as d:
        test_arquivo_tem_as_duas_faixas_com_detect_e_default_pergunta()
        test_casamento_mecanico_dos_tool_calls()
        test_override_do_repo_so_endurece(d)
        test_plugin_yaml_malformado_cai_tudo_em_pergunta(d)
        test_cli_classificar_e_listar()
        test_atalho_do_board_flow_resolve_o_cepa_autonomy_do_common(d)
        test_decide_le_a_lista()
    if FALHAS:
        print(f"\n{len(FALHAS)} falha(s)")
        sys.exit(1)
    print("\nall green")


if __name__ == "__main__":
    main()
