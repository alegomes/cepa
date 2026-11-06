"""One help layout for `cepa` and every `cepa-*` command.

Before this module each command wrote its own help: some had examples, some
exit codes, some only argparse's default dump; `cepa plan help` was an error
while `cepa doctor help` worked; Portuguese and English aliases were mixed in
the same listing. `Parser` is an `argparse.ArgumentParser` that renders every
help in the same order and the same look:

    usage: cepa <command> ...
    <summary: one sentence>
    <description: what it does and why, free text>
    subcommands:   (when there are any)
    arguments:     (positionals)
    options:
    examples:
    exit codes:
    see also:

Rules it enforces, so no command has to remember them:

  * `help` as the first word is the same as `--help`, at every level
    (`cepa plan help`, `cepa plan write help`); `-h`, `--help` and `help`
    print the same text and exit 0.
  * Only the first long name of each option is shown, and subcommand aliases
    are hidden: the old Portuguese names still work, the help shows one name.
  * A usage error prints `✗ <prog>: <reason>`, the usage line and where the
    full help is, and exits 2. An unknown subcommand names the nearest one.
  * On a terminal (the same test `_tui` uses: tty, no NO_COLOR, TERM not
    dumb, CEPA_COR forces) headings become rules and names get color. Piped,
    the text is plain, `heading:` lines and all.

The summary defaults to the first docstring line of the running script
(`cepa-x — <summary>`), the same line `cepa help` lists, so the two never
disagree.
"""

import argparse
import difflib
import os
import re
import shutil
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _tui  # noqa: E402

HELP_WORDS = ("help", "ajuda")
MAX_WIDTH = 100


def _screen(stream):
    return _tui.Screen(stream)


def _width():
    try:
        cols = shutil.get_terminal_size((MAX_WIDTH, 40)).columns
    except (OSError, ValueError):
        cols = MAX_WIDTH
    return max(min(cols - 1, MAX_WIDTH), 60)


def doc_summary(doc):
    """`cepa-x — does this.` → `Does this.`"""
    first = (doc or "").strip().splitlines()[0] if (doc or "").strip() else ""
    first = re.sub(r"^cepa(-[\w-]+)?\s*[—-]+\s*", "", first).strip()
    return sentence(first)


def sentence(text):
    text = (text or "").strip()
    if not text:
        return text
    text = text[0].upper() + text[1:]
    return text if text[-1] in ".!?)" or text.endswith("`") else text + "."


def _real_stdout():
    # `_tui.install()` wraps stdout in a filter that guesses decoration from
    # the shape of each line; the help is already decorated, so it bypasses it.
    out = sys.stdout
    return getattr(out, "_stream", out) if isinstance(out, _tui.Filter) else out


