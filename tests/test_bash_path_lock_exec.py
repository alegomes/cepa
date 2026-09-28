#!/usr/bin/env python3
"""Camada 1 do bash-path-lock: deny-by-default em quatro baldes.

Sem dependências — rode com `python3 tests/test_bash_path_lock_exec.py`.
Sai não-zero em falha.

## O furo que este arquivo trava

WEGO-1936: um qa-engineer, trancado para escrever só em `*/src/test/**`,
precisava reverter um arquivo de `src/main` para provar que o teste ficava
vermelho sem o conserto. O `cp` foi barrado pelo cadeado. O agente trocou por
`python3 -c "open('src/main/...','w').write(...)"` e passou: o hook antigo
tratava interpretador inline como "não sei analisar" e LIBERAVA, deixando só
uma linha num log em /tmp que ninguém lia.

A correção (desenho em docs/internals/gauntlet-pilot-bash-path-lock.md,
"Camada 1") inverte a pergunta do hook. Antes: "isto parece uma escrita
conhecida?". Agora: "isto é comprovadamente inofensivo?". Todo comando de agente
trancado cai em exatamente um balde:

1. escritor analisável — o alvo é conferido contra os globs do agente;
2. verbo inocente — lista auditada, com flags perigosas negadas por verbo;
3. fora da jurisdição — roda num diretório fora da raiz do projeto (o worktree
   descartável de perturbação) sem citar a raiz;
4. todo o resto — NEGADO. Interpretador inline e verbo que ninguém listou caem
   aqui por construção, sem precisar constar em lista nenhuma.

Os casos rodam contra as CINCO cópias do hook, como subprocesso e olhando o
código de saída real — um conserto que falta numa topologia continua sendo bug.

## Perturbação (como saber que este teste prova algo)

Em `common/hooks/_templates/bash-path-lock.py.tmpl`, faça `_INNOCENT` aceitar
qualquer verbo (ou troque o `sys.exit(2)` do balde 4 por `sys.exit(0)`),
regenere com `python3 bin/gen-locks.py --write` e rode: os casos do WEGO-1936
e da classe de interpretadores ficam vermelhos nas cinco cópias.
"""

import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from _telemetria_isolada import isola

isola()

REPO = Path(__file__).resolve().parent.parent
HOOKS = sorted(REPO.glob("*/hooks/bash-path-lock.py"))

# Por topologia: um agente trancado que existe no allowlist dela, um arquivo
# DENTRO da pista dele e um FORA. Os caminhos são relativos à raiz do projeto.
LANES = {
    "build-hex":     ("qa-engineer",   "domain/src/test/java/FTest.java",
                      "domain/src/main/java/F.java"),
    "build-team":    ("qa-engineer",   "tests/test_f.py", "apps/x/api/f.py"),
    "design":        ("ux-architect",  "docs/design/f.md", "src/f.js"),
    "discovery":     ("user-researcher", "docs/discovery/f.md", "src/f.js"),
    "docs-topology": ("doc-author",    "docs/how-to/f.md", "src/f.js"),
    "marketing":     ("copywriter",    "docs/marketing/x/pecas/f.md", "src/f.js"),
}

# Marcas nos comandos: {IN} arquivo na pista, {OUT} arquivo fora da pista,
# {INDIR} diretório da pista, {TMP} diretório fora da raiz (o worktree
# descartável), {ROOT} a raiz absoluta do projeto.

WEGO_1936 = "python3 -c \"open('{OUT}','w').write('revertido')\""

