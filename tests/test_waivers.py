"""Regression of the human's waivers (board-flow/bin/waivers.py).

What these tests protect: that the same question does not come back (it is the reason the
file exists), and that a waiver is never valid without author, reason and revisit
trigger — an anonymous waiver with no deadline is exactly what the proof gate exists
to prevent, only recorded on disk.
"""
import os
import sys
from datetime import date

import pytest

yaml = pytest.importorskip("yaml")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "board-flow", "bin"))
import waivers  # noqa: E402

TODAY = date(2026, 8, 3)


@pytest.fixture(autouse=True)
def outside_autonomous_run(monkeypatch):
    """The suite may run inside a cepa-until window (`CEPA_UNTIL_RUN`
    set): the tests that expect a real waiver need a clean environment.
    """
    monkeypatch.delenv("CEPA_UNTIL_RUN", raising=False)
    monkeypatch.delenv("CLAUDE_AUTONOMOUS_RUN_ID", raising=False)


def _write(repo, **kw):
    base = dict(reason="teste-cego", scope="PlugSignAdapter",
                rationale="aceito a prova interna: o fornecedor não é alcançável no automatizado",
                author="alegomes", revisit_trigger="quando o adapter mudar")
    base.update(kw)
    return waivers.write(repo, today=TODAY, **base)


def test_recorded_waiver_prevents_the_same_question(tmp_path):
    repo = str(tmp_path)
    _write(repo)
    loaded = waivers.load(repo)
    assert len(loaded) == 1
    assert waivers.applicable(loaded, "teste-cego", "PlugSignAdapter", TODAY)


def test_different_scope_still_asks(tmp_path):
    repo = str(tmp_path)
    _write(repo)
    loaded = waivers.load(repo)
    assert waivers.applicable(loaded, "teste-cego", "TasyGatewayAdapter", TODAY) is None


def test_different_reason_in_same_scope_still_asks(tmp_path):
    repo = str(tmp_path)
    _write(repo)
    loaded = waivers.load(repo)
    assert waivers.applicable(loaded, "guarda-fraca", "PlugSignAdapter", TODAY) is None


def test_scope_matches_by_slug_not_by_spelling(tmp_path):
    repo = str(tmp_path)
    _write(repo)
    loaded = waivers.load(repo)
    assert waivers.applicable(loaded, "teste-cego", "plugsign adapter", TODAY)


def test_trigger_with_expired_date_asks_again(tmp_path):
    repo = str(tmp_path)
    _write(repo, revisit_trigger="revisar em 2026-07-01")
    loaded = waivers.load(repo)
    assert waivers.applicable(loaded, "teste-cego", "PlugSignAdapter", TODAY) is None
    assert waivers.expired(loaded[0], TODAY)


def test_trigger_with_future_date_still_waives(tmp_path):
    repo = str(tmp_path)
    _write(repo, revisit_trigger="revisar em 2026-12-31")
    loaded = waivers.load(repo)
    assert waivers.applicable(loaded, "teste-cego", "PlugSignAdapter", TODAY)


def test_prose_trigger_is_not_evaluated_by_code(tmp_path):
    """Prose is shown to the human, never interpreted here.

    Code that decided by itself that "when the adapter changes" has already happened
    would be waiving on its own — which is what the gate forbids.
    """
    repo = str(tmp_path)
    _write(repo, revisit_trigger="quando o adapter mudar")
    assert not waivers.expired(waivers.load(repo)[0], TODAY)


@pytest.mark.parametrize("missing", ["rationale", "author", "revisit_trigger"])
def test_does_not_record_waiver_without_required_field(tmp_path, missing):
    with pytest.raises(ValueError):
        _write(str(tmp_path), **{missing: ""})


def test_malformed_file_is_ignored_instead_of_waiving(tmp_path):
    """The safe side is to ignore: a waiver without author or deadline that held
    would waive a proof with no one able to say who waived it.
    """
    d = tmp_path / ".claude" / "waivers"
    d.mkdir(parents=True)
    (d / "teste-cego--plugsignadapter.yaml").write_text(
        "motivo: teste-cego\nescopo: PlugSignAdapter\n", encoding="utf-8")
    loaded = waivers.load(str(tmp_path))
    assert loaded == []


def test_what_was_recorded_is_human_readable(tmp_path):
    path = _write(str(tmp_path))
    d = yaml.safe_load(open(path))
    assert d["autor"] == "alegomes"
    assert d["criado_em"] == "2026-08-03"
    assert "prova interna" in d["razao"]


# ── autonomous run: a waiver is a proposal, only the owner converts (fb-20261014-3) ──

RUN_VARS = ["CEPA_UNTIL_RUN", "CLAUDE_AUTONOMOUS_RUN_ID"]


def _in_run(monkeypatch, var):
    monkeypatch.setenv(var, "1" if var == "CEPA_UNTIL_RUN" else "run-42")


def _outside_run(monkeypatch):
    for v in RUN_VARS:
        monkeypatch.delenv(v, raising=False)


@pytest.mark.parametrize("var", RUN_VARS)
def test_in_autonomous_run_recording_becomes_proposal(tmp_path, monkeypatch, var):
    repo = str(tmp_path)
    _in_run(monkeypatch, var)
    assert waivers.in_autonomous_run()
    path = _write(repo, queue="fila", item="a1")
    d = yaml.safe_load(open(path))
    assert d["status"] == "proposta"
    assert "autor" in d and d["autor"] is None
    assert "alegomes" in d["proposto_por"]
    assert (d["fila"], d["item"]) == ("fila", "a1")
    assert d["pergunta"].startswith("Aceito a dispensa de PlugSignAdapter")
    assert waivers.load(repo) == []
    assert waivers.applicable(waivers.load(repo), "teste-cego", "PlugSignAdapter", TODAY) is None
    assert [p["_path"] for p in waivers.proposals(repo)] == [path]


