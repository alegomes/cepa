#!/usr/bin/env python3
"""Classifies a NEEDS-HUMAN verdict into one of the seven reasons.

Input:  the dict of a proof artifact (`docs/proof/<KEY>.yaml`, or the
        `.claude/proof/<KEY>.yaml` of the old rounds).
Output: (slug, evidence) — the evidence is the phrase that made the rule match,
        so the command can show it without the user opening the file.

The reasons, what each one means and who decides each one are in
docs/needs-human-motivos.md. The list is CLOSED: a case that matches no rule
comes out as `sem-motivo`, and `/board-flow:decide` stops and warns — it never
invents an eighth reason at run time, because an invented reason is what makes
a recorded waiver later match the wrong card.

The regression suite is tests/test_needs_human_reasons.py, built on 33 real
artifacts from wego-assinatura-backend and wego-tasy-gateway.

Usage as a script (read-only, writes nothing):
    classify_needs_human.py <repo> [<repo> ...]
"""
from __future__ import annotations

import glob
import os
import re
import sys

REASONS = {
    "nao-rodou": "A prova não chegou a rodar",
    "teste-cego": "O teste não consegue enxergar essa mudança",
    "sem-cobertura": "Apareceu comportamento que nenhum teste confere",
    "guarda-fraca": "Os testes rodam, mas seguram pouco",
    "nao-separavel": "Dois cards, uma mudança só",
    "nada-a-provar": "Não havia o que provar aqui",
    "fora-do-alcance": "Depende de alguém de fora",
    "sem-motivo": ">>> não cabe em nenhum motivo",
}

# Only this one does not become a question for the human: nobody decides
# anything about a Docker that did not come up. The command re-runs and, if it
# persists, opens ONE infra card.
NOT_A_QUESTION = {"nao-rodou"}

# The order of the queue the user reads: decreasing risk. `nao-rodou` is left
# out because it never becomes a question.
QUEUE_ORDER = [
    "sem-cobertura",
    "teste-cego",
    "guarda-fraca",
    "nao-separavel",
    "fora-do-alcance",
    "nada-a-provar",
]

# The artifacts on disk use two spellings for the same levels (see
# docs/needs-human-motivos.md). Reading only the documented one loses half the base.
ALIAS = {
    "l2": ("l2_coverage", "l2_external_coverage"),
    "l3": ("l3_load_bearing", "l3_diff_mutation"),
    "l4": ("l4_adversarial_input",),
    "bug": ("bugfix_regression_red_at_base", "bugfix_regression_red_on_base"),
}


def _level(levels: dict, key: str) -> dict:
    for name in ALIAS[key]:
        if name in levels:
            value = levels[name]
            return value if isinstance(value, dict) else {"status": value}
    return {}


def _text(*values) -> str:
    return " ".join(str(v) for v in values if v).lower()


# Each pattern below came from a real artifact; the cited card is the living example.
OUT_OF_REACH = [
    (r"decis[ãa]o operacional", "decisão operacional fora da sessão"),        # WEGO-1757
    (r"n[ãa]o fa[çc]o merge|n[ãa]o edito o schedule|fora do meu poder", "ação que a sessão não pode executar"),
    (r"n[ãa]o confirmad[ao] com a |aguardando (o |a )?(fornecedor|terceiro)", "pendente de confirmação de terceiro"),
]

# Only the diff matters here: no production line changed.
DIFF_WITHOUT_PRODUCTION = [
    (r"no production (code|line)|nenhuma linha de produ[çc][ãa]o", "diff sem código de produção"),   # WEGO-1709
    (r"pure adr|doc-only|somente documenta|apenas documenta", "diff só de documentação"),            # WEGO-1658
    (r"nothing to perturb|structurally inapplicable|estruturalmente inaplic", "não há o que perturbar"),
]

# The other half of reason 6: everything was proved, and ONE check does not fit
# this kind of change. Only valid with the structural test in `classify` — the
# phrase alone shows up in the prose of unrelated artifacts ("PIT does not
# apply", "regression check not applicable" on a card that is not a bug) and
# would steal half the base for the wrong reason.
CHECK_NOT_APPLICABLE = [
    (r"n[ãa]o se aplica|not applicable|n[ãa]o [ée] aplic[áa]vel|lacuna de expressividade do schema",
     "checagem que não cabe nesse tipo de mudança"),                                                 # WEGO-1962
]

