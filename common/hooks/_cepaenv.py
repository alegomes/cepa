"""Environment variables Cepa owns: the English `CEPA_*` names, and the old ones still read.

CS-6 of docs/spec/reforma-de-nomes-dos-comandos.md. Every variable Cepa owns has the
`CEPA_` prefix and an English name. The names used before the rename keep working:
`get()` reads the new name first and falls back to the old one only when the new one
is unset or empty, so a shell that still exports `CEPA_MODE=off` is not silently
ignored, and when both are set the new one wins.

This file is the single place that holds the old -> new table and the fallback read
(the launcher `common/bin/cepa` keeps a small shell twin, `_cepa_old_name`, because
it cannot import Python; tests/test_env_names_in_english.py checks the two agree).
Every reader in `common/bin` and `common/hooks` goes through `get()`/`is_set()`;
where Cepa SETS a variable for a child process it sets the NEW name.

Two values were renamed along with their variables: `CEPA_PERMISSIONS=classifier`
(was `CEPA_PERMISSOES=classificador`) and `CEPA_PROMPT_MODE=replace` (was
`CEPA_PROMPT_MODO=substitui`). `get()` returns the new value for either spelling,
under either name.

Variables that belong to someone else (HOME, TERM, NO_COLOR, CLAUDE_PROJECT_DIR,
CLAUDE_PLUGIN_ROOT, CLAUDE_SESSION_ID, HC_TERMINAL_ID...) are not here and are
read directly.
"""
import os

# old name -> new name
RENAMED = {
    "CEPA_MODO": "CEPA_MODE",
    "CEPA_MODO_DEFAULT": "CEPA_MODE_DEFAULT",
    "CEPA_ENCADEAR": "CEPA_CHAIN",
    "CEPA_PERMISSOES": "CEPA_PERMISSIONS",
    "CEPA_PROMPT_MODO": "CEPA_PROMPT_MODE",
    "CEPA_COR": "CEPA_COLOR",
    # the marker `cepa run` exports on every `claude -p` it launches
    "CEPA_UNTIL_RUN": "CEPA_RUN",
    "CEPA_UNTIL_TETO_LEITURA": "CEPA_RUN_READER_CEILING",
    "CEPA_UNTIL_SONDA_REDE": "CEPA_RUN_NETWORK_PROBE",
    "CEPA_UNTIL_SONDA_INTERVALO": "CEPA_RUN_PROBE_INTERVAL",
    "CEPA_UNTIL_MODELO_LEITOR": "CEPA_RUN_READER_MODEL",
    "CEPA_UNTIL_MARGEM_RESET": "CEPA_RUN_RESET_MARGIN",
    "CEPA_UNTIL_LINHA_VIVA": "CEPA_RUN_LIVE_LINE",
    "CEPA_UNTIL_LIMITE_ANALISE": "CEPA_RUN_ANALYSIS_LIMIT",
    "CEPA_UNTIL_LEITOR": "CEPA_RUN_READER",
    "CEPA_UNTIL_HEARTBEAT": "CEPA_RUN_HEARTBEAT",
    "CEPA_UNTIL_GRACA_SIGTERM": "CEPA_RUN_SIGTERM_GRACE",
    "CEPA_UNTIL_ESPERA_RESPOSTA": "CEPA_RUN_ANSWER_WAIT",
    "CEPA_UNTIL_COR": "CEPA_RUN_COLOR",
    "CEPA_HEARTBEAT_ORFA": "CEPA_HEARTBEAT_ORPHAN",
    # set by /common:autonomous-start, so it is Cepa's, not Claude Code's
    "CLAUDE_AUTONOMOUS_RUN_ID": "CEPA_AUTONOMOUS_RUN_ID",
    "CLAUDE_WT_CLAIM": "CEPA_WT_CLAIM",
    "CLAUDE_WT_CLAUDE_BIN": "CEPA_WT_CLAUDE_BIN",
    "CLAUDE_WT_NUDGE": "CEPA_WT_NUDGE",
    "CLAUDE_WT_ROOT": "CEPA_WT_ROOT",
    "CLAUDE_WT_SESSION_SOFTCAP": "CEPA_WT_SESSION_SOFTCAP",
    "CLAUDE_WT_SLICE": "CEPA_WT_SLICE",
    "CLAUDE_WT_SUBJECT": "CEPA_WT_SUBJECT",
    "CLAUDE_WT_SUBJECT_MINPROMPTS": "CEPA_WT_SUBJECT_MINPROMPTS",
    "CLAUDE_WT_SUBJECT_THRESHOLD": "CEPA_WT_SUBJECT_THRESHOLD",
    "CCW_SEED": "CEPA_SEED",
    "CCW_WORKTREE_HOME": "CEPA_WORKTREE_HOME",
    "CAPTURE_BUILD_DEBUG": "CEPA_CAPTURE_BUILD_DEBUG",
    "CAPTURE_BUILD_DEBUG_LOG": "CEPA_CAPTURE_BUILD_DEBUG_LOG",
    "LEAD_WORKTREE_DEBUG": "CEPA_LEAD_WORKTREE_DEBUG",
    "LEAD_WORKTREE_DEBUG_LOG": "CEPA_LEAD_WORKTREE_DEBUG_LOG",
}

# new name -> old value -> new value (the old spelling of a value is still accepted)
OLD_VALUES = {
    "CEPA_PERMISSIONS": {"classificador": "classifier"},
    "CEPA_PROMPT_MODE": {"substitui": "replace"},
}

_OLD_OF = {new: old for old, new in RENAMED.items()}


def old_name(new):
    """The pre-rename name of `new`, or None."""
    return _OLD_OF.get(new)


def _clean(v):
    return None if v is None or v == "" else v


def get(new, default="", env=None):
    """The value of the variable `new` (a CEPA_ name), falling back to its old name.

    The new name wins when both are set; an empty value counts as unset. `env` is
    a mapping (default `os.environ`). A renamed value (see OLD_VALUES) comes back
    in its new spelling.
    """
    env = os.environ if env is None else env
    v = _clean(env.get(new))
    if v is None:
        old = _OLD_OF.get(new)
        v = _clean(env.get(old)) if old else None
    if v is None:
        return default
    return OLD_VALUES.get(new, {}).get(v, v)


def is_set(new, env=None):
    """True when `new` (or its old name) is set to a non-empty value."""
    return bool(get(new, "", env))
