#!/usr/bin/env python3
"""_jiramut: recognizes a Jira (and Bitbucket) mutation by EFFECT, not by tool name.

## Why it exists

Four `common` gates decide whether a change in Jira may pass:
`acceptance-gate` (acceptance criterion met), `merge-truth-gate` (the code is
really on the integration branch), `summary-nulls-gate` (summary without holes)
and `bounce-reason-gate` (bounce reason filled in).

All four matched on the **MCP tool name** and let the call through when the name
did not match:

    if "transitionJiraIssue" not in tool_name and "jira_transition_issue" not in tool_name:
        sys.exit(0)          # <- exit 0 means ALLOW

That worked while the only path to Jira was MCP. It stopped working when
Atlassian released the `twg` CLI (2026-08): the call arrives as
`tool_name == "Bash"`, matches neither name, and the four gates allow it
**silently**. That is not weakened enforcement, it is disabled enforcement, and
`twg` is already installed and authenticated on this machine, with `twg-*`
skills visible to any session, so the exposure does not depend on anyone
migrating anything.

This module is the answer: given the hook payload, it says whether the call
**mutates Jira**, by which mechanism, and returns the fields already normalized
to the names the gates always used, so each gate keeps its business logic
intact.

## The rule that must not be loosened

Faced with a call that touches Jira and that it **cannot classify**, this module
returns `opaque=True` and the gate must **block**. The concrete case is
`twg api`, the CLI's REST/GraphQL escape hatch:

    twg api jira:/rest/api/3/issue -X POST --input payload.json

This creates a card without containing `create` on the command line, and with
`--input` the body does not even appear in the inspected string. Any
verb-denylist design is defeated by that single line. That is why read
recognition here is an **allowlist**: whatever is not declared a known read is
treated as a mutation, and what is a mutation and cannot be inspected is blocked.

Usage, following the pattern of the other private helpers in this folder:

    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _jiramut as J

    m = J.classify(payload)
    if m is None:
        sys.exit(0)                      # not a Jira mutation
    if m["opaque"]:
        J.block(m, "gate-name")          # blocks with exit 2 and an explanation
    tool_input = m["tool_input"]         # normalized; use as before
"""

import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _shellscan as S  # noqa: E402

_split_segments = S._split_segments

KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")

# MCP names the gates always knew. Kept because the MCP path is still alive
# (the `/schedule` cloud routine has no shell).
_MCP_TRANSITION = ("transitionJiraIssue", "jira_transition_issue")
_MCP_COMMENT = ("addCommentToJiraIssue", "jira_add_comment")

# `twg jira ...` paths that are proven reads. ALLOWLIST: whatever is not here
# and falls under `twg jira` is treated as a mutation. Verified against the
# CLI 1.2.5 `--help`.
_TWG_JIRA_READ = frozenset({
    ("workitem", "get"), ("workitem", "bulk-get"), ("workitem", "query"),
    ("workitem", "search"), ("workitem", "similar"), ("workitem", "statuses"),
    ("workitem", "transitions"), ("workitem", "types"), ("workitem", "priorities"),
    ("workitem", "changelog"), ("workitem", "link-types"),
    ("workitem", "project-link-candidates"),
    ("space", "get"), ("space", "query"), ("space", "list"),
    ("space", "issue-types"), ("space", "status"),
    ("board", "get"), ("board", "query"), ("board", "list"),
    ("sprint", "get"), ("sprint", "query"), ("sprint", "list"),
    ("filter", "get"), ("filter", "query"), ("filter", "list"),
    ("field", "get"), ("field", "query"), ("field", "list"),
    ("dashboard", "get"), ("dashboard", "query"), ("dashboard", "list"),
})

# `twg` version whose `help describe` was checked against the allowlists below.
# atlassian-expert.md cites the same number, and tests/test_atlassian_expert_spec.py
# fails if the two diverge. A new version breaks nothing by itself: an unknown
# verb already falls as an opaque write.
TWG_VERIFIED = "1.3.1"

# Third-level reads (`twg jira workitem link query`). Verified against the
# CLI 1.3.1 `twg help describe`.
_TWG_JIRA_READ_SUB = frozenset({
    ("workitem", "link", "query"),
    ("workitem", "field", "create-metadata"),
    ("workitem", "attachment", "query"), ("workitem", "attachment", "get"),
})

