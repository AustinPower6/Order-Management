"""Gemeinsame UI-Hilfswidgets und -Layouts."""
import collections
import logging
from PyQt6.QtCore import Qt, QPoint, QRect, QSize, QTimer, QEventLoop, QObject
from PyQt6.QtWidgets import (QLayout, QWidget, QSizePolicy, QHBoxLayout, QLabel, QPushButton,
                              QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox,
                              QMessageBox, QApplication, QStyle, QStyleOptionTab,
                              QStylePainter, QTabBar, QTabWidget, QComboBox, QTableView,
                              QLineEdit, QAbstractSpinBox, QCheckBox, QScrollArea)
from i18n import _
import theme


def resolve_iban_in_felder(iban_edit, bic_edit, bank_edit, hint_label, *, ueberschreiben,
                           dialog_parent=None):
    """Validiert die IBAN aus `iban_edit` (MOD-97, offline), löst BIC/Bankname auf und
    füllt `bic_edit`/`bank_edit` — bei `ueberschreiben=False` nur, wenn das Zielfeld leer
    ist (nicht-destruktiv), bei `True` immer (expliziter „ermitteln"-Klick). `hint_label`
    zeigt Bank/BIC bzw. eine Fehlermeldung. Rein anzeigend; keine DB-Änderung.

    Bei gesetztem `dialog_parent` (expliziter Button-Klick) erscheint zusätzlich eine
    **Meldung** (QMessageBox), wenn die Funktion nicht anwendbar ist: leere/ungültige IBAN,
    Land nicht unterstützt (nur DE) oder keine Bank in der Registry gefunden. Ohne
    `dialog_parent` (passives Auflösen beim Verlassen des Felds) nur der stille Hinweis.
    Nutzt das Qt-freie `bank`-Modul (schwifty)."""
    import bank

    def _melde(text):
        if dialog_parent is not None:
            QMessageBox.information(dialog_parent, _("bank.titel"), text)

    roh = (iban_edit.text() or "").strip()
    if not roh:
        hint_label.setText("")
        _melde(_("bank.keine_iban"))
        return
    if not bank.validiere_iban(roh):
        hint_label.setText(_("bank.iban_ungueltig"))
        hint_label.setStyleSheet(theme.error_text_style())
        _melde(_("bank.iban_ungueltig"))
        return
    try:
        bd = bank.resolve_bankdaten(roh)
    except bank.LandNichtUnterstuetzt:
        hint_label.setText(_("bank.land_nicht_unterstuetzt"))
        hint_label.setStyleSheet(theme.hint_label_style())
        _melde(_("bank.land_nicht_unterstuetzt"))
        return
    except bank.UngueltigeIBAN:
        hint_label.setText(_("bank.iban_ungueltig"))
        hint_label.setStyleSheet(theme.error_text_style())
        _melde(_("bank.iban_ungueltig"))
        return
    hint_label.setStyleSheet(theme.hint_label_style())
    if not bd:
        hint_label.setText(_("bank.keine_bank"))   # gültig, aber keine Registry-Zuordnung
        _melde(_("bank.keine_bank"))
        return
    if bd.bic and (ueberschreiben or not (bic_edit.text() or "").strip()):
        bic_edit.setText(bd.bic)
    if bd.bank_name and (ueberschreiben or not (bank_edit.text() or "").strip()):
        bank_edit.setText(bd.bank_name)
    hint_label.setText(_("bank.aufgeloest", bank=bd.bank_name or "—", bic=bd.bic or "—"))


def focus_skip_non_input(forward: bool) -> None:
    """Nach focusNextChild/focusPreviousChild Nicht-Eingabe-Widgets überspringen:
    read-only QLineEdit/QTextEdit sowie QPushButton. Schleife mit Abbruchzähler
    gegen Endlosloop (z. B. Dialog nur aus Buttons)."""
    for _step in range(50):
        w = QApplication.focusWidget()
        if w is None:
            break
        skip = (
            isinstance(w, QPushButton) or
            (isinstance(w, (QLineEdit, QTextEdit)) and w.isReadOnly())
        )
        if not skip:
            break
        if forward:
            w.focusNextChild()
        else:
            w.focusPreviousChild()


