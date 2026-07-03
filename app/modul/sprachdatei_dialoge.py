"""Hilfsdialoge/-Delegates des Sprachdatei-Generators (`mod_sprachdatei.py`).

1:1 aus `mod_sprachdatei.py` ausgelagert (Refactoring 2026-07, Schritt 5):
`_TextEditDialog` (Einzeltext bearbeiten), `_FortschrittDialog` (selbst-schließendes
Status-Fenster für mehrschrittige KI-Aktionen) und `_MarkerHighlightDelegate`
(invers-rote Hervorhebung fehlerhafter Format-Marker in der Übersetzungsspalte).
"""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit, QLabel,
                             QHBoxLayout, QPushButton, QMessageBox, QApplication,
                             QTextEdit, QStyledItemDelegate, QStyle, QStyleOptionViewItem)
from PyQt6.QtCore import Qt, QSize, QRectF
from PyQt6.QtGui import QTextDocument, QPalette

import html
import re
import settings
import i18n
import theme
import spellcheck
from i18n import _


class _TextEditDialog(settings.DialogSizeMixin, QDialog):
    """Kleines Bearbeitungsfenster für einen einzelnen UI-Text (Quell- oder Zielsprache).
    Zeigt zur Orientierung eine read-only Kontextzeile (Schlüssel bzw. Quelltext) und ein
    mehrzeiliges Eingabefeld mit dem vorhandenen Text. Über `bearbeite(...)` als modaler
    Dialog: Rückgabe der neue (getrimmte) Text oder `None` bei Abbruch."""

    def __init__(self, parent, titel, kontext_label, kontext_text, feld_label, text,
                 spell_lang=None):
        super().__init__(parent)
        self.setWindowTitle(titel)
        self._dirty = False
        self._dirty_dot = QLabel("●")
        self._dirty_dot.setStyleSheet(theme.dirty_dot_style())
        self._dirty_dot.hide()

        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        kontext_feld = QLineEdit(kontext_text or "")
        kontext_feld.setReadOnly(True)
        form.addRow(kontext_label, kontext_feld)
        lay.addLayout(form)

        lay.addWidget(QLabel(feld_label))
        self._edit = QTextEdit()
        # Rechtschreibprüfung in der bearbeiteten Sprache (nicht der App-Sprache). Die
        # Prüfung nutzt ein globales Dictionary → vor dem Anhängen auf `spell_lang` umschalten;
        # `bearbeite()` stellt nach dem Schließen die App-Sprache wieder her. Ohne passendes
        # Wörterbuch (z. B. Singhalesisch) bleibt die Prüfung still inaktiv.
        if spell_lang:
            spellcheck.load_lang(spell_lang)
            self._edit._spell_hl = spellcheck.SpellCheckHighlighter(self._edit.document())
        # Snapshot VOR setPlainText: der Highlighter-Timer (400ms) feuert nach dem Laden
        # erneut textChanged, ohne dass der Nutzer etwas geändert hat. Statt blind dirty zu
        # setzen, wird der aktuelle Text mit dem Snapshot verglichen.
        self._snapshot = text or ""
        self._edit.setPlainText(self._snapshot)
        self._edit.textChanged.connect(self._refresh_dirty)
        lay.addWidget(self._edit, 1)

        btn_bar = QHBoxLayout()
        btn_bar.addStretch()
        btn_bar.addWidget(self._dirty_dot)
        btn_ok = QPushButton(_("btn.speichern"))
        btn_ok.clicked.connect(self.accept)
        btn_bar.addWidget(btn_ok)
        btn_cancel = QPushButton(_("btn.abbrechen"))
        btn_cancel.clicked.connect(self._handle_esc)
        btn_bar.addWidget(btn_cancel)
        lay.addLayout(btn_bar)

        # Vorbelegung zählt nicht als Änderung.
        self._dirty = False
        self._dirty_dot.hide()

    def _refresh_dirty(self):
        # textChanged feuert auch vom Highlighter; nur dirty setzen, wenn sich der Text
        # gegenüber dem geladenen Snapshot wirklich geändert hat.
        if self._edit.toPlainText() != self._snapshot:
            self._mark_dirty()

    def _mark_dirty(self):
        self._dirty = True
        self._dirty_dot.show()

    def _handle_esc(self):
        """Abbrechen/ESC: bei ungespeicherten Änderungen rückfragen, sonst sofort schließen."""
        if not self._dirty:
            self.reject()
            return
        if QMessageBox.question(
                self, _("msg.hinweis"), _("dlg.sprachdatei.edit_verwerfen")
        ) == QMessageBox.StandardButton.Yes:
            self.reject()

    def keyPressEvent(self, event):
        # Escape mit Dirty-Check abfangen; Enter/Pfeile bleiben dem mehrzeiligen Textfeld.
        if event.key() == Qt.Key.Key_Escape:
            self._handle_esc()
            return
        super().keyPressEvent(event)

    def wert(self) -> str:
        return self._edit.toPlainText().strip()

    @classmethod
    def bearbeite(cls, parent, titel, kontext_label, kontext_text, feld_label, text,
                  spell_lang=None):
        """Öffnet den Dialog modal; gibt den neuen getrimmten Text zurück oder `None` bei
        Abbruch. `spell_lang` aktiviert die Rechtschreibprüfung in dieser Sprache; danach
        wird die globale Prüfsprache wieder auf die App-Sprache gesetzt."""
        dlg = cls(parent, titel, kontext_label, kontext_text, feld_label, text,
                  spell_lang=spell_lang)
        try:
            if dlg.exec() == QDialog.DialogCode.Accepted:
                return dlg.wert()
            return None
        finally:
            if spell_lang:
                spellcheck.load_lang(i18n.current())