DENY = [
    # --- o vetor real do incidente ---
    ("WEGO-1936: python3 -c escrevendo src/main", WEGO_1936),
    # --- a CLASSE, não o nome: variantes que ninguém listou antes ---
    ("python3 -B -c", "python3 -B -c \"open('{OUT}','w')\""),
    ("python3 -Bc (flags combinadas)", "python3 -Bc \"open('{OUT}','w')\""),
    ("python sem 3", "python -c 'print(1)'"),
    ("perl -e", "perl -e 'open(F,\">{OUT}\")'"),
    ("perl -pi -e", "perl -pi -e 's/a/b/' {OUT}"),
    ("ruby -rfileutils -e", "ruby -rfileutils -e 'FileUtils.touch(\"{OUT}\")'"),
    ("node -e", "node -e \"require('fs').writeFileSync('{OUT}','x')\""),
    ("node --eval", "node --eval \"1\""),
    ("osascript -e", "osascript -e 'do shell script \"x\"'"),
    ("bash -c", "bash -c 'echo x > {OUT}'"),
    ("sh -c", "sh -c 'true'"),
    ("zsh -c", "zsh -c 'true'"),
    ("script em /tmp executado por sh", "sh {TMP}/x.sh"),
    ("script em /tmp executado direto", "{TMP}/a.out"),
    ("script DENTRO da própria pista", "bash {INDIR}/gerado.sh"),
    ("python3 rodando script da própria pista", "python3 {INDIR}/gera.py"),
    ("heredoc alimentando python3",
     "python3 <<'EOF'\nopen('{OUT}','w').write('x')\nEOF"),
    ("heredoc com python3 -", "python3 - <<EOF\nprint(1)\nEOF"),
    ("pipe alimentando python3", "echo 'print(1)' | python3"),
    ("here-string para python3", "python3 <<< 'print(1)'"),
    ("source de script em /tmp", "source {TMP}/env.sh"),
    ("eval", "eval \"echo x > {OUT}\""),
    ("exec", "exec python3"),
    ("trap com código", "trap 'python3 -c 1' EXIT"),
    ("compilar na hora", "cc -o {TMP}/a.out {TMP}/a.c"),
    ("verbo desconhecido", "frobnicate --all"),
    ("verbo via variável desconhecida", "$ZZ_CEPA_NAO_EXISTE -c 1"),
    # --- git que reescreve arquivo ---
    ("git apply", "git apply fix.patch"),
    ("git checkout -- fora da pista (balde 1)", "git checkout -- {OUT}"),
    ("git checkout <arquivo> sem --", "git checkout {OUT}"),
    ("git restore fora da pista (balde 1)", "git restore {OUT}"),
    ("git stash", "git stash"),
    ("git stash pop", "git stash pop"),
    ("git reset --hard", "git reset --hard HEAD~1"),
    ("git clean", "git clean -fd"),
    ("git cherry-pick", "git cherry-pick abc123"),
    ("git -c core.pager executa comando", "git -c core.pager='sh -c x' log"),
    ("git config grava hooksPath", "git config core.hooksPath /tmp/h"),
    ("git worktree add DENTRO da raiz", "git worktree add wt-interno HEAD"),
    ("git diff --output para fora da pista", "git diff --output={OUT}"),
    # --- verbo inocente com flag que o transforma em escritor/executor ---
    ("sed -i fora da pista (balde 1)", "sed -i 's/a/b/' {OUT}"),
    ("sed com comando w", "sed 's/a/b/w {OUT}' {IN}"),
    ("sed com flag e (executa)", "sed 's/.*/date/e' {IN}"),
    ("find -exec", "find . -name '*.java' -exec rm {} \\;"),
    ("find -delete", "find . -name '*.java' -delete"),
    ("rg --pre executa", "rg --pre ./x.sh foo"),
    ("awk com redirect", "awk '{print > \"{OUT}\"}' {IN}"),
    ("awk com system()", "awk 'BEGIN{system(\"rm -rf x\")}'"),
    ("xargs com escritor", "ls | xargs -I{} cp {} {OUT}"),
    ("xargs com interpretador", "ls | xargs python3 -c 'print(1)'"),
    ("tar -x", "tar -xf a.tar"),
    ("npm exec", "npm exec -- node x.js"),
    ("npm install <pacote>", "npm install left-pad"),
    ("npx node -e", "npx node -e 1"),
    ("npx -c", "npx -c 'echo x > {OUT}'"),
    ("npx prettier --write", "npx prettier --write src/"),
    ("mvn exec:exec", "./mvnw exec:exec -Dexec.executable=python3"),
    ("env -S", "env -S 'python3 -c 1'"),
    ("GIT_EXTERNAL_DIFF executa", "GIT_EXTERNAL_DIFF={TMP}/x.sh git diff"),
    ("export de PAGER", "export GIT_PAGER='sh -c x' && git log"),
    # --- wrappers não lavam o verbo ---
    ("timeout python3 -c", "timeout 5 python3 -c 1"),
    ("nohup perl -e", "nohup perl -e 1"),
    ("env python3 -c", "env FOO=1 python3 -c 1"),
    ("sudo", "sudo ls"),
    # --- gap: substituição de comando em argumento de verbo inocente ---
    ("$(...) dentro de echo", "echo $(python3 -c \"open('{OUT}','w')\")"),
    ("$(...) entre aspas duplas", "echo \"$(python3 -c 1)\""),
    ("crase dentro de echo", "echo `python3 -c 1`"),
    ("process substitution <(...)", "diff <(python3 -c 1) {IN}"),
    ("atribuição com substituição maliciosa", "D=$(python3 -c 1) && ls $D"),
    # --- encadeamento: um segmento ruim contamina a linha ---
    ("ls; python3 -c", "ls; python3 -c 1"),
    ("git status && perl -e", "git status && perl -e 1"),
    # --- cd que pode falhar não tira da jurisdição ---
    ("cd /tmp; python3 -c (cd pode falhar)", "cd {TMP}; python3 -c 1"),
    ("cd /tmp || python3 -c", "cd {TMP} || python3 -c 1"),
    ("subshell (cd /tmp) && python3 -c", "(cd {TMP}) && python3 -c 1"),
    ("cd /tmp | python3 (pipe não herda cd)", "cd {TMP} | python3 -c 1"),
    ("cd /tmp && python3 citando a raiz",
     "cd {TMP} && python3 -c \"open('{ROOT}/{OUT}','w')\""),
    # --- escritores do balde 1 que faltavam ---
    ("mkdir fora da pista", "mkdir -p {OUT}.d"),
    ("rm fora da pista", "rm -f {OUT}"),
    ("ln fora da pista", "ln -s /etc/passwd {OUT}"),
    ("sort -o fora da pista", "sort -o {OUT} {IN}"),
    ("cp -t fora da pista", "cp -t src {IN}"),
    ("alvo com variável desconhecida", "echo x > $ZZ_CEPA_NAO_EXISTE/f"),
    ("redirect 1> (dígito) fora da pista", "echo 'class X{}' 1> {OUT}"),
    ("redirect >| fora da pista", "echo x >| {OUT}"),
    ("heredoc para arquivo fora da pista", "cat <<EOF > {OUT}\nclass X{}\nEOF"),
    ("curl -sSLo (flags combinadas)", "curl -sSLo {OUT} http://x"),
    ("docker run montando a raiz", "docker run --rm -v $(pwd):/w alpine true"),
    # substituição que esconde uma flag: o valor se parte em palavras
    ("flag escondida em $(printf)", "sed $(printf -- -i) 's/a/b/' {OUT}"),
    ("git pull reescreve a árvore", "git pull"),
]

