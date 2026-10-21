"""Aparência de TUI para a saída dos comandos cepa-*, só quando ela é um terminal.

Os comandos imprimem texto corrido: é o que os testes leem, o que um agente
recebe pelo Bash e o que um `nohup` grava. Este módulo decora essa mesma saída
quando, e só quando, ela vai para um terminal: cabeçalho em barra, seção com
régua, glifos coloridos, separadores apagados e linha longa quebrada com recuo
pendurado (a continuação alinha com o texto, não com a margem). Fora do
terminal, com NO_COLOR ou com TERM=dumb, nada muda: a saída é byte a byte a de
antes. `CEPA_COR=sempre` e `CEPA_COR=nunca` forçam.

Dois jeitos de usar:

  * `instalar()` no `__main__`: troca o sys.stdout por um filtro que decora
    linha a linha pelo formato do texto (`# título`, `## seção`, `seção (3)`,
    `✓ [tag] ...`, `18. id — título`, `chave: valor`). É o que todo comando usa.
  * `TELA` e suas primitivas, para quem monta a tela por conta própria (o
    `cepa-plan status`). Linha que já traz cor passa pelo filtro intocada.
"""

import os
import re
import shutil
import sys
import textwrap

CORES = {"verde": "32", "vermelho": "31", "amarelo": "33", "azul": "34",
         "magenta": "35", "ciano": "36", "cinza": "2", "negrito": "1"}
FIM = "\033[0m"

# Glifo no começo da linha → cor dele.
MARCADORES = {"✓": "verde", "✔": "verde", "✗": "vermelho", "✘": "vermelho",
              "⚠": "amarelo", "!": "amarelo", "→": "ciano", "▶": "ciano",
              "↻": "amarelo", "◆": "magenta", "⊕": "ciano", "●": "ciano",
              "○": "cinza", "■": "vermelho", "-": "cinza", "•": "cinza",
              "*": "cinza", ">": "magenta"}
_MARCADOR = re.compile(r"^(\d+[.)]|[" + re.escape("".join(MARCADORES)) + r"])\s+")
_ID_TRACO = re.compile(r"^(\S+)( — )")
_TAG = re.compile(r"^(\[[^\]]{1,32}\])\s")
_CHAVE = re.compile(r"^([^\W\d][\w À-ÿ/-]{0,22}):\s+(?=\S)")
_SECAO_CONTAGEM = re.compile(r"^(.*?)\s*\((\d+)\):?$")
_PALAVRAS = [
    (re.compile(r"\b(PROVEN|COMPLETE|PASS|OK|verde)\b"), "verde"),
    (re.compile(r"\b(UNPROVEN|INCOMPLETE|FAIL(?:URE)?|ERRO|vermelho)\b"),
     "vermelho"),
    (re.compile(r"\b(NEEDS-HUMAN|COLISÃO|bloqueado)\b"), "amarelo"),
]