class _FortschrittDialog(QDialog):
    """Schlankes, modales Status-Fenster für mehrschrittige KI-Aktionen: zeigt je Schritt
    eine Beschreibung an und wird vom Aufrufer nach Abschluss automatisch geschlossen.
    Bewusst ohne `DialogSizeMixin` — ein transientes Popup ohne Eingabefelder, das sich
    selbst schließt; Geometrie-Speicherung, Auto-Fokus und Tastatur-Navigation hätten hier
    keinen Nutzen."""

    def __init__(self, parent, titel):
        super().__init__(parent)
        self.setWindowTitle(titel)
        self.setModal(True)
        # Nur selbst-schließend: System-Schließknopf entfernen.
        self.setWindowFlags(
            (self.windowFlags() | Qt.WindowType.CustomizeWindowHint)
            & ~Qt.WindowType.WindowCloseButtonHint)
        lay = QVBoxLayout(self)
        self._lbl = QLabel("", self)
        self._lbl.setWordWrap(True)
        self._lbl.setMinimumWidth(360)
        lay.addWidget(self._lbl)

    def schritt(self, text: str):
        """Beschreibung des aktuellen Schritts anzeigen und das Fenster sofort neu zeichnen."""
        self._lbl.setText(text)
        QApplication.processEvents()

    def keyPressEvent(self, event):
        # ESC nicht durchlassen — das Fenster schließt erst nach Abschluss der Aktion.
        if event.key() == Qt.Key.Key_Escape:
            return
        super().keyPressEvent(event)


class _MarkerHighlightDelegate(QStyledItemDelegate):
    """Rendert die Übersetzungsspalte als Rich-Text und hebt fehlerhafte Format-Marker
    (Platzhalter, die nicht in der Quelle stehen) **invers rot** hervor — roter Hintergrund,
    weiße Schrift. Die Liste der hervorzuhebenden Marker liegt je Zelle in `Qt.UserRole`
    (von `_set_row` gesetzt); die Basis-Schriftfarbe stammt aus dem `ForegroundRole` (bleibt
    rot bei unstimmigen Zeilen). Word-Wrap und Zeilenhöhe bleiben über `sizeHint` erhalten."""

    # Innenabstand der Zelle (links/oben), passend zum Standard-Item-Delegate.
    _PAD_X = 4
    _PAD_Y = 2

    def __init__(self, parent, bg_hex):
        super().__init__(parent)
        self._bg = bg_hex

    def _markup(self, text, marker):
        """HTML-Body: `text` html-escaped, jedes Vorkommen eines falschen Markers invers rot
        eingefasst (einmaliger Regex-Durchlauf → keine Doppel-Einfassung)."""
        roh = html.escape(text or "")
        uniq = [m for m in dict.fromkeys(marker or []) if m]
        if not uniq:
            return roh
        muster = re.compile("|".join(re.escape(html.escape(m)) for m in uniq))
        return muster.sub(
            lambda mo: (f"<span style=\"background-color:{self._bg}; color:#ffffff;\">"
                        f"{mo.group(0)}</span>"), roh)

    def _doc(self, option, index, width):
        """`QTextDocument` der Zelle, mit invers-roten Marker-Spans und passender Breite."""
        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        marker = index.data(Qt.ItemDataRole.UserRole) or []
        if option.state & QStyle.StateFlag.State_Selected:
            base = option.palette.color(QPalette.ColorRole.HighlightedText)
        else:
            fg = index.data(Qt.ItemDataRole.ForegroundRole)
            base = fg.color() if fg is not None else option.palette.color(
                QPalette.ColorRole.Text)
        doc.setHtml(f"<span style=\"color:{base.name()}\">{self._markup(text, marker)}</span>")
        if width > 0:
            doc.setTextWidth(width)
        return doc

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""                              # Text zeichnet das Dokument selbst
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        doc = self._doc(opt, index, opt.rect.width() - 2 * self._PAD_X)
        painter.save()
        painter.translate(opt.rect.left() + self._PAD_X, opt.rect.top() + self._PAD_Y)
        doc.drawContents(painter, QRectF(0, 0, opt.rect.width() - 2 * self._PAD_X,
                                         opt.rect.height() - 2 * self._PAD_Y))
        painter.restore()

    def sizeHint(self, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        breite = opt.rect.width() - 2 * self._PAD_X
        doc = self._doc(opt, index, breite if breite > 0 else 0)
        return QSize(int(doc.idealWidth()) + 2 * self._PAD_X,
                     int(doc.size().height()) + 2 * self._PAD_Y)
