#!/usr/bin/env python3
"""_modes — the table of work modes, in ONE place only.

## Why it exists

A session's mode is a STATE that lasts (`docs/modos-de-trabalho.md`), and each
mode has an entry, a product and an exit condition. That information used to
live in three places that did not talk to each other:

- `common/bin/cepa` — the list of valid names (`MODES=`), to validate `--mode`;
- `common/hooks/session-mode.py` — only the exit conditions, to inject in the turn;
- `docs/modos-de-trabalho.md` — the full prose, which nobody reads mid-session.

Whoever forgets a mode's purpose halfway through the work is not going to open a
307-line doc. And three copies of the same table is the pattern this repo has
already paid dearly for (memory `hooks-texto-citado-nao-e-shell`: 7 copies of the
same parser, fix applied to 5). Here the table is one; the hook imports it,
`cepa-modes` prints it, and `tests/test_modes_single_source.py` fails if the
`cepa` list diverges from this one.

Each mode also declares `write`: the allow-list of DESTINATIONS it produces,
read by `write-mode-gate.py`. `"tudo"` ("everything") means the mode has no
list — not that it is free of enforcement: in construction the
completion-auditor and the proof-reviewer enforce, and in refactor the
`refactor-gate.py` does.

`deploy` is NOT here on purpose: it is the 8th mode of the document, left out of
the round by the owner's decision (it is the only one that depends on external
infra). When it comes in, it comes in here first.

The VALUES of the table (purpose/entry/produces/exit/gate prose) stay in
pt-BR: they are shown to the user and injected into the turn, and
`cepa-modes --json` prints them. The dict KEYS are English here; `cepa-modes
--json` maps them back to the legacy keys (`proposito`, `entrada`, `produz`,
`saida`, `gate`, `escrita`) because compass reads `saida` from that JSON.
"""

import os
import re

# order = the order of the work cycle, not alphabetical
MODES = {
    "exploration": {
        "purpose": "entender uma dor que ainda não tem solução proposta, e sair com um caminho recomendado",
        "entry": "uma dor em linguagem natural, SEM solução proposta — se você "
                   "já sabe a solução, não é exploração",
        "produces": "um documento de estratégia com 2+ caminhos considerados, um "
                  "recomendado, e a dor reformulada com o que se aprendeu",
        "exit": "um documento de estratégia com 2+ caminhos considerados, "
                 "passado pelo painel /common:advisors com as discordâncias nomeadas",
        "gate": "parcial — o painel existe, o veredito não; o write-mode-gate já barra escrita fora de docs/**",
        "write": ["docs/**", ".claude/**", "BACKLOG.md"],
    },
    "discovery": {
        "purpose": "virar um comportamento desejado em critério de aceite cobrável, com evidência atrás",
        "entry": "um comportamento desejado, vindo da exploração ou direto",
        "produces": "oportunidade enquadrada, evidência coletada, e os critérios de "
                  "aceite escritos NA ALTITUDE em que serão cobrados",
        "exit": "evidence-auditor Confirmed nas suposições de risco + os "
                 "critérios de aceite escritos na altitude + o teste vermelho de cada um",
        "gate": "em parte: o spec-readiness-gate barra especificação pronta sem superfície e teste vermelho declarados por critério, mas não roda o teste; o write-mode-gate barra escrita fora de docs/discovery, docs/spec e docs/epics",
        "write": ["docs/discovery/**", "docs/spec/**", "docs/epics/**", ".claude/**", "BACKLOG.md"],
    },
    "design": {
        "purpose": "desenhar como a coisa funciona e como ela se parece, antes de existir código",
        "entry": "oportunidade validada",
        "produces": "fluxos, estados, spec visual reconciliada com o design system, "
                  "protótipo compartilhável",
        "exit": "design-critic devolvendo SHIP",
        "gate": "existe e funciona (topologia design); o write-mode-gate barra escrita fora de docs/design",
        "write": ["docs/design/**", ".claude/**", "BACKLOG.md"],
    },
    "construction": {
        "purpose": "escrever o código que faz o teste vermelho do critério ficar verde",
        "entry": "UM TESTE VERMELHO escrito a partir do critério de aceite, antes "
                   "do código, por quem não vai implementar",
        "produces": "código + testes",
        "exit": "completion-auditor COMPLETE e proof-reviewer PROVEN",
        "gate": "existe e funciona (os dois gates, nesta ordem)",
        "write": "tudo",
    },
    "refactor": {
        "purpose": "reorganizar código já entregue sem mudar nada que se veja de fora",
        "entry": "ORÇAMENTO DECLARADO — a lista fechada do que será reformado e o "
                   "limite; sem orçamento a reforma nunca termina",
        "produces": "código reorganizado, comportamento externo idêntico",
        "exit": "o orçamento declarado exaurido, build verde, e NENHUM teste "
                 "externo editado (teste editado = mudou comportamento = não era reforma)",
        "gate": "refactor-gate.py bloqueia editar teste externo enquanto o modo dura",
        "write": "tudo",
    },
    "reflection": {
        "purpose": "olhar o que já existe por uma lente escolhida e transformar cada achado em destino",
        "entry": "um RECORTE e uma LENTE, ambos escolhidos de menu — reflexão sem "
                   "recorte vira leitura infinita do repo",
        "produces": "um relatório de achados classificados",
        "exit": "nenhum achado sem destino — cada um virou card ou foi "
                 "descartado com motivo escrito",
        "gate": "reflection-gate.py barra relatório fechado com achado solto, e o write-mode-gate barra escrita fora de docs/** e .claude/reflection (ou o legado .claude/reflexao)",
        "write": [".claude/reflection/**", ".claude/reflexao/**", "docs/**", "BACKLOG.md"],
    },
    "documentation": {
        "purpose": "documentar código estável na árvore Diátaxis, com cada porquê citando sua fonte",
        "entry": "código estável, não em construção ativa",
        "produces": "a árvore Diátaxis fundamentada",
        "exit": "consistency-reviewer PASS e sua assinatura em /docs:finalize",
        "gate": "existe e funciona (topologia docs); o write-mode-gate barra escrita fora de docs/**",
        "write": ["docs/**", ".claude/**", "BACKLOG.md"],
    },
}