def _navigation_root(w: QWidget) -> QWidget:
    """Ermittelt die Navigationsgrenze für w.

    In QDialog-Fenstern: der Dialog selbst (Fokuskette ist ohnehin auf ihn begrenzt).
    In QWidget-Formularen (z. B. Firmenstamm-Reiter): die direkte Unterseite des
    nächstgelegenen QTabWidget — damit navigate_next/prev nicht aus dem aktuellen
    Reiter in die Toolbar oder andere Reiter herausspringen."""
    window = w.window()
    if isinstance(window, QDialog):
        return window
    prev = w
    parent = w.parent()
    while parent and parent is not window:
        if isinstance(parent, QTabWidget):
            return prev  # prev ist die aktuelle Tab-Seite
        prev = parent
        parent = parent.parent()
    return window


def _scroll_into_view(w: QWidget) -> None:
    """Scrollt den nächstgelegenen QScrollArea so, dass w sichtbar ist."""
    parent = w.parent()
    while parent is not None:
        if isinstance(parent, QScrollArea):
            parent.ensureWidgetVisible(w)
            return
        parent = parent.parent()


def _is_navigable(w) -> bool:
    """Gibt True zurück, wenn w ein echtes Eingabefeld ist — kein Button, kein read-only."""
    if not isinstance(w, QWidget):
        return False
    if not w.isVisible() or not w.isEnabled():
        return False
    if isinstance(w, QPushButton):
        return False
    # Internes QLineEdit eines QAbstractSpinBox ist KEIN eigenes Ziel — der Spinbox
    # selbst ist das navigierbare Feld. Sonst landet navigate_next() im internen
    # Editor derselben Spinbox (Fokus bleibt scheinbar stehen).
    if isinstance(w, QLineEdit) and isinstance(w.parent(), QAbstractSpinBox):
        return False
    if isinstance(w, (QLineEdit, QTextEdit)) and w.isReadOnly():
        return False
    return isinstance(w, (QLineEdit, QAbstractSpinBox, QComboBox, QTextEdit, QCheckBox))


def _effective_current() -> QWidget | None:
    """Liefert das effektive Startwidget für die Navigation.
    Wenn das Fokus-Widget das interne QLineEdit eines QAbstractSpinBox ist,
    wird der Spinbox selbst zurückgegeben — sonst würde nextInFocusChain()
    sofort zum Container-Spinbox zurücklaufen und die Navigation stecken bleiben."""
    w = QApplication.focusWidget()
    if w is None:
        return None
    if isinstance(w, QLineEdit) and isinstance(w.parent(), QAbstractSpinBox):
        return w.parent()
    return w


def navigate_next() -> bool:
    """Fokus auf das nächste Eingabefeld innerhalb derselben Tab-Seite/desselben Dialogs.
    Am letzten Feld kein Wrap-Around — Fokus bleibt. Gibt True zurück, wenn der Fokus
    auf ein neues Feld gesetzt wurde."""
    current = _effective_current()
    if current is None:
        return False
    root = _navigation_root(current)
    w = current.nextInFocusChain()
    for _step in range(200):
        if w is current:
            return False  # einmal rundherum ohne Fund = letztes Feld, bleiben
        in_root = (root is w.window()) or root.isAncestorOf(w)
        if in_root and _is_navigable(w):
            w.setFocus()
            _scroll_into_view(w)
            return True
        w = w.nextInFocusChain()
    return False


def navigate_prev() -> bool:
    """Fokus auf das vorherige Eingabefeld innerhalb derselben Tab-Seite/desselben Dialogs.
    Am ersten Feld kein Wrap-Around — Fokus bleibt. Gibt True zurück, wenn der Fokus
    auf ein neues Feld gesetzt wurde."""
    current = _effective_current()
    if current is None:
        return False
    root = _navigation_root(current)
    w = current.previousInFocusChain()
    for _step in range(200):
        if w is current:
            return False  # einmal rundherum ohne Fund = erstes Feld, bleiben
        in_root = (root is w.window()) or root.isAncestorOf(w)
        if in_root and _is_navigable(w):
            w.setFocus()
            _scroll_into_view(w)
            return True
        w = w.previousInFocusChain()
    return False


