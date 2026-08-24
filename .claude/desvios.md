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
- [ ] 2026-08-24 · modo: construcao (sessao onda2 do wego-acesso-backend) · `herdr worktree list` mantem registro proprio que DIVERGE do git: mostrou `w19 session/WEGO-paralelo-S-2057` como worktree viva enquanto `git worktree list` nao tinha nenhum registro dela e o diretorio nao existia. O passo 2 do /maestro:run (gc de orfaos) usa exatamente `herdr worktree list --json` como fonte para decidir o que limpar — mesmo defeito de confianca do passo 6a, num passo diferente. Ver maestro/commands/run.md passo 2
- [ ] 2026-08-24 · modo: reflexao · o hook que escreve `.claude/session-log.md` grava relativo ao cwd do turno, nao a raiz do repo: um `cd .claude/programs` no meio da sessao criou `.claude/programs/.claude/session-log.md` com as 2 ultimas mensagens do usuario, e o log canonico ficou so com a 1a. /common:recap le so o canonico, entao a sessao aparece truncada e nada avisa. Juntei os dois a mao nesta sessao. Ver common/hooks (session-log)
