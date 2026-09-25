import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "common", "hooks"))
import _jiramut as J

def bash(cmd): return {"tool_name":"Bash","tool_input":{"command":cmd}}
def mcp(n,ti): return {"tool_name":n,"tool_input":ti}

CASES = [
 # (descricao, payload, esperado: None|"pass"|"opaque", kind)
 ("MCP transition (regressao)", mcp("mcp__claude_ai_Atlassian__transitionJiraIssue",{"issueIdOrKey":"W-1","transition":{"id":"31"}}), "pass","transition"),
 ("MCP comment (regressao)", mcp("mcp__mcp-atlassian__jira_add_comment",{"issue_key":"W-1","comment":"x"}), "pass","comment"),
 ("Write nao relacionado", {"tool_name":"Write","tool_input":{"file_path":"/a"}}, None,None),
 ("bash sem twg", bash("git status"), None,None),

 # --- o furo C1 que 5 lentes apontaram ---
 ("twg api POST cria card", bash("twg api jira:/rest/api/3/issue -X POST --input p.json"), "opaque","mutation"),
 ("twg api POST graphql", bash("twg api graphql -X POST -f query=@m.gql"), "opaque","mutation"),
 ("twg api GET e leitura", bash("twg api jira:/rest/api/3/myself"), None,None),

 # --- transicao via CLI ---
 ("twg transition por id", bash("twg jira workitem transition --id WEGO-1 --transition-id 31"), "pass","transition"),
 ("twg transition por NOME", bash("twg jira workitem transition --id WEGO-1 --transition-id Done"), "pass","transition"),
 ("twg transition descoberta (read-only)", bash("twg jira workitem transition --id WEGO-1"), None,None),

 # --- comentario via CLI ---
 ("twg comment create", bash("twg jira workitem comment create --issue-id WEGO-1 --body 'texto'"), "pass","comment"),
 ("twg comment sem body (opaco)", bash("twg jira workitem comment create --issue-id WEGO-1 --body-format markdown"), "opaque","comment"),

 # --- leituras nao podem ser barradas ---
 ("twg query", bash("twg jira workitem query 'project = WEGO' -o json"), None,None),
 ("twg get", bash("twg jira workitem get WEGO-1"), None,None),
 ("twg bulk-get", bash("twg jira workitem bulk-get WEGO-1 WEGO-2"), None,None),

 # --- evasao ---
 ("encadeado com &&", bash("cd /tmp && twg jira workitem transition --id WEGO-1 --transition-id 31"), "pass","transition"),
 ("escondido apos ; ainda e achado", bash("echo oi; twg jira workitem create --summary x"), "pass","create"),
 ("caminho absoluto", bash("/Users/alegomes/.local/bin/twg jira workitem delete WEGO-1"), "opaque","mutation"),
 ("com env var na frente", bash("TWG_AGENT_DEFAULTS=1 twg jira workitem update --id WEGO-1 --summary x"), "pass","edit"),
 ("flag com = em vez de espaco", bash("twg jira workitem transition --id=WEGO-1 --transition-id=31"), "pass","transition"),
 ("bulk-transition (verbo novo)", bash("twg jira workitem bulk-transition --jql 'project=WEGO'"), "opaque","mutation"),
 ("archive", bash("twg jira workitem archive --id WEGO-1"), "opaque","mutation"),
 ("outro produto nao e deste gate", bash("twg confluence content create --title x"), None,None),
 ("aspas nao fechadas", bash("twg jira workitem comment create --body 'aberta"), "opaque","mutation"),
 # --- O3 (2026-09-24): escrita legivel que nao transiciona nem comenta ---
 ("create legivel", bash("twg jira workitem create --space WEGO --type Task --summary x"), "pass","create"),
 ("update de campo legivel", bash("twg jira workitem update --id WEGO-1 --add-labels a"), "pass","edit"),
 ("link entre cards", bash("twg jira workitem link workitem --id WEGO-1 --target-id WEGO-2 --link-type-id 10003"), "pass","link"),
 ("update --status transiciona por fora", bash("twg jira workitem update --id WEGO-1 --status Done"), "opaque","mutation"),
 ("update --comment comenta por fora", bash("twg jira workitem update --id WEGO-1 --comment ok"), "opaque","mutation"),
 ("update --field nomeia um campo so", bash("twg jira workitem update --id WEGO-1 --field 'customfield_10020=3'"), "pass","edit"),
 ("update --variables-json e JSON livre", bash("twg jira workitem update --id WEGO-1 --variables-json '{}'"), "opaque","mutation"),
 ("update --fields-json e JSON livre", bash("twg jira workitem update --id WEGO-1 --fields-json '{}'"), "opaque","mutation"),
 ("update --resolution fecha por fora", bash("twg jira workitem update --id WEGO-1 --resolution Done"), "opaque","mutation"),
 ("link para commit segue opaco", bash("twg jira workitem link commit --id WEGO-1 --url x"), "opaque","mutation"),
 # --- leituras de terceiro nivel e ajuda ---
 ("link query e leitura", bash("twg jira workitem link query --issue-id WEGO-1"), None,None),
 ("create-metadata e leitura", bash("twg jira workitem field create-metadata --space WEGO --type Task"), None,None),
 ("comment query e leitura", bash("twg jira workitem comment query --issue-id WEGO-1"), None,None),
 ("--help nao e escrita", bash("twg jira workitem create --help"), None,None),
 ("-h nao e escrita", bash("twg jira workitem update -h"), None,None),
 # o falso-positivo historico do repo
 (">= nao pode virar redirect", bash("twg jira workitem query 'sp >= 3' -o json"), None,None),
]