ALLOW = [
    # --- leitura e diagnóstico ---
    ("grep com >=", "grep -rn '>=' src/"),
    ("[[ >= ]] && mvnw", "[[ $a >= $b ]] && ./mvnw test"),
    ("ls", "ls -la"),
    ("cat | head", "cat {IN} | head -5"),
    ("find | xargs grep", "find . -name '*.java' | xargs grep -l Foo"),
    ("find sem -exec", "find . -type f -name '*.md'"),
    ("wc", "wc -l {IN}"),
    ("jq", "jq . package.json"),
    ("rg", "rg -n foo src"),
    ("sed -n", "sed -n '1,20p' {IN}"),
    ("sed s///g sem -i", "sed 's/a/b/g' {IN}"),
    ("awk de leitura", "awk '{print $1}' {IN}"),
    ("sort | uniq -c", "sort {IN} | uniq -c"),
    ("diff", "diff {IN} {OUT}"),
    ("echo citando python3 -c", "echo 'python3 -c é negado'"),
    ("pwd / date / which", "pwd && date && which git"),
    ("for ... do ... done", "for f in a b; do grep x $f; done"),
    ("if [ -f ] then cat fi", "if [ -f {IN} ]; then cat {IN}; fi"),
    ("while read", "git ls-files | while read f; do wc -l \"$f\"; done"),
    ("substituição inocente", "echo $(git rev-parse HEAD)"),
    ("cd para a raiz via substituição", "cd $(git rev-parse --show-toplevel) && git status"),
    ("variável de ambiente conhecida", "ls $HOME"),
    ("xargs com verbo de leitura", "git diff --name-only | xargs wc -l"),
    # --- git do dia a dia dos workers e do lead ---
    ("git status", "git status --short"),
    ("git diff", "git diff HEAD~1 -- {IN}"),
    ("git log", "git log --oneline -3"),
    ("git show", "git show HEAD --stat"),
    ("git rev-parse", "git rev-parse --abbrev-ref HEAD"),
    ("git add", "git add {IN}"),
    ("git commit -m citando interpretador",
     "git commit -m \"fix: python3 -c e perl -e agora sao negados\""),
    ("git commit -F heredoc",
     "git commit -F - <<'MSG'\nfix: algo\n\npython3 -c 'x' > {OUT}\nMSG"),
    ("git checkout -b", "git checkout -b story-integration"),
    ("git checkout <branch>", "git checkout main"),
    ("git switch", "git switch -c nova"),
    ("git merge --no-ff (lead)", "git merge --no-ff story-integration"),
    ("git branch -d", "git branch -d story-integration"),
    ("git worktree remove (worker)", "git worktree remove .claude/worktrees/agent-1"),
    ("git worktree list", "git worktree list"),
    ("git checkout -- dentro da pista", "git checkout HEAD -- {IN}"),
    ("git -c color.ui", "git -c color.ui=false log -1"),
    ("git push", "git push"),
    # --- build ---
    ("./mvnw test -pl", "./mvnw test -pl domain"),
    ("./mvnw -am -Dtest", "./mvnw -pl bootstrap -am test -Dtest=FooIT -Dsurefire.failIfNoSpecifiedTests=false"),
    ("mvnw 2> err.log", "./mvnw test 2> err.log"),
    ("mvn verify", "mvn -q verify"),
    ("pitest", "./mvnw -pl domain -am test-compile org.pitest:pitest-maven:mutationCoverage"),
    ("./gradlew", "./gradlew test"),
    ("npm test", "npm test"),
    ("npm run build", "npm run build"),
    ("npm ci", "npm ci"),
    ("npx jest", "npx jest --ci"),
    ("npx playwright test", "npx playwright test"),
    ("pytest", "pytest -q"),
    ("python3 -m pytest", "python3 -m pytest tests -q"),
    ("PYTHONPATH=. pytest", "PYTHONPATH=. pytest -q"),
    ("python3 -m json.tool", "python3 -m json.tool package.json"),
    ("python3 --version", "python3 --version"),
    ("timeout ./mvnw", "timeout 600 ./mvnw verify"),
    ("export && npm test", "export FOO=bar && npm test"),
    ("docker ps", "docker ps"),
    ("docker compose up", "docker compose up -d"),
    ("docker compose logs", "docker compose logs api"),
    ("script do projeto fora da pista", "bash scripts/build.sh"),
    ("make", "make test"),
    # --- balde 1: escrita analisável dentro da pista ---
    ("cp para a pista", "cp {OUT} {IN}"),
    ("redirect para a pista", "echo x > {IN}"),
    ("sed -i na pista", "sed -i 's/a/b/' {IN}"),
    ("mkdir na pista", "mkdir -p {INDIR}/sub"),
    ("redirect para /tmp", "echo x > {TMP}/out.txt"),
    ("tee para /tmp", "git diff | tee {TMP}/d.patch"),
    # --- balde 3: a rota sancionada de perturbação RED ---
    ("receita canônica em uma linha",
     "D=$(mktemp -d) && git worktree add --detach \"$D/red\" HEAD && "
     "cd \"$D/red\" && git checkout HEAD~1 -- {OUT} && ./mvnw test -pl domain"),
    ("git worktree add em /tmp", "git worktree add {TMP}/red HEAD"),
    ("git worktree remove em /tmp", "git worktree remove --force {TMP}/red"),
    ("cd /tmp && python3 -c (worktree descartável)",
     "cd {TMP} && python3 -c \"open('{OUT}','w')\""),
    ("cd /tmp && sed -i fora da pista",
     "cd {TMP} && sed -i 's/>=/>/' {OUT} && ./mvnw test"),
    ("cd /tmp && git apply -R", "cd {TMP} && git apply -R x.patch"),
    ("git -C /tmp checkout --", "git -C {TMP} checkout HEAD~1 -- {OUT}"),
    ("git -C /tmp apply -R", "git -C {TMP} apply -R x.patch"),
    ("cd /tmp && cp lendo da raiz", "cd {TMP} && cp {ROOT}/{OUT} {OUT}"),
    ("pushd /tmp && python3 -c", "pushd {TMP} && python3 -c 1"),
    # --- formas comuns que o hook antigo lia errado ou que um classificador
    #     ingênuo negaria ---
    ("commit no padrão $(cat <<'EOF')",
     "git commit -m \"$(cat <<'EOF'\nfix: don't (break) it\n\nCorpo.\nEOF\n)\""),
    ("2>&1 | tail não é separador", "./mvnw test 2>&1 | tail -50"),
    ("log em /tmp com 2>&1", "./mvnw -q test > {TMP}/out.log 2>&1; echo $?"),
    ("heredoc para arquivo na pista", "cat <<EOF > {IN}\nconteudo\nEOF"),
    ("here-string para verbo inocente", "cat <<< 'x y' | grep x"),
    ("mvnw de módulo filho", "cd api-rest && ../mvnw test"),
    ("awk com comparação NR>1", "awk -F, 'NR>1 {print $2}' d.csv"),
    ("awk com alternância /a|b/", "awk '/a|b/ {print}' {IN}"),
    ("curl para jq", "curl -sS http://localhost:8080/q/health | jq ."),
    ("docker compose -f up", "docker compose -f docker-compose.yml up -d postgres"),
    ("python3 -W ignore -m pytest", "python3 -W ignore -m pytest -q"),
    ("git worktree add irmão fora da raiz", "git worktree add {TMP}/irmao HEAD"),
]