# What `session-mode.py` injects every turn — only the exit condition.
EXIT = {name: d["exit"] for name, d in MODES.items()}

# The old (pt-BR) mode names, accepted on read during the transition
# (item `interface-in-english`): a `.claude/session-mode` written by an old
# `cepa` keeps working. Whoever WRITES writes only the new name.
OLD_TO_NEW_MODE = {
    "exploracao": "exploration",
    "descoberta": "discovery",
    "design": "design",
    "construcao": "construction",
    "reforma": "refactor",
    "reflexao": "reflection",
    "documentacao": "documentation",
}

# The old keys of `.claude/session-mode` -> the new ones.
_LEGACY_SESSION_MODE_KEYS = {"modo": "mode", "rotina": "routine",
                        "orcamento": "budget", "aberto_em": "opened_at"}




def normalize_mode(value):
    """Mode name (old or new) -> the new name; unknown comes back as it came."""
    v = str(value or "").strip()
    return OLD_TO_NEW_MODE.get(v, v)


def parse_session_mode(text):
    """Text of `.claude/session-mode` -> dict with the NEW keys (mode,
    routine, budget, opened_at), also reading the old ones. `null`/empty -> None.
    The value of `mode` already comes normalized to the new name. Never raises."""
    data = {}
    try:
        for line in (text or "").splitlines():
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            k = k.strip()
            v = v.strip().strip('"')
            val = None if v in ("null", "") else v
            if k in _LEGACY_SESSION_MODE_KEYS:  # old key: only counts if the new one did not come
                data.setdefault(_LEGACY_SESSION_MODE_KEYS[k], val)
            else:
                data[k] = val
    except Exception:  # noqa: BLE001
        pass
    if data.get("mode"):
        data["mode"] = normalize_mode(data["mode"])
    return data


def read_session_mode(root):
    """`<root>/.claude/session-mode` -> dict (new keys), or None if the file
    does not exist/is unreadable or declares no mode."""
    try:
        with open(os.path.join(str(root), ".claude", "session-mode"),
                  encoding="utf-8", errors="replace") as f:
            data = parse_session_mode(f.read())
    except OSError:
        return None
    return data if data.get("mode") else None