class TableHomeEndNavFilter(QObject):
    """Globaler Event-Filter für Tabellen (QTableView/QTableWidget):

    **Pos1** springt zur ersten, **Ende** zur letzten Zeile der Tabelle (statt zur
    ersten/letzten Spalte wie im Qt-Standard). **Bild auf/ab** blättern seitenweise
    — das ist bereits Qt-Standard und wird hier bewusst nicht abgefangen.
    Greift nur ohne Modifier, damit Shift-/Strg-Bereichsauswahl unverändert bleibt.
    Wird in main() einmalig auf die QApplication installiert."""

    def eventFilter(self, obj, event):
        if event.type() != event.Type.KeyPress:
            return False
        if not isinstance(obj, QTableView):
            return False
        if event.modifiers() != Qt.KeyboardModifier.NoModifier:
            return False
        key = event.key()
        if key not in (Qt.Key.Key_Home, Qt.Key.Key_End):
            return False
        model = obj.model()
        if model is None or model.rowCount() == 0:
            return False
        col = obj.currentIndex().column()
        if col < 0:
            col = 0
        row = 0 if key == Qt.Key.Key_Home else model.rowCount() - 1
        target = model.index(row, col)
        obj.setCurrentIndex(target)
        obj.scrollTo(target)
        return True


class LineEditNavFilter(QObject):
    """Globaler Event-Filter für Eingabefelder in QWidget-Formularen:

    - QLineEdit (nicht read-only): Enter/Pfeil-runter → nächstes Feld,
      Pfeil-hoch → vorheriges Feld.
    - QAbstractSpinBox (QSpinBox, QDoubleSpinBox, QDateEdit): nur Enter navigiert;
      Pfeil-hoch/runter bleibt dem Widget (Wert ändern) überlassen.
    In QDialog-Fenstern wird nicht eingegriffen — dort greift DialogSizeMixin,
    und Dialoge wie PosDialog behalten ihr Enter → _ok()-Verhalten.
    Wird in main() einmalig auf die QApplication installiert."""

    def eventFilter(self, obj, event):
        if event.type() != event.Type.KeyPress:
            return False
        key = event.key()
        # Liegt der Fokus auf einem QPushButton, soll Pfeil hoch/runter nicht Qt's
        # eingebaute Button-zu-Button-Navigation auslösen, sondern in den Felder-Durchlauf
        # zurückführen. Nur konsumieren, wenn tatsächlich ein Feld gefunden wurde — so
        # bleiben Buttons in QMessageBox/QDialogButtonBox-Leisten ohne Felder unberührt.
        if isinstance(obj, QPushButton):
            if key == Qt.Key.Key_Down:
                return navigate_next()
            if key == Qt.Key.Key_Up:
                return navigate_prev()
            return False
        # Internes QLineEdit eines QAbstractSpinBox: Verhalten vom Parent-Spinbox ableiten.
        # Qt6 sendet Tastaturevents an das interne QLineEdit, nicht an den Spinbox selbst.
        if isinstance(obj, QLineEdit) and isinstance(obj.parent(), QAbstractSpinBox):
            spinbox = obj.parent()
            if isinstance(spinbox.window(), QDialog):
                return False
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                navigate_next()
                return True
            if spinbox.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons:
                if key == Qt.Key.Key_Down:
                    navigate_next()
                    return True
                if key == Qt.Key.Key_Up:
                    navigate_prev()
                    return True
            return False
        if isinstance(obj, QLineEdit) and not obj.isReadOnly():
            if isinstance(obj.window(), QDialog):
                return False
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Down):
                navigate_next()
                return True
            if key == Qt.Key.Key_Up:
                navigate_prev()
                return True
        elif isinstance(obj, QAbstractSpinBox):
            # Fallback: Qt sendet Event direkt an QAbstractSpinBox (Qt5-Verhalten)
            if isinstance(obj.window(), QDialog):
                return False
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                navigate_next()
                return True
            if obj.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons:
                if key == Qt.Key.Key_Down:
                    navigate_next()
                    return True
                if key == Qt.Key.Key_Up:
                    navigate_prev()
                    return True
        return False


class ComboArrowNavFilter(QObject):
    """Globaler Event-Filter für Auswahlfelder (nicht editierbare QComboBox):

    Pfeil **links/rechts** ändert die Auswahl, Pfeil **hoch/runter** bleibt für den
    Durchlauf durch den Dialog reserviert (Fokuswechsel statt Auswahländerung) —
    konsistent zur Feld-Navigation des DialogSizeMixin. Wird in main() einmalig auf
    die QApplication installiert. Editierbare ComboBoxen liefern ihre Tasten über
    das interne QLineEdit und bleiben daher unberührt (Cursor-Bewegung)."""

    def eventFilter(self, obj, event):
        if event.type() != event.Type.KeyPress:
            return False
        if not isinstance(obj, QComboBox) or obj.isEditable():
            return False
        key = event.key()
        if key == Qt.Key.Key_Up:
            navigate_prev()
            return True
        if key == Qt.Key.Key_Down:
            navigate_next()
            return True
        if key == Qt.Key.Key_Left:
            if obj.currentIndex() > 0:
                obj.setCurrentIndex(obj.currentIndex() - 1)
            return True
        if key == Qt.Key.Key_Right:
            if obj.currentIndex() < obj.count() - 1:
                obj.setCurrentIndex(obj.currentIndex() + 1)
            return True
        return False


