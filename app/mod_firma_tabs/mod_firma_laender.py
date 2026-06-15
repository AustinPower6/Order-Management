"""Verwaltung der firma-spezifischen Tabellen `sprachen` und `laender`.

Wird als zwei Unter-Reiter im Parameter-Reiter des Firmenstamms angezeigt.
Schreibt direkt in die DB (firma-spezifisch). Analog zu MarkenVerwaltung."""
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout,
                             QLabel, QLineEdit, QMessageBox, QProgressDialog, QPushButton,
                             QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt
from modul.mod_belege import (_apply_saved_columns, _connect_save_columns,
                              _frage_ungespeicherte_anderungen)
from ui_widgets import zeige_fehler, zeige_warnung
from lock_manager import Module
from i18n import _
import ki_client
import settings


# ─────────────────────────────────────────────────────────────────────────────
# Sprachen
# ─────────────────────────────────────────────────────────────────────────────
class SprachenVerwaltung(QWidget):
    """Tabelle der Sprachen + Neu/Bearbeiten/Löschen. Je Sprache: KI-Unterstützung
    (Checkbox) und Fallback-Sprache (falls die KI sie nicht beherrscht)."""

    def __init__(self):
        super().__init__()
        self.db = None
        self._build()

    def set_db(self, db):
        self.db = db

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        ueberschrift = QLabel(_("firma.sprache.ueberschrift"))
        ueberschrift.setStyleSheet("font-weight: bold;")
        lay.addWidget(ueberschrift)

        btn_bar = QHBoxLayout()
        for lbl_key, fn in [("btn.neu", self._neu),
                            ("btn.bearbeiten", self._bearbeiten),
                            ("btn.loeschen", self._loeschen)]:
            b = QPushButton(_(lbl_key)); b.clicked.connect(fn); btn_bar.addWidget(b)
        self._btn_pruefen = QPushButton(_("firma.sprache.btn_pruefen"))
        self._btn_pruefen.clicked.connect(self._sprachen_pruefen)
        btn_bar.addWidget(self._btn_pruefen)
        self._btn_prompts = QPushButton(_("firma.sprache.btn_prompts"))
        self._btn_prompts.clicked.connect(self._prompts_bearbeiten)
        btn_bar.addWidget(self._btn_prompts)
        btn_bar.addStretch()
        lay.addLayout(btn_bar)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            _("firma.sprache.col.bezeichnung"), _("firma.sprache.col.ki"),
            _("firma.sprache.col.ki_antwort"), _("firma.sprache.col.faehigkeit"),
            _("firma.sprache.col.fallback")])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._bearbeiten)
        _apply_saved_columns(self.table, "firma_sprachen")
        _connect_save_columns(self.table, "firma_sprachen")
        lay.addWidget(self.table, 1)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F5:
            self.refresh()
            return
        super().keyPressEvent(event)

    def refresh(self):
        if not self.db:
            return
        sprachen = [dict(s) for s in self.db.get_sprachen()]
        namen = {s["id"]: s["bezeichnung"] for s in sprachen}
        self.table.setRowCount(0)
        for s in sprachen:
            r = self.table.rowCount()
            self.table.insertRow(r)
            item = QTableWidgetItem(s["bezeichnung"])
            item.setData(Qt.ItemDataRole.UserRole, s["id"])
            self.table.setItem(r, 0, item)
            self.table.setItem(r, 1, QTableWidgetItem(
                "✓" if s.get("ki_unterstuetzt") else ""))
            self.table.setItem(r, 2, QTableWidgetItem(s.get("ki_antwort") or ""))
            self.table.setItem(r, 3, QTableWidgetItem(s.get("faehigkeit") or ""))
            fb = s.get("fallback_sprache_id")
            self.table.setItem(r, 4, QTableWidgetItem(namen.get(fb, "—") if fb else "—"))

    def _sel_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _sprachen_pruefen(self):
        """Fragt für jede Sprache beim LLM (a) Unterstützung und (b) Fähigkeit ab.
        Voraussetzung: aktive KI-Anbindung. Fortschrittsdialog mit Abbrechen."""
        if not self.db:
            return
        firma = dict(self.db.get_firma(self.db._firma_id()) or {})
        if not firma.get("ki_aktiv"):
            zeige_warnung(self, _("msg.hinweis"), _("firma.sprache.ki_inaktiv"))
            return
        anbieter, api_key, basis_url, modell = ki_client.firma_cfg(firma)
        if not modell:
            zeige_warnung(self, _("msg.hinweis"), _("firma.ki.msg.kein_modell"))
            return
        sup_prompt = firma.get("ki_prompt_sprach_support") or ki_client.SPRACHE_SUPPORT_PROMPT
        fae_prompt = firma.get("ki_prompt_sprach_faehigkeit") or ki_client.SPRACHE_FAEHIGKEIT_PROMPT
        sprachen = [dict(s) for s in self.db.get_sprachen()]
        prog = QProgressDialog(_("firma.sprache.pruefe_start"), _("btn.abbrechen"),
                               0, len(sprachen), self)
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        prog.setMinimumDuration(0)
        for i, s in enumerate(sprachen):
            if prog.wasCanceled():
                break
            prog.setValue(i)
            prog.setLabelText(_("firma.sprache.pruefe_label",
                                sprache=s["bezeichnung"], n=i + 1, gesamt=len(sprachen)))
            bez = s["bezeichnung"]
            try:
                a1 = ki_client.chat(anbieter, api_key, basis_url, modell, "",
                                    sup_prompt.replace("{sprache}", bez))
                # Enthält die Antwort "nein" → nicht unterstützt, Fähigkeit = 5;
                # die zweite Anfrage entfällt dann.
                if "nein" in a1.strip().lower():
                    self.db.set_sprache_pruefung(s["id"], False, "5", a1.strip())
                    continue
                a2 = ki_client.chat(anbieter, api_key, basis_url, modell, "",
                                    fae_prompt.replace("{sprache}", bez))
            except Exception as ex:
                prog.cancel()
                zeige_fehler(self, _("msg.fehler"),
                             _("firma.sprache.pruefe_fehler", detail=str(ex)))
                break
            self.db.set_sprache_pruefung(s["id"], True, a2.strip(), a1.strip())
        prog.setValue(len(sprachen))
        self.refresh()

    def _prompts_bearbeiten(self):
        """Dialog zum Bearbeiten der beiden Prüf-Prompts (je Firma gespeichert)."""
        if not self.db:
            return
        firma = dict(self.db.get_firma(self.db._firma_id()) or {})
        sup = firma.get("ki_prompt_sprach_support") or ki_client.SPRACHE_SUPPORT_PROMPT
        fae = firma.get("ki_prompt_sprach_faehigkeit") or ki_client.SPRACHE_FAEHIGKEIT_PROMPT
        dlg = _PromptDialog(self, sup, fae)
        if dlg.exec():
            v = dlg.value()
            self.db.save_firma({"id": self.db._firma_id(),
                                "ki_prompt_sprach_support": v["support"],
                                "ki_prompt_sprach_faehigkeit": v["faehigkeit"],
                                "_modul": Module.FIRMA})

    def _neu(self):
        if not self.db:
            return
        dlg = _SpracheDialog(self, None, self.db.get_sprachen())
        if dlg.exec():
            data = dlg.value()
            if not data["bezeichnung"]:
                zeige_fehler(self, _("msg.fehler"), _("firma.sprache.bezeichnung_pflicht"))
                return
            if data["bezeichnung"] in {s["bezeichnung"] for s in self.db.get_sprachen()}:
                zeige_fehler(self, _("msg.fehler"),
                             _("firma.sprache.existiert_bereits", bez=data["bezeichnung"]))
                return
            self.db.save_sprache(data)
            self.refresh()

    def _bearbeiten(self):
        sid = self._sel_id()
        if not sid:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.sprache.bitte_auswaehlen"))
            return
        aktuell = dict(self.db.get_sprache(sid) or {})
        dlg = _SpracheDialog(self, aktuell, self.db.get_sprachen())
        if dlg.exec():
            data = dlg.value()
            if not data["bezeichnung"]:
                zeige_fehler(self, _("msg.fehler"), _("firma.sprache.bezeichnung_pflicht"))
                return
            if data["bezeichnung"] in {s["bezeichnung"] for s in self.db.get_sprachen()
                                       if s["id"] != sid}:
                zeige_fehler(self, _("msg.fehler"),
                             _("firma.sprache.existiert_bereits", bez=data["bezeichnung"]))
                return
            data["id"] = sid
            self.db.save_sprache(data)
            self.refresh()

    def _loeschen(self):
        sid = self._sel_id()
        if not sid:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.sprache.bitte_auswaehlen"))
            return
        if QMessageBox.question(self, _("msg.loeschen"),
                                _("firma.sprache.frage_loeschen")) == QMessageBox.StandardButton.Yes:
            self.db.delete_sprache(sid)
            self.refresh()


