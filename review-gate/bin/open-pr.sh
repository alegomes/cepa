#!/usr/bin/env bash
# bin/open-pr.sh — abre um Pull Request no Bitbucket Cloud via REST API.
#
# Bundled with the review-gate plugin. Invoked by the bitbucket-expert agent as
# ${CLAUDE_PLUGIN_ROOT}/bin/open-pr.sh. Runs against the host repo's working
# directory (resolves origin + branch from the cwd's git repo), so one copy
# serves every repo — no per-repo duplication.
#
# Auth: lê a credencial de ~/.netrc (machine api.bitbucket.org). O segredo nunca
# aparece na linha de comando nem nos logs. Dois formatos suportados:
#
#   - Repository/Workspace Access Token (recomendado) — login `x-token-auth`:
#     a REST API exige header `Authorization: Bearer <token>` (Basic dá 401),
#     então este script manda Bearer quando o login é x-token-auth.
#
#         machine api.bitbucket.org
#           login x-token-auth
#           password <token>     # escopo: pullrequest:write + repository:read
#
#   - App Password — login = seu username Bitbucket: usa Basic via `curl -n`.
#
#         machine api.bitbucket.org
#           login <username>
#           password <app-password>   # scope: Pull requests:Write, Repositories:Read
#
#   chmod 600 ~/.netrc
#
# Workspace/repo são resolvidos do remote `origin`. Source = branch atual por
# padrão; destino = main por padrão.
#
# Uso:
#   bin/open-pr.sh -t "WEGO-1234: título" [-b "corpo markdown"] [-s source-branch] [-d dest-branch] [--no-close]
#   bin/open-pr.sh -t "..." -B caminho/para/corpo.md     # corpo de arquivo
#
# Saída: imprime o link do PR (e o id) em caso de sucesso; sai != 0 em erro.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_bb-common.sh"

DEST="main"
SOURCE=""   # resolved to the current branch after arg-parse (see below)
TITLE=""
BODY=""
CLOSE_SOURCE="true"

usage() { sed -n '2,35p' "$0"; exit "${1:-0}"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    -t|--title)   TITLE="$2"; shift 2 ;;
    -b|--body)    BODY="$2"; shift 2 ;;
    -B|--body-file) BODY="$(cat "$2")"; shift 2 ;;
    -s|--source)  SOURCE="$2"; shift 2 ;;
    -d|--dest)    DEST="$2"; shift 2 ;;
    --no-close)   CLOSE_SOURCE="false"; shift ;;
    -h|--help)    usage 0 ;;
    *) echo "argumento desconhecido: $1" >&2; usage 1 ;;
  esac
done

[[ -n "$TITLE" ]] || { echo "erro: -t/--title é obrigatório" >&2; usage 1; }
[[ -f "$HOME/.netrc" ]] || { echo "erro: ~/.netrc ausente — veja o cabeçalho deste script" >&2; exit 2; }

# Source defaults to the current branch — resolved here (not at top level) so
# `--help` and the friendly error paths work even outside a git repo.
SOURCE="${SOURCE:-$(git rev-parse --abbrev-ref HEAD)}"

resolve_slug   # sets WORKSPACE, REPO (from _bb-common.sh)
API="https://api.bitbucket.org/2.0/repositories/${WORKSPACE}/${REPO}/pullrequests"

select_auth    # sets AUTH_ARGS (from _bb-common.sh)

# Monta o JSON com python3 (escapa título/corpo com segurança).
PAYLOAD="$(SOURCE="$SOURCE" DEST="$DEST" TITLE="$TITLE" BODY="$BODY" CLOSE_SOURCE="$CLOSE_SOURCE" python3 - <<'PY'
import json, os
print(json.dumps({
    "title": os.environ["TITLE"],
    "description": os.environ.get("BODY", ""),
    "source": {"branch": {"name": os.environ["SOURCE"]}},
    "destination": {"branch": {"name": os.environ["DEST"]}},
    "close_source_branch": os.environ["CLOSE_SOURCE"] == "true",
}))
PY
)"

echo ">> abrindo PR: ${SOURCE} -> ${DEST}  em ${WORKSPACE}/${REPO}" >&2

RESP="$(curl -sS "${AUTH_ARGS[@]}" -X POST "$API" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  -w $'\n%{http_code}')"

CODE="$(printf '%s' "$RESP" | tail -1)"
BODY_RESP="$(printf '%s' "$RESP" | sed '$d')"

if [[ "$CODE" == "201" ]]; then
  printf '%s' "$BODY_RESP" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("PR #%s criado: %s" % (d["id"], d["links"]["html"]["href"]))'
  exit 0
fi

# 400 com "duplicate" geralmente = PR já existe para esse source->dest.
echo "erro: API retornou HTTP $CODE" >&2
printf '%s\n' "$BODY_RESP" | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin); print(json.dumps(d.get("error", d), indent=2, ensure_ascii=False), file=sys.stderr)
except Exception:
    print(sys.stdin.read(), file=sys.stderr)' || true
exit 1
