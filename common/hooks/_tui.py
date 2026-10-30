"""TUI look for the output of the cepa-* commands, only when it is a terminal.

The commands print plain text: it is what the tests read, what an agent
receives through Bash and what a `nohup` records. This module decorates that
same output when, and only when, it goes to a terminal: bar header, section
with a rule, colored glyphs, dimmed separators and long lines wrapped with a
hanging indent (the continuation aligns with the text, not with the margin).
Outside a terminal, with NO_COLOR or with TERM=dumb, nothing changes: the
output is byte for byte the one from before. `CEPA_COR=sempre` and
`CEPA_COR=nunca` force it on and off.

Two ways to use it:

  * `install()` in `__main__`: swaps sys.stdout for a filter that decorates
    line by line according to the text format (`# title`, `## section`,
    `section (3)`, `✓ [tag] ...`, `18. id — title`, `key: value`). It is what
    every command uses.
  * `SCREEN` and its primitives, for whoever builds the screen by hand (the
    `cepa-plan status`). A line that already carries color goes through the
    filter untouched.
"""

import os
import re
import shutil
import sys
import textwrap

COLORS = {"verde": "32", "vermelho": "31", "amarelo": "33", "azul": "34",
          "magenta": "35", "ciano": "36", "cinza": "2", "negrito": "1"}
END = "\033[0m"

# Glyph at the start of the line → its color.
MARKERS = {"✓": "verde", "✔": "verde", "✗": "vermelho", "✘": "vermelho",
           "⚠": "amarelo", "!": "amarelo", "→": "ciano", "▶": "ciano",
           "↻": "amarelo", "◆": "magenta", "⊕": "ciano", "●": "ciano",
           "○": "cinza", "■": "vermelho", "-": "cinza", "•": "cinza",
           "*": "cinza", ">": "magenta"}
_MARKER = re.compile(r"^(\d+[.)]|[" + re.escape("".join(MARKERS)) + r"])\s+")
_ID_DASH = re.compile(r"^(\S+)( — )")
_TAG = re.compile(r"^(\[[^\]]{1,32}\])\s")
_KEY = re.compile(r"^([^\W\d][\w À-ÿ/-]{0,22}):\s+(?=\S)")
_SECTION_COUNT = re.compile(r"^(.*?)\s*\((\d+)\):?$")
_WORDS = [
    (re.compile(r"\b(PROVEN|COMPLETE|PASS|OK|verde)\b"), "verde"),
    (re.compile(r"\b(UNPROVEN|INCOMPLETE|FAIL(?:URE)?|ERRO|vermelho)\b"),
     "vermelho"),
    (re.compile(r"\b(NEEDS-HUMAN|COLISÃO|bloqueado)\b"), "amarelo"),
]