DID_NOT_RUN = [
    # The polarity is mandatory. The previous version matched the bare word
    # "docker" and, in a Quarkus project, EVERY well-made external proof
    # artifact cites Testcontainers — even saying "Docker OK". Since `nao-rodou`
    # is the only reason that leaves the queue without going through the human,
    # the rule erased precisely the proofs that ran right. Found on 2026-08-14
    # in the prove-drain of wego-acesso-backend: WEGO-1894 and WEGO-1897, both
    # with real Postgres and a security finding, were classified "Docker
    # unavailable" because of the phrase "Docker OK". The other rules in this
    # block always required the unavailability marker ("jacoco ausente", "pit
    # absent"); this one was the exception.
    (r"(docker|dev services|testcontainers?)[^.\n]{0,60}"
     r"(indispon[íi]vel|unavailable|not (available|running|started|installed)|"
     r"n[ãa]o (subiu|iniciou|est[áa] (dispon[íi]vel|rodando)|dispon[íi]vel)|"
     r"fora do ar|ausente|down)"
     r"|(?:sem|no|without) (docker|dev services|testcontainers?)"
     r"|(?:cannot|could not|unable to|n[ãa]o (?:consegui|foi poss[íi]vel)) "
     r"(?:connect to |start |iniciar |subir |conectar (?:a|ao|no) )?"
     r"(?:the )?(docker|dev services|testcontainers?)",
     "Docker/Dev Services indisponível"),                                                            # WEGO-1683
    (r"jacoco (ausente|absent|n[ãa]o|missing)|no quarkus-jacoco|sem quarkus-jacoco|jacoco not (configured|wired)|no quarkus-jacoco wired",
     "ferramenta de cobertura ausente no projeto"),
    (r"pit is absent|pit ausente|pitest (absent|ausente|not configured)|no pit plugin",
     "PIT ausente no projeto"),                                                                      # WEGO-1698
    (r"path-lock|path_lock|bloqueio do harness|permiss[ãa]o negada pelo hook",
     "trava do próprio harness bloqueou a prova"),                                                   # WEGO-1785
    (r"base_commit (missing|ausente|n[ãa]o)", "commit-base ausente"),
    (r"build (falhou|failed|quebrado)|compilation (error|failure)", "build não subiu"),
]

NOT_SEPARABLE = [
    (r"n[ãa]o (consegui|foi poss[íi]vel) separar|not separable|aggregate verdict",
     "evidência não atribuível a um card"),
]

# NAMED blindness beats everything: when the artifact says which design
# prevents the proof, that is what the human will decide — even if the same
# artifact also complains about a missing tool (WEGO-1540 has both, and what
# matters is the no-op double, not the jacoco that was missing).
NAMED_BLIND_TEST = [
    (r"no-op|noop|mock.*(engole|swallow)", "dublê engole o sinal"),                                      # WEGO-1540
    (r"n[ãa]o alcan[çc]|not reachable", "a superfície real não é alcançável pelo teste"),
    (r"only collective|apenas coletiv|s[óo] coletiv|double-gate|both .{0,30}layers|layered.defense|ambas as camadas",
     "só vai vermelho quando as duas camadas caem juntas"),                                              # WEGO-1778
]

BLIND_TEST = [
    (r"nenhum @quarkustest|no @quarkustest|sem teste externo|unobservable at (the )?http",
     "nenhum teste externo passa por esse caminho"),
    # a base/revert that does not compile is an obstacle of the SHAPE OF THE
    # CODE, not of the environment: the machine ran, it is the red-on-base
    # that cannot be produced.
    (r"n[ãa]o compila|do(es)? not compile", "reverter só esse pedaço não compila no commit-base"),       # WEGO-1614, 1710, 1783
    (r"analytical proof|prova anal[íi]tica|argumento estrutural|structural argument|an[áa]lise est[áa]tica",
     "sobrou argumento analítico no lugar da prova"),                                                    # WEGO-1710
    (r"n[ãa]o (é |e )?por endpoint|prova o mecanismo uma vez|sem http|adapter diretamente",
     "prova só uma vez, não em cada endpoint"),                                                          # WEGO-1783
]


PASSED = ("pass", "clean", "ran", "n/a", None)


def _blocked_levels(levels: dict) -> list[tuple[str, str]]:
    """Levels that prevent PROVEN — what is left without evidence, by name."""
    out = []
    for key, label in (("l2", "L2"), ("l3", "L3"), ("l4", "L4"), ("bug", "regressão")):
        level = _level(levels, key)
        if not level:
            continue
        status = level.get("status")
        pert = level.get("perturbation")
        if isinstance(pert, dict) and pert.get("status") not in PASSED:
            out.append((label, pert.get("status")))
        elif status not in PASSED:
            out.append((label, status))
    return out


DOC_EXT = (".md", ".adoc", ".rst", ".txt")


