"""_state: the single reader of the five state deposits (DUR-4, strategy O1 item 3).

READ-ONLY. This module never writes a deposit and never creates one (rule R3 of
docs/estrategia-durabilidade.md: "nenhum depósito de estado novo"). It exists so
that `/common:next`, `/common:doctor`, `/common:until-review` and
`/common:whereami` (through `cepa-plan`, `cepa-doctor`, `cepa-until-digest` and
`cepa-intent`) answer "what is the state?" from ONE place and with ONE liveness
rule, instead of four copies that drift ("um storage, uma conformidade").

The five deposits (each has exactly one writer family):

  fila       the queue: `.claude/queues/<n>/queue.yaml` (legacy:
             `.claude/programs/<n>/plan.yaml`). Written only by `cepa-plan`.
  run        the record of a `cepa-until` run: `<queue dir>/until/<run>.jsonl`
             and `<run>.estado.json` (+ `.log`, `.review.md`). Written by
             `cepa-until`; the `.estado.json` carries the `heartbeat`.
  handoff    `.claude/handoffs/<branch>.md` (+ `.claim`, `archive/`). Written by
             `_handoff.py`.
  sessao     live sessions: `.claude/sessions/<key>.json` (+ `.launch`,
             `.next.json`, `.prune-on-exit`). Written by the session-* hooks.
  autonomo   autonomous-mode run state: `docs/autonomous/<run>/state.yaml`.
             Written by `autonomous-checkpoint.py`.

Maestro's `wave-state.yaml` (frozen orchestrator) lives inside
`.claude/programs/<n>/`; it is catalogued, never read for decisions here.

The catalogue (`CATALOGUE`) lists EVERY known entry under `.claude/`, tagged
with its deposit or `None` ("not a state deposit": an artifact, a config, a
log). `tests/test_state_deposits.py` scans the writers in `common/` for
`.claude/<name>` literals and goes red when a name is not here, and
`cepa-doctor` warns about entries in a real `.claude/` that are not here. To add
a writer, declare it in `CATALOGUE` in the same change.

Run liveness has ONE rule, `run_liveness`: a `rodando` record is alive only when
its heartbeat is fresh (and, on the same host, its pid answers). A `rodando`
record with no heartbeat is `desconhecido`, never `vivo`.
"""
import fnmatch
import json
import os
from datetime import datetime
from pathlib import Path

import _queuepath as qp
import _wtlib as wt

# A run is presumed dead when its heartbeat is older than this many seconds. The
# only copy of the constant: `cepa-plan` imports it from here.
HEARTBEAT_STALE_SEC = float(os.environ.get("CEPA_HEARTBEAT_ORFA", "900"))

DEPOSITS = {
    "fila": "a fila (queue.yaml / plan.yaml)",
    "run": "o registro de um run do cepa-until",
    "handoff": "o handoff por branch",
    "sessao": "as sessões vivas",
    "autonomo": "o estado do modo autônomo",
}

