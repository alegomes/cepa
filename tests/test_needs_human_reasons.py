"""Regression of the NEEDS-HUMAN reason classifier.

The fixtures in tests/fixtures/needs-human/ are the 33 real artifacts that the
2026-08-03 pilot found in wego-assinatura-backend and wego-tasy-gateway,
reduced to the fields the classifier reads. The expected classification below
was checked by hand, artifact by artifact.

Why this suite exists: the first version of the classifier got 7 of the 33 wrong
by reading only one of the two spellings of level name that exist on disk — among
them WEGO-1698, which is the reference case in the documentation.
"""
import os
import sys

import pytest

yaml = pytest.importorskip("yaml")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "board-flow", "bin"))
from classify_needs_human import (  # noqa: E402
    REASONS,
    NOT_A_QUESTION,
    QUEUE_ORDER,
    classify,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "needs-human")

# card -> expected reason
EXPECTED = {
    # The proof did not even get to run — nobody decides anything here
    "WEGO-1558": "nao-rodou",
    "WEGO-1698": "nao-rodou",   # PIT absent from the whole project
    "WEGO-1732": "nao-rodou",
    "WEGO-1763": "nao-rodou",
    "WEGO-1769": "nao-rodou",
    "WEGO-1770": "nao-rodou",
    "WEGO-1812": "nao-rodou",
    "WEGO-1949": "nao-rodou",
    "WEGO-1958": "nao-rodou",
    "WEGO-1675": "nao-rodou",
    "WEGO-1785": "nao-rodou",   # the harness lock blocked the write of the proof
    # The test cannot see this change
    "WEGO-1529": "teste-cego",
    "WEGO-1538": "teste-cego",
    "WEGO-1540": "teste-cego",
    "WEGO-1546": "teste-cego",
    "WEGO-1611": "teste-cego",
    "WEGO-1710": "teste-cego",  # red-on-base only by analytical argument
    "WEGO-1778": "teste-cego",  # collective-only perturbation (two gates together)
    "WEGO-1783": "teste-cego",
    "WEGO-1510": "teste-cego",  # PlugSign's live surface is not reachable in the automated run
    "WEGO-1614": "teste-cego",  # reverting only the piece does not compile on the base commit
    "WEGO-1619": "teste-cego",  # the @QuarkusTest that asserts the 400 on rejection is missing
    # Has the three signals of a doc-only diff (changed_classes empty, L4 n/a,
    # perturbation skipped), but the only file is application.properties:
    # configuration changes behavior, it is not "nothing to prove".
    "WEGO-2021": "teste-cego",
    # There was nothing to prove here
    # Parent Epic without its own base commit. Classified `nao-rodou` until 2026-08-04,
    # when the first real run of /board-flow:decide showed the cost: `nao-rodou`
    # is the only reason that leaves the human's front without asking, and its prescribed exit
    # is to re-run the proof — which on an Epic returns the same result
    # forever. The artifact already said in prose "does not fabricate a synthetic diff aggregating
    # the 8 child Stories"; the rule was missing a look at issue_type.
    "WEGO-1550": "nada-a-provar",
    "WEGO-1658": "nada-a-provar",   # documentation-only card
    "WEGO-1709": "nada-a-provar",   # pure ADR
    "WEGO-1962": "nada-a-provar",   # an HTTP fuzzer does not fit in log leakage
    # Only .md, recognized by structure (changed_classes empty, L4 n/a,
    # perturbation skipped): the prose does not match DIFF_WITHOUT_PRODUCTION and until
    # 2026-09-25 the three fell into `teste-cego` through the skipped-perturbation
    # fallback. They came from the prove-drain of wego-acesso-backend.
    "WEGO-2117": "nada-a-provar",
    "WEGO-2275": "nada-a-provar",
    "WEGO-2276": "nada-a-provar",
    # The tests run, but hold little
    "WEGO-1564": "guarda-fraca",    # PedidoAssinatura, 60% of the mutants killed
    # Behavior appeared that no test checks
    "WEGO-1819": "sem-cobertura",
    # These four expected `nao-rodou` until 2026-08-22, and the expectation was
    # what was wrong, not the rule. On 2026-08-14 the structural check of
    # `l4_adversarial_input.status == "findings"` moved up to BEFORE the prose
    # matchers, because the text of the finding itself was routing the card: an
    # artifact whose prose cites "quarkus-jacoco not configured" or "PIT absent
    # from the worktree's pom" matched the "did not run" pattern and fell into the ONLY
    # bucket that leaves the human's front without asking. That is how WEGO-1894
    # (hash collision) and WEGO-1897 (NUL byte taking the API down) vanished from the
    # prove-drain queue of wego-acesso-backend.
    #
    # In the four the proof RAN — perturbation with green→red→green recorded
    # — and L4 found things that need a human decision:
    #   1612: GET ?syncStatus=true transitions ENVIADO→ABERTO and no @QuarkusTest
    #         asserts the transition.
    #   1663: 14 @Disabled tests delivered inside a card whose title is
    #         "complete E2E coverage" (high-severity finding).
    #   1682: four findings that the routing_reason itself orders triaged.
    #   1683: the flag wego.refresh-on-dispatch.enabled defaults to false and has no
    #         override in %prod — production without the protection the card delivered.
    # Keeping `nao-rodou` here would be asking the command to hide the four.
    "WEGO-1612": "sem-cobertura",
    "WEGO-1663": "sem-cobertura",
    "WEGO-1682": "sem-cobertura",
    "WEGO-1683": "sem-cobertura",
    # Depends on someone outside
    "WEGO-1757": "fora-do-alcance",  # schedule in Bitbucket + Tecnospeed quota
    # The six of fb-20261106-2 (wego-acessos-backend Review, 2026-11-06). Each
    # artifact already NAMED its reason in a field of its own, and the
    # classifier ignored the field and matched loose phrases instead:
    #   2357, 2368, 2369: a derived base_commit (`base_commit_resolved: false`,
    #     comment ".claude/cards/<KEY>.yaml nao existe") came out `nao-rodou`
    #     while `motivo_needs_human` says nada-a-provar / teste-cego;
    #   2044, 2416: a level SKIPPED by `bash-path-lock` in a proof that ran
    #     came out `nao-rodou` ("trava do próprio harness"), while
    #     `routing_reason` / `needs_human_motivo` name the reason;
    #   2355: `verdict: proven` held before Done (`done_transition_held.reason`)
    #     came out `sem-motivo`.
    "WEGO-2357": "nada-a-provar",    # motivo_needs_human (under inspection)
    "WEGO-2368": "nada-a-provar",    # motivo_needs_human (under inspection)
    "WEGO-2369": "teste-cego",       # motivo_needs_human (under inspection)
    "WEGO-2044": "fora-do-alcance",  # routing_reason: 'motivo "fora-do-alcance"'
    "WEGO-2416": "nada-a-provar",    # needs_human_motivo (top level)
    "WEGO-2355": "fora-do-alcance",  # done_transition_held.reason
}