def run(hook, agent_type, command, cwd, env_extra=None):
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "agent_type": agent_type,
        "cwd": str(cwd),
    }
    env = dict(os.environ)
    env.pop("CEPA_BASHLOCK_ENFORCE", None)
    env.update(env_extra or {})
    p = subprocess.run([sys.executable, str(hook)], input=json.dumps(payload),
                       capture_output=True, text=True, env=env, timeout=60)
    return p.returncode, p.stderr


def plugin_of(hook: Path) -> str:
    return json.loads((hook.parent.parent / ".claude-plugin" / "plugin.json")
                      .read_text(encoding="utf-8"))["name"]


def fill(cmd, lane_in, lane_out, root, tmp):
    return (cmd.replace("{INDIR}", str(Path(lane_in).parent))
               .replace("{IN}", lane_in).replace("{OUT}", lane_out)
               .replace("{ROOT}", str(root)).replace("{TMP}", str(tmp)))


FAILURES = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok  {label}")
    else:
        FAILURES.append(label)
        print(f"FAIL  {label}  {detail}")


def test_plugin_name_vem_do_caminho():
    """Gap do desenho: a checagem anti-deriva deriva PLUGIN_NAME do caminho.

    O PLUGIN_NAME de cada cópia tem de ser o `name` do plugin.json da pasta
    onde a cópia mora. Um PLUGIN_NAME errado não quebra nada à vista: o hook
    compara o prefixo do agent_type, não casa nunca, e passa a liberar TUDO
    daquela topologia em silêncio.
    """
    import importlib.util
    for hook in HOOKS:
        spec = importlib.util.spec_from_file_location(
            f"bpl_pn_{hook.parent.parent.name}", str(hook))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        want = plugin_of(hook)
        check(f"[{hook.parent.parent.name}] PLUGIN_NAME == plugin.json name ({want})",
              mod.PLUGIN_NAME == want, f"PLUGIN_NAME={mod.PLUGIN_NAME!r}")