class _MemoryLogHandler(logging.Handler):
    """Behält die letzten N formatierten Log-Einträge im Speicher.

    Wird von _setup_logging() (main.py) am Root-Logger registriert und von
    _MsgDialog automatisch ausgelesen, um technische Details im Fehlerdialog
    anzuzeigen.
    """
    def __init__(self, capacity=5):
        super().__init__()
        self._records: collections.deque = collections.deque(maxlen=capacity)
        self.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"))

    def emit(self, record):
        try:
            self._records.append(self.format(record))
        except Exception:
            self.handleError(record)

    def get_last(self) -> str:
        return "\n".join(self._records)

    def clear(self):
        self._records.clear()


# Globale Instanz — von main._setup_logging() am Root-Logger registriert.
last_log_handler = _MemoryLogHandler(capacity=5)

# Callback zum Versand an den Entwickler — wird von main.py nach DB-Init gesetzt.
# Signatur: fn(fehlertext: str) → None
developer_email_fn = None


class LadeOverlay:
    """Kontextmanager: zeigt 'Daten werden geladen …' zentriert über parent_widget."""

    def __init__(self, parent: QWidget):
        self._parent = parent
        self._lbl: QLabel | None = None

    def __enter__(self):
        import settings as _settings
        if not _settings.get_lade_overlay_aktiv():
            return self
        # Top-Level-Fenster: keine Z-Order-Probleme durch Kind-Widgets
        lbl = QLabel(_("msg.daten_werden_geladen"))
        lbl.setWindowFlags(
            Qt.WindowType.Tool |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        lbl.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(theme.overlay_style())
        # Erst show(), damit Qt das Stylesheet polished und adjustSize() korrekt rechnet
        lbl.show()
        lbl.adjustSize()
        if self._parent and self._parent.isVisible():
            center = self._parent.mapToGlobal(self._parent.rect().center())
        else:
            center = QApplication.primaryScreen().geometry().center()
        lbl.move(center.x() - lbl.width() // 2,
                 center.y() - lbl.height() // 2)
        lbl.repaint()
        # QEventLoop mit ExcludeUserInputEvents: WM_PAINT wird verarbeitet (Overlay sichtbar),
        # Maus-/Tastatur-Events bleiben in der Queue (kein Drag-Ruckeln)
        _loop = QEventLoop()
        QTimer.singleShot(0, _loop.quit)
        _loop.exec(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        self._lbl = lbl
        return self

    def __exit__(self, *_args):
        if self._lbl:
            self._lbl.hide()
            self._lbl.deleteLater()
            self._lbl = None


class HorizontalLeftTabBar(QTabBar):
    """TabBar für TabPosition.West, hält den Beschriftungstext aber horizontal
    (statt vertikal um 90° gedreht wie im Qt-Default). Tabs sind links neben
    dem Inhalt, alle gleichzeitig sichtbar."""

    _MAX_WIDTH = 140
    _TAB_HEIGHT = 24

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setExpanding(False)

    def tabSizeHint(self, index):
        s = super().tabSizeHint(index)
        if s.height() > s.width():
            s.transpose()
        s.setWidth(min(s.width(), self._MAX_WIDTH))
        s.setHeight(self._TAB_HEIGHT)
        return s

    def paintEvent(self, event):
        painter = QStylePainter(self)
        opt = QStyleOptionTab()
        for i in range(self.count()):
            self.initStyleOption(opt, i)
            painter.drawControl(QStyle.ControlElement.CE_TabBarTabShape, opt)
            rect = self.tabRect(i)
            text_rect = rect.adjusted(6, 0, -4, 0)
            text = self.fontMetrics().elidedText(
                self.tabText(i), Qt.TextElideMode.ElideRight, text_rect.width())
            painter.drawText(text_rect,
                             int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                             text)


class FlowLayout(QLayout):
    """Layout das Widgets automatisch in neue Zeilen umbricht (Fließ-Layout)."""

    def __init__(self, parent=None, h_spacing=2, v_spacing=2):
        super().__init__(parent)
        self._items = []
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = eff.x(), eff.y(), 0
        for item in self._items:
            sh = item.sizeHint()
            next_x = x + sh.width() + self._h_spacing
            if next_x - self._h_spacing > eff.right() and line_h > 0:
                x = eff.x()
                y += line_h + self._v_spacing
                next_x = x + sh.width() + self._h_spacing
                line_h = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), sh))
            x = next_x
            line_h = max(line_h, sh.height())
        return y + line_h - rect.y() + m.bottom()