def _load(card):
    with open(os.path.join(FIXTURES, f"{card}.yaml")) as fh:
        return yaml.safe_load(fh)


@pytest.mark.parametrize("card,reason", sorted(EXPECTED.items()))
def test_classifies_real_artifact(card, reason):
    slug, evidence = classify(_load(card))
    assert slug == reason, f"{card}: esperado {reason}, veio {slug} ({evidence})"
    assert evidence, f"{card}: motivo sem evidência para mostrar ao usuário"


def test_all_fixtures_are_covered():
    on_disk = {f[:-5] for f in os.listdir(FIXTURES) if f.endswith(".yaml")}
    assert on_disk == set(EXPECTED), (
        "fixture sem classificação esperada (ou vice-versa): "
        f"{on_disk ^ set(EXPECTED)}"
    )


def test_no_real_artifact_falls_into_no_reason():
    """The list is closed, but it needs to cover what really exists.

    A `sem-motivo` here means the list of seven was left incomplete — it is
    a sign of a new reason to discuss with the owner, never of a rule to loosen.
    """
    orphans = [c for c in EXPECTED if classify(_load(c))[0] == "sem-motivo"]
    assert not orphans, f"artefatos sem motivo: {orphans}"


def test_epic_only_leaves_not_run_when_it_has_no_base_commit():
    """The Epic guard is narrow on purpose.

    It exists for the parent Epic that will never have its own diff (WEGO-1550). An Epic
    WITH a resolved base commit has a diff and remains subject to all the
    following rules — sweeping every Epic into `nada-a-provar` would hide real proof.
    WEGO-1732 is that case: Epic, resolved base_commit, and the artifact points to
    mutants that really survived.
    """
    mil732 = _load("WEGO-1732")
    assert mil732["issue_type"] == "Epic"
    assert mil732["base_commit"], "fixture perdeu o commit-base que faz o caso"
    assert classify(mil732)[0] != "nada-a-provar"

    # and the same Epic, if it lost the base commit, would fall into the guard
    without_base = dict(mil732, base_commit=None, scope={"base_commit_resolved": False})
    assert classify(without_base)[0] == "nada-a-provar"


