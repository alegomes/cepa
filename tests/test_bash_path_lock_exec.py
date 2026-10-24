#!/usr/bin/env python3
"""Layer 1 of bash-path-lock: deny-by-default in four buckets.

No dependencies — run with `python3 tests/test_bash_path_lock_exec.py`.
Exits non-zero on failure.

## The hole this file locks

WEGO-1936: a qa-engineer, locked to write only in `*/src/test/**`,
needed to revert a `src/main` file to prove the test went
red without the fix. The `cp` was stopped by the lock. The agent swapped it for
`python3 -c "open('src/main/...','w').write(...)"` and got through: the old hook
treated an inline interpreter as "I don't know how to analyze" and RELEASED it, leaving only
a line in a log in /tmp that nobody read.

The fix (design in docs/internals/gauntlet-pilot-bash-path-lock.md,
"Layer 1") inverts the hook's question. Before: "does this look like a known
write?". Now: "is this provably harmless?". Every command of a locked agent
falls into exactly one bucket:

1. analyzable writer — the target is checked against the agent's globs;
2. innocent verb — audited list, with dangerous flags denied per verb;
3. outside the jurisdiction — runs in a directory outside the project root (the disposable
   perturbation worktree) without naming the root;
4. everything else — DENIED. Inline interpreter and a verb nobody listed fall
   here by construction, without needing to be on any list.

The cases run against the FIVE copies of the hook, as a subprocess and looking at the real
exit code — a fix missing in one topology is still a bug.

## Perturbation (how to know this test proves something)

In `common/hooks/_templates/bash-path-lock.py.tmpl`, make `_INNOCENT` accept
any verb (or swap the `sys.exit(2)` of bucket 4 for `sys.exit(0)`),
regenerate with `python3 bin/gen-locks.py --write` and run: the WEGO-1936 cases
and the interpreter-class cases turn red in all five copies.
"""

import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from _isolated_telemetry import isolate

isolate()

REPO = Path(__file__).resolve().parent.parent
HOOKS = sorted(REPO.glob("*/hooks/bash-path-lock.py"))

# Per topology: a locked agent that exists in its allowlist, a file
# INSIDE its lane and one OUTSIDE. Paths are relative to the project root.
LANES = {
    "build-hex":     ("qa-engineer",   "domain/src/test/java/FTest.java",
                      "domain/src/main/java/F.java"),
    "build-team":    ("qa-engineer",   "tests/test_f.py", "apps/x/api/f.py"),
    "design":        ("ux-architect",  "docs/design/f.md", "src/f.js"),
    "discovery":     ("user-researcher", "docs/discovery/f.md", "src/f.js"),
    "docs-topology": ("doc-author",    "docs/how-to/f.md", "src/f.js"),
    "marketing":     ("copywriter",    "docs/marketing/x/pecas/f.md", "src/f.js"),
}

# Marks in the commands: {IN} file in the lane, {OUT} file outside the lane,
# {INDIR} directory of the lane, {TMP} directory outside the root (the disposable
# worktree), {ROOT} the absolute root of the project.

WEGO_1936 = "python3 -c \"open('{OUT}','w').write('revertido')\""