# `workitem update` options that transition, comment or carry free JSON.
# `--field <id>=<value>` is left out: it names a single field, visible on the
# line, and Jira accepts neither status nor comment as an edit field.
_UPDATE_OPAQUE = (
    "--status", "--comment", "--transition-comment", "--resolution",
    "--fields-json", "--variables-json",
)

# `comment` subcommands that write text to the card.
_TWG_COMMENT_WRITE = frozenset({"create", "update"})

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# `twg bitbucket pull-requests ...` that are proven reads. ALLOWLIST, for the
# same reason as Jira. Verified against the CLI 1.2.5 --help.
_TWG_BB_PR_READ = frozenset({
    "get", "query", "list", "activity", "commits", "diff", "diffstat", "patch",
    "for-commit", "merge-status", "effective-default-reviewer",
})

# PR verbs that decide the code's fate. Approving and merging one's own PR is
# exactly what the review-gate exists to prevent.
_TWG_BB_PR_DECIDE = frozenset({
    "approve", "merge", "decline", "request-changes", "remove-request-changes",
})


# Logical status keys the gates understand (those of `status_map` and
# `transition_ids` in board-flow.yaml).
LOGICAL_STATUSES = frozenset({"to_do", "in_progress", "in_review", "done", "wont_do"})
_CONFIG_NAMES = ("board-flow.yaml", ".claude/board-flow.lifecycle.yaml")


def logical_status(name, cwd):
    """Translates a status NAME (as the `twg` CLI accepts it) to the logical key.

    `twg` accepts `--transition-id "In Review"`. Just lowercasing gave
    `in review`, which is no key at all, and the acceptance-gate read that as a
    lateral move and let the card through (hole reproduced on 2026-09-19).

    Order: the technical name declared in the `status_map` of board-flow.yaml
    (that is where "Em Revisão" becomes `in_review`); then the normalized form
    (space and hyphen become `_`). A name that does not resolve returns None: an
    UNRESOLVED target, which the gate treats as in doubt, not as a lateral move.
    """
    if not name or not str(name).strip():
        return None
    target = " ".join(str(name).split()).casefold()
    for cfg_name in _CONFIG_NAMES:
        path = os.path.join(str(cwd), cfg_name)
        if not os.path.isfile(path):
            continue
        try:
            import yaml  # noqa: deferred, absence falls to the normalized path
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            smap = (data.get("defaults") or {}).get("status_map") or {}
        except Exception:
            smap = {}
        if isinstance(smap, dict):
            for key, technical in smap.items():
                if " ".join(str(technical).split()).casefold() == target:
                    return str(key).strip().lower()
        break
    norm = re.sub(r"[\s\-]+", "_", target)
    return norm if norm in LOGICAL_STATUSES else None


def classify_bitbucket(command: str):
    """Bitbucket mutation via `twg`. None when there is none.

    Returns {"verb", "decides", "reason"}; `decides` marks the verbs that
    determine whether the code gets in (approve/merge/decline/request-changes),
    which are the ones only the review-gate agent may run.
    """
    if not command or "twg" not in command:
        return None
    for seg in _split_segments(command):
        seg = seg.strip()
        if not seg:
            continue
        try:
            argv = shlex.split(seg)
        except ValueError:
            if re.search(r"(^|/)twg\b", seg) and "bitbucket" in seg:
                return {"verb": "<ilegivel>", "decides": True,
                        "reason": "linha com aspas nao fechadas, impossivel de ler"}
            continue
        while argv and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[0]):
            argv.pop(0)
        if not argv or os.path.basename(argv[0]) != "twg":
            continue
        rest = [a for a in argv[1:] if a]
        if not rest or rest[0] not in ("bitbucket", "bb"):
            continue
        words = [a for a in rest[1:] if not a.startswith("-")]
        if len(words) < 2:
            continue
        resource, verb = words[0], words[1]
        if resource in ("pull-requests", "pr"):
            if verb in _TWG_BB_PR_READ:
                return None
            return {"verb": f"{resource} {verb}",
                    "decides": verb in _TWG_BB_PR_DECIDE,
                    "reason": f"`twg bitbucket {resource} {verb}` escreve no pull request"}
        # repo/branch/deployment/pipeline: a known read passes, the rest is a write
        if verb in ("get", "query", "list", "url", "file", "contributors", "search"):
            return None
        return {"verb": f"{resource} {verb}", "decides": False,
                "reason": f"`twg bitbucket {resource} {verb}` nao esta na lista de leituras conhecidas"}
    return None