def test_doc_only_diff_only_leaves_blind_test_with_the_three_signals():
    """The structural `nada-a-provar` rule is narrow on purpose.

    It needs all three: `changed_classes` WRITTEN and empty, perturbation `skipped`
    and L4 `n/a` — and, when the artifact lists `changed_files`, every file has
    to be documentation. If any is missing, the card goes on to the fallback and remains
    `teste-cego` — otherwise the rule would swallow a perturbation that did not run on a diff
    with real code.
    """
    doc = _load("WEGO-2117")
    assert classify(doc) == (
        "nada-a-provar", "diff sem classe de produção (changed_classes vazio)")

    without_key = dict(doc, scope={"base_commit_resolved": True})
    with_class = dict(doc, scope={"base_commit_resolved": True,
                                  "changed_classes": ["com.wego.Foo"]})
    levels_l4_ran = dict(doc["levels"])
    levels_l4_ran["l4_adversarial_input"] = {"status": "pass"}
    l4_ran = dict(doc, levels=levels_l4_ran)
    config = dict(doc, scope=dict(doc["scope"], changed_files=[
        {"file": "docs/x.md"}, {"file": "bootstrap/src/main/resources/application.properties"}]))
    for case in (without_key, with_class, l4_ran, config):
        assert classify(case)[0] == "teste-cego"

    # A perturbation that RAN is not a diff with nothing to prove, even with only .md.
    # Synthetic and without prose: WEGO-2117's matches another `nada-a-provar` rule
    # and would hide the condition this case exists to hold.
    pert_ran = {
        "card": "X-4", "verdict": "needs-human", "base_commit": "abc1234",
        "scope": {"changed_classes": [], "changed_files": [{"file": "docs/x.md"}]},
        "levels": {"l3_load_bearing": {"perturbation": {"status": "pass"}},
                   "l2_coverage": {"status": "assumed"},
                   "l4_adversarial_input": {"status": "n/a"}},
    }
    assert classify(pert_ran)[0] != "nada-a-provar"


def test_l2_waived_is_not_a_blocked_level():
    from classify_needs_human import _blocked_levels
    levels = {"l2_coverage": {"status": "waived"},
              "l4_adversarial_input": {"status": "skipped"}}
    assert _blocked_levels(levels) == [("L4", "skipped")]


def test_only_not_run_stops_becoming_a_question():
    assert NOT_A_QUESTION == {"nao-rodou"}


def test_queue_order_covers_every_reason_that_becomes_a_question():
    askable = set(REASONS) - NOT_A_QUESTION - {"sem-motivo"}
    assert set(QUEUE_ORDER) == askable
    assert QUEUE_ORDER[0] == "sem-cobertura", "a fila abre pelo de maior risco"


def test_accepts_both_level_spellings():
    """The old spelling and schema 2 must give the same reason.

    Reading only the documented one was the mistake that classified 7 of the 33 wrong.
    """
    old = {
        "card": "X-1", "verdict": "needs-human", "base_commit": "abc1234",
        "routing_reason": "L4 encontrou algo",
        "levels": {"l4_adversarial_input": {"status": "findings",
                                            "findings": ["header aceito sem validação"]}},
    }
    new = dict(old)
    new["levels"] = {"l4_adversarial_input": dict(old["levels"]["l4_adversarial_input"])}
    assert classify(old)[0] == classify(new)[0] == "sem-cobertura"

    perturbed_old = {
        "card": "X-2", "verdict": "needs-human", "base_commit": "abc1234",
        "routing_reason": "sem prova externa",
        "levels": {"l3_diff_mutation": {"status": "skipped", "note": "sem detalhe"}},
    }
    perturbed_new = {
        "card": "X-2", "verdict": "needs-human", "base_commit": "abc1234",
        "routing_reason": "sem prova externa",
        "levels": {"l3_load_bearing": {"perturbation": {"status": "skipped",
                                                        "results": ["sem detalhe"]}}},
    }
    assert classify(perturbed_old)[0] == classify(perturbed_new)[0] == "teste-cego"