def test_run_id_appears_in_proposto_por(tmp_path, monkeypatch):
    _in_run(monkeypatch, "CLAUDE_AUTONOMOUS_RUN_ID")
    d = yaml.safe_load(open(_write(str(tmp_path))))
    assert "run-42" in d["proposto_por"]


@pytest.mark.parametrize("var", RUN_VARS)
def test_convert_and_refuse_are_forbidden_in_the_run(tmp_path, monkeypatch, var):
    repo = str(tmp_path)
    _in_run(monkeypatch, var)
    _write(repo)
    with pytest.raises(PermissionError):
        waivers.convert(repo, "teste-cego", "PlugSignAdapter", "alegomes")
    with pytest.raises(PermissionError):
        waivers.decline(repo, "teste-cego", "PlugSignAdapter", "não")
    assert waivers.load(repo) == []


def test_owner_converts_the_proposal_into_a_valid_waiver(tmp_path, monkeypatch):
    repo = str(tmp_path)
    _in_run(monkeypatch, "CEPA_UNTIL_RUN")
    _write(repo, queue="fila", item="a1")
    _outside_run(monkeypatch)
    waivers.convert(repo, "teste-cego", "PlugSignAdapter", "alegomes",
                      answer="sim: aceito", today=TODAY)
    w = waivers.applicable(waivers.load(repo), "teste-cego", "PlugSignAdapter", TODAY)
    assert w is not None
    assert w["autor"] == "alegomes" and "status" not in w
    assert w["criado_em"] == "2026-08-03"
    assert w["resposta_do_dono"] == "sim: aceito"
    assert "alegomes" in w["proposto_por"] and w["proposto_em"] == "2026-08-03"
    assert waivers.proposals(repo) == []


def test_convert_without_proposal_or_over_real_waiver(tmp_path):
    repo = str(tmp_path)
    with pytest.raises(FileNotFoundError):
        waivers.convert(repo, "teste-cego", "PlugSignAdapter", "alegomes")
    _write(repo)  # outside the run: real waiver
    with pytest.raises(ValueError):
        waivers.convert(repo, "teste-cego", "PlugSignAdapter", "alegomes")
    with pytest.raises(ValueError):
        waivers.convert(repo, "teste-cego", "PlugSignAdapter", "")


def test_refuse_leaves_the_proposal_without_effect(tmp_path, monkeypatch):
    repo = str(tmp_path)
    _in_run(monkeypatch, "CEPA_UNTIL_RUN")
    path = _write(repo)
    _outside_run(monkeypatch)
    waivers.decline(repo, "teste-cego", "PlugSignAdapter", "não: prova de verdade", today=TODAY)
    d = yaml.safe_load(open(path))
    assert d["status"] == "recusada" and d["recusada_em"] == "2026-08-03"
    assert d["resposta_do_dono"] == "não: prova de verdade"
    assert waivers.load(repo) == [] and waivers.proposals(repo) == []


def test_proposal_status_never_waives_even_with_author_filled(tmp_path):
    d = tmp_path / ".claude" / "waivers"
    d.mkdir(parents=True)
    (d / "teste-cego--x.yaml").write_text(
        "status: proposta\nmotivo: teste-cego\nescopo: X\nrazao: r\nautor: alguem\n"
        "criado_em: 2026-08-03\nrevisit_trigger: t\n", encoding="utf-8")
    assert waivers.load(str(tmp_path)) == []


@pytest.mark.parametrize("var", RUN_VARS)
def test_propose_does_not_overwrite_valid_waiver(tmp_path, monkeypatch, var):
    repo = str(tmp_path)
    path = _write(repo)  # real waiver by the owner, outside the run
    before = open(path).read()
    _in_run(monkeypatch, var)
    again = _write(repo, rationale="outra razão qualquer")
    assert again == path
    assert open(path).read() == before
    assert waivers.applicable(waivers.load(repo), "teste-cego", "PlugSignAdapter", TODAY)


def test_propose_overwrites_old_proposal_and_requires_fields(tmp_path):
    repo = str(tmp_path)
    kw = dict(reason="teste-cego", scope="X", rationale="r1", revisit_trigger="t",
              proposed_by="agente", today=TODAY)
    path = waivers.propose(repo, **kw)
    waivers.propose(repo, **dict(kw, rationale="r2"))
    assert yaml.safe_load(open(path))["razao"] == "r2"
    for missing in ("rationale", "revisit_trigger", "proposed_by"):
        with pytest.raises(ValueError):
            waivers.propose(repo, **dict(kw, **{missing: ""}))


def test_propose_does_not_reopen_what_the_owner_refused(tmp_path, monkeypatch):
    repo = str(tmp_path)
    _in_run(monkeypatch, "CEPA_UNTIL_RUN")
    path = _write(repo)
    _outside_run(monkeypatch)
    waivers.decline(repo, "teste-cego", "PlugSignAdapter", "não: prova de verdade", today=TODAY)
    _in_run(monkeypatch, "CEPA_UNTIL_RUN")
    assert _write(repo, rationale="outra tentativa") == path
    d = yaml.safe_load(open(path))
    assert d["status"] == "recusada"
    assert d["resposta_do_dono"] == "não: prova de verdade"


def test_corrupted_yaml_is_ignored_without_taking_down_the_other_waivers(tmp_path):
    repo = str(tmp_path)
    _write(repo)
    (tmp_path / ".claude" / "waivers" / "quebrado.yaml").write_text(
        "motivo: [unclosed", encoding="utf-8")
    assert [w["motivo"] for w in waivers.load(repo)] == ["teste-cego"]
    assert waivers.proposals(repo) == []
