# Síntese do painel de advisors — design do P6 (ui-proof-gate)

Painel de 2026-07-11: 7 lentes isoladas (contrarian, fundamentalista, expansionista,
outsider, executor, operador-sre, custo-de-manutencao) sobre
`common/agents/ui-proof-reviewer.md` + `docs/ui-proof-manifest.md` +
`common/commands/prove-ui.md`. Primeiro uso real do /common:advisors (P7).

## Convergências (o que 3+ lentes viram independentemente)

1. **[ALTA — 5 lentes] O green→red→green não é executável como escrito.** O agente
   deve "rebuildar/reiniciar o app a partir do worktree numa porta livre", mas o
   manifesto não tem campo `build:` nem parametrização de porta; `extension_dir`
   aponta para `dist/` compilado (perturbar `src/` exige pipeline de build que
   ninguém declarou); e `{base_url}` fixo faz steps e assert.backend apontarem para a
   instância PRIMÁRIA, não a perturbada — RED/GREEN falso ou `assumed` crônico.
   O diferencial inteiro do gate vira letra morta.
2. **[ALTA — 4 lentes] Veredito "mecânico" sem guarda mecânica.** O
   proof-verdict-guard só parseia o schema `levels` do irmão de backend e mora em
   build-hex; o artifact `ui-*.yaml` (schema `flows`) passa limpo. O repo já provou
   (WEGO-1785) que prosa sozinha não segura essa regra.
3. **[ALTA/MÉDIA — 4 lentes] Scripts regenerados de prosa a cada run = compilador
   não-determinístico dentro de um gate.** UNPROVEN vira indistinguível de
   flakiness/tradução divergente; sem retry, sem pinning do script que passou, sem
   separar "assert falhou" de "seletor não encontrado" de "timeout de infra".
4. **[ALTA — contrarian] Assert sem disciplina de frescor.** O exemplo canônico passa
   com dado residual de run anterior (substring em endpoint compartilhado) → PROVEN
   falso. Falta nonce/contagem-antes-depois/timestamp — a lição "non-vacuous" do
   irmão não foi importada.
5. **[ALTA/MÉDIA — 3 lentes] O gate não gateia.** Comando avulso, fora do lifecycle
   que invoca o irmão (prove, prove-drain, review-gate:merge): card que toca
   `extension/src/**` sai PROVEN do board sem nunca passar pela UI. Precisa do fio:
   quando o repo tem `ui-proof.yaml` e o diff toca superfície de UI, o prove do
   board exige o veredito de UI também.
6. **[MÉDIA — executor] O fluxo-vitrine é inexecutável:** "clicar no ícone da
   extensão na toolbar" não é DOM — Playwright não faz por seletor; o workaround
   (abrir `chrome-extension://<id>/popup.html`) precisa ser a receita documentada.
7. **[MÉDIA — operador-sre] Sem teardown:** falha parcial deixa worktree, Chromium,
   instância fantasma e porta ocupada — que travam o preflight do run seguinte.
8. **[MÉDIA — outsider] Referências opacas** (P3, P6, cepa-doctor, cards) e
   colocação em common/ + escolha "Playwright via Bash" sem justificativa registrada.

## Discordâncias nomeadas (não mediar em silêncio)

- **Dois dialetos de YAML em `.claude/`**: custo-de-manutencao vê carga permanente
  (env.yaml raso vs ui-proof.yaml aninhado); fundamentalista vê "quebra bem feita"
  (explícita e justificada). Decide: manter os dois dialetos, mas a justificativa
  precisa morar nos DOIS docs, não na cabeça de quem decidiu.
- **Agente em common/**: fundamentalista aponta quebra da doutrina "common não tem
  agentes" do agents-overview; na prática a doutrina JÁ estava quebrada pelo
  completion-auditor. Decide: atualizar o agents-overview (a doutrina está stale),
  não mover o agente.
- **Scripts gerados: exaust ou ativo?** expansionista quer promovê-los a suíte E2E
  reutilizável; custo-de-manutencao alerta para manter um compilador. Convergem no
  meio: PINAR o script que passou (cache por fluxo, regenerar só quando steps
  mudam) — determinismo de graça, sem prometer suíte.

## Propostas consolidadas (prioridade)

1. Manifesto ganha `build:` (como recompilar de um diretório arbitrário) e
   `serve:` com template de porta (`{port}` interpolável em base_url) — destrava o
   green→red→green de verdade. Steps/assert interpolam a base_url DA INSTÂNCIA em
   teste, nunca a fixa.
2. Frescor obrigatório no assert: `expect` deve referenciar um nonce do run (o
   agente injeta um marcador nos dados do fluxo e o exige no check) OU
   contagem-antes/depois. Assert sem frescor = evidência fraca, rebaixa o veredito.
3. Pinning de scripts: `.claude/ui-proof/runs/<fluxo>.spec.ts` é regenerado apenas
   quando os steps do manifesto mudam (hash na primeira linha); senão, reusado.
   Retry 1x para falha de infra; taxonomia de falha (assert / seletor / infra) no
   artifact.
4. Guard mecânico: estender proof-verdict-guard (ou gêmeo em common/hooks) para o
   schema `flows` — bloquear `verdict: proven` com flow não-pass/visual-only.
5. Fio no lifecycle: prove do board-flow consulta ui-proof quando o diff toca
   superfície declarada; acceptance-completeness reconhece a altitude UI.
6. Receita da extensão: documentar `chrome-extension://<id>/popup.html` como o
   caminho canônico (nunca "clicar na toolbar"); teardown com trap (worktree,
   processo, porta) + área "ambiente" do doctor detecta órfãos.
7. Higiene dos docs: definir P3/P6/cepa-doctor na primeira menção; justificar
   common/ e Playwright-via-Bash; modo `--draft` que PROPÕE esqueleto de manifesto
   comentado (proposta ≠ prova — não viola a doutrina).

## Meta (dogfood do P7)

- O painel funcionou: isolamento produziu convergência genuína (5 lentes acharam o
  mesmo furo nº 1 por caminhos diferentes) e discordâncias reais para nomear.
- Bugs do próprio advisors encontrados no primeiro uso: (a) `args` do Workflow chega
  como string JSON — o script inline precisa da guarda `typeof args === 'string' ?
  JSON.parse(args) : args`; (b) enriquecimento pós-agent (`.then`) não aparece no
  journal por agente — incluir a lente DENTRO do schema de saída.