DENY = [
    # --- the real vector of the incident ---
    ("WEGO-1936: python3 -c escrevendo src/main", WEGO_1936),
    # --- the CLASS, not the name: variants nobody listed before ---
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
    # --- git that rewrites a file ---
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
    # --- innocent verb with a flag that turns it into a writer/executor ---
    ("sed -i fora da pista (balde 1)", "sed -i 's/a/b/' {OUT}"),
    ("sed com comando w", "sed 's/a/b/w {OUT}' {IN}"),
    ("sed com flag e (executa)", "sed 's/.*/date/e' {IN}"),
    # w/e command after an address or after an a/i/c text: the per-command
    # reader that removed the false positive on "stays" must not open this hole
    ("sed w depois de endereço com stays", "sed '/stays/w {OUT}' {IN}"),
    ("sed w na linha seguinte ao texto do a", "sed -i '1a stays\nw {OUT}' {IN}"),
    ("sed e depois de rótulo", "sed ':a;e date' {IN}"),
    ("sed com comando que ninguém conhece", "sed -i 'k' {IN}"),
    # proof of 2026-09-29: a backslash at the end of a comment or of `r file` does not
    # continue the line — the next command executes in the real sed
    ("sed w depois de comentário com barra", "sed -n '#c\\\nw {OUT}' {IN}"),
    ("sed w depois de r com barra", "sed -n 'r x\\\nw {OUT}' {IN}"),
    ("sed w depois de rótulo e espaço (GNU)", "sed -n 'ba w {OUT}' {IN}"),
    ("sed com flag do s desconhecida", "sed -i 's/a/b/Z' {IN}"),
    ("sed com y malformado", "sed -i 'y/ab/' {IN}"),
    ("sed com endereço sem comando", "sed -i '/x/' {IN}"),
    # braces: the `w` inside a block, or stuck to the `}`, is still a w
    ("sed w dentro de bloco", "sed -n '/x/{p;w {OUT}}' {IN}"),
    ("sed w na linha depois do bloco", "sed -n '{p}\nw {OUT}' {IN}"),
    ("sed w colado ao fim do bloco", "sed -n '{p}w {OUT}' {IN}"),
    ("sed w depois de rótulo fechado por }", "sed -n '{bx}w{OUT}' {IN}"),
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
    # --- wrappers do not launder the verb ---
    ("timeout python3 -c", "timeout 5 python3 -c 1"),
    ("nohup perl -e", "nohup perl -e 1"),
    ("env python3 -c", "env FOO=1 python3 -c 1"),
    ("sudo", "sudo ls"),
    # --- gap: command substitution in the argument of an innocent verb ---
    ("$(...) dentro de echo", "echo $(python3 -c \"open('{OUT}','w')\")"),
    ("$(...) entre aspas duplas", "echo \"$(python3 -c 1)\""),
    ("crase dentro de echo", "echo `python3 -c 1`"),
    ("process substitution <(...)", "diff <(python3 -c 1) {IN}"),
    ("atribuição com substituição maliciosa", "D=$(python3 -c 1) && ls $D"),
    # --- chaining: one bad segment contaminates the line ---
    ("ls; python3 -c", "ls; python3 -c 1"),
    ("git status && perl -e", "git status && perl -e 1"),
    # --- a cd that may fail does not take it out of the jurisdiction ---
    ("cd /tmp; python3 -c (cd pode falhar)", "cd {TMP}; python3 -c 1"),
    ("cd /tmp || python3 -c", "cd {TMP} || python3 -c 1"),
    ("subshell (cd /tmp) && python3 -c", "(cd {TMP}) && python3 -c 1"),
    ("cd /tmp | python3 (pipe não herda cd)", "cd {TMP} | python3 -c 1"),
    ("cd /tmp && python3 citando a raiz",
     "cd {TMP} && python3 -c \"open('{ROOT}/{OUT}','w')\""),
    # --- bucket 1 writers that were missing ---
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
    # substitution that hides a flag: the value splits into words
    ("flag escondida em $(printf)", "sed $(printf -- -i) 's/a/b/' {OUT}"),
    ("git pull reescreve a árvore", "git pull"),
]