def _docs_only(changed_files) -> bool:
    """True if the file list (when there is one) is all documentation.

    An absent list does not fail: the artifact only declared the classes. A
    present list needs every file under `docs/` or with a text extension.
    """
    if changed_files is None:
        return True
    for item in changed_files:
        path = str(item.get("file") if isinstance(item, dict) else item or "")
        if not (path.startswith("docs/") or path.lower().endswith(DOC_EXT)):
            return False
    return True


def _match(rules, blob):
    for pattern, evidence in rules:
        if re.search(pattern, blob):
            return evidence
    return None


def classify(d: dict) -> tuple[str, str]:
    """Returns (slug, evidence) for an already-read proof artifact."""
    levels = d.get("levels") or {}
    l3 = _level(levels, "l3")
    l2 = _level(levels, "l2")
    l4 = _level(levels, "l4")
    bug = _level(levels, "bug")
    # in schema 2 the perturbation is a sub-block; in the old spelling the level is flat
    pert = l3.get("perturbation") or {
        "status": l3.get("status"),
        "results": l3.get("results") or l3.get("note"),
    }
    scope = d.get("scope") or {}

    blob = _text(
        d.get("routing_reason"),
        pert.get("results"), pert.get("note"),
        l2.get("run"), l2.get("note"),
        l3.get("pit"), l3.get("note"),
        l4.get("reason"), l4.get("note"), l4.get("findings"),
        bug.get("run"), bug.get("note"),
    )

    # STRUCTURAL, and therefore it comes before any prose matcher: if L4
    # recorded a finding, the proof ran AND found a defect in the changed
    # surface. That is the human's decision by definition, and no phrase can
    # reroute it.
    #
    # This check existed, but further down, after the text matchers — and the
    # blob includes `l4.findings`, that is, the PROSE OF THE FINDING ITSELF. A
    # finding that described "jacoco ausente" or "docker" was classified by its
    # own description and fell into `nao-rodou`, the only bucket that spares the
    # human. Found on 2026-08-14 in the prove-drain of wego-acesso-backend:
    # WEGO-1894 (hash collision) and WEGO-1897 (NUL byte taking the API down)
    # vanished from the queue, the two most serious findings of the batch. The
    # fact beats the text.
    #
    # `findings` holds prose, not state: WEGO-1819 is marked `findings` and the
    # text says the finding was already closed. So the evidence returned is the
    # text itself — the reader is the human; the command does not claim it is open.
    if l4.get("status") == "findings":
        return "sem-cobertura", str(l4.get("findings") or "")[:200]

    # The order is precedence, not taste. "Depends on someone outside" and "diff
    # without production" come first because they also cite the environment in
    # the prose and would be swallowed by "did not run".
    ev = _match(OUT_OF_REACH, blob)
    if ev:
        return "fora-do-alcance", ev

    ev = _match(NAMED_BLIND_TEST, blob)
    if ev:
        return "teste-cego", ev

    ev = _match(DIFF_WITHOUT_PRODUCTION, blob)
    if ev:
        return "nada-a-provar", ev

    no_base = scope.get("base_commit_resolved") is False or not d.get("base_commit")

    # A parent Epic has no diff of its own: the work lives in the child Stories,
    # each with its own base_commit and artifact. Without this guard it falls
    # into the missing-base-commit rule right below and comes out as
    # `nao-rodou` — the ONLY reason that spares the human without asking, and
    # whose prescribed exit is to re-run the proof. Re-running on an Epic
    # returns the same result forever and the card sits in Review in silence.
    # Found in the command's first real run (WEGO-1550, 2026-08-04), whose
    # artifact already said in prose "a parent Epic, by definition, does not
    # produce this diff" — the issue_type field is what the rule was missing.
    if no_base and str(d.get("issue_type") or "").strip().lower() == "epic":
        return "nada-a-provar", "Epic agrega Stories filhas e não tem diff próprio"

    if no_base:
        return "nao-rodou", "commit-base não resolvido"
    ev = _match(DID_NOT_RUN, blob)
    if ev:
        return "nao-rodou", ev

    ev = _match(NOT_SEPARABLE, blob)
    if ev:
        return "nao-separavel", ev

    ev = _match(BLIND_TEST, blob)
    if ev:
        return "teste-cego", ev

    # A docs-only diff recognized by STRUCTURE, not by prose: the artifact
    # declares `scope.changed_classes: []`, L4 came out `n/a` and the
    # perturbation `skipped`. Without this rule the card falls into the
    # fallback right below and becomes `teste-cego`, mixing spec with truly
    # blind tests in the /board-flow:decide grouping. Found on 2026-09-25 in the
    # prove-drain of wego-acesso-backend: WEGO-2117, 2275 and 2276 (.md only)
    # whose text did not match DIFF_WITHOUT_PRODUCTION. The empty list has to be
    # WRITTEN: an absent key is an artifact that did not say, and does not
    # prove a diff without production. And no class at all is not enough when
    # the artifact lists the files: WEGO-2021 also has `changed_classes: []`,
    # but the diff is application.properties — a configuration change, which
    # changes behavior.
    if (scope.get("changed_classes") == []
            and pert.get("status") == "skipped"
            and l4.get("status") == "n/a"
            and _docs_only(scope.get("changed_files"))):
        return "nada-a-provar", "diff sem classe de produção (changed_classes vazio)"

    if pert.get("status") == "skipped":
        return "teste-cego", "perturbação externa não pôde rodar"

    # The second half of reason 6, and it is STRUCTURAL: everything passed but
    # one check, and that check does not fit the kind of change. Without this
    # condition the phrase "não se aplica" (which shows up loose in half the
    # artifacts) sent missing-tool cards to the wrong reason.
    blocked = _blocked_levels(levels)
    if len(blocked) == 1 and _match(CHECK_NOT_APPLICABLE, blob):
        return "nada-a-provar", f"{blocked[0][0]} não cabe nesse tipo de mudança"

    # (The `l4.status == "findings"` check that used to be here moved up to before
    # the prose matchers — see the comment above. From here it was never reached
    # when the text of the finding itself matched another rule.)

    for r in ((l3.get("pit") or {}).get("results") or []):
        m = re.search(r"\((\d+)%\)", str(r))
        if m and int(m.group(1)) < 70:
            return "guarda-fraca", str(r)[:200]

    for name, level in (("L2", l2), ("perturbação", pert), ("L4", l4), ("regressão", bug)):
        if level.get("status") in ("assumed", "skipped"):
            return "sem-motivo", f"{name} = {level.get('status')}, sem causa reconhecida"
    return "sem-motivo", "needs-human sem nível bloqueado identificável"


