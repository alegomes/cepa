#!/usr/bin/env python3
"""Phase 1 acceptance of "Decision friction": `common/autonomy.yaml` read by code.

No pytest — run with `python3 tests/test_autonomy_yaml.py`. Exits non-zero on the
first failure.

What is at stake: "do I ask or do it?" stopped being the agent's judgment in the
turn and became a versioned file with two lists (execute and report /
always ask), each action with a `detect:` that matches the tool call. These tests
pin (1) the shape of the file and the actions the WEGO session of 08-03/08-10 proved
necessary, (2) the mechanical matching, with `sempre_pergunta` winning when
a call matches both lanes, (3) the per-repo override that can only tighten,
(4) the CLI and the board-flow shortcut, and (5) the prose of `/board-flow:decide` that
consumes the list (BACKLOG § "Decision friction";
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

REQUIRED_AUTOMATIC = {
    "rodar-build", "commit-local", "criar-card", "apagar-branch-contida",
    "apagar-handoff-vencido", "mover-arquivo", "atualizar-plano",
}
REQUIRED_QUESTION = {
    "push-remoto", "merge-integracao", "descartar-trabalho",
    "transicao-terminal", "segredo", "terceiros",
}

FAILURE_LIST = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        FAILURE_LIST.append(msg)


def ids(cfg, lane):
    return [i["id"] for i in cfg[lane]]


def test_file_has_the_two_lanes_with_detect_and_default_question():
    import yaml

    check(YAML_PATH.is_file(), "common/autonomy.yaml existe")
    raw = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    check(raw.get("default_nao_listado") == "sempre-pergunta",
          "ação não listada cai em sempre-pergunta, declarado no arquivo")
    cfg = aut.load(None)
    check(cfg["avisos"] == [], f"o arquivo do plugin carrega sem aviso: {cfg['avisos']}")
    all_ = ids(cfg, "executa_e_reporta") + ids(cfg, "sempre_pergunta")
    check(len(all_) == len(set(all_)), "nenhum id repetido entre as faixas")
    for lane in aut.BANDS:
        for item in raw[lane]:
            check(any(k in item["detect"] for k in aut.DETECT_KEYS),
                  f"{item['id']} tem detect: com bash/mcp/path/slash")
    check(REQUIRED_AUTOMATIC <= set(ids(cfg, "executa_e_reporta")),
          f"as mecânicas carimbadas de 08-03/08-10 estão na faixa automática: "
          f"faltam {REQUIRED_AUTOMATIC - set(ids(cfg, 'executa_e_reporta'))}")
    check(REQUIRED_QUESTION <= set(ids(cfg, "sempre_pergunta")),
          f"as irreversíveis estão na faixa de pergunta: "
          f"faltam {REQUIRED_QUESTION - set(ids(cfg, 'sempre_pergunta'))}")
    check(len(cfg["executa_e_reporta"]) == 10 and len(cfg["sempre_pergunta"]) == 6,
          "10 ações automáticas e 6 de pergunta, como no design")


def test_mechanical_matching_of_tool_calls():
    cfg = aut.load(None)
    cases = [
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
        # pair review (2026-10-16): loose build regex and laundered compound command
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
        # proof (2026-10-16): the question wins in ANY position, not only the last
        (dict(bash="git push && pytest"), "sempre_pergunta", "push-remoto"),
        (dict(bash="git push; pytest"), "sempre_pergunta", "push-remoto"),
        (dict(bash="pytest && git push && echo x"), "sempre_pergunta", "push-remoto"),
        (dict(bash="git reset --hard && git commit -m x && pytest"), "sempre_pergunta", "descartar-trabalho"),
        (dict(bash="git commit -m 'fix (x)'"), "executa_e_reporta", "commit-local"),
        (dict(bash="git merge x", cond={"branch_atual": "main"}), "sempre_pergunta", "merge-integracao"),
        (dict(bash="git merge x", cond={"branch_atual": "feature/y"}), "sempre_pergunta", None),
        (dict(mcp="mcp__Atlassian__createJiraIssue"), "executa_e_reporta", "criar-card"),
        (dict(mcp="mcp__Atlassian__createJiraIssue", cond={"label": "infra"}), "executa_e_reporta", "card-infra-agregado"),
        # pair review, round 2: substitution in the middle of the arguments and neutral with redirection
        (dict(bash="pytest `git push`"), "sempre_pergunta", None),
        (dict(bash="pytest $(rm -rf x)"), "sempre_pergunta", None),
        (dict(bash="mvn test $(git push)"), "sempre_pergunta", None),
        (dict(bash="pytest <(git push)"), "sempre_pergunta", None),
        (dict(bash="printf x > ~/.bashrc && pytest"), "sempre_pergunta", None),
        (dict(bash="echo x > important.py && pytest"), "sempre_pergunta", None),
        (dict(bash="echo x >(git push) && pytest"), "sempre_pergunta", None),
        # and what must NOT become a needless question
        (dict(bash="git add . && git commit -m x"), "executa_e_reporta", "commit-local"),
        (dict(bash="pytest -q 2>&1 | tail -5"), "sempre_pergunta", None),  # `2>&1` is a redirection: stays as is, asks
        (dict(bash="pytest -q | tail -5"), "executa_e_reporta", "rodar-build"),
        (dict(bash="X=1 mvn test"), "executa_e_reporta", "rodar-build"),
        (dict(bash="git status && git add -A && git commit -m x"), "executa_e_reporta", "commit-local"),
        # round 3: neutral that writes without `>` and export that changes what pytest executes
        (dict(bash="sort -o important.py x && pytest"), "sempre_pergunta", None),
        (dict(bash="git diff --output=important.py && pytest"), "sempre_pergunta", None),
        (dict(bash="git log --output=a.py && pytest"), "sempre_pergunta", None),
        (dict(bash="export PYTHONPATH=/tmp/evil && pytest"), "sempre_pergunta", None),
        (dict(bash="export LD_PRELOAD=/tmp/x.so && pytest"), "sempre_pergunta", None),
        (dict(bash="tail -o x f && pytest"), "sempre_pergunta", None),
        (dict(bash="grep --output=x f && pytest"), "sempre_pergunta", None),
    ]
    for input_, lane, ident in cases:
        r = aut.match(cfg, **input_)
        check((r["faixa"], r["id"]) == (lane, ident),
              f"{input_} → {lane}/{ident} (veio {r['faixa']}/{r['id']})")

    r = aut.match(cfg, bash="git branch -D feature/x")
    check(r["id"] == "apagar-branch-contida" and "merge-base --is-ancestor" in (r["precondicao"] or ""),
          "apagar branch casa a ação automática E devolve a precondição que o hook confere")

    r = aut.match(cfg, path=".claude/handoffs/x.md", op="edit")
    check(r["id"] is None and r["faixa"] == "sempre_pergunta" and r["listado"] is False,
          "editar um handoff NÃO é apagar handoff: cai no default (não listado)")

    r = aut.match(cfg, bash="rm -rf /tmp/qualquer")
    check(r["listado"] is False and r["faixa"] == "sempre_pergunta",
          "comando fora da lista → não listado → sempre pergunta")

    r = aut.match(cfg, mcp="mcp__Atlassian__transitionJiraIssue")
    check(r["condicoes"].get("destino_terminal") is True,
          "a condição que o hook da Fase 2 resolve volta em `condicoes`")


def test_repo_override_only_tightens(tmp):
    repo = Path(tmp) / "repo"
    (repo / ".claude").mkdir(parents=True)
    (repo / ".claude" / "autonomy.yaml").write_text(
        "executa_e_reporta:\n"
        "  - {id: push-remoto, detect: {bash: '^git push'}}\n"   # loosen: ignored
        "sempre_pergunta:\n"
        "  - commit-local\n"                                      # move: applied
        "  - {id: apagar-tag, detect: {bash: '^git tag -d'}}\n"   # append: applied
        "  - {id: sem-detect}\n"                                  # malformed: discarded
        "default_nao_listado: executa-e-reporta\n",               # ignored
        encoding="utf-8",
    )
    cfg = aut.load(str(repo))
    check("commit-local" in ids(cfg, "sempre_pergunta") and "commit-local" not in ids(cfg, "executa_e_reporta"),
          "override MOVE commit-local para sempre_pergunta")
    check(aut.match(cfg, bash="git commit -m x")["faixa"] == "sempre_pergunta",
          "e o casamento respeita a movida")
    check("apagar-tag" in ids(cfg, "sempre_pergunta"), "override ACRESCENTA ação nova à faixa de pergunta")
    check("push-remoto" in ids(cfg, "sempre_pergunta") and "push-remoto" not in ids(cfg, "executa_e_reporta"),
          "override NÃO promove push-remoto para a faixa automática")
    check(cfg["default_nao_listado"] == "sempre-pergunta", "override não muda o default")
    check("sem-detect" not in ids(cfg, "sempre_pergunta"), "item sem detect: do override é descartado")
    warnings = " ".join(cfg["avisos"])
    check("executa_e_reporta" in warnings and "default_nao_listado" in warnings and "sem-detect" in warnings,
          f"cada coisa ignorada vira aviso nomeado: {cfg['avisos']}")
    check(len(cfg["fontes"]) == 2, "as duas fontes (plugin + override) ficam registradas")

    without_override = aut.load(str(Path(tmp) / "nao-existe"))
    check(without_override["avisos"] == [] and "commit-local" in ids(without_override, "executa_e_reporta"),
          "repo sem .claude/autonomy.yaml usa só o plugin, sem aviso")


def test_malformed_plugin_yaml_all_falls_to_question(tmp):
    bad = Path(tmp) / "autonomy.yaml"
    bad.write_text(
        "versao: 2\n"
        "executa_e_reporta:\n"
        "  - {id: sem-detect}\n"
        "  - {id: regex-ruim, detect: {bash: '('}}\n"
        "  - {id: dois-padroes, detect: {bash: '^x', mcp: 'y'}}\n"
        "sempre_pergunta: []\n",
        encoding="utf-8",
    )
    cfg = aut.load(None, plugin_yaml=bad)
    check(cfg["executa_e_reporta"] == [], "item sem detect, regex inválida e dois padrões num detect são descartados")
    check(len(cfg["avisos"]) == 3, f"um aviso por item descartado: {cfg['avisos']}")
    check(aut.match(cfg, bash="git commit")["faixa"] == "sempre_pergunta",
          "sem lista válida, tudo cai em pergunta (o lado seguro)")
    cfg2 = aut.load(None, plugin_yaml=Path(tmp) / "inexistente.yaml")
    check(cfg2["executa_e_reporta"] == [] and cfg2["avisos"], "arquivo ausente: lista vazia + aviso, sem exceção")


def test_cli_classify_and_list():
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
    check(r.returncode == 0 and all(i in r.stdout for i in REQUIRED_AUTOMATIC | REQUIRED_QUESTION),
          "listar mostra todas as ações")


def test_board_flow_shortcut_resolves_the_cepa_autonomy_of_common(tmp):
    check(SHIM.read_bytes() == SHIM_PLAN.read_bytes(),
          "board-flow/bin/cepa-autonomy é cópia byte a byte do shim cepa-plan (o alvo vem do nome)")
    check(os.access(SHIM, os.X_OK), "o atalho é executável")
    # fake repo layout: the shim must find <repo>/common/bin/cepa-autonomy, not cepa-plan
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


def test_decide_reads_the_list():
    s = DECIDE.read_text(encoding="utf-8")
    check("cepa-autonomy" in s and "classify" in s, "decide.md consulta o cepa-autonomy classify")
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
        test_file_has_the_two_lanes_with_detect_and_default_question()
        test_mechanical_matching_of_tool_calls()
        test_repo_override_only_tightens(d)
        test_malformed_plugin_yaml_all_falls_to_question(d)
        test_cli_classify_and_list()
        test_board_flow_shortcut_resolves_the_cepa_autonomy_of_common(d)
        test_decide_reads_the_list()
    if FAILURE_LIST:
        print(f"\n{len(FAILURE_LIST)} falha(s)")
        sys.exit(1)
    print("\nall green")


if __name__ == "__main__":
    main()