def _readable(kind, rest):
    """A write the gate can read and that is neither a transition nor a comment."""
    key = _flag(rest, "--id", "--issue-id", "--key") or _first_key(rest)
    return {
        "kind": kind, "mechanism": "twg",
        "tool_input": {"issueIdOrKey": key} if key else {},
        "opaque": False, "reason": "", "target_status": None,
    }


def _flag(argv, *names):
    """Value of `--flag value` or `--flag=value`, whichever appears first."""
    for i, tok in enumerate(argv):
        for n in names:
            if tok == n and i + 1 < len(argv):
                return argv[i + 1]
            if tok.startswith(n + "="):
                return tok.split("=", 1)[1]
    return None


def _first_key(argv):
    """First card key among the positional arguments (e.g. WEGO-123)."""
    for tok in argv:
        if KEY_RE.match(tok.strip()):
            return tok.strip()
    return None


def _classify_twg(argv):
    """Tokenized argv, argv[0] is `twg`. Returns a dict or None."""
    rest = [a for a in argv[1:] if a]
    if not rest:
        return None

    head = rest[0]

    # ---- REST/GraphQL escape hatch: the hole that defeats any denylist ----
    if head == "api":
        method = (_flag(rest, "-X", "--method") or "GET").upper()
        target = rest[1] if len(rest) > 1 else ""
        touches_jira = "jira" in target.lower() or "graphql" in target.lower()
        if method in _WRITE_METHODS and touches_jira:
            return {
                "kind": "mutation",
                "mechanism": "twg",
                "tool_input": {},
                "opaque": True,
                "reason": (
                    f"`twg api` com -X {method} em {target or '<endpoint>'} muta o Jira por "
                    "REST cru. O gate não consegue ler qual card nem qual conteúdo — "
                    "ainda mais com --input, onde o corpo está num arquivo e não na linha."
                ),
                "target_status": None,
            }
        return None  # GET, or an endpoint that is not Jira

    if head != "jira":
        return None  # bitbucket, confluence, goals... are not this gate's business

    # `--help` only prints help, whatever the path. Without this even
    # `twg jira workitem create --help` was blocked as an opaque write.
    if "--help" in rest or "-h" in rest:
        return None

    path = tuple(a for a in rest[1:3] if not a.startswith("-"))
    if len(path) < 2:
        return None
    if path in _TWG_JIRA_READ:
        return None

    resource, verb = path

    # Third level: `workitem link query`, `workitem field create-metadata`.
    words = [a for a in rest[1:] if not a.startswith("-")]
    sub = words[2] if len(words) > 2 else None
    if (resource, verb, sub) in _TWG_JIRA_READ_SUB:
        return None

    # ---- write that neither transitions nor comments ----
    # Creating a card, editing a field and linking cards are not what the four
    # gates audit (they never were over MCP either). They are a READABLE write:
    # the gate lets it pass, and `jira-write-lock` decides who may write.
    if resource == "workitem" and verb == "create":
        return _readable("create", rest)
    if resource == "workitem" and verb == "link" and sub == "workitem":
        return _readable("link", rest)
    if resource == "workitem" and verb == "update":
        # `update --status` transitions and `--comment` comments: the same effect
        # as the two auditable paths, through a door the gate does not read. And
        # `--fields-json` and `--variables-json` carry free JSON. In those
        # cases, opaque.
        hidden = [f for f in _UPDATE_OPAQUE if _flag(rest, f) is not None]
        if hidden:
            return {
                "kind": "mutation", "mechanism": "twg", "tool_input": {},
                "opaque": True,
                "reason": (
                    f"`twg jira workitem update` com {', '.join(hidden)} muda status, "
                    "comenta ou carrega JSON livre. Use `workitem transition` e "
                    "`workitem comment create`, que o gate consegue ler"
                ),
                "target_status": None,
            }
        return _readable("edit", rest)

    # ---- transition ----
    if (resource, verb) == ("workitem", "transition"):
        tid = _flag(rest, "--transition-id", "--transitionId")
        if tid is None:
            # Without --transition-id the command is read-only discovery: it lists
            # the available transitions. Verified in `--help` and in a real run.
            return None
        key = _flag(rest, "--id", "--issue-id", "--key") or _first_key(rest)
        ti = {}
        if key:
            ti["issueIdOrKey"] = key
        target_status = None
        if tid.isdigit():
            ti["transition_id"] = tid
        else:
            # The CLI accepts the status NAME in place of the id. In that case
            # there is nothing to look up in board-flow.yaml's transition_ids:
            # the target already came.
            target_status = tid.strip().lower()
        comment = _flag(rest, "--transition-comment")
        if comment:
            ti["commentBody"] = comment
        return {
            "kind": "transition",
            "mechanism": "twg",
            "tool_input": ti,
            "opaque": not key,
            "reason": "não foi possível achar a chave do card na linha de comando",
            "target_status": target_status,
        }

    # ---- comment ----
    if resource == "comment" or (resource == "workitem" and verb == "comment"):
        sub = None
        for tok in rest[2:]:
            if not tok.startswith("-"):
                if tok == "comment":
                    continue
                sub = tok
                break
        if sub is not None and sub not in _TWG_COMMENT_WRITE:
            return None  # query/delete: delete carries no body to audit
        key = _flag(rest, "--issue-id", "--id", "--key") or _first_key(rest)
        body = _flag(rest, "--body")
        ti = {}
        if key:
            ti["issueIdOrKey"] = key
        if body is not None:
            ti["commentBody"] = body
        opaque = body is None
        return {
            "kind": "comment",
            "mechanism": "twg",
            "tool_input": ti,
            "opaque": opaque,
            "reason": (
                "o corpo do comentário não está na linha de comando (provavelmente "
                "veio de arquivo ou stdin), então o gate não tem o que auditar"
            ),
            "target_status": None,
        }

    # ---- anything else under `twg jira` ----
    # Allowlist: create, update, delete, archive, clone, bulk-transition,
    # create-bulk, link, worklog, watcher... and whatever the CLI gains tomorrow.
    return {
        "kind": "mutation",
        "mechanism": "twg",
        "tool_input": {},
        "opaque": True,
        "reason": (
            f"`twg jira {resource} {verb}` não está na lista de leituras conhecidas, "
            "então é tratado como escrita que o gate não sabe auditar"
        ),
        "target_status": None,
    }