# name (fnmatch glob, relative to `.claude/`) -> (deposit or None, who writes it).
CATALOGUE = {
    # the five deposits
    "queues": ("fila", "cepa-plan (layout novo; `until/` guarda os runs do cepa-until)"),
    "programs": ("fila", "cepa-plan (layout legado); maestro-wave-state grava wave-state.yaml aqui"),
    "handoffs": ("handoff", "_handoff.py, via /common:handoff e os hooks de sessão"),
    "sessions": ("sessao", "session-registry.py, session-launch.py, session-next.py, session-chain.py"),
    # not state deposits: artifacts, caches, configuration, logs
    "acceptance": (None, "/common:acceptance e completion-auditor (artefatos de aceite)"),
    "proof": (None, "/common:prove (artefatos de prova)"),
    "prove": (None, "/common:prove (rascunhos da prova)"),
    "ui-proof": (None, "ui-proof-reviewer (artefatos de prova de UI)"),
    "validation": (None, "validação de ciclo (artefatos)"),
    "external-tests": (None, "registro de testes externos (artefato)"),
    "waivers": (None, "cepa-plan (dispensas aprovadas pelo dono)"),
    "topology": (None, "cepa-topology (retrato da topologia do projeto)"),
    "deviations.md": (None, "registro de desvios, escrito à mão e por comandos"),
    "session-log.md": (None, "/session (diário da sessão)"),
    "session-intent": (None, "cepa-intent (intenção da sessão; lida por /common:whereami)"),
    "reminders": (None, "cepa-intent remind (lembretes do dono; lidos por /common:whereami e pelo hook de sessão)"),
    "session-mode": (None, "cepa-mode (modo da sessão)"),
    "mode-menu-pending": (None, "session-mode.py (menu do modo mostrado no turno anterior; consumido no seguinte para medir a escolha)"),
    "last-build.json": (None, "cepa-build (baseline do último build)"),
    "no-build": (None, "o dono (opta por não ter baseline de build)"),
    "last-root-install.json": (None, "bin/install.sh (registro da última instalação)"),
    "doctor-last-run": (None, "cepa-doctor (carimbo da última execução)"),
    "feedback-nudge": (None, "hook de feedback (carimbo)"),
    "feedback.md": (None, "/common:feedback (texto de feedback)"),
    "cepa-feedback": (None, "/common:feedback (fila de feedback)"),
    "cepa-validation-owed": (None, "validação devida (marcador)"),
    "reflection": (None, "/common:reflect (reflexões)"),
    "reflexao": (None, "/common:reflect (nome antigo)"),
    "rescued": (None, "_wtlib.rescue_artifacts (artefatos salvos de worktree descartado)"),
    "expertise": (None, "mental-model (link para a expertise dos agentes)"),
    "worktrees": (None, "worktrees internos do cepa"),
    "worktree-seed": (None, "o dono (lista de arquivos semeados em worktree)"),
    "env.yaml": (None, "o dono (manifesto de ambiente do projeto)"),
    "prompts": (None, "cepa-prompts (cache de prompts)"),
    "cepa-prompts": (None, "cepa-prompts (cache de prompts)"),
    "loop-state.json": (None, "loop de comandos (estado do laço)"),
    "editorial-lint": (None, "lint editorial (configuração)"),
    "board-flow.lifecycle.yaml": (None, "board-flow (ciclo de vida do quadro)"),
    "autonomy.yaml": (None, "o dono (override de bandas do modo autônomo)"),
    "settings.json": (None, "configuração do Claude Code"),
    "settings.local.json": (None, "configuração local do Claude Code"),
    "keybindings.json": (None, "configuração do Claude Code"),
    "hooks": (None, "hooks instalados"),
    "plugins": (None, "plugins instalados (home)"),
    "projects": (None, "memória por projeto do Claude Code (home)"),
    "cepa-report-style": (None, "report-style-lint.py (medições do formato do relatório, em ~/.claude)"),
    "cepa-telemetry": (None, "telemetria do cepa (home)"),
    "cepa-wt-index": (None, "_wtlib.index_register (índice worktree -> clone principal, em ~/.claude; lido por session-heartbeat)"),
    "ops": (None, "operações do instalador"),
    ".DS_Store": (None, "macOS"),
}

# Entries inside `.claude/sessions/` and `.claude/handoffs/` by file kind.
SESSIONS_KINDS = {
    "*.json": "sessão viva ou reserva (session-registry.py)",
    "*.next.json": "próximo passo do encadeamento (session-next.py)",
    "*.launch": "lançamentos do launcher (session-registry.py)",
    "*.prune-on-exit": "marcador de poda ao sair (session-registry.py)",
    ".launch.lock": "trava do lançador (session-launch.py)",
}
HANDOFFS_KINDS = {
    "*.md": "handoff da branch (_handoff.py)",
    "*.claim": "reserva da retomada (_handoff.py)",
    "archive": "handoffs arquivados (_handoff.py)",
}

# Deposits that live OUTSIDE `.claude/`.
EXTERNAL = {
    "docs/autonomous/<run>/state.yaml": ("autonomo", "autonomous-checkpoint.py"),
    ".claude/programs/<n>/wave-state.yaml": ("fila", "maestro-wave-state (orquestrador congelado)"),
}


def _match(name, patterns):
    return any(fnmatch.fnmatchcase(name, p) for p in patterns)


def catalogued(name):
    """True if `name` (a top-level entry of `.claude/`) is declared."""
    return _match(name, CATALOGUE)


def _unknown_in(d, kinds, label):
    if not d.is_dir():
        return []
    return [f"{label}/{p.name}" for p in sorted(d.iterdir())
            if not _match(p.name, kinds)]


def unknown_entries(root):
    """Entries under `<root>/.claude/` (top level, plus the file kinds inside
    `sessions/` and `handoffs/`) that the catalogue does not declare."""
    base = Path(root) / ".claude"
    if not base.is_dir():
        return []
    out = [p.name for p in sorted(base.iterdir()) if not catalogued(p.name)]
    out += _unknown_in(base / "sessions", SESSIONS_KINDS, "sessions")
    out += _unknown_in(base / "handoffs", HANDOFFS_KINDS, "handoffs")
    return out


# ── run liveness: the one rule ───────────────────────────────────────────

def _heartbeat_age(estado):
    """Seconds since the record's `heartbeat`, or None (absent / unparseable).
    A naive stamp (older files) is the writer's local time; aware carries its offset."""
    stamp = (estado or {}).get("heartbeat")
    if not stamp:
        return None
    try:
        beat = datetime.fromisoformat(str(stamp))
    except ValueError:
        return None
    if beat.tzinfo:
        cur = datetime.now(beat.tzinfo)
    else:
        cur = datetime.now()
    return (cur - beat).total_seconds()