class Parser(argparse.ArgumentParser):
    """ArgumentParser with the cepa help layout.

    Extra keyword arguments (all optional):
      summary      one sentence; default: first docstring line of __main__
      examples     list of (command, comment) or plain command strings
      exit_codes   list of (code, meaning)
      see_also     list of strings (commands, docs)
      commands     list of (name, help) for subcommands dispatched by hand,
                   before argparse runs (cepa-until does this)
      groups       list of (title, [subcommand names]) to list subcommands
                   by family instead of in definition order
      options_title  heading of the options section (default "options")
    """

    def __init__(self, *args, summary=None, examples=None, exit_codes=None,
                 see_also=None, commands=None, groups=None, options_title="options",
                 **kw):
        if sys.version_info >= (3, 14):
            kw.setdefault("color", False)
        kw.setdefault("formatter_class", argparse.RawDescriptionHelpFormatter)
        super().__init__(*args, **kw)
        if summary is None:
            summary = doc_summary(getattr(sys.modules.get("__main__"), "__doc__", ""))
        self.summary = sentence(summary) if summary else ""
        self.examples = list(examples or [])
        self.exit_codes = list(exit_codes or [])
        self.see_also = list(see_also or [])
        self.commands = list(commands or [])
        self.groups = list(groups or [])
        self.options_title = options_title
        for a in self._actions:
            if isinstance(a, argparse._HelpAction):
                a.help = "show this help and exit (same as `help`)"

    # ── subparsers inherit the layout ──────────────────────────────────

    def add_subparsers(self, **kw):
        kw.setdefault("parser_class", Parser)
        kw.setdefault("metavar", "<subcommand>")
        action = super().add_subparsers(**kw)
        add = action.add_parser

        def add_parser(name, **pkw):
            pkw.setdefault("summary", pkw.get("help") or "")
            return add(name, **pkw)

        action.add_parser = add_parser
        return action

    # ── `help` as a word ───────────────────────────────────────────────

    def parse_known_args(self, args=None, namespace=None):
        args = list(sys.argv[1:] if args is None else args)
        if args and args[0] in HELP_WORDS:
            args[0] = "--help"
        return super().parse_known_args(args, namespace)

    # ── errors ─────────────────────────────────────────────────────────

    def error(self, message):
        m = re.match(r"argument [^:]+: invalid choice: '([^']*)'", message)
        sub = self._subparsers_action()
        if m and sub is not None:
            names = [c.dest for c in sub._choices_actions]
            near = difflib.get_close_matches(m.group(1), names, n=1)
            message = f"'{m.group(1)}' is not a subcommand"
            if near:
                message += f" (did you mean `{self.prog} {near[0]}`?)"
            message += "\n" + "\n".join(textwrap.wrap(
                "subcommands: " + ", ".join(names), width=_width(),
                initial_indent="  ", subsequent_indent="    "))
        err = sys.stderr
        err.write(f"✗ {self.prog}: {message}\n")
        err.write(textwrap.indent(self.format_usage().strip(), "  ") + "\n")
        err.write(f"  full help: {self.prog} --help\n")
        sys.exit(2)

    # ── rendering ──────────────────────────────────────────────────────

    def _subparsers_action(self):
        for a in self._actions:
            if isinstance(a, argparse._SubParsersAction):
                return a
        return None

    def print_help(self, file=None):
        stream = file or _real_stdout()
        stream.write(self.render(_screen(stream)))

    def format_help(self):
        return self.render(_NoColor())

    def format_usage(self):
        fmt = self._get_formatter()
        fmt.add_usage(self.usage, self._actions,
                      self._mutually_exclusive_groups, prefix="usage: ")
        return fmt.format_help()

    def _invocation(self, action):
        if not action.option_strings:
            return action.metavar or action.dest
        shorts = [o for o in action.option_strings if not o.startswith("--")]
        longs = [o for o in action.option_strings if o.startswith("--")]
        shown = shorts[:1] + longs[:1]
        name = ", ".join(shown)
        if action.nargs == 0:
            return name
        fmt = self._get_formatter()
        default = action.dest.upper()
        return f"{name} {fmt._format_args(action, default)}"

    def render(self, s):
        w = _width()
        out = []

        def head(title):
            out.append("")
            out.append(s.section(title) if s.enabled else f"{title}:")

        def rows(items, color="ciano", col=None):
            # items: (left, right); right wraps with a hanging indent.
            if not items:
                return
            col = col or min(max(len(left) for left, _ in items) + 4, 30)
            for left, right in items:
                right = " ".join((right or "").split())
                pad = col - 2 - len(left)
                lead = "  " + s.c(color, left)
                body = textwrap.wrap(right, width=max(w - col, 30)) or [""]
                if pad < 2:
                    out.append(lead)
                    out.extend(" " * col + b for b in body)
                else:
                    out.append(lead + " " * pad + body[0])
                    out.extend(" " * col + b for b in body[1:])

        usage = self.format_usage().strip()
        if s.enabled:
            usage = re.sub(r"^usage: (\S+(?: [a-z][\w-]*)*)",
                           lambda m: s.c("negrito+magenta", "usage:") + " "
                           + s.c("negrito+ciano", m.group(1)), usage, count=1)
        out.append(usage)
        if self.summary:
            out.append("")
            out.extend(s.c("negrito", x) for x in textwrap.wrap(self.summary, width=w))
        if self.description:
            out.append("")
            out.extend(self.description.rstrip("\n").split("\n"))

        sub = self._subparsers_action()
        subs = [(c.dest, c.help) for c in sub._choices_actions] if sub else []
        subs += [(n, h) for n, h in self.commands]
        if subs:
            head("subcommands")
            if self.groups:
                by_name = dict(subs)
                listed = set()
                col = min(max(len(n) for n, _ in subs) + 6, 30)
                for title, names in self.groups:
                    out.append("  " + s.c("negrito", title + ":"))
                    rows([("  " + n, by_name.get(n, "")) for n in names], col=col)
                    listed.update(names)
                rest = [(n, h) for n, h in subs if n not in listed]
                if rest:
                    rows(rest, col=col)
            else:
                rows(subs)

        positionals = [a for a in self._actions if not a.option_strings
                       and not isinstance(a, argparse._SubParsersAction)
                       and a.help is not argparse.SUPPRESS]
        if positionals:
            head("arguments")
            rows([(self._invocation(a), self._help_text(a)) for a in positionals])

        options = [a for a in self._actions if a.option_strings
                   and a.help is not argparse.SUPPRESS]
        if options:
            head(self.options_title)
            rows([(self._invocation(a), self._help_text(a)) for a in options])

        if self.examples:
            head("examples")
            ex = [e if isinstance(e, tuple) else (e, "") for e in self.examples]
            col = min(max(len(c) for c, _ in ex) + 2, 48)
            for cmd, note in ex:
                line = "  " + s.c("ciano", cmd)
                if note and len(cmd) + 2 > col:
                    out.append(line)
                    out.append(" " * (col + 2) + s.c("cinza", "# " + note))
                    continue
                if note:
                    line += " " * (col - len(cmd)) + s.c("cinza", "# " + note)
                out.append(line)

        if self.exit_codes:
            head("exit codes")
            rows([(str(c), m) for c, m in self.exit_codes], color="negrito")

        if self.see_also:
            head("see also")
            for item in self.see_also:
                out.extend(textwrap.wrap(item, width=w, initial_indent="  ",
                                         subsequent_indent="    ",
                                         break_on_hyphens=False))

        notes = []
        if subs and sub is not None or self.commands:
            notes.append(f"Each subcommand has its own help: {self.prog} <subcommand> --help.")
        if self._has_aliases():
            notes.append("Older Portuguese names of subcommands and flags still work.")
        if notes:
            out.append("")
            out.extend(s.c("cinza", n) for n in notes)
        return "\n".join(out).rstrip() + "\n"

    def _help_text(self, action):
        text = action.help or ""
        if "%(" in text:
            params = dict(vars(action), prog=self.prog)
            if params.get("choices") is not None:
                params["choices"] = ", ".join(map(str, params["choices"]))
            try:
                text = text % params
            except (KeyError, TypeError, ValueError):
                pass
        if action.choices and not isinstance(action, argparse._SubParsersAction) \
                and "{" not in self._invocation(action) and "one of" not in text:
            text += " (one of: " + ", ".join(map(str, action.choices)) + ")"
        return text

    def _has_aliases(self):
        for a in self._actions:
            if isinstance(a, argparse._SubParsersAction):
                if len(a.choices) > len(a._choices_actions):
                    return True
            elif len([o for o in a.option_strings if o.startswith("--")]) > 1:
                return True
        return False