class FlowWidget(QWidget):
    """QWidget mit FlowLayout, das hasHeightForWidth() korrekt an den Eltern propagiert.

    Verwendung: widget = FlowWidget(); widget.layout().addWidget(btn)
    """

    def __init__(self, parent=None, h_spacing=2, v_spacing=2):
        super().__init__(parent)
        FlowLayout(self, h_spacing=h_spacing, v_spacing=v_spacing)
        # QSizePolicy muss hasHeightForWidth setzen, damit QVBoxLayout
        # heightForWidth() tatsächlich aufruft
        sp = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        lay = self.layout()
        return lay.heightForWidth(width) if lay else super().heightForWidth(width)

    def sizeHint(self):
        lay = self.layout()
        if lay:
            w = self.width() if self.width() > 0 else 600
            return QSize(w, lay.heightForWidth(w))
        return super().sizeHint()

    def minimumSizeHint(self):
        lay = self.layout()
        if lay:
            return QSize(50, lay.heightForWidth(600))
        return super().minimumSizeHint()


def setze_formular_readonly(root, ausser=()):
    """Alle Eingabefelder unter `root` schreibgeschützt schalten (Rechtestufe „lesen").

    Der Datensatz bleibt vollständig lesbar — nur ändern lässt sich nichts:
    - Text-/Zahlenfelder: `setReadOnly(True)`. Bewusst nicht `setEnabled(False)`,
      sonst wäre der Inhalt nicht mehr markier- und kopierbar. Das graue Aussehen
      kommt global aus `theme.py` (`QLineEdit:read-only`).
    - Auswahlfelder/Checkboxen: `setEnabled(False)` — sie kennen kein read-only,
      ihr Wert bleibt aber lesbar.

    Buttons bleiben unberührt: Sie schaltet der Aufrufer gezielt (Speichern über
    `SaveBar.set_speichern_gesperrt`), und die Methoden dahinter haben ohnehin
    ihre eigenen Rechte-Guards. `ausser` nimmt Widgets aus, die bedienbar bleiben
    müssen (z. B. eine Sprachauswahl, die nur die Anzeige umschaltet).
    """
    for w in root.findChildren(QWidget):
        if w in ausser:
            continue
        if isinstance(w, (QLineEdit, QTextEdit)):
            w.setReadOnly(True)
        elif isinstance(w, QAbstractSpinBox):
            w.setReadOnly(True)
            w.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        elif isinstance(w, (QComboBox, QCheckBox)):
            w.setEnabled(False)


def dialog_readonly(dlg, modul_label=""):
    """Dialog nur zum Ansehen öffnen (Rechtestufe „lesen").

    Felder werden schreibgeschützt, und jeder Weg, der die Eingabe übernehmen
    würde, wird gesperrt: „Speichern"/„OK" als QDialogButtonBox-Standardbutton
    ebenso wie als eigener QPushButton. „Abbrechen"/„Schließen" bleibt bedienbar —
    sonst käme man aus dem Dialog nur noch über ESC heraus.

    Vor `exec()` aufrufen, nachdem der Dialog gebaut und gefüllt ist.
    """
    setze_formular_readonly(dlg)
    tipp = _("msg.nur_lesen", modul=modul_label)

    for bb in dlg.findChildren(QDialogButtonBox):
        for sb in (QDialogButtonBox.StandardButton.Ok,
                   QDialogButtonBox.StandardButton.Save,
                   QDialogButtonBox.StandardButton.Apply):
            b = bb.button(sb)
            if b is not None:
                b.setEnabled(False)
                b.setToolTip(tipp)

    for b in dlg.findChildren(QPushButton):
        if b.text() in (_("btn.speichern"), _("btn.ok")):
            b.setEnabled(False)
            b.setToolTip(tipp)