class _SpracheDialog(settings.DialogSizeMixin, QDialog):
    def __init__(self, parent, sprache, alle_sprachen):
        super().__init__(parent)
        self._dirty = False
        self._dirty_dot = QLabel("●")
        self._dirty_dot.setStyleSheet("color: red; font-size: 14px;")
        self._dirty_dot.hide()
        ist_neu = not sprache
        self.setWindowTitle(_("firma.sprache.dlg_neu") if ist_neu
                            else _("firma.sprache.dlg_bearbeiten"))
        self._self_id = sprache.get("id") if sprache else None
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)

        self._bez = QLineEdit((sprache or {}).get("bezeichnung", "") or "")
        form.addRow(_("firma.sprache.lbl.bezeichnung"), self._bez)
        self._bez.textChanged.connect(self._mark_dirty)

        self._ki = QCheckBox()
        self._ki.setChecked(bool((sprache or {}).get("ki_unterstuetzt", 1)))
        form.addRow(_("firma.sprache.lbl.ki"), self._ki)
        self._ki.stateChanged.connect(self._mark_dirty)

        self._fallback = QComboBox()
        self._fallback.addItem(_("firma.sprache.kein_fallback"), None)
        for s in alle_sprachen:
            if s["id"] != self._self_id:   # nicht sich selbst als Fallback
                self._fallback.addItem(s["bezeichnung"], s["id"])
        akt_fb = (sprache or {}).get("fallback_sprache_id")
        if akt_fb:
            idx = self._fallback.findData(akt_fb)
            if idx >= 0:
                self._fallback.setCurrentIndex(idx)
        form.addRow(_("firma.sprache.lbl.fallback"), self._fallback)
        self._fallback.currentIndexChanged.connect(self._mark_dirty)

        lay.addLayout(form)
        lay.addStretch()
        lay.addWidget(_button_bar(self._dirty_dot, self.accept, self.reject))
        self._dirty = False
        self._dirty_dot.hide()

    def _mark_dirty(self, *args):
        self._dirty = True
        self._dirty_dot.show()

    def keyPressEvent(self, event):
        _dialog_keypress(self, event)

    def value(self):
        return {
            "bezeichnung": self._bez.text().strip(),
            "ki_unterstuetzt": 1 if self._ki.isChecked() else 0,
            "fallback_sprache_id": self._fallback.currentData(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Länder
# ─────────────────────────────────────────────────────────────────────────────
class LaenderVerwaltung(QWidget):
    """Tabelle der Länderkennzeichen (ISO-Code, Bezeichnung, Hauptsprache)."""

    def __init__(self):
        super().__init__()
        self.db = None
        self._build()

    def set_db(self, db):
        self.db = db

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        ueberschrift = QLabel(_("firma.land.ueberschrift"))
        ueberschrift.setStyleSheet("font-weight: bold;")
        lay.addWidget(ueberschrift)

        btn_bar = QHBoxLayout()
        for lbl_key, fn in [("btn.neu", self._neu),
                            ("btn.bearbeiten", self._bearbeiten),
                            ("btn.loeschen", self._loeschen)]:
            b = QPushButton(_(lbl_key)); b.clicked.connect(fn); btn_bar.addWidget(b)
        btn_bar.addStretch()
        lay.addLayout(btn_bar)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            _("firma.land.col.iso"), _("firma.land.col.bezeichnung"),
            _("firma.land.col.sprache"), _("firma.land.col.eu_mitglied")])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._bearbeiten)
        _apply_saved_columns(self.table, "firma_laender_v2")
        _connect_save_columns(self.table, "firma_laender_v2")
        lay.addWidget(self.table, 1)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F5:
            self.refresh()
            return
        super().keyPressEvent(event)

    def refresh(self):
        if not self.db:
            return
        namen = {s["id"]: s["bezeichnung"] for s in self.db.get_sprachen()}
        self.table.setRowCount(0)
        for land in self.db.get_laender():
            land = dict(land)
            r = self.table.rowCount()
            self.table.insertRow(r)
            item = QTableWidgetItem(land["iso_code"])
            item.setData(Qt.ItemDataRole.UserRole, land["id"])
            self.table.setItem(r, 0, item)
            self.table.setItem(r, 1, QTableWidgetItem(land["bezeichnung"]))
            spid = land.get("sprache_id")
            self.table.setItem(r, 2, QTableWidgetItem(namen.get(spid, "—") if spid else "—"))
            eu_item = QTableWidgetItem("✓" if land.get("eu_mitglied", 1) else "")
            eu_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, 3, eu_item)

    def _sel_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _neu(self):
        if not self.db:
            return
        dlg = _LandDialog(self, None, self.db.get_sprachen())
        if dlg.exec():
            data = dlg.value()
            if not data["iso_code"] or not data["bezeichnung"]:
                zeige_fehler(self, _("msg.fehler"), _("firma.land.pflicht"))
                return
            if data["iso_code"] in {dict(x)["iso_code"] for x in self.db.get_laender()}:
                zeige_fehler(self, _("msg.fehler"),
                             _("firma.land.existiert_bereits", iso=data["iso_code"]))
                return
            self.db.save_land(data)
            self.refresh()

    def _bearbeiten(self):
        lid = self._sel_id()
        if not lid:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.land.bitte_auswaehlen"))
            return
        aktuell = dict(self.db.get_land(lid) or {})
        dlg = _LandDialog(self, aktuell, self.db.get_sprachen())
        if dlg.exec():
            data = dlg.value()
            if not data["iso_code"] or not data["bezeichnung"]:
                zeige_fehler(self, _("msg.fehler"), _("firma.land.pflicht"))
                return
            if data["iso_code"] in {dict(x)["iso_code"] for x in self.db.get_laender()
                                    if x["id"] != lid}:
                zeige_fehler(self, _("msg.fehler"),
                             _("firma.land.existiert_bereits", iso=data["iso_code"]))
                return
            data["id"] = lid
            self.db.save_land(data)
            self.refresh()

    def _loeschen(self):
        lid = self._sel_id()
        if not lid:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.land.bitte_auswaehlen"))
            return
        if QMessageBox.question(self, _("msg.loeschen"),
                                _("firma.land.frage_loeschen")) == QMessageBox.StandardButton.Yes:
            self.db.delete_land(lid)
            self.refresh()


