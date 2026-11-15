# Especificação: a trava de build reconhece `manage.py test` (Django)

**Status:** ready-to-build
**Aberta em:** 2026-11-15            **Fechada em:** 2026-11-15
**Fontes lidas:** common/hooks/capture-build-result.py, common/hooks/gate-advance.py, common/hooks/_buildsource.py, tests/test_capture_build_result_pytest.py, .claude/no-build

## Como chegamos aqui
"A trava do harness bloqueia o meu commit porque não reconhece manage.py test como build." (dono, 2026-11-15)

## Problema
Num projeto Django, o dono roda `python manage.py test`, os testes passam, e o commit continua bloqueado. O hook que grava o resultado do build (`capture-build-result.py`) só conhece Maven, Gradle, npm/yarn/pnpm, pytest, cargo, deno, xcodebuild, SwiftPM, go test e docker build. Como `manage.py test` não casa com nenhum desses, o `.claude/last-build.json` nunca é escrito, e o `gate-advance.py` (a trava do commit) segue em STALE ou sem baseline.

## Escopo
### Entra
- `capture-build-result.py` (o hook que grava `.claude/last-build.json` depois de cada comando Bash) reconhece `manage.py test` em qualquer posição do comando: `python manage.py test`, `uv run python manage.py test`, `poetry run ...`, `docker compose exec web python manage.py test`.
- O mesmo reconhecimento para `django-admin test` e `python -m unittest`, que imprimem a mesma saída.
- Verde quando a saída tem `Ran N tests` com N > 0 e uma linha `OK`. Vermelho quando tem `FAILED (`. Vazio (EMPTY, que a trava trata como não verde) quando diz `Ran 0 tests` ou `NO TESTS RAN`, com ou sem rótulo de teste no comando.
### Não entra
- Arquivo de configuração para declarar um comando de build qualquer (ex.: `.claude/build-command`). Sem marcador de verde na saída, ele cai no buraco do exit code omitido. Vira especificação própria se outro caso aparecer.
- `make test`, `tox`, `nox` e scripts que chamam o `manage.py` por dentro. O texto do comando não mostra o `manage.py`, então a trava não tem como reconhecê-los.
- Mudança no `gate-advance.py` (a trava do commit). Ele já libera o commit quando `last-build.json` diz SUCCESS, e o defeito está só em quem escreve o arquivo.

## Estado e migração
Nada a migrar. No projeto Django, o `.claude/last-build.json` que hoje está STALE ou ausente é sobrescrito no primeiro `manage.py test` verde depois da mudança. A lista de extensões que invalida a baseline (`_buildsource.py`) já inclui `.py` e não muda.

## Critérios de sucesso

### CS-1: `manage.py test` verde, em qualquer formato de comando, grava SUCCESS no `.claude/last-build.json`
**Surface:** cli
**Red test:** dado o payload de PostToolUse de um Bash com comando `uv run python manage.py test` (e, parametrizado, `python manage.py test` e `docker compose exec web python manage.py test`), saída `Found 12 test(s).\nRan 12 tests in 0.312s\n\nOK` e sem exit code, rodar `capture-build-result.py` pela entrada padrão escreve `.claude/last-build.json` com `status: SUCCESS`. Hoje o arquivo não é escrito.

### CS-2: `manage.py test` com teste falhando ou com erro grava FAILURE
**Surface:** cli
**Red test:** o mesmo payload com saída `Ran 12 tests in 0.4s\n\nFAILED (failures=1, errors=2)` grava `status: FAILURE`. Hoje o arquivo não é escrito.

### CS-3: `Ran 0 tests` grava EMPTY, com ou sem rótulo no comando
**Surface:** cli
**Red test:** comando `python manage.py test` com saída `Ran 0 tests in 0.000s\n\nOK`, e comando `python manage.py test app.tests.NaoExiste` com saída `Ran 0 tests in 0.000s\n\nNO TESTS RAN`, gravam `status: EMPTY` nos dois casos. Hoje o arquivo não é escrito.

### CS-4: `python -m unittest` e `django-admin test` são reconhecidos igual
**Surface:** cli
**Red test:** comandos `python3 -m unittest discover` e `django-admin test --settings=proj.settings` com saída `Ran 5 tests in 0.1s\n\nOK` gravam `status: SUCCESS`. Hoje o arquivo não é escrito.

### CS-5: depois de um `manage.py test` verde, a trava libera o `git commit`
**Surface:** cli
**Red test:** num repositório git temporário com `pyproject.toml`, um `.py` alterado e `.claude/last-build.json` em STALE, rodar `capture-build-result.py` com o payload verde do CS-1 e depois `gate-advance.py` com o payload de PreToolUse de `git commit -m x` termina sem bloqueio (exit 0). Hoje o `gate-advance.py` bloqueia com "build is STALE".

## Perguntas em aberto
- [x] Que formatos de comando a trava reconhece? — Qualquer formato que contenha `manage.py test` (python direto, uv, poetry, docker compose exec).
- [x] `python -m unittest` e `django-admin test` entram? — Sim, os três.
- [x] `Ran 0 tests` é verde ou EMPTY? — EMPTY sempre, com ou sem rótulo.
- [x] Entra um arquivo de configuração para declarar comando de build qualquer? — Não, fica fora desta especificação.

## Decided without asking
- A saída a ler é a do runner `unittest` que o Django usa por padrão: `Ran N tests in Xs` seguido de `OK` (verde) ou `FAILED (failures=…, errors=…)` (vermelho). Motivo: o Claude Code omite o exit code no sucesso, então sem marcador de texto o verde nunca é registrado, como já aconteceu com o pytest em 2026-10-10. Vete aqui se discordar.
- Falha vence sucesso na mesma saída, igual aos outros tipos de build do hook. Vete aqui se discordar.
- O marcador de verde é a linha `OK` sozinha (ou `OK (skipped=N)`) ancorada no início da linha, não a substring `OK`. Motivo: `OK` solto aparece em qualquer log de app Django e viraria verde falso. Vete aqui se discordar.
- Os três comandos gravam o mesmo `kind: unittest` no `last-build.json`, porque o leitor da saída é um só. Vete aqui se discordar.
- O verde não depende de `-v`/`--verbosity`: o runner do unittest imprime `Ran N tests` e `OK`/`FAILED` em qualquer verbosidade, `-v 0` inclusive. Vete aqui se discordar.
- Comando que só menciona o texto entre aspas (`echo "manage.py test"`) não conta como build, pela mesma regra de texto sem aspas que os outros tipos já usam. Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação
- Runner de teste trocado no `settings.py` (`TEST_RUNNER` apontando para pytest-django ou xmlrunner) muda a saída. Com pytest-django, o comando costuma ser `pytest`, que já é reconhecido. Outros runners ficam fora.
- Um `grep manage.py test arquivo` sem aspas casa com o padrão, igual acontece hoje com `pytest`. Como não traz `Ran N tests`, não classifica e não grava nada.