heartbeat_age = _heartbeat_age


def _span(sec):
    sec = int(sec)
    if sec < 120:
        return f"{sec}s"
    if sec < 7200:
        return f"{sec // 60} min"
    return f"{sec // 3600}h"


def run_liveness(estado):
    """(state, detail) of a run record (the parsed `.estado.json`).

    state is `vivo`, `morto`, `desconhecido`, or the literal non-running estado
    (`esperando-dono`, `aterrissado`, `interrompido`, ...). Only `rodando` is
    judged: same host -> the pid must answer AND the heartbeat be fresh; other
    host -> the heartbeat only (a pid can't be probed there). No heartbeat
    (a file from before DUR-1) is `desconhecido`: never `vivo`.
    """
    est = estado if isinstance(estado, dict) else {}
    cur = est.get("estado")
    if cur != "rodando":
        return (cur or "desconhecido"), f"run {cur or 'sem estado'}: não está rodando"
    same_host = est.get("host") in (None, wt.host())
    if same_host and "pid" in est and not wt.pid_alive(est.get("pid")):
        return "morto", (f"rodando no registro mas MORTO: o pid {est.get('pid')} "
                         "não existe mais nesta máquina")
    age = _heartbeat_age(est)
    if age is None:
        return "desconhecido", ("rodando no registro, sem heartbeat legível "
                                "(registro anterior ao heartbeat): não dá para "
                                "dizer se está vivo")
    if age < -HEARTBEAT_STALE_SEC:
        return "desconhecido", (f"rodando no registro, mas o heartbeat está no "
                                f"futuro ({_span(-age)} à frente): relógio de "
                                "outra máquina adiantado; não dá para dizer se "
                                "está vivo")
    if age > HEARTBEAT_STALE_SEC:
        return "morto", (f"rodando no registro mas MORTO: último heartbeat há "
                         f"{_span(age)}")
    return "vivo", f"rodando, vivo (heartbeat há {_span(age)})"


# ── readers of the five deposits ─────────────────────────────────────────

def _load_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def main_root(cwd):
    """The main clone, where every deposit lives, from any linked worktree."""
    return wt.main_root(cwd)


def runs(root):
    """[{path, estado, liveness: (state, detail)}] for every `*.estado.json`, both layouts."""
    found = []
    for base in (qp.LEGACY_DIR, qp.NEW_DIR):
        for path in sorted((Path(root) / base).glob("*/until/*.estado.json")):
            est = _load_json(path)
            if est is not None:
                found.append({"path": path, "estado": est,
                              "liveness": run_liveness(est)})
    return found


def run_of(root, run_id=None, tree=None):
    """The run record whose `run` is `run_id`, else whose `arvore` is `tree`. Or None."""
    all_runs = runs(root)
    if run_id:
        for r in all_runs:
            if r["estado"].get("run") == run_id:
                return r
    if tree:
        for r in all_runs:
            if r["estado"].get("arvore") and wt.same_path(r["estado"]["arvore"], tree):
                return r
    return None


def sessions(root):
    """[{path, entry, live}] for every session registry entry."""
    return [{"path": p, "entry": e,
             "live": bool(isinstance(e, dict) and wt.entry_is_live(e))}
            for p, e in wt.read_entries(root)]


def handoffs(root):
    """[{path, meta}] for every handoff of the branches (archive/ excluded)."""
    import _handoff as ho
    d = ho.handoffs_dir(root)
    if not d.is_dir():
        return []
    return [{"path": p, "meta": ho.parse(p)[0]} for p in sorted(d.glob("*.md"))]


def queues(root):
    """[(name, path)] of every queue file, both layouts (wave plans included: the
    caller filters by `mode`)."""
    return qp.queue_files(root)


def autonomous_runs(root):
    """[{run, path, state}] for `docs/autonomous/<run>/state.yaml`; [] if absent."""
    d = Path(root) / "docs" / "autonomous"
    if not d.is_dir():
        return []
    import _autonomy
    found = []
    for path in sorted(d.glob("*/state.yaml")):
        try:
            data = _autonomy._read_yaml(path)
        except ImportError:  # no PyYAML: list the run without its content
            data = None
        found.append({"run": path.parent.name, "path": path, "state": data})
    return found


def snapshot(root):
    """All five deposits plus the unknown entries."""
    return {"fila": queues(root), "run": runs(root),
            "handoff": handoffs(root), "sessao": sessions(root),
            "autonomo": autonomous_runs(root),
            "unknown": unknown_entries(root)}