fail=0
for desc, payload, exp, kind in CASES:
    m = J.classify(payload)
    if exp is None:
        got = None if m is None else ("opaque" if m["opaque"] else "pass")
    else:
        got = None if m is None else ("opaque" if m["opaque"] else "pass")
    ok = (got == exp) and (m is None or kind is None or m["kind"]==kind)
    if not ok:
        fail+=1
        print(f"  FALHOU: {desc}\n     esperado={exp}/{kind}  obtido={got}/{m and m['kind']}")
    else:
        print(f"  ok  [{str(exp or 'ignora'):6}] {desc}")
print(f"\n{len(CASES)-fail}/{len(CASES)} passaram")

# --- Bitbucket: quem pode decidir o destino de um PR ---
BB = [
 ("dev aprova proprio PR",        "build-hex:domain-dev",            "twg bitbucket pull-requests approve 42",        2),
 ("dev mergeia",                  "build-hex:domain-dev",            "twg bitbucket pull-requests merge --id 42",     2),
 ("dev recusa",                   "build-team:backend-dev",          "twg bitbucket pull-requests decline 42",        2),
 ("alias bb/pr escondido apos ;", "build-hex:domain-dev",            "echo oi; twg bb pr approve 42",                 2),
 ("bitbucket-expert aprova",      "review-gate:bitbucket-expert",    "twg bitbucket pull-requests approve 42",        0),
 ("dev le o diff",                "build-hex:domain-dev",            "twg bitbucket pull-requests diff 42",           0),
 ("dev consulta PRs",             "build-hex:domain-dev",            "twg bitbucket pull-requests query --state OPEN",0),
 ("sessao principal (humano)",    "",                                "twg bitbucket pull-requests merge --id 42",     0),
 ("embutido sem prefixo aprova",  "general-purpose",                 "twg bitbucket pull-requests approve 42",        2),
 ("embutido sem prefixo mergeia", "Explore",                         "twg bitbucket pull-requests merge --id 42",     2),
 ("comentar nao e decidir",       "build-hex:domain-dev",            "twg bitbucket pull-requests comment create 42 --content x", 0),
 ("sem twg",                      "build-hex:domain-dev",            "git log",                                       0),
]
import subprocess, json as _json
HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "common", "hooks", "bitbucket-decision-lock.py")
bfail = 0
print("\n--- bitbucket-decision-lock ---")
for desc, agent, cmd, want in BB:
    _b = {"tool_name": "Bash", "tool_input": {"command": cmd}}
    if agent:
        _b["agent_type"] = agent
    payload = _json.dumps(_b)
    rc = subprocess.run([sys.executable, HOOK], input=payload, capture_output=True,
                        text=True).returncode
    if rc != want:
        bfail += 1; print(f"  FALHOU: {desc} — esperado exit={want}, obtido {rc}")
    else:
        print(f"  ok  [exit {want}] {desc}")
print(f"{len(BB)-bfail}/{len(BB)} passaram")