def test_baldes():
    jobs = []
    for hook in HOOKS:
        topo = hook.parent.parent.name
        agent, lane_in, lane_out = LANES[topo]
        agent_type = f"{plugin_of(hook)}:{agent}"
        proj = Path(tempfile.mkdtemp(prefix="bpl-proj-")).resolve()
        tmp = Path(tempfile.mkdtemp(prefix="bpl-wt-")).resolve()
        for want, cases in ((2, DENY), (0, ALLOW)):
            for label, cmd in cases:
                jobs.append((topo, hook, agent_type, label,
                             fill(cmd, lane_in, lane_out, proj, tmp), proj, want))

    def one(job):
        topo, hook, agent_type, label, cmd, proj, want = job
        rc, err = run(hook, agent_type, cmd, proj)
        return job, rc, err

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(one, jobs))
    for (topo, _h, _a, label, cmd, _p, want), rc, err in results:
        verbo = "nega" if want == 2 else "libera"
        # Um erro interno do classificador também nega (falha fechada). Sem esta
        # trava, um caso de negação poderia estar verde pelo motivo errado.
        check(f"[{topo:13}] {verbo}: {label}",
              rc == want and "erro interno" not in err,
              f"exit={rc} (esperado {want}) cmd={cmd!r} stderr={err.strip()[:240]!r}")