class SaveBar(QWidget):
    """Zeilen-Widget mit Speichern/Abbrechen-Buttons und dirty-Punkt."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        self._dirty = False
        self._grace = False

        lay.addStretch()

        self._dot = QLabel("●")
        self._dot.setStyleSheet(theme.dirty_dot_style())
        self._dot.hide()
        lay.addWidget(self._dot)

        self._btn_save = QPushButton(_("btn.speichern"))
        lay.addWidget(self._btn_save)

        self._btn_cancel = QPushButton(_("btn.abbrechen"))
        lay.addWidget(self._btn_cancel)

    def set_callbacks(self, save_fn, cancel_fn):
        """Callbacks für Speichern und Abbrechen setzen."""
        try:
            self._btn_save.clicked.disconnect()
        except TypeError:
            pass
        try:
            self._btn_cancel.clicked.disconnect()
        except TypeError:
            pass
        self._btn_save.clicked.connect(save_fn)
        self._btn_cancel.clicked.connect(cancel_fn)

    def set_dirty(self, dirty=True):
        if self._grace:
            return
        if dirty and not self._dirty:
            self._dirty = True
            self._dot.show()
        elif not dirty:
            self._dirty = False
            self._dot.hide()

    def is_dirty(self):
        return self._dirty

    def reset_dirty(self):
        self._dirty = False
        self._dot.hide()
        self._grace = True
        QTimer.singleShot(100, lambda: setattr(self, '_grace', False))

    def set_speichern_gesperrt(self, gesperrt, modul_label=""):
        """Speichern ausgrauen und funktionslos machen (Rechtestufe „lesen").

        Nur die Anzeige — die Methoden dahinter haben ihre eigenen Guards; wer
        über Tastatur o. Ä. doch auslöst, läuft dort auf.
        """
        self._btn_save.setEnabled(not gesperrt)
        self._btn_save.setToolTip(
            _("msg.nur_lesen", modul=modul_label) if gesperrt else "")


class _MsgDialog(QDialog):
    """Resizable Meldungs-Dialog mit optionalem Log-Detail und Kopieren-Button."""

    def __init__(self, parent, titel, text, icon):
        super().__init__(parent)
        self.setWindowTitle(titel)
        self.setMinimumSize(560, 260)
        self.setSizeGripEnabled(True)
        lay = QVBoxLayout(self)

        log_detail = last_log_handler.get_last()
        full_text = text
        if log_detail:
            full_text = text + "\n\n" + ("─" * 60) + "\n" + log_detail

        self._te = QTextEdit()
        self._te.setReadOnly(True)
        self._te.setPlainText(full_text)
        self._te.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard)
        lay.addWidget(self._te)

        btns = QDialogButtonBox()
        btn_kopieren = btns.addButton(_("btn.kopieren"), QDialogButtonBox.ButtonRole.ActionRole)
        btn_kopieren.clicked.connect(self._kopieren)
        import settings as _settings
        if _settings.get_developer_email() and developer_email_fn is not None:
            self._dev_text = full_text
            btn_dev = btns.addButton(_("btn.an_entwickler"), QDialogButtonBox.ButtonRole.ActionRole)
            btn_dev.clicked.connect(self._an_entwickler)
        btns.addButton(QDialogButtonBox.StandardButton.Close)
        btns.button(QDialogButtonBox.StandardButton.Close).setText(_("btn.schliessen"))
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        icon_map = {
            "critical": QMessageBox.Icon.Critical,
            "warning":  QMessageBox.Icon.Warning,
        }
        if icon in icon_map:
            ico = self.style().standardIcon(
                {QMessageBox.Icon.Critical: self.style().StandardPixmap.SP_MessageBoxCritical,
                 QMessageBox.Icon.Warning:  self.style().StandardPixmap.SP_MessageBoxWarning}
                [icon_map[icon]])
            self.setWindowIcon(ico)

    def _kopieren(self):
        QApplication.clipboard().setText(self._te.toPlainText())

    def _an_entwickler(self):
        from PyQt6.QtWidgets import QMessageBox as _QMB
        if _QMB.question(self, _("msg.hinweis"), _("msg.entwickler_zustimmung")) \
                != _QMB.StandardButton.Yes:
            return
        if developer_email_fn is not None:
            developer_email_fn(getattr(self, "_dev_text", self._te.toPlainText()))


def zeige_fehler(parent, titel, text):
    """Zeigt eine resizable Fehlermeldung mit Kopieren-Button."""
    dlg = _MsgDialog(parent, titel, text, "critical")
    dlg.exec()
    dlg.deleteLater()          # Dialog freigeben (sonst bleibt er als Kind am Leben)


def zeige_warnung(parent, titel, text):
    """Zeigt eine resizable Warnung mit Kopieren-Button."""
    dlg = _MsgDialog(parent, titel, text, "warning")
    dlg.exec()
    dlg.deleteLater()          # Dialog freigeben (sonst bleibt er als Kind am Leben)