def _scan_bash(command: str):
    """Scans the whole command line. Returns the first mutation found."""
    if not command or "twg" not in command:
        return None
    for seg in _split_segments(command):
        seg = seg.strip()
        if not seg:
            continue
        try:
            argv = shlex.split(seg)
        except ValueError:
            # Unclosed quotes. If the segment mentions twg it cannot be read,
            # and not being able to read is exactly when to block.
            if re.search(r"(^|/)twg\b", seg):
                return {
                    "kind": "mutation", "mechanism": "twg", "tool_input": {},
                    "opaque": True,
                    "reason": "linha de comando com aspas não fechadas, impossível de ler",
                    "target_status": None,
                }
            continue
        if not argv:
            continue
        # skip env vars ahead of the command: FOO=1 twg ...
        while argv and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[0]):
            argv.pop(0)
        if not argv:
            continue
        if os.path.basename(argv[0]) != "twg":
            continue
        hit = _classify_twg(argv)
        if hit:
            return hit
    return None


def classify(payload: dict):
    """None when the call does not mutate Jira; else the dict described at the top."""
    tool_name = payload.get("tool_name", "") or ""
    tool_input = payload.get("tool_input") or {}

    if any(n in tool_name for n in _MCP_TRANSITION):
        return {"kind": "transition", "mechanism": "mcp", "tool_input": tool_input,
                "opaque": False, "reason": "", "target_status": None}
    if any(n in tool_name for n in _MCP_COMMENT):
        return {"kind": "comment", "mechanism": "mcp", "tool_input": tool_input,
                "opaque": False, "reason": "", "target_status": None}

    if tool_name == "Bash":
        return _scan_bash(tool_input.get("command", "") or "")

    return None


def block(m: dict, gate: str):
    """Blocks a mutation the gate cannot audit. Does not return."""
    print(
        f"[{gate}] BLOCKED: mutação de Jira que este gate não consegue auditar.\n"
        f"  Motivo: {m['reason']}\n"
        f"  Este gate existe para conferir uma condição ANTES de o card mudar de estado.\n"
        f"  Uma chamada que ele não consegue ler não é uma chamada segura — é uma\n"
        f"  chamada invisível, e liberar por não enxergar é como o enforcement morre\n"
        f"  calado. Faça a mudança por um caminho auditável:\n"
        f"    - `twg jira workitem transition --id <KEY> --transition-id <ID>`\n"
        f"    - `twg jira workitem comment create --issue-id <KEY> --body '<texto>'`\n"
        f"    - ou a ferramenta MCP equivalente.\n"
        f"  Se o caminho opaco for mesmo necessário, quem libera é uma pessoa, não o agente.",
        file=sys.stderr,
    )
    sys.exit(2)
