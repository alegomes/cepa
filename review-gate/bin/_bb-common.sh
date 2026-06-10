#!/usr/bin/env bash
# _bb-common.sh — shared Bitbucket transport helpers, SOURCED by open-pr.sh and
# merge-pr.sh. Single source of truth for the two host-specific bits, so the two
# scripts can never drift: a drift here = open-pr authenticates while merge-pr
# 401s at the most irreversible step. Keep ALL Bitbucket-host knowledge in here.
#
# Not executable on its own — it only defines functions.

# resolve_slug — set WORKSPACE and REPO from the origin remote (SSH or HTTPS).
# Exits 2 with a friendly message if the remote isn't a bitbucket.org repo.
resolve_slug() {
  local origin slug
  origin="$(git remote get-url origin)"
  slug="$(printf '%s' "$origin" | sed -E 's#^(git@bitbucket.org:|https://[^/]*bitbucket.org/)##; s#\.git$##')"
  WORKSPACE="${slug%%/*}"
  REPO="${slug#*/}"
  if [[ -z "$WORKSPACE" || -z "$REPO" || "$WORKSPACE" == "$slug" ]]; then
    echo "erro: não consegui resolver workspace/repo de '$origin'" >&2
    exit 2
  fi
}

# select_auth — set the AUTH_ARGS array from ~/.netrc.
# login=x-token-auth -> Access Token -> Bearer (Basic gives 401 on the REST API).
# any other login   -> App Password -> Basic via curl -n.
# NOTE (known limit): the awk reads login/password on SEPARATE lines under the
# `machine api.bitbucket.org` block — the multi-line .netrc form documented in
# open-pr.sh. A single-line entry is not parsed; use the multi-line form.
select_auth() {
  local login token
  login="$(awk '/^[[:space:]]*machine[[:space:]]+api.bitbucket.org/{b=1;next} b&&/login/{print $2;exit}' "$HOME/.netrc")"
  if [[ "$login" == "x-token-auth" ]]; then
    token="$(awk '/^[[:space:]]*machine[[:space:]]+api.bitbucket.org/{b=1;next} b&&/password/{print $2;exit}' "$HOME/.netrc")"
    AUTH_ARGS=(-H "Authorization: Bearer ${token}")
  else
    AUTH_ARGS=(-n)
  fi
}
