set -u
J(){ python3 -c "import json,sys;d=json.load(sys.stdin)['result'];print(eval(sys.argv[1]))" "$1"; }
ORIG=$(herdr pane current | J "d['pane']['tab_id']")
WT=$(mktemp -d /tmp/maestro-e2e-wt.XXXX)
# aba A = onde o /maestro:run "roda"; aba B = onde o dono clica
A=$(herdr tab create --workspace "$HERDR_WORKSPACE_ID" --label e2e-A --cwd /tmp --no-focus)
A_TAB=$(echo "$A" | J "d['tab']['tab_id']"); A_PANE=$(echo "$A" | J "d['root_pane']['pane_id']")
B=$(herdr tab create --workspace "$HERDR_WORKSPACE_ID" --label e2e-B --cwd /tmp --no-focus)
B_TAB=$(echo "$B" | J "d['tab']['tab_id']")
# passo 1: captura do pane-lar, executada DE DENTRO da aba A
herdr pane run "$A_PANE" "herdr pane current > $WT/home.json"; sleep 2
HOME_PANE=$(J "d['pane']['pane_id']" < $WT/home.json); HOME_TAB=$(J "d['pane']['tab_id']" < $WT/home.json)
echo "capturado: pane=$HOME_PANE tab=$HOME_TAB (A=$A_TAB)"
# o dono clica na aba B durante o intake
herdr tab focus "$B_TAB" >/dev/null; sleep 1
echo "foco agora: $(herdr tab get $B_TAB | J "d['tab']['focused']") em B"
# passo 6c, receita do run.md (claude -p trocado por echo)
for s in s1 s2; do
  N=$(herdr pane split "$HOME_PANE" --direction right --cwd "$WT" --env MAESTRO_LINGER=1 --no-focus)
  NP=$(echo "$N" | J "d['pane']['pane_id']"); NT=$(echo "$N" | J "d['pane']['tab_id']")
  herdr pane rename "$NP" "e2e-$s" >/dev/null
  herdr pane run "$NP" "bash -c 'set -o pipefail; echo filha-$s 2>&1 | tee resultado-$s.txt; ec=\${PIPESTATUS[0]}; echo \"MAESTRO-EXIT:\$ec\" | tee -a resultado-$s.txt; sleep \"\$MAESTRO_LINGER\"'"
  echo "$s nasceu em tab=$NT"
done
sleep 3
echo "A panes=$(herdr tab get $A_TAB | J "d['tab']['pane_count']")  B panes=$(herdr tab get $B_TAB | J "d['tab']['pane_count']")  B focused=$(herdr tab get $B_TAB | J "d['tab']['focused']")"
cat $WT/resultado-s1.txt $WT/resultado-s2.txt
# fallback: aba A fechada antes do fork
herdr tab close "$A_TAB" >/dev/null
herdr pane split "$HOME_PANE" --direction right --cwd "$WT" --no-focus; echo "split_no_lar_morto exit=$?"
F=$(herdr tab create --workspace "$HERDR_WORKSPACE_ID" --label e2e-PROG --cwd "$WT" --env MAESTRO_LINGER=1 --no-focus)
F_TAB=$(echo "$F" | J "d['tab']['tab_id']"); echo "fallback: aba nova $F_TAB rotulo=$(echo "$F" | J "d['tab']['label']") focada=$(echo "$F" | J "d['tab']['focused']")"
# limpeza
herdr tab focus "$ORIG" >/dev/null; herdr tab close "$B_TAB" >/dev/null; herdr tab close "$F_TAB" >/dev/null
echo "foco devolvido a $ORIG: $(herdr tab get $ORIG | J "d['tab']['focused']")"; herdr tab list --workspace "$HERDR_WORKSPACE_ID" | J "[t['label'] for t in d['tabs']]"