ALLOW = [
    # --- reading and diagnostics ---
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
    # --- everyday git of the workers and of the lead ---
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
    # --- bucket 1: analyzable write inside the lane ---
    ("cp para a pista", "cp {OUT} {IN}"),
    ("redirect para a pista", "echo x > {IN}"),
    ("sed -i na pista", "sed -i 's/a/b/' {IN}"),
    # deviations.md 2026-09-27: "stays" outside an s/// was read as s + delimiter t
    ("sed -i com stays no endereço", "sed -i '/o item stays at the entry/d' {IN}"),
    ("sed -i com stays no texto do a", "sed -i '/^fim/a o item stays até que o teste rode' {IN}"),
    ("sed -i com stays no texto do c",
     "sed -i '/^Status/c\\\nO card stays at the top of the entry' {IN}"),
    ("sed -i com rótulo e laço", "sed -i ':a;N;/fim/!ba;s/\\n/ /g' {IN}"),
    ("mkdir na pista", "mkdir -p {INDIR}/sub"),
    ("redirect para /tmp", "echo x > {TMP}/out.txt"),
    ("tee para /tmp", "git diff | tee {TMP}/d.patch"),
    # --- bucket 3: the sanctioned RED perturbation route ---
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
    # --- common forms the old hook misread or that a naive classifier
    #     would deny ---
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


def test_plugin_name_comes_from_the_path():
    """Design gap: the anti-drift check derives PLUGIN_NAME from the path.

    The PLUGIN_NAME of each copy must be the `name` of the plugin.json of the folder
    where the copy lives. A wrong PLUGIN_NAME breaks nothing in plain sight: the hook
    compares the agent_type prefix, never matches, and starts releasing EVERYTHING
    of that topology in silence.
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


def test_buckets():
    jobs = []
    for hook in HOOKS:
        top = hook.parent.parent.name
        agent, lane_in, lane_out = LANES[top]
        agent_type = f"{plugin_of(hook)}:{agent}"
        proj = Path(tempfile.mkdtemp(prefix="bpl-proj-")).resolve()
        tmp = Path(tempfile.mkdtemp(prefix="bpl-wt-")).resolve()
        for want, cases in ((2, DENY), (0, ALLOW)):
            for label, cmd in cases:
                jobs.append((top, hook, agent_type, label,
                             fill(cmd, lane_in, lane_out, proj, tmp), proj, want))

    def one(job):
        top, hook, agent_type, label, cmd, proj, want = job
        rc, err = run(hook, agent_type, cmd, proj)
        return job, rc, err

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(one, jobs))
    for (top, _h, _a, label, cmd, _p, want), rc, err in results:
        verb = "nega" if want == 2 else "libera"
        # An internal error of the classifier also denies (fails closed). Without this
        # lock, a denial case could be green for the wrong reason.
        check(f"[{top:13}] {verb}: {label}",
              rc == want and "erro interno" not in err,
              f"exit={rc} (esperado {want}) cmd={cmd!r} stderr={err.strip()[:240]!r}")


def test_out_of_scope_remains_free():
    """Fail-open contract: main session, built-in and foreign plugin pass."""
    for hook in HOOKS:
        top = hook.parent.parent.name
        proj = Path(tempfile.mkdtemp(prefix="bpl-proj-")).resolve()
        for agent_type, caption in (("", "sessão principal"),
                                   ("Explore", "agente built-in"),
                                   ("outro-plugin:dev", "plugin alheio")):
            rc, err = run(hook, agent_type, WEGO_1936.replace("{OUT}", "src/F.java"), proj)
            check(f"[{top:13}] {caption} não é trancado", rc == 0, err[:200])


def test_message_names_bucket_and_exit():
    """The message says which bucket failed and what the legitimate path is.

    The disposable worktree recipe appears only for the proof-reviewer
    (fb-20261013-3): the other agents are sent to ordem/proof-reviewer.
    """
    for hook in HOOKS:
        top = hook.parent.parent.name
        agent, lane_in, lane_out = LANES[top]
        proj = Path(tempfile.mkdtemp(prefix="bpl-proj-")).resolve()
        rc, err = run(hook, f"{plugin_of(hook)}:{agent}",
                      WEGO_1936.replace("{OUT}", lane_out), proj)
        check(f"[{top:13}] deny do interpretador nomeia o balde 4",
              rc == 2 and "balde 4" in err, err[:300])
        check(f"[{top:13}] deny da pista NÃO ensina worktree descartável",
              "git worktree add" not in err and "mktemp" not in err, err[:600])
        check(f"[{top:13}] deny da pista nomeia o proof-reviewer como dono da prova",
              "proof-reviewer" in err, err[:600])
        rc_p, err_p = run(hook, f"{plugin_of(hook)}:proof-reviewer",
                          WEGO_1936.replace("{OUT}", lane_out), proj)
        check(f"[{top:13}] deny do proof-reviewer ensina worktree descartável",
              rc_p == 2 and "git worktree add" in err_p and "mktemp" in err_p,
              err_p[:600])
        check(f"[{top:13}] deny aponta Write/Edit", "Write" in err and "Edit" in err,
              err[:600])
        # git worktree add INSIDE the root: the reason also teaches the recipe only to the proof-reviewer
        cmd_wt = "git worktree add wt-interno HEAD"
        rc, err = run(hook, f"{plugin_of(hook)}:{agent}", cmd_wt, proj)
        check(f"[{top:13}] worktree add dentro da raiz: pista não recebe a receita",
              rc == 2 and "mktemp" not in err and "proof-reviewer" in err
              and "ORDEM" in err, err[:600])
        rc_p, err_p = run(hook, f"{plugin_of(hook)}:proof-reviewer", cmd_wt, proj)
        check(f"[{top:13}] worktree add dentro da raiz: proof-reviewer recebe a receita",
              rc_p == 2 and "mktemp" in err_p and "crie fora" in err_p, err_p[:600])
        rc, err = run(hook, f"{plugin_of(hook)}:{agent}", f"cp x {lane_out}", proj)
        check(f"[{top:13}] deny de escrita fora da pista nomeia o balde 1",
              rc == 2 and "balde 1" in err and lane_out in err, err[:300])


def test_shadow_mode_and_telemetry():
    """CEPA_BASHLOCK_ENFORCE=0 releases bucket 4, but records what it would deny.

    And the real deny also becomes an event in the ledger — the silent failure of the
    log in /tmp that nobody read is what this item exists to kill.
    """
    for hook in HOOKS:
        top = hook.parent.parent.name
        agent, lane_in, lane_out = LANES[top]
        at = f"{plugin_of(hook)}:{agent}"
        proj = Path(tempfile.mkdtemp(prefix="bpl-proj-")).resolve()
        tdir = Path(tempfile.mkdtemp(prefix="bpl-tel-"))
        env = {"CEPA_TELEMETRY_DIR": str(tdir)}

        def events():
            out = []
            for f in tdir.glob("events-*.jsonl"):
                out += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
            return out

        rc, _ = run(hook, at, WEGO_1936.replace("{OUT}", lane_out), proj,
                    {**env, "CEPA_BASHLOCK_ENFORCE": "0"})
        check(f"[{top:13}] modo sombra libera o balde 4", rc == 0)
        ev = [e for e in events() if e.get("event") == "bash_pathlock_would_deny"]
        check(f"[{top:13}] modo sombra grava bash_pathlock_would_deny",
              len(ev) == 1 and ev[0].get("bucket") == 4 and ev[0].get("agent") == agent,
              str(events())[:300])

        rc, _ = run(hook, at, f"cp x {lane_out}", proj,
                    {**env, "CEPA_BASHLOCK_ENFORCE": "0"})
        check(f"[{top:13}] modo sombra NÃO afrouxa o balde 1", rc == 2)

        rc, _ = run(hook, at, WEGO_1936.replace("{OUT}", lane_out), proj, env)
        ev = [e for e in events() if e.get("event") == "bash_pathlock_deny"]
        check(f"[{top:13}] deny grava bash_pathlock_deny no ledger",
              rc == 2 and any(e.get("bucket") == 4 and e.get("verb") == "python3"
                              for e in ev), str(ev)[:300])

        tmp = Path(tempfile.mkdtemp(prefix="bpl-wt-")).resolve()
        rc, _ = run(hook, at, f"git worktree add --detach {tmp}/red HEAD", proj, env)
        ev = [e for e in events() if e.get("event") == "perturb_worktree_created"]
        check(f"[{top:13}] worktree de perturbação vira evento contável",
              rc == 0 and len(ev) == 1, str(events())[-300:])


def test_hint_unresolved_directory():
    """Disposable worktree in two calls: the denial says why and what to use.

    Case of 2026-09-26: the proof agent creates the worktree in one call and uses
    `cd "$WT" && git checkout ...` in the next. The lock reads each call
    alone; `$WT` has no value, the `cd` counts as "still at the root" and the
    revert is denied. The old message only said "write outside your lane",
    and the agents got around it with python3 -c (the WEGO-1936 vector). The denial
    stays (the lock cannot guess the destination); what changes is that it
    names the variable and offers a literal path or `git -C`, which pass.

    Perturbation: remove the call to `_dica_dir_desconhecido` from `_build_message` in the
    template and regenerate; the "names the variable" cases turn red.
    """
    var = "$CEPA_WT_NAO_EXISTE"
    for hook in HOOKS:
        top = hook.parent.parent.name
        agent, _lane_in, lane_out = LANES[top]
        at = f"{plugin_of(hook)}:{agent}"
        proj = Path(tempfile.mkdtemp(prefix="bpl-proj-")).resolve()
        tmp = Path(tempfile.mkdtemp(prefix="bpl-wt-")).resolve()
        for caption, cmd in (
                ("cd \"$VAR\" && git checkout",
                 f'cd "{var}" && git checkout HEAD~1 -- {lane_out}'),
                ("git -C \"$VAR\" checkout",
                 f'git -C "{var}" checkout HEAD~1 -- {lane_out}')):
            rc, err = run(hook, at, cmd, proj)
            check(f"[{top:13}] {caption}: continua negado", rc == 2, err[:200])
            check(f"[{top:13}] {caption}: nomeia a variável e a causa",
                  f"{var} não tem valor" in err and "Cada chamada do Bash" in err,
                  err[:600])
            check(f"[{top:13}] {caption}: sugere caminho literal e git -C",
                  "caminho LITERAL" in err and "git -C /tmp/" in err, err[:600])
        for caption, cmd in (
                ("cd <literal> && git checkout",
                 f"cd {tmp}/red && git checkout HEAD~1 -- {lane_out}"),
                ("git -C <literal> checkout",
                 f"git -C {tmp}/red checkout HEAD~1 -- {lane_out}"),
                ("variável definida na MESMA chamada",
                 f"WT={tmp}/red; cd \"$WT\" && git checkout HEAD~1 -- {lane_out}")):
            rc, err = run(hook, at, cmd, proj)
            check(f"[{top:13}] {caption}: liberado", rc == 0, err[:300])
        rc, err = run(hook, at, f"cp x {lane_out}", proj)
        check(f"[{top:13}] negação sem variável não ganha a dica",
              rc == 2 and "não tem valor" not in err, err[:400])


def test_proof_agents_address_worktree_by_literal_path():
    """The two proof agents say to use a literal path or git -C.

    The hook only explains after denying; the agent's text avoids the denial.
    Without this rule in the agent, each proof run bumps into the lock once
    before getting it right, and it is in that bump that python3 -c shows up.
    """
    for rel in ("build-hex/agents/proof-reviewer.md",
                "common/agents/ui-proof-reviewer.md"):
        txt = (REPO / rel).read_text(encoding="utf-8")
        check(f"{rel} manda endereçar a worktree pelo caminho literal",
              "by its literal path" in txt and "`git -C /tmp/" in txt
              and "python3 -c" in txt)


def test_script_on_the_disposable_copy():
    """python3 script run from INSIDE the disposable worktree passes (bucket 3).

    Found in run 2026-09-28-0558: the proof-reviewer, path-locked, creates the disposable
    copy with `git worktree add /tmp/proof-<KEY> <commit>` and was denied
    when running the test from inside it. Two of the real forms that fell into
    bucket 4 ("script outside the project"):

      cd /tmp/proof-agb-head && ls tests/ | grep -i gate_status; \\
        timeout 120 python3 tests/test_gate_status_by_name.py; echo "EXIT=$?"

      python3 /tmp/proof-vigia-solo/tests/test_no_background_build.py 2>&1 \\
        | grep -A5 ...

    What distinguishes the legitimate case is the script living inside a
    REGISTERED worktree of this repo (`git worktree list --porcelain`), not in any
    /tmp: a loose script outside the root and outside any worktree stays
    denied (pinned in DENY above, "script in /tmp run by sh").
    """
    for hook in HOOKS:
        top = hook.parent.parent.name
        agent, _lane_in, lane_out = LANES[top]
        at = f"{plugin_of(hook)}:{agent}"
        proj = Path(tempfile.mkdtemp(prefix="bpl-proj-")).resolve()
        outside = Path(tempfile.mkdtemp(prefix="bpl-wtreg-")).resolve()
        wt = outside / "proof-x"
        loose = outside / "solto"
        loose.mkdir()
        (loose / "x.sh").write_text("#!/bin/sh\necho hi\n")

        def git(*args):
            subprocess.run(["git", "-C", str(proj), *args], check=True,
                            capture_output=True, text=True)

        git("init", "-q")
        git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
            "--allow-empty", "-m", "init")
        # "harness/", not "tests/": in build-team the qa-engineer's lane IS
        # "tests/**" — a script in there would fall into the "own lane" deny
        # (pinned in DENY: "script INSIDE the own lane"), masking the
        # case this test proves.
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
                check(f"[{top:13}] libera: {label}", rc == 0, err[:300])

            rc, err = run(hook, at, f"python3 {wt}/harness/t.py {proj}/{lane_out}", proj)
            check(f"[{top:13}] nega: script na cópia citando a raiz (paridade balde 3)",
                  rc == 2 and "erro interno" not in err, err[:300])

            rc, err = run(hook, at, f"sh {loose}/x.sh", proj)
            check(f"[{top:13}] nega: script fora da raiz e fora de worktree registrado",
                  rc == 2 and "erro interno" not in err, err[:300])

            git("worktree", "remove", "--force", str(wt))
            rc, err = run(hook, at, f"python3 {wt}/harness/t.py", proj)
            check(f"[{top:13}] nega: worktree removido do registro (perturbação)",
                  rc == 2 and "erro interno" not in err, err[:300])
        finally:
            subprocess.run(["git", "-C", str(proj), "worktree", "remove", "--force", str(wt)],
                           capture_output=True, text=True)


def main():
    if not HOOKS:
        print("FAIL: nenhum */hooks/bash-path-lock.py em", REPO)
        return 1
    test_plugin_name_comes_from_the_path()
    test_buckets()
    test_out_of_scope_remains_free()
    test_message_names_bucket_and_exit()
    test_hint_unresolved_directory()
    test_proof_agents_address_worktree_by_literal_path()
    test_shadow_mode_and_telemetry()
    test_script_on_the_disposable_copy()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} falha(s) em {len(HOOKS)} cópias")
        return 1
    print(f"tudo verde em {len(HOOKS)} cópias")
    return 0


if __name__ == "__main__":
    sys.exit(main())