def test_fora_de_escopo_continua_livre():
    """Contrato fail-open: sessão principal, built-in e plugin alheio passam."""
    for hook in HOOKS:
        topo = hook.parent.parent.name
        proj = Path(tempfile.mkdtemp(prefix="bpl-proj-")).resolve()
        for agent_type, rotulo in (("", "sessão principal"),
                                   ("Explore", "agente built-in"),
                                   ("outro-plugin:dev", "plugin alheio")):
            rc, err = run(hook, agent_type, WEGO_1936.replace("{OUT}", "src/F.java"), proj)
            check(f"[{topo:13}] {rotulo} não é trancado", rc == 0, err[:200])


def test_mensagem_nomeia_balde_e_saida():
    """A mensagem diz qual balde falhou e qual é o caminho legítimo."""
    for hook in HOOKS:
        topo = hook.parent.parent.name
        agent, lane_in, lane_out = LANES[topo]
        proj = Path(tempfile.mkdtemp(prefix="bpl-proj-")).resolve()
        rc, err = run(hook, f"{plugin_of(hook)}:{agent}",
                      WEGO_1936.replace("{OUT}", lane_out), proj)
        check(f"[{topo:13}] deny do interpretador nomeia o balde 4",
              rc == 2 and "balde 4" in err, err[:300])
        check(f"[{topo:13}] deny aponta o worktree descartável",
              "git worktree add" in err and "mktemp" in err, err[:600])
        check(f"[{topo:13}] deny aponta Write/Edit", "Write" in err and "Edit" in err,
              err[:600])
        rc, err = run(hook, f"{plugin_of(hook)}:{agent}", f"cp x {lane_out}", proj)
        check(f"[{topo:13}] deny de escrita fora da pista nomeia o balde 1",
              rc == 2 and "balde 1" in err and lane_out in err, err[:300])


def test_modo_sombra_e_telemetria():
    """CEPA_BASHLOCK_ENFORCE=0 libera o balde 4, mas registra o que negaria.

    E o deny de verdade também vira evento no ledger — a falha silenciosa do
    log em /tmp que ninguém lia é o que este item existe para matar.
    """
    for hook in HOOKS:
        topo = hook.parent.parent.name
        agent, lane_in, lane_out = LANES[topo]
        at = f"{plugin_of(hook)}:{agent}"
        proj = Path(tempfile.mkdtemp(prefix="bpl-proj-")).resolve()
        tdir = Path(tempfile.mkdtemp(prefix="bpl-tel-"))
        env = {"CEPA_TELEMETRY_DIR": str(tdir)}

        def eventos():
            out = []
            for f in tdir.glob("events-*.jsonl"):
                out += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
            return out

        rc, _ = run(hook, at, WEGO_1936.replace("{OUT}", lane_out), proj,
                    {**env, "CEPA_BASHLOCK_ENFORCE": "0"})
        check(f"[{topo:13}] modo sombra libera o balde 4", rc == 0)
        ev = [e for e in eventos() if e.get("event") == "bash_pathlock_would_deny"]
        check(f"[{topo:13}] modo sombra grava bash_pathlock_would_deny",
              len(ev) == 1 and ev[0].get("bucket") == 4 and ev[0].get("agent") == agent,
              str(eventos())[:300])

        rc, _ = run(hook, at, f"cp x {lane_out}", proj,
                    {**env, "CEPA_BASHLOCK_ENFORCE": "0"})
        check(f"[{topo:13}] modo sombra NÃO afrouxa o balde 1", rc == 2)

        rc, _ = run(hook, at, WEGO_1936.replace("{OUT}", lane_out), proj, env)
        ev = [e for e in eventos() if e.get("event") == "bash_pathlock_deny"]
        check(f"[{topo:13}] deny grava bash_pathlock_deny no ledger",
              rc == 2 and any(e.get("bucket") == 4 and e.get("verb") == "python3"
                              for e in ev), str(ev)[:300])

        tmp = Path(tempfile.mkdtemp(prefix="bpl-wt-")).resolve()
        rc, _ = run(hook, at, f"git worktree add --detach {tmp}/red HEAD", proj, env)
        ev = [e for e in eventos() if e.get("event") == "perturb_worktree_created"]
        check(f"[{topo:13}] worktree de perturbação vira evento contável",
              rc == 0 and len(ev) == 1, str(eventos())[-300:])