class _LandDialog(settings.DialogSizeMixin, QDialog):
    def __init__(self, parent, land, alle_sprachen):
        super().__init__(parent)
        self._dirty = False
        self._dirty_dot = QLabel("●")
        self._dirty_dot.setStyleSheet("color: red; font-size: 14px;")
        self._dirty_dot.hide()
        ist_neu = not land
        self.setWindowTitle(_("firma.land.dlg_neu") if ist_neu
                            else _("firma.land.dlg_bearbeiten"))
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)

        self._iso = QLineEdit((land or {}).get("iso_code", "") or "")
        self._iso.setMaxLength(2)
        self._iso.setMaximumWidth(60)
        self._iso.setPlaceholderText("DE")
        form.addRow(_("firma.land.lbl.iso"), self._iso)
        self._iso.textChanged.connect(self._mark_dirty)

        self._bez = QLineEdit((land or {}).get("bezeichnung", "") or "")
        form.addRow(_("firma.land.lbl.bezeichnung"), self._bez)
        self._bez.textChanged.connect(self._mark_dirty)

        self._sprache = QComboBox()
        self._sprache.addItem(_("firma.land.keine_sprache"), None)
        for s in alle_sprachen:
            self._sprache.addItem(s["bezeichnung"], s["id"])
        akt = (land or {}).get("sprache_id")
        if akt:
            idx = self._sprache.findData(akt)
            if idx >= 0:
                self._sprache.setCurrentIndex(idx)
        form.addRow(_("firma.land.lbl.sprache"), self._sprache)
        self._sprache.currentIndexChanged.connect(self._mark_dirty)

        self._eu = QCheckBox()
        self._eu.setChecked(bool((land or {}).get("eu_mitglied", 1)))
        form.addRow(_("firma.land.lbl.eu_mitglied"), self._eu)
        self._eu.stateChanged.connect(self._mark_dirty)

        lay.addLayout(form)
        lay.addStretch()
        lay.addWidget(_button_bar(self._dirty_dot, self.accept, self.reject))
        self._dirty = False
        self._dirty_dot.hide()

    def _mark_dirty(self, *args):
        self._dirty = True
        self._dirty_dot.show()

    def keyPressEvent(self, event):
        _dialog_keypress(self, event)

    def value(self):
        return {
            "iso_code": self._iso.text().strip().upper(),
            "bezeichnung": self._bez.text().strip(),
            "sprache_id": self._sprache.currentData(),
            "eu_mitglied": 1 if self._eu.isChecked() else 0,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Abfrage-Prompts bearbeiten
# ─────────────────────────────────────────────────────────────────────────────
class _PromptDialog(settings.DialogSizeMixin, QDialog):
    """Bearbeitet die beiden Prüf-Prompts. {sprache} wird beim Senden durch die
    jeweilige Sprache ersetzt."""

    def __init__(self, parent, support, faehigkeit):
        super().__init__(parent)
        self._dirty = False
        self._dirty_dot = QLabel("●")
        self._dirty_dot.setStyleSheet("color: red; font-size: 14px;")
        self._dirty_dot.hide()
        self.setWindowTitle(_("firma.sprache.prompt_dlg.titel"))
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)

        lay.addWidget(QLabel(_("firma.sprache.prompt_dlg.support")))
        self._sup = QTextEdit()
        self._sup.setFixedHeight(70)
        self._sup.setPlainText(support)
        self._sup.textChanged.connect(self._mark_dirty)
        lay.addWidget(self._sup)

        lay.addWidget(QLabel(_("firma.sprache.prompt_dlg.faehigkeit")))
        self._fae = QTextEdit()
        self._fae.setFixedHeight(70)
        self._fae.setPlainText(faehigkeit)
        self._fae.textChanged.connect(self._mark_dirty)
        lay.addWidget(self._fae)

        hint = QLabel(_("firma.sprache.prompt_dlg.hinweis"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #777777; font-size: 10px;")
        lay.addWidget(hint)

        lay.addWidget(_button_bar(self._dirty_dot, self.accept, self.reject))
        self._dirty = False
        self._dirty_dot.hide()

    def _mark_dirty(self, *args):
        self._dirty = True
        self._dirty_dot.show()

    def keyPressEvent(self, event):
        _dialog_keypress(self, event)

    def value(self):
        return {"support": self._sup.toPlainText().strip(),
                "faehigkeit": self._fae.toPlainText().strip()}


# ─────────────────────────────────────────────────────────────────────────────
# gemeinsame Dialog-Helfer (Button-Leiste + Enter/Escape mit Dirty-Check)
# ─────────────────────────────────────────────────────────────────────────────
def _button_bar(dirty_dot, ok_fn, cancel_fn):
    w = QWidget()
    bl = QHBoxLayout(w)
    bl.setContentsMargins(0, 4, 0, 0)
    bl.addStretch()
    bl.addWidget(dirty_dot)
    btn_ok = QPushButton(_("btn.ok"))
    btn_ok.clicked.connect(ok_fn)
    bl.addWidget(btn_ok)
    btn_cancel = QPushButton(_("btn.abbrechen"))
    btn_cancel.clicked.connect(cancel_fn)
    bl.addWidget(btn_cancel)
    return w


def _dialog_keypress(dlg, event):
    if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
        dlg.accept()
        return
    if event.key() == Qt.Key.Key_Escape:
        if dlg._dirty:
            result = _frage_ungespeicherte_anderungen(dlg)
            if result == "save":
                dlg.accept()
            elif result == "discard":
                dlg.reject()
        else:
            dlg.reject()
        return
    QDialog.keyPressEvent(dlg, event)
