"""Deutsche Rechtschreibprüfung für QTextEdit-Widgets (Hunspell via pyenchant)."""
import re
import enchant
from PyQt6.QtGui import (QSyntaxHighlighter, QTextCharFormat, QColor,
                          QPainter, QPen)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QLineEdit, QStyle, QStyleOptionFrame

_ERROR_FORMAT = QTextCharFormat()
_ERROR_FORMAT.setUnderlineColor(QColor(220, 20, 60))
_ERROR_FORMAT.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)

# Abkürzungen und Fachbegriffe, die zusätzlich akzeptiert werden
_KNOWN_WORDS = {
    "nr", "str", "zb", "usw", "uu", "zzgl", "inkl", "exkl",
    "bzw", "ggf", "evtl", "ca", "betr",
    "mahnkondition", "mahnkonditionen", "zahlungskondition", "zahlungskonditionen",
    "lieferscheinnr", "auftragsnr", "angebotsnr", "rechnungsnr",
    "fälligkeitdatum", "skonto",
    "sepa", "iban", "bic",
    "mazins",
}

_dict = None
try:
    _dict = enchant.Dict('de_DE')
except enchant.errors.DictNotFoundError as e:
    print(f"Deutsches Wörterbuch nicht gefunden: {e}")

# Token: Wort aus Buchstaben (inkl. Umlaute), evtl. mit Bindestrich/Apostroph
_WORD_RE = re.compile(r"[A-Za-zÄÖÜäöüß]+(?:[-'][A-Za-zÄÖÜäöüß]+)*")
# Marker {ABC} oder {ABC%}/{ABC€} überspringen
_MARKER_RE = re.compile(r"\{[A-Za-zÄÖÜäöüß%€]+\}")


def add_words(words):
    """Fügt Wörter zur Whitelist hinzu (z. B. Firmennamen)."""
    for w in words:
        _KNOWN_WORDS.add(w.lower())


def _is_misspelled(word):
    if word.lower() in _KNOWN_WORDS:
        return False
    if len(word) < 2:
        return False
    return not _dict.check(word)


def _find_misspelled_spans(text):
    """Liefert eine Liste (start, length) der falsch geschriebenen Wörter."""
    if _dict is None or not text:
        return []
    masked = list(text)
    for m in _MARKER_RE.finditer(text):
        for i in range(m.start(), m.end()):
            masked[i] = ' '
    masked_text = ''.join(masked)
    spans = []
    for m in _WORD_RE.finditer(masked_text):
        word = m.group()
        if _is_misspelled(word):
            spans.append((m.start(), len(word)))
    return spans


class SpellCheckHighlighter(QSyntaxHighlighter):
    """Rechtschreibprüfung für QTextEdit/QPlainTextEdit (mehrzeilig)."""

    def __init__(self, document):
        super().__init__(document)
        # Debounce: nur prüfen, wenn 400ms keine Eingabe mehr kam
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self.rehighlight)
        document.contentsChanged.connect(self._timer.start)

    def highlightBlock(self, text):
        for start, length in _find_misspelled_spans(text):
            self.setFormat(start, length, _ERROR_FORMAT)


class SpellCheckLineEdit(QLineEdit):
    """Einzeiliges Eingabefeld mit Rechtschreibprüfung (rote Wellenlinien)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._spans = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._do_check)
        self.textChanged.connect(self._timer.start)
        # Initial-Check für vorbefüllten Text
        QTimer.singleShot(0, self._do_check)

    def _do_check(self):
        new_spans = _find_misspelled_spans(self.text())
        if new_spans != self._spans:
            self._spans = new_spans
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._spans or _dict is None:
            return
        text = self.text()
        if not text:
            return
        # Text-Bereich vom Style ermitteln (innerhalb von Frame/Padding)
        opt = QStyleOptionFrame()
        self.initStyleOption(opt)
        contents = self.style().subElementRect(
            QStyle.SubElement.SE_LineEditContents, opt, self)
        # QLineEdit zeichnet den Text mit zusätzlich 2px horizontalem Margin
        contents = contents.adjusted(2, 0, -2, 0)

        fm = self.fontMetrics()
        # Vertikale Mitte berechnen, Baseline + 2px für die Wellenlinie
        text_h = fm.height()
        top = contents.top() + (contents.height() - text_h) // 2
        baseline = top + fm.ascent()
        y = baseline + 2

        painter = QPainter(self)
        pen = QPen(QColor(220, 20, 60))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setClipRect(contents)

        for start, length in self._spans:
            x1 = contents.left() + fm.horizontalAdvance(text[:start])
            x2 = x1 + fm.horizontalAdvance(text[start:start + length])
            self._draw_squiggle(painter, x1, x2, y)
        painter.end()

    @staticmethod
    def _draw_squiggle(painter, x1, x2, y):
        """Zickzack-Linie zwischen x1 und x2 auf Höhe y."""
        step = 2
        amplitude = 2
        x = x1
        up = True
        while x < x2:
            nx = min(x + step, x2)
            y1 = y - (amplitude if up else 0)
            y2 = y - (amplitude if not up else 0)
            painter.drawLine(int(x), int(y1), int(nx), int(y2))
            up = not up
            x = nx


def attach(widget):
    """Hängt Rechtschreibprüfung an ein QTextEdit/QPlainTextEdit an.

    Für QLineEdit-Felder direkt `SpellCheckLineEdit` als Klasse verwenden.
    """
    widget._spell_hl = SpellCheckHighlighter(widget.document())
    return widget._spell_hl
