# Desvios capturados

Achados que apareceram fora do modo da sessão em que nasceram. Registrados em
vez de trabalhados, para não virarem o próprio vazamento que os modos existem
para impedir (docs/modos-de-trabalho.md).

- [x] 2026-08-18 · modo: construcao · RESOLVIDO em board-flow 0.16.0 (a regra saiu; Won't Do entra na rodada única). `/board-flow:triage` proibia agrupar
  exatamente a decisão mais repetitiva da triagem: *"Nothing destructive without
  a per-card yes. OBSOLETE → Won't Do is never batch-applied. Each cancellation
  is confirmed individually"* (`board-flow/commands/triage.md:38`). Isso
  contradiz o passo 6 do mesmo arquivo, que manda juntar TODAS as decisões numa
  rodada só aplicando `default-yes` (linha 133). Numa fila com K cards obsoletos
  são K interrupções, mais o grill, mais o "Apply?" do passo 7. Evidência: a
  sessão session/triage_2025 começou 20:25 para triar a coluna To Do e montar um
  plano de execução noturna e às 21:45 ainda não tinha chegado ao plano.
- [ ] 2026-08-23 · modo: descoberta · spec-readiness-gate só enxerga new_string numa Edit, então virar Status para pronta-para-construir por edição pontual é sempre bloqueado; só passa com Write do arquivo inteiro; vi em common/hooks/spec-readiness-gate.py:72-84
- [ ] 2026-08-23 · modo: descoberta · o resgate de worktree salvou so marcadores efemeros (.claude/rescued/*/session-mode, 78 bytes, modo de sessao encerrada) e mesmo assim cobra atencao em todo SessionStart prometendo "planos, prova e aceite"; o filtro do que merece resgate esta largo demais
- [ ] 2026-08-24 · modo: construcao (sessao onda2 do wego-acesso-backend) · `herdr worktree create` devolveu JSON de sucesso completo (path, branch, workspace) para 4 de 5 chamadas e o git nao registrou nenhuma delas; a onda quase nasceu morta em silencio. Gatilho NAO reproduzido depois (tentei --base main, --base de branch em worktree ligada, e 4 chamadas back-to-back em loop: todas funcionaram). Conserto certo independe da causa: /maestro:run passo 6a tem que conferir `git worktree list` apos cada create em vez de confiar no exit code. Ver maestro/commands/run.md:80
- [ ] 2026-08-24 · modo: construcao (sessao onda2 do wego-acesso-backend) · `herdr worktree list` SEM `--cwd` resolve para um repositorio imprevisivel: rodado de dentro de uma worktree do wego, respondeu com worktrees do cepa (`w6 main`, `session/herdr_worktree`, `session/pane_intrusion`). COM `--cwd <clone principal>` bate exato com o git (13 = 13, mesmas branches). Efeito real: minha poda das 5 worktrees da onda 2 nao removeu nada e nao reclamou, porque o filtro nao casou com nada. O passo 2 do /maestro:run (gc de orfaos) e o passo 9 (prune) chamam `herdr worktree list --json` sem `--cwd` na prosa — tem que passar `--cwd <raiz-principal>` e conferir contra `git worktree list`. Ver maestro/commands/run.md passos 2 e 9
- [ ] 2026-08-24 · modo: reflexao · o hook que escreve `.claude/session-log.md` grava relativo ao cwd do turno, nao a raiz do repo: um `cd .claude/programs` no meio da sessao criou `.claude/programs/.claude/session-log.md` com as 2 ultimas mensagens do usuario, e o log canonico ficou so com a 1a. /common:recap le so o canonico, entao a sessao aparece truncada e nada avisa. Juntei os dois a mao nesta sessao. Ver common/hooks (session-log)
