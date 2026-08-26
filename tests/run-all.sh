#!/usr/bin/env bash
#
# Roda TODA a suíte do cepa e diz, no fim, quantos arquivos rodaram.
#
#     tests/run-all.sh              # tudo
#     tests/run-all.sh drift proof  # só os arquivos cujo nome casa um dos termos
#     PYTHON=python3.12 tests/run-all.sh
#
# ## Por que este arquivo existe
#
# Os testes do repo vêm em duas famílias, e elas se rodam de maneiras
# diferentes:
#
#   - **script** — a maioria. `python3 tests/test_x.py` imprime `ok`/`FAIL` por
#     caso e sai não-zero em falha. Não precisa de nada instalado.
#   - **pytest** — os que fazem `import pytest` (hoje test_needs_human_motivos e
#     test_waivers). Sem o pytest instalado eles não rodam.
#
# O modo de falha que este runner existe para matar: sem o pytest, os arquivos
# da segunda família não davam erro — eles simplesmente sumiam de qualquer
# varredura, e um `for t in tests/test_*.py; do python3 "$t"; done` terminava
# parecendo verde. Em 22/08/2026 isso escondia quatro expectativas erradas em
# test_needs_human_motivos, que por sua vez faziam o classificador de motivos
# esconder quatro cards com achado de L4 da fila do /board-flow:decide. Falha
# silenciosa em cima de falha silenciosa.
#
# Então: **pytest ausente é ERRO, nunca skip.** O runner sai não-zero nomeando
# os arquivos que ficariam sem rodar e o comando que instala. Se um dia você
# quiser mesmo rodar só a primeira família, diga isso em voz alta com
# SKIP_PYTEST=1 — e o resumo final registra o que ficou de fora.

set -uo pipefail

cd "$(dirname "$0")/.." || exit 2
PYTHON="${PYTHON:-python3}"

# ── telemetria da suíte não entra no seu ledger ───────────────────────────
# Os hooks gravam eventos em ~/.claude/cepa-telemetry/, e esta suíte executa os
# hooks. Sem isto, um `run-all.sh` inventa repos ("main-repo", "r3", "sem-git")
# no relatório do /common:metrics e desloca as conclusões dele — foi o que
# aconteceu até 26/08/2026. tests/sitecustomize.py faz o mesmo para quem roda um
# teste solto; aqui é explícito para ficar à vista de quem lê o runner.
export CEPA_TELEMETRY_DIR="${CEPA_TELEMETRY_DIR:-${TMPDIR:-/tmp}/cepa-telemetry-tests}"

# ── seleção ───────────────────────────────────────────────────────────────
todos=(tests/test_*.py)
if [ "$#" -gt 0 ]; then
  selecionados=()
  for t in "${todos[@]}"; do
    for termo in "$@"; do
      case "$t" in *"$termo"*) selecionados+=("$t"); break ;; esac
    done
  done
  [ "${#selecionados[@]:-0}" -eq 0 ] && { echo "nenhum teste casa: $*"; exit 2; }
  todos=("${selecionados[@]}")
  echo "filtro: $* → ${#todos[@]} arquivo(s)"
fi

# ── separa as duas famílias ───────────────────────────────────────────────
scripts=() ; pytests=()
for t in "${todos[@]}"; do
  if grep -qE '^[[:space:]]*import pytest' "$t"; then pytests+=("$t"); else scripts+=("$t"); fi
done

# ── pytest ausente é erro, não skip ───────────────────────────────────────
tem_pytest=0
"$PYTHON" -m pytest --version >/dev/null 2>&1 && tem_pytest=1

if [ "${#pytests[@]}" -gt 0 ] && [ "$tem_pytest" -eq 0 ] && [ "${SKIP_PYTEST:-0}" != "1" ]; then
  echo
  echo "ERRO: ${#pytests[@]} arquivo(s) precisam do pytest e ele não está instalado em $PYTHON:"
  printf '  - %s\n' "${pytests[@]}"
  echo
  echo "  Instale:  $PYTHON -m pip install pytest"
  echo "  Ou rode a suíte sem eles, ASSUMINDO a lacuna:  SKIP_PYTEST=1 $0"
  echo
  echo "  Isto é erro e não skip de propósito: um teste que some sem avisar"
  echo "  deixa a suíte verde por ausência, que é pior do que vermelha."
  exit 2
fi

# ── roda ──────────────────────────────────────────────────────────────────
falhas=() ; rodados=0

echo
echo "── família script (${#scripts[@]}) ──"
# `${arr[@]+...}` é o guarda de array vazio: o bash 3.2 que vem no macOS trata
# "${arr[@]}" de um array vazio como variável não-definida sob `set -u` e aborta.
for t in ${scripts[@]+"${scripts[@]}"}; do
  saida=$("$PYTHON" "$t" 2>&1) ; rc=$?
  rodados=$((rodados + 1))
  if [ "$rc" -eq 0 ]; then
    printf '  ok    %s\n' "$t"
  else
    falhas+=("$t")
    printf 'FALHA   %s  (saída %d)\n' "$t" "$rc"
    printf '%s\n' "$saida" | grep -E '^FAIL|failure|Error|Traceback' | sed 's/^/          /' | head -12
  fi
done

pulados_pytest=0
if [ "${#pytests[@]}" -gt 0 ]; then
  if [ "$tem_pytest" -eq 1 ]; then
    echo
    echo "── família pytest (${#pytests[@]}) ──"
    saida=$("$PYTHON" -m pytest "${pytests[@]}" -q 2>&1) ; rc=$?
    rodados=$((rodados + ${#pytests[@]}))
    printf '%s\n' "$saida" | tail -3 | sed 's/^/  /'
    [ "$rc" -ne 0 ] && falhas+=("${pytests[@]}")
  else
    pulados_pytest=${#pytests[@]}
  fi
fi

# ── resumo: o que rodou E o que não rodou ─────────────────────────────────
echo
echo "─────────────────────────────────────────"
echo "arquivos rodados: $rodados de ${#todos[@]}"
if [ "$pulados_pytest" -gt 0 ]; then
  echo "NÃO rodados (SKIP_PYTEST=1, pytest ausente): $pulados_pytest"
  printf '  - %s\n' "${pytests[@]}"
fi
if [ "${#falhas[@]}" -gt 0 ]; then
  echo "com falha: ${#falhas[@]}"
  printf '  - %s\n' "${falhas[@]}"
  exit 1
fi
if [ "$pulados_pytest" -gt 0 ]; then
  echo "verde no que rodou — e a lacuna acima segue aberta."
  exit 0
fi
echo "tudo verde"
