"""Dialoge/Widgets des Firmenstamm-Reiters „Anbindung KI" (`mod_firma_ki.py`).

1:1 ausgelagert (Refactoring 2026-07, Schritt 6): `_PromptFeld` (klickbares
Prompt-Anzeigefeld), `PromptMarkdownDialog` (Markdown-Editor mit Live-Vorschau),
`ModellAuswahlDialog` (Modell-Liste mit Filter) sowie der Höhen-Helfer
`_hoehe_zeilen`.
"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QTextEdit,
                             QLabel, QPushButton, QDialog, QListWidget, QListWidgetItem,
                             QDialogButtonBox, QMessageBox, QSplitter)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QTextCursor
from spellcheck import SpellCheckHighlighter
from i18n import _
import settings
import theme


def _hoehe_zeilen(te, zeilen):
    """Feste Höhe eines QTextEdit für die angegebene Zeilenzahl (aus Schriftmetrik)."""
    fm = te.fontMetrics()
    return fm.lineSpacing() * zeilen + 2 * int(te.document().documentMargin()) + 14


class _PromptFeld(QTextEdit):
    """Zweizeiliges, read-only Anzeigefeld für einen KI-Prompt. Der Inhalt bleibt der
    Markdown-Rohtext (damit `toPlainText` weiterhin den Prompt liefert); ein Klick öffnet
    den Markdown-Editor (Signal `clicked`).

    Das Feld zeigt immer den Textanfang (keine vertikale Scrollleiste, kein „Rollfeld"):
    längere Prompts werden oben angeschnitten, der volle Text steht im Editor."""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def setPlainText(self, text):
        # Nach dem Setzen immer an den Textanfang springen, damit das Feld oben beginnt
        # (und nicht beim zuletzt gescrollten/Cursor-Stand stehen bleibt).
        super().setPlainText(text)
        self.moveCursor(QTextCursor.MoveOperation.Start)
        self.verticalScrollBar().setValue(0)

    def mousePressEvent(self, event):
        # Klick = bearbeiten; kein super() (keine Markierung/Cursor-Positionierung nötig).
        self.clicked.emit()


class PromptMarkdownDialog(settings.DialogSizeMixin, QDialog):
    """Markdown-Editor mit Live-Vorschau zum Bearbeiten eines KI-Prompts.

    Links der Markdown-Quelltext (mit Rechtschreibprüfung), rechts die gerenderte Vorschau
    (read-only, via `setMarkdown`, bei jeder Änderung aktualisiert). Optionale Marker-Buttons
    fügen Platzhalter an der Cursorposition ein. Über `bearbeite(...)` als modaler Dialog;
    Rückgabe der neue Text oder `None` bei Abbruch."""

    def __init__(self, parent, titel, text, marker=()):
        super().__init__(parent)
        self.setWindowTitle(titel)
        self.setMinimumSize(760, 440)
        self._dirty = False
        self._dirty_dot = QLabel("●")
        self._dirty_dot.setStyleSheet(theme.dirty_dot_style())
        self._dirty_dot.hide()

        lay = QVBoxLayout(self)

        # Marker-Buttons (nur bei Prompts mit Platzhaltern) – fügen an der Cursorposition ein.
        if marker:
            mrow = QHBoxLayout()
            mrow.setContentsMargins(0, 0, 0, 0)
            mrow.setSpacing(6)
            mrow.addWidget(QLabel(_("firma.ki.marker_label")))
            for m in marker:
                b = QPushButton(m)
                b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                b.setToolTip(_("firma.ki.marker_tip"))
                b.clicked.connect(lambda _c=False, mm=m: self._edit.insertPlainText(mm))
                mrow.addWidget(b)
            mrow.addStretch()
            lay.addLayout(mrow)

        # Split: links Editor (Markdown-Quelle), rechts Live-Vorschau.
        split = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel(_("firma.ki.prompt_quelle")))
        self._edit = QTextEdit()
        self._edit.setAcceptRichText(False)
        self._edit._spell_hl = SpellCheckHighlighter(self._edit.document())
        ll.addWidget(self._edit, 1)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel(_("firma.ki.prompt_vorschau")))
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        rl.addWidget(self._preview, 1)
        split.addWidget(right)

        split.setSizes([400, 400])
        lay.addWidget(split, 1)

        # Snapshot VOR setPlainText: der Highlighter-Timer feuert textChanged ohne echte
        # Änderung – Dirty wird daher gegen den Snapshot verglichen, nicht blind gesetzt.
        self._snapshot = text or ""
        self._edit.setPlainText(self._snapshot)
        self._preview.setMarkdown(self._snapshot)
        self._edit.textChanged.connect(self._on_changed)

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

    def _on_changed(self):
        txt = self._edit.toPlainText()
        self._preview.setMarkdown(txt)
        if txt != self._snapshot:
            self._dirty = True
            self._dirty_dot.show()

    def _handle_esc(self):
        """Abbrechen/ESC: bei ungespeicherten Änderungen rückfragen, sonst sofort schließen."""
        if not self._dirty:
            self.reject()
            return
        if QMessageBox.question(
                self, _("msg.hinweis"), _("firma.ki.prompt_edit_verwerfen")
        ) == QMessageBox.StandardButton.Yes:
            self.reject()

    def keyPressEvent(self, event):
        # Escape mit Dirty-Check; Enter/Pfeile bleiben dem mehrzeiligen Textfeld.
        if event.key() == Qt.Key.Key_Escape:
            self._handle_esc()
            return
        super().keyPressEvent(event)

    @classmethod
    def bearbeite(cls, parent, titel, text, marker=()):
        """Öffnet den Dialog modal; gibt den neuen Text zurück oder `None` bei Abbruch."""
        dlg = cls(parent, titel, text, marker)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg._edit.toPlainText()
        return None


class ModellAuswahlDialog(settings.DialogSizeMixin, QDialog):
    """Auswahl eines Modells aus der vollständigen Anbieter-Liste (mit Filter).
    Bestätigung per OK, Doppelklick oder Enter (Listen-Dialog-Regel)."""
    HELP_ANCHOR = "firma-ki"

    def __init__(self, parent, modelle, aktuell=""):
        super().__init__(parent)
        self._modelle = list(modelle)
        self._gewaehlt = None
        self.setWindowTitle(_("firma.ki.dlg.modell_auswahl.titel"))
        self.setMinimumSize(420, 460)

        lay = QVBoxLayout(self)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText(_("firma.ki.dlg.modell_auswahl.filter"))
        self._filter.textChanged.connect(self._refresh)
        lay.addWidget(self._filter)

        self.table = QListWidget()
        self.table.doubleClicked.connect(self._ok)
        lay.addWidget(self.table, 1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("btn.ok"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self._refresh()
        self._select_aktuell(aktuell)

    def _refresh(self):
        flt = self._filter.text().strip().lower()
        self.table.clear()
        for m in self._modelle:
            if not flt or flt in m.lower():
                self.table.addItem(QListWidgetItem(m))
        if self.table.count() > 0 and self.table.currentRow() < 0:
            self.table.setCurrentRow(0)

    def _select_aktuell(self, aktuell):
        if not aktuell:
            return
        treffer = self.table.findItems(aktuell, Qt.MatchFlag.MatchExactly)
        if treffer:
            self.table.setCurrentItem(treffer[0])

    def _ok(self):
        item = self.table.currentItem()
        if item is None:
            return
        self._gewaehlt = item.text()
        self.accept()

    def gewaehltes_modell(self):
        return self._gewaehlt

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._ok()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)
