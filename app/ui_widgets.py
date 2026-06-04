"""Gemeinsame UI-Hilfswidgets und -Layouts."""
import collections
import logging
from PyQt6.QtCore import Qt, QPoint, QRect, QSize, QTimer, QThread
from PyQt6.QtWidgets import (QLayout, QWidget, QSizePolicy, QHBoxLayout, QLabel, QPushButton,
                              QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox,
                              QMessageBox, QApplication, QStyle, QStyleOptionTab,
                              QStylePainter, QTabBar)
from i18n import _


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

    _STYLE = ("QLabel { background-color: #3a3a3a; color: #ffffff; "
              "font-size: 13px; padding: 14px 28px; border-radius: 8px; }")

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
        lbl.setStyleSheet(self._STYLE)
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
        QApplication.processEvents()
        # Kurze Pause damit Windows den Window-Manager benachrichtigen kann
        # und das Fenster tatsächlich gemalt wird bevor der Ladevorgang startet
        QThread.msleep(1000)
        QApplication.processEvents()
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
        self._dot.setStyleSheet("color: red; font-size: 14px;")
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
    _MsgDialog(parent, titel, text, "critical").exec()


def zeige_warnung(parent, titel, text):
    """Zeigt eine resizable Warnung mit Kopieren-Button."""
    _MsgDialog(parent, titel, text, "warning").exec()