# --- jira-write-lock: so o atlassian-expert escreve no Jira pela twg (O3) ---
JW = [
 ("dev cria card",                "build-hex:domain-dev",       "twg jira workitem create --space WEGO --type Task --summary x", 2),
 ("dev transiciona",              "build-team:backend-dev",     "twg jira workitem transition --id WEGO-1 --transition-id 31",   2),
 ("dev comenta",                  "build-hex:domain-dev",       "twg jira workitem comment create --issue-id WEGO-1 --body x",   2),
 ("embutido sem prefixo edita",   "general-purpose",            "twg jira workitem update --id WEGO-1 --summary x",              2),
 ("dev por twg api POST",         "build-hex:domain-dev",       "twg api jira:/rest/api/3/issue -X POST --input p.json",         2),
 ("dev le o card",                "build-hex:domain-dev",       "twg jira workitem get WEGO-1",                                  0),
 ("dev consulta transicoes",      "build-hex:domain-dev",       "twg jira workitem transition --id WEGO-1",                      0),
 ("atlassian-expert cria",        "board-flow:atlassian-expert","twg jira workitem create --space WEGO --type Task --summary x", 0),
 ("atlassian-expert transiciona", "board-flow:atlassian-expert","twg jira workitem transition --id WEGO-1 --transition-id 31",   0),
 ("sessao principal (humano)",    "",                           "twg jira workitem create --space WEGO --type Task --summary x", 0),
 ("sem twg",                      "build-hex:domain-dev",       "git status",                                                    0),
]
JHOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "common", "hooks", "jira-write-lock.py")
jfail = 0
print("\n--- jira-write-lock ---")
for desc, agent, cmd, want in JW:
    body = {"tool_name": "Bash", "tool_input": {"command": cmd}}
    if agent:
        body["agent_type"] = agent
    rc = subprocess.run([sys.executable, JHOOK], input=_json.dumps(body),
                        capture_output=True, text=True).returncode
    if rc != want:
        jfail += 1; print(f"  FALHOU: {desc} — esperado exit={want}, obtido {rc}")
    else:
        print(f"  ok  [exit {want}] {desc}")
print(f"{len(JW)-jfail}/{len(JW)} passaram")

# --- registro: hook que existe mas nao esta no plugin.json nunca roda ---
# A prova de 2026-09-24 (docs/proof/TWG-O0-O3.yaml) apagou a entrada do
# jira-write-lock no plugin.json e nenhum teste ficou vermelho: todos chamam o
# script direto. Estes hooks precisam estar no PreToolUse de matcher Bash, que e
# por onde a twg chega.
PLUGIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "common", ".claude-plugin", "plugin.json")
_pre = _json.load(open(PLUGIN, encoding="utf-8"))["hooks"]["PreToolUse"]
_bash = [h["command"] for e in _pre if e.get("matcher") == "Bash" for h in e["hooks"]]
rfail = 0
print("\n--- registro no plugin.json (PreToolUse, matcher Bash) ---")
for nome in ("jira-write-lock.py", "bitbucket-decision-lock.py", "acceptance-gate.py",
             "merge-truth-gate.py", "summary-nulls-gate.py", "bounce-reason-gate.py"):
    if any(c.endswith(f'/hooks/{nome}"') for c in _bash):
        print(f"  ok  {nome}")
    else:
        rfail += 1; print(f"  FALHOU: {nome} nao esta registrado no matcher Bash")

# --- os quatro gates, rodados como processo, com comando twg (altitude do AC5) ---
# O loop CASES prova o classify; isto prova que cada gate de verdade usa a
# classificacao: escrita legivel e leitura passam, escrita opaca e barrada.
import tempfile
GATES = ("acceptance-gate.py", "merge-truth-gate.py", "summary-nulls-gate.py",
         "bounce-reason-gate.py")
GCASOS = [
 ("create legivel passa",           "twg jira workitem create --space WEGO --type Task --summary x", 0),
 ("update de campo passa",          "twg jira workitem update --id WEGO-1 --add-labels a",           0),
 ("link entre cards passa",         "twg jira workitem link workitem --id WEGO-1 --target-id WEGO-2", 0),
 ("--help passa",                   "twg jira workitem create --help",                              0),
 ("comment query passa",            "twg jira workitem comment query --issue-id WEGO-1",            0),
 ("update --status e barrado",      "twg jira workitem update --id WEGO-1 --status Done",           2),
 ("update --comment e barrado",     "twg jira workitem update --id WEGO-1 --comment ok",            2),
 ("update --fields-json e barrado", "twg jira workitem update --id WEGO-1 --fields-json '{}'",      2),
]
HOOKS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "common", "hooks")
gfail = 0
print("\n--- quatro gates como processo, com twg ---")
with tempfile.TemporaryDirectory() as cwd:
    for gate in GATES:
        for desc, cmd, want in GCASOS:
            body = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": cwd,
                    "agent_type": "board-flow:atlassian-expert"}
            rc = subprocess.run([sys.executable, os.path.join(HOOKS, gate)],
                                input=_json.dumps(body), capture_output=True,
                                text=True, cwd=cwd).returncode
            if rc != want:
                gfail += 1; print(f"  FALHOU: {gate}: {desc} — esperado exit={want}, obtido {rc}")
            else:
                print(f"  ok  [exit {want}] {gate}: {desc}")
print(f"{len(GATES)*len(GCASOS)-gfail}/{len(GATES)*len(GCASOS)} passaram")
sys.exit(1 if (fail or bfail or jfail or rfail or gfail) else 0)
