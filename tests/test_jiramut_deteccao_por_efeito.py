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
 ("escondido apos ;", bash("echo oi; twg jira workitem create --summary x"), "opaque","mutation"),
 ("caminho absoluto", bash("/Users/alegomes/.local/bin/twg jira workitem delete WEGO-1"), "opaque","mutation"),
 ("com env var na frente", bash("TWG_AGENT_DEFAULTS=1 twg jira workitem update --id WEGO-1 --summary x"), "opaque","mutation"),
 ("flag com = em vez de espaco", bash("twg jira workitem transition --id=WEGO-1 --transition-id=31"), "pass","transition"),
 ("bulk-transition (verbo novo)", bash("twg jira workitem bulk-transition --jql 'project=WEGO'"), "opaque","mutation"),
 ("archive", bash("twg jira workitem archive --id WEGO-1"), "opaque","mutation"),
 ("outro produto nao e deste gate", bash("twg confluence content create --title x"), None,None),
 ("aspas nao fechadas", bash("twg jira workitem comment create --body 'aberta"), "opaque","mutation"),
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
sys.exit(1 if fail else 0)