class Tela:
    def __init__(self, fluxo=None):
        fluxo = sys.stdout if fluxo is None else fluxo
        modo = os.environ.get("CEPA_COR", "").strip().lower()
        if modo in ("sempre", "always", "1"):
            ligada = True
        elif modo in ("nunca", "never", "0") or os.environ.get("NO_COLOR"):
            ligada = False
        else:
            try:
                ligada = bool(fluxo.isatty()) and os.environ.get("TERM") != "dumb"
            except (AttributeError, ValueError):
                ligada = False
        self.ligada = ligada

    def largura(self):
        try:
            return max(shutil.get_terminal_size((100, 40)).columns - 1, 40)
        except (OSError, ValueError):
            return 99

    def c(self, cor, texto):
        if not self.ligada or not texto:
            return texto
        codigos = ";".join(CORES[x] for x in cor.split("+"))
        return f"\033[{codigos}m{texto}{FIM}"

    # ── primitivas ───────────────────────────────────────────────────────

    def cabecalho(self, titulo, direita=""):
        """Barra cheia na largura do terminal: título à esquerda, `direita`
        (contagem, data) encostado à direita."""
        if not self.ligada:
            return titulo
        w = self.largura()
        esq = f" {titulo} "
        dir_ = f" {direita} " if direita else ""
        meio = max(w - len(esq) - len(dir_), 0)
        return f"\033[1;7;35m{esq}{' ' * meio}{dir_}{FIM}"

    def secao(self, titulo, contagem=None, cor="magenta", glifo=""):
        """`── glifo título (n) ─────────` até a margem direita."""
        if not self.ligada:
            return titulo if contagem is None else f"{titulo} ({contagem})"
        rotulo = f"{glifo} {titulo}" if glifo else titulo
        n = "" if contagem is None else f" ({contagem})"
        resto = max(self.largura() - len(rotulo) - len(n) - 4, 0)
        return (self.c(cor, "── ") + self.c(f"negrito+{cor}", rotulo)
                + self.c("cinza", n) + " " + self.c(cor, "─" * resto))

    def quebra(self, texto, recuo=0, pendurado=None, largura=None):
        """Quebra `texto` na largura do terminal com recuo pendurado. Devolve
        a lista de linhas, sem cor."""
        pendurado = recuo if pendurado is None else pendurado
        w = largura or self.largura()
        if len(texto) + recuo <= w:
            return [" " * recuo + texto]
        return textwrap.wrap(texto, width=w, initial_indent=" " * recuo,
                             subsequent_indent=" " * pendurado,
                             break_on_hyphens=False) or [" " * recuo]

    def corta(self, texto, largura):
        return texto if len(texto) <= largura else texto[:max(largura - 1, 1)] + "…"

    def barra(self, frac, n=24, cor="verde"):
        k = round(max(0.0, min(1.0, frac)) * n)
        return self.c(cor, "▰" * k) + self.c("cinza", "▱" * (n - k))

    def realce(self, texto):
        """Separadores apagados e palavras de veredito na cor delas."""
        if not self.ligada:
            return texto
        texto = texto.replace(" · ", self.c("cinza", " · "))
        texto = texto.replace(" — ", self.c("cinza", " — "))
        for padrao, cor in _PALAVRAS:
            texto = padrao.sub(lambda m, cor=cor: self.c(cor, m.group(0)), texto)
        return texto

    # ── decoração linha a linha, pelo formato do texto ──────────────────

    def linha(self, linha):
        if (not self.ligada or "\033" in linha or "\r" in linha
                or not linha.strip()):
            return linha
        corpo = linha.strip()
        if corpo[0] in "{}[]\"":
            return linha
        recuo = len(linha) - len(linha.lstrip(" "))

        m = re.match(r"^#\s+(.+)$", linha)
        if m:
            return self.cabecalho(m.group(1))
        m = re.match(r"^(?:#{2,}|──)\s+(.+?)\s*─*$", linha)
        if m:
            return self._secao_livre(m.group(1))
        if recuo == 0 and len(corpo) <= 72 and ": " not in corpo and (
                corpo.endswith(":") or _SECAO_CONTAGEM.match(corpo)):
            return self._secao_livre(corpo)

        prefixo, resto, cor = "", corpo, None
        m = _MARCADOR.match(resto)
        if m:
            prefixo, resto = m.group(0), resto[m.end():]
            cor = "cinza" if m.group(1)[0].isdigit() else MARCADORES[m.group(1)]
        chave = None
        m = _TAG.match(resto) or _CHAVE.match(resto)
        if m:
            chave = m.group(0)
            resto = resto[m.end():]
        pendurado = recuo + len(prefixo) + (len(chave) if chave and len(chave) <= 24 else 0)
        linhas = self.quebra(prefixo + (chave or "") + resto, recuo, pendurado)

        primeira = linhas[0][recuo + len(prefixo) + len(chave or ""):]
        id_traco = _ID_TRACO.match(primeira) if prefixo[:1].isdigit() else None
        if id_traco:
            primeira = (self.c("negrito+ciano", id_traco.group(1))
                        + self.c("cinza", id_traco.group(2))
                        + self.realce(primeira[id_traco.end():]))
        else:
            primeira = self.realce(primeira)
        saida = (" " * recuo + self.c(cor, prefixo) if prefixo else " " * recuo)
        if chave:
            saida += self.c("ciano" if chave.startswith("[") else "cinza", chave)
        saida += primeira
        return "\n".join([saida] + [self.realce(x) for x in linhas[1:]])

    def _secao_livre(self, texto):
        texto = texto.rstrip(":").rstrip()
        m = _SECAO_CONTAGEM.match(texto)
        if m:
            return self.secao(m.group(1), m.group(2))
        return self.secao(texto)


class Filtro:
    """Stdout que decora cada linha completa e repassa o resto como veio."""

    def __init__(self, fluxo, tela):
        self._fluxo = fluxo
        self._tela = tela
        self._pendente = ""

    def write(self, texto):
        self._pendente += texto
        if "\n" not in self._pendente:
            return len(texto)
        *completas, self._pendente = self._pendente.split("\n")
        self._fluxo.write("".join(self._tela.linha(l) + "\n" for l in completas))
        return len(texto)

    def flush(self):
        if self._pendente:
            self._fluxo.write(self._pendente)
            self._pendente = ""
        self._fluxo.flush()

    def __getattr__(self, nome):
        return getattr(self._fluxo, nome)


TELA = Tela()


def instalar():
    """Decora o stdout do comando quando ele é um terminal. Saída em JSON
    (`--json`) e pedido explícito de texto puro (`--sem-cor`) nunca são
    tocados."""
    if (not TELA.ligada or isinstance(sys.stdout, Filtro)
            or {"--json", "--sem-cor"} & set(sys.argv)):
        return
    sys.stdout = Filtro(sys.stdout, TELA)