class Screen:
    def __init__(self, stream=None):
        stream = sys.stdout if stream is None else stream
        mode = os.environ.get("CEPA_COR", "").strip().lower()
        if mode in ("sempre", "always", "1"):
            enabled = True
        elif mode in ("nunca", "never", "0") or os.environ.get("NO_COLOR"):
            enabled = False
        else:
            try:
                enabled = bool(stream.isatty()) and os.environ.get("TERM") != "dumb"
            except (AttributeError, ValueError):
                enabled = False
        self.enabled = enabled

    def width(self):
        try:
            return max(shutil.get_terminal_size((100, 40)).columns - 1, 40)
        except (OSError, ValueError):
            return 99

    def c(self, color, text):
        if not self.enabled or not text:
            return text
        codes = ";".join(COLORS[x] for x in color.split("+"))
        return f"\033[{codes}m{text}{END}"

    # ── primitives ───────────────────────────────────────────────────────

    def header(self, title, right=""):
        """Full bar at the terminal width: title on the left, `right`
        (count, date) flush to the right edge."""
        if not self.enabled:
            return title
        w = self.width()
        left = f" {title} "
        right_ = f" {right} " if right else ""
        middle = max(w - len(left) - len(right_), 0)
        return f"\033[1;7;35m{left}{' ' * middle}{right_}{END}"

    def section(self, title, count=None, color="magenta", glyph=""):
        """`── glyph title (n) ─────────` up to the right margin."""
        if not self.enabled:
            return title if count is None else f"{title} ({count})"
        label = f"{glyph} {title}" if glyph else title
        n = "" if count is None else f" ({count})"
        rest = max(self.width() - len(label) - len(n) - 4, 0)
        return (self.c(color, "── ") + self.c(f"negrito+{color}", label)
                + self.c("cinza", n) + " " + self.c(color, "─" * rest))

    def wrap(self, text, indent=0, hanging=None, width=None):
        """Wrap `text` at the terminal width with a hanging indent. Returns
        the list of lines, without color."""
        hanging = indent if hanging is None else hanging
        w = width or self.width()
        if len(text) + indent <= w:
            return [" " * indent + text]
        return textwrap.wrap(text, width=w, initial_indent=" " * indent,
                             subsequent_indent=" " * hanging,
                             break_on_hyphens=False) or [" " * indent]

    def cut(self, text, width):
        return text if len(text) <= width else text[:max(width - 1, 1)] + "…"

    def bar(self, frac, n=24, color="verde"):
        k = round(max(0.0, min(1.0, frac)) * n)
        return self.c(color, "▰" * k) + self.c("cinza", "▱" * (n - k))

    def highlight(self, text):
        """Dimmed separators and verdict words in their own color."""
        if not self.enabled:
            return text
        text = text.replace(" · ", self.c("cinza", " · "))
        text = text.replace(" — ", self.c("cinza", " — "))
        for pattern, color in _WORDS:
            text = pattern.sub(lambda m, color=color: self.c(color, m.group(0)), text)
        return text

    # ── line-by-line decoration, by the shape of the text ──────────────

    def line(self, line):
        if (not self.enabled or "\033" in line or "\r" in line
                or not line.strip()):
            return line
        body = line.strip()
        if body[0] in "{}[]\"":
            return line
        indent = len(line) - len(line.lstrip(" "))

        m = re.match(r"^#\s+(.+)$", line)
        if m:
            return self.header(m.group(1))
        m = re.match(r"^(?:#{2,}|──)\s+(.+?)\s*─*$", line)
        if m:
            return self._free_section(m.group(1))
        if indent == 0 and len(body) <= 72 and ": " not in body and (
                body.endswith(":") or _SECTION_COUNT.match(body)):
            return self._free_section(body)

        prefix, rest, color = "", body, None
        m = _MARKER.match(rest)
        if m:
            prefix, rest = m.group(0), rest[m.end():]
            color = "cinza" if m.group(1)[0].isdigit() else MARKERS[m.group(1)]
        key = None
        m = _TAG.match(rest) or _KEY.match(rest)
        if m:
            key = m.group(0)
            rest = rest[m.end():]
        hanging = indent + len(prefix) + (len(key) if key and len(key) <= 24 else 0)
        lines = self.wrap(prefix + (key or "") + rest, indent, hanging)

        first = lines[0][indent + len(prefix) + len(key or ""):]
        id_dash = _ID_DASH.match(first) if prefix[:1].isdigit() else None
        if id_dash:
            first = (self.c("negrito+ciano", id_dash.group(1))
                     + self.c("cinza", id_dash.group(2))
                     + self.highlight(first[id_dash.end():]))
        else:
            first = self.highlight(first)
        out = (" " * indent + self.c(color, prefix) if prefix else " " * indent)
        if key:
            out += self.c("ciano" if key.startswith("[") else "cinza", key)
        out += first
        return "\n".join([out] + [self.highlight(x) for x in lines[1:]])

    def _free_section(self, text):
        text = text.rstrip(":").rstrip()
        m = _SECTION_COUNT.match(text)
        if m:
            return self.section(m.group(1), m.group(2))
        return self.section(text)


class Filter:
    """Stdout that decorates each complete line and passes the rest through as it came."""

    def __init__(self, stream, screen):
        self._stream = stream
        self._screen = screen
        self._pending = ""

    def write(self, text):
        self._pending += text
        if "\n" not in self._pending:
            return len(text)
        *complete, self._pending = self._pending.split("\n")
        self._stream.write("".join(self._screen.line(l) + "\n" for l in complete))
        return len(text)

    def flush(self):
        if self._pending:
            self._stream.write(self._pending)
            self._pending = ""
        self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


SCREEN = Screen()


def install():
    """Decorate the command's stdout when it is a terminal. JSON output
    (`--json`) and an explicit request for plain text (`--no-color`, or the
    old `--sem-cor`) are never touched."""
    if (not SCREEN.enabled or isinstance(sys.stdout, Filter)
            or {"--json", "--no-color", "--sem-cor"} & set(sys.argv)):
        return
    sys.stdout = Filter(sys.stdout, SCREEN)
