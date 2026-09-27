#!/usr/bin/env bash
# Roteiro ao vivo contra o herdr instalado: uma onda de brinquedo com duas
# slices (A aterrissada, B que falhou), cada uma com worktree + Space criados
# pela mesma receita do passo 6a do /maestro:run, e o maestro-prune do passo 9.
# Esperado: o Space e a worktree de A somem; os de B ficam. Roda de qualquer
# diretório — o repo da onda fica em /tmp e NÃO é o Space em foco, que é o caso
# que a primeira versão do prune errava.
set -u
PRUNE="$(cd "$(dirname "$0")/../../.." && pwd)/maestro/bin/maestro-prune"
J(){ python3 -c "import json,sys;d=json.load(sys.stdin)['result'];print(eval(sys.argv[1]))" "$1"; }
spaces(){ herdr workspace list | J "sorted(w['label'] for w in d['workspaces'])"; }
R=$(mktemp -d /tmp/herdr-space-e2e.XXXX); git -C "$R" init -q -b main; git -C "$R" commit -q --allow-empty -m init
for s in A B; do herdr worktree create --cwd "$R" --branch "s/$s" --base main --no-focus --trust-repository --json > "$R/.c$s.json"; done
PA=$(J "d['worktree']['path']" < "$R/.cA.json"); WA=$(J "d['workspace']['workspace_id']" < "$R/.cA.json")
PB=$(J "d['worktree']['path']" < "$R/.cB.json"); WB=$(J "d['workspace']['workspace_id']" < "$R/.cB.json")
mkdir -p "$R/prog"; printf 'wave: 1\nslices:\n  A: {status: LANDED, worktree: %s}\n  B: {status: FAIL, worktree: %s}\nlanded: [A]\n' "$PA" "$PB" > "$R/prog/wave-state.yaml"
echo "em foco: $(herdr workspace list | J "[w['label'] for w in d['workspaces'] if w['focused']]")"
echo "Spaces antes:  $(spaces)"
python3 "$PRUNE" "$R/prog" --repo "$R"; echo "prune exit=$?"
echo "Spaces depois: $(spaces)"
echo "Space de A ($WA) existe? $(herdr workspace get "$WA" >/dev/null 2>&1 && echo sim || echo nao)"
echo "Space de B ($WB) existe? $(herdr workspace get "$WB" >/dev/null 2>&1 && echo sim || echo nao)"
echo "git worktree list:"; git -C "$R" worktree list | sed "s|$R|<repo>|; s|$HOME|~|"
# limpeza: B e o Space do clone de brinquedo
herdr worktree remove --workspace "$WB" --trust-repository >/dev/null
SRC=$(herdr workspace list | J "[w['workspace_id'] for w in d['workspaces'] if w['label']=='$(basename "$R")']")
for w in $(echo "$SRC" | tr -d "[]',"); do herdr workspace close "$w" >/dev/null; done
rm -rf "$R" "$HOME/.herdr/worktrees/$(basename "$R")"
echo "Spaces após limpeza: $(spaces)"
