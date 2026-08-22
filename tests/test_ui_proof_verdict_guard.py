#!/usr/bin/env python3
"""Regressão do `common/hooks/ui-proof-verdict-guard.py`.

Sem dependências — rode com `python3 tests/test_ui_proof_verdict_guard.py`.
Sai não-zero em falha.

## O que este hook faz, e o que este arquivo prova

O `ui-proof-reviewer` grava o veredito da prova de tela num YAML. Duas coisas
podem dar errado nesse arquivo, e o hook pega as duas:

1. **O veredito mente sobre os próprios fluxos.** `verdict: proven` ao lado de
   um fluxo `skipped` / `pass-visual-only` / `fail` é um waiver que o agente se
   deu sozinho. O hook recomputa o veredito dos status e bloqueia.
2. **O veredito é gravado onde ele não sobrevive.** Até 22/08/2026 o destino
   era `.claude/proof/ui-<slug>.yaml`. Nos projetos que rodam o portão,
   `.claude/` é gitignored: o arquivo é invisível para o git e some junto com a
   worktree descartável da sessão, sem ninguém notar. O destino agora é
   `docs/proof/`, e o caminho antigo BLOQUEIA.

O segundo bloqueio mora aqui, e não no `path-lock`, por um motivo mecânico: o
`path-lock` só age sobre agente cujo prefixo de plugin bate com uma topologia
que carrega o lock, e o `ui-proof-reviewer` é um agente do `common`, que não
carrega. Este hook é o único ponto que consegue segurar o destino do gate de
tela — o que também significa que, se ele parar de reconhecer um caminho, não
fica mais rígido: fica mudo.

## Perturbação (como saber que este teste prova algo)

Troque `_LEGACY_PROOF_DIR_RE` para nunca casar, ou tire `docs` de
`_UI_PROOF_DIR_RE`, e este arquivo fica vermelho nomeando o caso.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "common" / "hooks" / "ui-proof-verdict-guard.py"
TMP = Path(tempfile.gettempdir()) / "repo"
NOVO = str(TMP / "docs" / "proof" / "ui-wego-acesso.yaml")
ANTIGO = str(TMP / ".claude" / "proof" / "ui-wego-acesso.yaml")

FAILURES = []


def artifact(verdict="proven", status="pass", perturbation="red"):
    return (
        "schema_version: 1\n"
        "slug: wego-acesso-registro\n"
        f"verdict: {verdict}\n"
        "manifest: docs/ui-proof.yaml\n"
        "flows:\n"
        "  registrar-acesso:\n"
        f"    status: {status}\n"
        "    script: docs/ui-proof/runs/registrar-acesso.spec.ts\n"
        '    run: "npx playwright test ... → OK; backend check contém o nonce"\n'
        "    perturbation:\n"
        f"      status: {perturbation}\n"
        '      run: "worktree @a47c52f, revert, re-run → FAILED — RED como exigido"\n'
    )


def run(content, file_path=NOVO):
    payload = json.dumps({
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": content},
        "cwd": str(TMP),
    })
    return subprocess.run([sys.executable, str(HOOK)], input=payload,
                          capture_output=True, text=True)


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


# ── destino: o caminho antigo bloqueia, com QUALQUER veredito ──────────────
for v in ("proven", "unproven", "needs-human"):
    r = run(artifact(verdict=v), file_path=ANTIGO)
    check(f"veredito {v} em .claude/proof → BLOQUEIA (destino)", r.returncode == 2,
          f"rc={r.returncode}")

r = run(artifact(), file_path=ANTIGO)
check("…e a mensagem nomeia o destino que sobrevive",
      "docs/proof/ui-wego-acesso.yaml" in r.stderr, r.stderr[:300])
check("…e diz por que o arquivo morria", "gitignored" in r.stderr, r.stderr[:300])

# ── conteúdo: a regra que já existia segue valendo, agora em docs/proof ────
r = run(artifact())
check("proven coerente com os fluxos em docs/proof → PASSA", r.returncode == 0,
      r.stderr[:300])

for ruim in ("skipped", "pass-visual-only", "pass-stale", "not-executable"):
    r = run(artifact(status=ruim))
    check(f"proven + fluxo {ruim} → BLOQUEIA", r.returncode == 2, f"rc={r.returncode}")

r = run(artifact(perturbation="survived"))
check("proven + perturbação survived → BLOQUEIA", r.returncode == 2,
      f"rc={r.returncode}")
check("…e o bloqueio computa unproven", "verdict: unproven" in r.stderr,
      r.stderr[:400])

r = run(artifact(status="skipped", perturbation="n/a"))
check("fluxo skipped computa needs-human", "verdict: needs-human" in r.stderr,
      r.stderr[:400])

# ── só `proven` pode ser contradito pelo conteúdo ──────────────────────────
for v in ("unproven", "needs-human"):
    r = run(artifact(verdict=v, status="skipped"))
    check(f"veredito {v} + fluxo skipped em docs/proof → PASSA", r.returncode == 0,
          r.stderr[:200])

# ── o que não é deste hook ────────────────────────────────────────────────
r = run(artifact(), file_path=str(TMP / "docs" / "proof" / "WEGO-1.yaml"))
check("artefato sem prefixo ui- → PASSA (é do guarda de backend)",
      r.returncode == 0, r.stderr[:200])

r = run(artifact(), file_path=str(TMP / "notas" / "ui-qualquer.yaml"))
check("fora de qualquer diretório de prova → PASSA", r.returncode == 0,
      r.stderr[:200])

r = run("::: isto não é yaml :::\nverdict: proven\n")
check("conteúdo ilegível → PASSA (nunca bloqueia no escuro)", r.returncode == 0,
      r.stderr[:200])

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {FAILURES}")
    sys.exit(1)
print("all ui-proof verdict-guard tests passed")