# The two artifact directories, in the order they win. `docs/proof/` is where
# the proof-reviewer writes since the path-lock started locking it there: in
# projects that run the gate, `.claude/` is gitignored, so a verdict written
# there dies along with the session's disposable worktree. `.claude/proof/`
# is still READ because it holds the whole base that already exists on disk —
# the reasons' regression suite was built on 33 of those artifacts.
# Narrowing the reader to a single path would blind it to them.
PROOF_DIRS = ("docs/proof", ".claude/proof")


def proof_artifacts(repo: str) -> list:
    """Paths of a repo's artifacts, one per card.

    When the same card has an artifact in both directories — the normal case of
    a card proved before the change of destination and re-proved after — the
    one in `docs/proof/` wins, because it is the one that survives the worktree
    and, being the current write destination, is also the newest. The other is
    silently ignored: it is not a divergence to resolve, it is the version that
    was left behind.
    """
    chosen: dict = {}
    for d in PROOF_DIRS:
        for path in sorted(glob.glob(os.path.join(repo, d, "*.yaml"))):
            chosen.setdefault(os.path.basename(path), path)
    return [chosen[k] for k in sorted(chosen)]


def _main(repos):
    import yaml

    buckets: dict[str, list] = {}
    total = 0
    for repo in repos:
        for path in proof_artifacts(repo):
            with open(path) as fh:
                d = yaml.safe_load(fh)
            if not isinstance(d, dict):
                continue
            if str(d.get("verdict", "")).strip().split()[:1] != ["needs-human"]:
                continue
            total += 1
            slug, ev = classify(d)
            card = d.get("card") or os.path.basename(path)
            buckets.setdefault(slug, []).append((card, os.path.basename(repo), ev))

    print(f"NEEDS-HUMAN nos artefatos: {total}\n")
    for slug in QUEUE_ORDER + ["nao-rodou", "sem-motivo"]:
        items = buckets.get(slug) or []
        if not items:
            continue
        print(f"[{len(items)}] {REASONS[slug]}  ({slug})")
        for card, repo, ev in items:
            print(f"    {card:12} {repo:26} {ev}")
        print()
    not_question = sum(len(buckets.get(s) or []) for s in NOT_A_QUESTION)
    print(f"{total} artefatos − {not_question} que não são decisão sua = {total - not_question}")
    print("⚠ isto conta ARTEFATOS, não a fila: a fila são os cards que estão em Review agora.")


if __name__ == "__main__":
    _main(sys.argv[1:])
