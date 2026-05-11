"""Gemeinsame UI-Hilfswidgets und -Layouts."""
from PyQt6.QtCore import Qt, QPoint, QRect, QSize
from PyQt6.QtWidgets import QLayout, QWidget, QSizePolicy


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