def test_dica_diretorio_nao_resolvido():
    """Worktree descartável em duas chamadas: a negação diz por que e o que usar.

    Caso de 2026-09-26: o agente de prova cria a worktree numa chamada e usa
    `cd "$WT" && git checkout ...` na seguinte. O cadeado lê cada chamada
    sozinha; `$WT` não tem valor, o `cd` conta como "continua na raiz" e a
    reversão é negada. A mensagem antiga só dizia "escrita fora da sua pista",
    e os agentes contornavam com python3 -c (o vetor do WEGO-1936). A negação
    continua (o cadeado não pode adivinhar o destino); o que muda é que ela
    nomeia a variável e oferece caminho literal ou `git -C`, que passam.

    Perturbação: tire a chamada a `_dica_dir_desconhecido` de `_mensagem` no
    molde e regenere; os casos "nomeia a variável" ficam vermelhos.
    """
    var = "$CEPA_WT_NAO_EXISTE"
    for hook in HOOKS:
        topo = hook.parent.parent.name
        agent, _lane_in, lane_out = LANES[topo]
        at = f"{plugin_of(hook)}:{agent}"
        proj = Path(tempfile.mkdtemp(prefix="bpl-proj-")).resolve()
        tmp = Path(tempfile.mkdtemp(prefix="bpl-wt-")).resolve()
        for rotulo, cmd in (
                ("cd \"$VAR\" && git checkout",
                 f'cd "{var}" && git checkout HEAD~1 -- {lane_out}'),
                ("git -C \"$VAR\" checkout",
                 f'git -C "{var}" checkout HEAD~1 -- {lane_out}')):
            rc, err = run(hook, at, cmd, proj)
            check(f"[{topo:13}] {rotulo}: continua negado", rc == 2, err[:200])
            check(f"[{topo:13}] {rotulo}: nomeia a variável e a causa",
                  f"{var} não tem valor" in err and "Cada chamada do Bash" in err,
                  err[:600])
            check(f"[{topo:13}] {rotulo}: sugere caminho literal e git -C",
                  "caminho LITERAL" in err and "git -C /tmp/" in err, err[:600])
        for rotulo, cmd in (
                ("cd <literal> && git checkout",
                 f"cd {tmp}/red && git checkout HEAD~1 -- {lane_out}"),
                ("git -C <literal> checkout",
                 f"git -C {tmp}/red checkout HEAD~1 -- {lane_out}"),
                ("variável definida na MESMA chamada",
                 f"WT={tmp}/red; cd \"$WT\" && git checkout HEAD~1 -- {lane_out}")):
            rc, err = run(hook, at, cmd, proj)
            check(f"[{topo:13}] {rotulo}: liberado", rc == 0, err[:300])
        rc, err = run(hook, at, f"cp x {lane_out}", proj)
        check(f"[{topo:13}] negação sem variável não ganha a dica",
              rc == 2 and "não tem valor" not in err, err[:400])


def test_agentes_de_prova_enderecam_worktree_por_caminho_literal():
    """Os dois agentes de prova dizem para usar caminho literal ou git -C.

    O hook só explica depois de negar; o texto do agente evita a negação.
    Sem esta regra no agente, cada run de prova esbarra no cadeado uma vez
    antes de acertar, e é nesse esbarrão que o python3 -c aparece.
    """
    for rel in ("build-hex/agents/proof-reviewer.md",
                "common/agents/ui-proof-reviewer.md"):
        txt = (REPO / rel).read_text(encoding="utf-8")
        check(f"{rel} manda endereçar a worktree pelo caminho literal",
              "by its literal path" in txt and "`git -C /tmp/" in txt
              and "python3 -c" in txt)