# ---------------------------------------------------------------------------
# The session intent: `.claude/session-intent`
# ---------------------------------------------------------------------------
#
# Format and reader live HERE, in one place, for the same reason as the table
# above. `session-mode` is read line by line by six readers (`grep`/`sed` and
# hooks) that do not understand lists, and the `cepa` `write_mode` rewrites it
# whole with `>`: putting the plan and the history in there would lose them on
# the first mode switch. That is why the intent is its own file, and whoever
# reads it (hook, `whereami`, statusline, `cepa-intent`) imports `read_intent`
# instead of copying a parser.
#
# The format, documented in `docs/estrategia-intencao-da-sessao.md`:
#
#   purpose, by_when, step_since, session_id, branch, opened_at, summary
#                 scalars (quoted "..." or bare)
#   plan          list of 1 to PLAN_MAX texts (`- item`)
#   step          integer, 1-based: the step IN PROGRESS, not the last one done
#   history       list of maps (`- at: ...` and indented keys below)
#
# The old keys (proposito, para_quando, plano, passo, passo_desde,
# aberto_em, resumo, historico and, in the history, em/proposito/plano_anterior/
# motivo_da_troca) are still READ and come back already under the new name; the
# writer writes only the new ones.
#
# No pyyaml: this repo's hooks do not depend on it (see `_wtlib.py`). The reader
# is tolerant on purpose — a hook that breaks because of a half-written file
# takes the whole turn down. It returns what it managed to read, keeps unknown
# keys and never raises. It does NOT enforce the writer's rules (plan item
# without a colon, for example): that is `cepa-intent`'s job.

INTENT_FILE = ".claude/session-intent"

# Plan of 1 to 6 steps; more than that is a program (`plan.yaml`).
PLAN_MAX = 6

# Keys whose value is a list of maps; any other list is a list of texts.
_INTENT_MAP_LISTS = ("history",)

# Old keys -> new, at the top of the file and inside the history entries.
_LEGACY_INTENT_KEYS = {
    "proposito": "purpose", "para_quando": "by_when", "plano": "plan",
    "passo": "step", "passo_desde": "step_since", "aberto_em": "opened_at",
    "resumo": "summary", "historico": "history",
}
_LEGACY_HISTORY_KEYS = {
    "em": "at", "proposito": "purpose", "plano_anterior": "previous_plan",
    "motivo_da_troca": "change_reason",
    "acao": "action", "motivo": "reason", "de": "from", "para": "to",
}

_KV = re.compile(r"^([A-Za-z_][\w-]*)\s*:(?:\s+(.*)|\s*)$")


def _intent_value(raw):
    """A scalar of the file: "quoted" (with \\" and \\\\) or bare without a `# note`."""
    s = (raw or "").strip()
    if s[:1] in ('"', "'"):
        q, out, i = s[0], [], 1
        while i < len(s):
            c = s[i]
            if c == "\\" and q == '"' and i + 1 < len(s):
                out.append(s[i + 1])
                i += 2
                continue
            if c == q:
                return "".join(out)
            out.append(c)
            i += 1
        return "".join(out)  # unclosed quote: return what there was
    m = re.search(r"\s#", s)
    return (s[:m.start()] if m else s).strip()


def parse_intent(text):
    """Text of `session-intent` -> dict. Tolerant: never raises."""
    data, key, last_map = {}, None, None
    try:
        for line in (text or "").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if not line[0].isspace():
                last_map = None
                m = _KV.match(line.rstrip())
                if not m:
                    key = None
                    continue
                key, rest = m.group(1), m.group(2)
                key = _LEGACY_INTENT_KEYS.get(key, key)
                if rest is None or rest.lstrip().startswith("#"):
                    data[key] = []  # opens a block; without items it becomes an empty list
                else:
                    data[key] = _intent_value(rest)
                continue
            if key is None or not isinstance(data.get(key), list):
                continue
            body = line.strip()
            is_map_list = key in _INTENT_MAP_LISTS
            if body.startswith("-"):
                item = body[1:].strip()
                if is_map_list:
                    last_map = {}
                    data[key].append(last_map)
                    m = _KV.match(item)
                    if m:
                        last_map[_LEGACY_HISTORY_KEYS.get(m.group(1), m.group(1))] = _intent_value(m.group(2))
                else:
                    data[key].append(_intent_value(item))
            elif is_map_list and last_map is not None:
                m = _KV.match(body)
                if m:
                    last_map[_LEGACY_HISTORY_KEYS.get(m.group(1), m.group(1))] = _intent_value(m.group(2))
        if "step" in data:
            try:
                data["step"] = int(str(data["step"]).strip())
            except (ValueError, TypeError):
                pass  # stays as it came; the reader decides
    except Exception:
        pass  # return what was already read
    return data


