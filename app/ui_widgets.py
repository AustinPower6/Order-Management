"""Gemeinsame UI-Hilfswidgets und -Layouts."""
from PyQt6.QtCore import Qt, QPoint, QRect, QSize, QTimer
from PyQt6.QtWidgets import (QLayout, QWidget, QSizePolicy, QHBoxLayout, QLabel, QPushButton,
                              QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox,
                              QMessageBox, QApplication)
from i18n import _


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

        self._dot = QLabel("●")
        self._dot.setStyleSheet("color: red; font-size: 14px;")
        self._dot.hide()
        lay.addWidget(self._dot)

        self._btn_save = QPushButton(_("btn.speichern"))
        lay.addWidget(self._btn_save)

        self._btn_cancel = QPushButton(_("btn.abbrechen"))
        lay.addWidget(self._btn_cancel)

        lay.addStretch()

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
    """Resizable Meldungs-Dialog mit Kopieren-Button."""

    def __init__(self, parent, titel, text, icon):
        super().__init__(parent)
        self.setWindowTitle(titel)
        self.setMinimumSize(520, 220)
        self.setSizeGripEnabled(True)
        lay = QVBoxLayout(self)

        self._te = QTextEdit()
        self._te.setReadOnly(True)
        self._te.setPlainText(text)
        self._te.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard)
        lay.addWidget(self._te)

        btns = QDialogButtonBox()
        btn_kopieren = btns.addButton(_("btn.kopieren"), QDialogButtonBox.ButtonRole.ActionRole)
        btn_kopieren.clicked.connect(self._kopieren)
        btns.addButton(QDialogButtonBox.StandardButton.Close)
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


def zeige_fehler(parent, titel, text):
    """Zeigt eine resizable Fehlermeldung mit Kopieren-Button."""
    _MsgDialog(parent, titel, text, "critical").exec()


def zeige_warnung(parent, titel, text):
    """Zeigt eine resizable Warnung mit Kopieren-Button."""
    _MsgDialog(parent, titel, text, "warning").exec()