def test_script_na_copia_descartavel():
    """Script python3 rodado de DENTRO do worktree descartável passa (balde 3).

    Achado no run 2026-09-28-0558: o proof-reviewer, path-locked, cria a cópia
    descartável com `git worktree add /tmp/proof-<KEY> <commit>` e era negado
    ao rodar o teste de dentro dela. Duas das formas reais que caíram no
    balde 4 ("script fora do projeto"):

      cd /tmp/proof-agb-head && ls tests/ | grep -i gate_status; \\
        timeout 120 python3 tests/test_gate_status_por_nome.py; echo "EXIT=$?"

      python3 /tmp/proof-vigia-solo/tests/test_no_background_build.py 2>&1 \\
        | grep -A5 ...

    A distinção do caso legítimo é o script morar dentro de um worktree
    REGISTRADO deste repo (`git worktree list --porcelain`), não em qualquer
    /tmp: um script solto fora da raiz e fora de qualquer worktree continua
    negado (pinned em DENY acima, "script em /tmp executado por sh").
    """
    for hook in HOOKS:
        topo = hook.parent.parent.name
        agent, _lane_in, lane_out = LANES[topo]
        at = f"{plugin_of(hook)}:{agent}"
        proj = Path(tempfile.mkdtemp(prefix="bpl-proj-")).resolve()
        outside = Path(tempfile.mkdtemp(prefix="bpl-wtreg-")).resolve()
        wt = outside / "proof-x"
        solto = outside / "solto"
        solto.mkdir()
        (solto / "x.sh").write_text("#!/bin/sh\necho hi\n")

        def git(*args):
            subprocess.run(["git", "-C", str(proj), *args], check=True,
                            capture_output=True, text=True)

        git("init", "-q")
        git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
            "--allow-empty", "-m", "init")
        # "harness/", não "tests/": em build-team a pista do qa-engineer É
        # "tests/**" — um script ali dentro cairia no deny de "própria pista"
        # (pinned em DENY: "script DENTRO da própria pista"), mascarando o
        # caso que este teste prova.
        (proj / "harness").mkdir(exist_ok=True)
        tpy = proj / "harness" / "t.py"
        tpy.write_text("#!/usr/bin/env python3\nprint(1)\n")
        tpy.chmod(0o755)
        git("add", "harness/t.py")
        git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
            "-m", "add t.py")
        git("worktree", "add", "-q", str(wt), "HEAD")

        try:
            for label, cmd in (
                ("cd {WT}; python3 harness/t.py (cd pode falhar)",
                 f"cd {wt}; python3 harness/t.py"),
                ("caso real 1: cd && ls|grep ; timeout python3 ; echo EXIT",
                 f'cd {wt} && ls harness/ | grep t; '
                 f'timeout 120 python3 harness/t.py; echo "EXIT=$?"'),
                ("caso real 2: cd && heredoc && python3 | tail",
                 f"cd {wt} && python3 - <<'EOF'\nprint(1)\nEOF\n"
                 f"python3 harness/t.py 2>&1 | tail -3"),
                ("caso real 3: python3 <WT>/harness/t.py | grep",
                 f"python3 {wt}/harness/t.py 2>&1 | grep -A5 x"),
                ("bash <WT>/harness/t.py", f"bash {wt}/harness/t.py"),
                ("<WT>/harness/t.py direto", f"{wt}/harness/t.py"),
            ):
                rc, err = run(hook, at, cmd, proj)
                check(f"[{topo:13}] libera: {label}", rc == 0, err[:300])

            rc, err = run(hook, at, f"python3 {wt}/harness/t.py {proj}/{lane_out}", proj)
            check(f"[{topo:13}] nega: script na cópia citando a raiz (paridade balde 3)",
                  rc == 2 and "erro interno" not in err, err[:300])

            rc, err = run(hook, at, f"sh {solto}/x.sh", proj)
            check(f"[{topo:13}] nega: script fora da raiz e fora de worktree registrado",
                  rc == 2 and "erro interno" not in err, err[:300])

            git("worktree", "remove", "--force", str(wt))
            rc, err = run(hook, at, f"python3 {wt}/harness/t.py", proj)
            check(f"[{topo:13}] nega: worktree removido do registro (perturbação)",
                  rc == 2 and "erro interno" not in err, err[:300])
        finally:
            subprocess.run(["git", "-C", str(proj), "worktree", "remove", "--force", str(wt)],
                           capture_output=True, text=True)


def main():
    if not HOOKS:
        print("FAIL: nenhum */hooks/bash-path-lock.py em", REPO)
        return 1
    test_plugin_name_vem_do_caminho()
    test_baldes()
    test_fora_de_escopo_continua_livre()
    test_mensagem_nomeia_balde_e_saida()
    test_dica_diretorio_nao_resolvido()
    test_agentes_de_prova_enderecam_worktree_por_caminho_literal()
    test_modo_sombra_e_telemetria()
    test_script_na_copia_descartavel()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} falha(s) em {len(HOOKS)} cópias")
        return 1
    print(f"tudo verde em {len(HOOKS)} cópias")
    return 0


if __name__ == "__main__":
    sys.exit(main())