def test_unknown_case_does_not_invent_a_reason():
    unknown = {
        "card": "X-3", "verdict": "needs-human", "base_commit": "abc1234",
        "routing_reason": "algo que nunca vimos antes",
        "levels": {"l2_coverage": {"status": "assumed"}},
    }
    slug, _ = classify(unknown)
    assert slug == "sem-motivo"


def _synthetic(**extra):
    """A NEEDS-HUMAN artifact whose prose would match `nao-rodou` by itself."""
    d = {
        "card": "X-5", "verdict": "needs-human", "base_commit": "abc1234",
        "scope": {"base_commit_resolved": True},
        "levels": {"l2_coverage": {"status": "skipped",
                                   "note": "negado pelo bash-path-lock"}},
    }
    d.update(extra)
    return d


def test_declared_reason_field_beats_phrase_matching():
    """fb-20261106-2: the artifact's own reason field is read before any phrase.

    Without the field the prose ("bash-path-lock") routes the card to
    `nao-rodou`, the only reason that spares the human. Each of the three
    field names, and the nested `inspection.motivo_needs_human`, has to win.
    """
    assert classify(_synthetic())[0] == "nao-rodou", "the case lost its phrase"
    for case in (
        _synthetic(needs_human_motivo="teste-cego"),
        _synthetic(motivo_needs_human="teste-cego (motivo 2): o dublê engole"),
        _synthetic(inspection={"motivo_needs_human": "teste-cego: sem guarda"}),
        _synthetic(routing_reason="NEEDS-HUMAN motivo 2 (teste-cego). Sem guarda."),
        _synthetic(routing_reason='NEEDS-HUMAN, motivo "teste-cego" do documento.'),
    ):
        slug, evidence = classify(case)
        assert slug == "teste-cego", case
        assert evidence


def test_declared_reason_accepts_only_the_closed_list():
    """A field naming a reason outside the seven does not invent an eighth."""
    for value in ("motivo-inventado", "sem-motivo", ""):
        assert classify(_synthetic(needs_human_motivo=value))[0] == "nao-rodou"


def test_routing_reason_counts_only_after_the_word_motivo():
    """Loose prose that merely mentions a slug is not a declaration.

    `routing_reason` is free text: a slug cited in passing ("não é
    nada-a-provar") must not route the card. Only "motivo <slug>",
    "motivo N (<slug>)" or 'motivo "<slug>"' declares it.
    """
    loose = _synthetic(routing_reason="não é nada-a-provar, a prova não rodou")
    assert classify(loose)[0] == "nao-rodou"


def test_l4_finding_still_beats_a_declared_reason():
    """The fact beats the text, including a declared field (WEGO-1894/1897)."""
    d = _synthetic(needs_human_motivo="nada-a-provar")
    d["levels"]["l4_adversarial_input"] = {"status": "findings",
                                           "findings": ["NUL derruba a API"]}
    assert classify(d)[0] == "sem-cobertura"


def test_declared_slug_must_be_a_whole_token():
    """A slug glued to a prefix ("xx-teste-cego") is not a declaration."""
    for value in ("xx-teste-cego", "pre_teste-cego", "teste-cego-xx"):
        assert classify(_synthetic(needs_human_motivo=value))[0] == "nao-rodou", value


def test_declared_field_must_be_a_scalar():
    """A nested value that merely contains a slug does not declare it."""
    for value in ({"slug": "teste-cego"}, ["teste-cego"]):
        assert classify(_synthetic(needs_human_motivo=value))[0] == "nao-rodou", value


def test_bare_declared_slug_shows_a_readable_evidence():
    """The evidence is read by the owner; a bare slug becomes a sentence."""
    assert classify(_synthetic(needs_human_motivo="teste-cego")) == (
        "teste-cego", "motivo declarado no próprio artefato de prova")
    long_value = "teste-cego (motivo 2): o dublê engole o sinal"
    assert classify(_synthetic(needs_human_motivo=long_value)) == ("teste-cego", long_value)
