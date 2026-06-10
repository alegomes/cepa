#!/usr/bin/env bash
# bin/merge-pr.sh — mergeia um Pull Request no Bitbucket Cloud via REST API.
#
# Bundled with the review-gate plugin; sibling of open-pr.sh and shares its auth
# model (~/.netrc, Bearer for x-token-auth else Basic via curl -n) and its
# workspace/repo resolution from the origin remote. The token needs
# pullrequest:write.
#
# This is the transport behind /review-gate:merge and "auto-merge on green":
# only call it AFTER the QA gate (proof-reviewer) has returned PROVEN. The
# script does NOT gate — it merges what it's told to.
#
# Uso:
#   bin/merge-pr.sh -i <pr-id> [-m "mensagem de merge"] [--strategy merge_commit|squash|fast_forward] [--no-close]
#
# Saída: imprime o estado do PR (MERGED) em caso de sucesso; sai != 0 em erro.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_bb-common.sh"

PR_ID=""
MESSAGE=""
STRATEGY="merge_commit"
CLOSE_SOURCE="true"

usage() { sed -n '2,16p' "$0"; exit "${1:-0}"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    -i|--id)        PR_ID="$2"; shift 2 ;;
    -m|--message)   MESSAGE="$2"; shift 2 ;;
    --strategy)     STRATEGY="$2"; shift 2 ;;
    --no-close)     CLOSE_SOURCE="false"; shift ;;
    -h|--help)      usage 0 ;;
    *) echo "argumento desconhecido: $1" >&2; usage 1 ;;
  esac
done

[[ -n "$PR_ID" ]] || { echo "erro: -i/--id (id do PR) é obrigatório" >&2; usage 1; }
[[ -f "$HOME/.netrc" ]] || { echo "erro: ~/.netrc ausente — veja open-pr.sh" >&2; exit 2; }
case "$STRATEGY" in
  merge_commit|squash|fast_forward) ;;
  *) echo "erro: --strategy inválida: '$STRATEGY' (merge_commit|squash|fast_forward)" >&2; exit 2 ;;
esac

resolve_slug   # sets WORKSPACE, REPO (from _bb-common.sh)
API="https://api.bitbucket.org/2.0/repositories/${WORKSPACE}/${REPO}/pullrequests/${PR_ID}/merge"

select_auth    # sets AUTH_ARGS (from _bb-common.sh)

PAYLOAD="$(MESSAGE="$MESSAGE" STRATEGY="$STRATEGY" CLOSE_SOURCE="$CLOSE_SOURCE" python3 - <<'PY'
import json, os
body = {
    "merge_strategy": os.environ["STRATEGY"],
    "close_source_branch": os.environ["CLOSE_SOURCE"] == "true",
}
if os.environ.get("MESSAGE"):
    body["message"] = os.environ["MESSAGE"]
print(json.dumps(body))
PY
)"

echo ">> mergeando PR #${PR_ID} (${STRATEGY}) em ${WORKSPACE}/${REPO}" >&2

RESP="$(curl -sS "${AUTH_ARGS[@]}" -X POST "$API" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  -w $'\n%{http_code}')"

CODE="$(printf '%s' "$RESP" | tail -1)"
BODY_RESP="$(printf '%s' "$RESP" | sed '$d')"

# 200 = merged synchronously. 202 = large PR, Bitbucket merges ASYNCHRONOUSLY
# and returns a task link instead of the PR object — that is a SUCCESS (the
# merge was accepted), not an error. Treating 202 as failure would make an
# auto-merge caller retry and risk a double merge.
if [[ "$CODE" == "200" || "$CODE" == "202" ]]; then
  printf '%s' "$BODY_RESP" | CODE="$CODE" PR_ID="$PR_ID" python3 -c 'import json,os,sys
raw=sys.stdin.read()
try:
    d=json.loads(raw)
except Exception:
    d={}
pr=os.environ["PR_ID"]
if os.environ.get("CODE")=="202":
    # async: the body is usually a task-status object, not the merged PR.
    print("PR #%s merge ACCEPTED (async, HTTP 202) — Bitbucket is completing it." % pr)
elif "id" in d:
    print("PR #%s %s: %s" % (d["id"], d.get("state","MERGED"), d.get("links",{}).get("html",{}).get("href","")))
else:
    print("PR #%s merged (HTTP 200)." % pr)'
  exit 0
fi

# 400/409 = falha de merge (conflito, checks pendentes, já mergeado, sem permissão).
echo "erro: API retornou HTTP $CODE ao mergear PR #${PR_ID}" >&2
printf '%s\n' "$BODY_RESP" | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin); print(json.dumps(d.get("error", d), indent=2, ensure_ascii=False), file=sys.stderr)
except Exception:
    print(sys.stdin.read(), file=sys.stderr)' || true
exit 1