class _NoColor:
    enabled = False

    def c(self, color, text):
        return text

    def section(self, title):
        return f"{title}:"


def launcher_help(bin_dir):
    """`cepa help`: the launcher's own help, in the same layout. The list of
    subcommands is the `cepa-*` scripts next to the launcher, each described
    by its first docstring line."""
    commands, old = [], []
    for name in sorted(os.listdir(bin_dir)):
        path = os.path.join(bin_dir, name)
        if not name.startswith("cepa-") or not os.access(path, os.X_OK):
            continue
        sub = name[len("cepa-"):]
        try:
            with open(path, encoding="utf-8") as fh:
                fh.readline()
                line = fh.readline()
        except OSError:
            line = ""
        desc = re.sub(r'^("""|#)\s*', "", line.strip())
        desc = re.sub(rf"^cepa-{re.escape(sub)}\s*[—-]+\s*", "", desc)
        m = re.search(r"renamed to cepa-([\w-]+)", desc)
        if m:
            old.append(f"{sub} (= {m.group(1)})")
            continue
        commands.append((sub, desc.rstrip(".")))

    ap = Parser(
        prog="cepa",
        usage="cepa <subcommand> [args]\n       cepa [launcher flags] [claude args]",
        summary="Opens a Claude Code session in the right worktree and mode, "
                "or runs one of the cepa subcommands",
        description=(
            "With a subcommand, `cepa <subcommand>` runs common/bin/cepa-<subcommand>\n"
            "(the `cepa-<subcommand>` names keep working). Without one, it opens a\n"
            "claude session: it asks for the work mode, isolates the session in its own\n"
            "worktree when another live session holds this one, runs the harness\n"
            "preflight (cepa doctor, at most every 12h) and starts in bypassPermissions\n"
            "(the harness hooks still apply)."),
        commands=commands,
        examples=[
            ("cepa --mode construction", "open a session in construction mode"),
            ("cepa -s billing-api", "resume or create the session/billing-api worktree"),
            ("cepa --mode help", "what each work mode is for"),
            ("cepa plan status", "run a subcommand"),
            ("cepa help plan", "the help of one subcommand (same as cepa plan --help)"),
            ("cepa --resume", "any other argument goes to claude"),
        ],
        exit_codes=[(0, "help printed, or the exit code of claude / the subcommand"),
                    (2, "invalid usage: unknown mode, missing value, typo in a subcommand")],
        see_also=["environment: CEPA_MODO=off (no mode), CEPA_PREFLIGHT=off, "
                  "CEPA_PERMISSOES=classificador, CEPA_ENCADEAR=off, CEPA_PROMPT=<name|path>",
                  "docs/modos-de-trabalho.md: the work modes"],
        add_help=False,
        options_title="launcher flags",
    )
    ap.add_argument("-h", "--help", action="help",
                    help="show this help and exit (same as `help`)")
    ap.add_argument("-s", "--slice", metavar="[NAME]",
                    help="force or resume the session/<NAME> worktree; with no name, "
                         "pick one from a list")
    ap.add_argument("-m", "--mode", metavar="MODE",
                    help="work mode of the session: exploration, discovery, design, "
                         "construction, refactor, reflection or documentation "
                         "(`--mode help` explains each one)")
    ap.add_argument("--budget", metavar="SCOPE",
                    help="the closed list of what will be refactored; required by "
                         "the refactor mode")
    ap.add_argument("--purpose", metavar="TEXT",
                    help="records the session purpose (.claude/session-intent)")
    ap.add_argument("--by-when", metavar="WHEN",
                    help="the stopping point of that purpose (with --purpose)")
    ap.add_argument("--plan", metavar="STEPS",
                    help="the plan, one step per line (with --purpose)")
    ap.add_argument("--prompt", metavar="NAME|PATH",
                    help="appends a system prompt to Claude Code's default one; a name "
                         "is looked up in ~/.claude/cepa-prompts and <repo>/.claude/prompts")
    ap.add_argument("--prompt-replace", metavar="NAME|PATH",
                    help="REPLACES the whole system prompt (use only with a prompt "
                         "that stands on its own)")
    text = ap.render(_screen(sys.stdout))
    if old:
        text += _screen(sys.stdout).c(
            "cinza", "Old subcommand names still work: " + ", ".join(old) + ".") + "\n"
    sys.stdout.write(text)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "launcher":
        launcher_help(sys.argv[2])
    else:
        sys.stderr.write("usage: _clihelp.py launcher <bin_dir>\n")
        sys.exit(2)
