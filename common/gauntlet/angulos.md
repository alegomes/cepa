# Ângulos do Gauntlet

Registry dos ângulos que o `/common:gauntlet` distribui entre os builders. Cada
ângulo tem uma `key` (o que `--angulos=` aceita) e um `brief` (o texto, em
inglês, que entra no prompt do builder). O brief é copiado como está para o
campo `angles[i].brief` do `args` do script.

Como o comando usa este arquivo:

- **Default:** sem `--angulos`, usa os três abaixo, nesta ordem.
- **`--angulos=a,b,c`:** seleciona por `key`, nessa ordem. Key fora do registry:
  o comando lista as válidas e para.
- **`--builders=N`:** cada builder recebe um ângulo. Com N maior que o número de
  ângulos, os ângulos ciclam (o 4º builder pega o 1º ângulo de novo, e assim por
  diante); com N menor, valem os N primeiros.

## mecanismo-novo

brief: Your angle: MECHANISM/CONFIG. Enforce mechanically wherever possible: new gates, hooks or command preambles that consult versioned config before acting, files with a schema and a defined consumer, a lint or test that blocks the failure. Design the config schema and the enforcement points concretely, and label honestly what stays prose.

## estender-o-que-existe

brief: Your angle: EXTEND WHAT EXISTS. Minimal new machinery: generalize and extend the commands, skills and hooks that already exist, and prefer conventions over new files. Optimize for shipping in one session and for not creating new surfaces that drift.

## livre

brief: Your angle: FREE. Ignore any sketch in the context if you have something better. Consider approaches the sketch did not: different data flows, queues, batching, scoring instead of binary rules, learning from existing telemetry, or something else entirely. Novelty counts only if buildable in this harness.