def read_intent(root):
    """`<root>/.claude/session-intent` -> dict, or None if the file does not exist."""
    try:
        with open(os.path.join(str(root), INTENT_FILE), encoding="utf-8",
                  errors="replace") as f:
            return parse_intent(f.read())
    except OSError:
        return None


# Order in which the writer emits the known keys; unknown ones (which the
# reader preserves) go after, so a future version of the format is not erased
# by an old `cepa-intent`.
_INTENT_ORDER = ("purpose", "by_when", "plan", "step", "step_since",
                 "session_id", "branch", "opened_at", "summary", "history")


def _intent_quotes(value):
    """Scalar -> `"..."` with \\ and \" escaped; a line break becomes a space."""
    s = " ".join(str(value).split("\n")).replace("\r", " ")
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_intent(data):
    """dict -> text of `session-intent`; `parse_intent` reads it back the same.

    Lives next to the parser so the pair is tested together: the writer
    (`cepa-intent`) is the only one that calls it, but the format is one.
    Scalars always come out quoted (`step` comes out bare, it is an integer and
    the parser converts it).
    """
    keys = [k for k in _INTENT_ORDER if k in data]
    keys += [k for k in data if k not in _INTENT_ORDER]
    out = []
    for k in keys:
        v = data[k]
        if k == "step":
            out.append(f"{k}: {int(v)}")
        elif k == "history":
            out.append(f"{k}:")
            for entry in v or []:
                pairs = list(entry.items())
                for i, (mk, mv) in enumerate(pairs):
                    out.append(("  - " if i == 0 else "    ") + f"{mk}: {_intent_quotes(mv)}")
        elif isinstance(v, list):
            out.append(f"{k}:")
            out += [f"  - {_intent_quotes(i)}" for i in v]
        else:
            out.append(f"{k}: {_intent_quotes(v)}")
    return "\n".join(out) + "\n"


def iso_utc(stamp):
    """`2026-10-16T21:40:00Z` (or with an offset) -> UTC datetime; None if it fails."""
    from datetime import datetime, timezone
    try:
        d = datetime.fromisoformat(str(stamp).strip().replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def same_session(recorded, current):
    """Is the intent from this session? The file may keep the truncated id (8
    characters); a prefix is enough. With no way to compare, it does not accuse
    another session.

    Single rule: the `session-mode.py` hook and `cepa-intent estado` (which
    /common:whereami runs) ask the same question and must not diverge."""
    g, a = str(recorded or "").strip(), str(current or "").strip()
    if not g or not a:
        return True
    return g.startswith(a) or a.startswith(g)


def other_session_question(intent, purpose):
    """The two sentences of decision D1 (intent recorded by ANOTHER session): the
    date and the question "continue or open a new one?". `purpose` already comes
    truncated from the caller (the hook pays a toll per turn; whereami shows it
    in full).

    The sentences stay in pt-BR: they are injected into the turn and shown by
    /common:whereami, like the rest of the `[intenção]` lines of `session-mode.py`."""
    when = iso_utc(intent.get("opened_at", ""))
    date = when.strftime("%Y-%m-%d %H:%M UTC") if when else "data desconhecida"
    return [
        f"[intenção] Intenção de {date}, gravada em outra sessão: \"{purpose}\". "
        "Não a trate como a desta sessão.",
        "Pergunte ao dono: continuo ou abro nova? Continuar = `cepa-intent "
        "continue`; abrir nova = `cepa-intent write ... --reason \"...\"`.",
    ]
