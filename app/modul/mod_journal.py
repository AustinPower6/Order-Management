from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QVBoxLayout)
from PyQt6.QtCore import Qt
import druck as druck_mod
import settings
from i18n import _, status_label
from ui_widgets import zeige_fehler, zeige_warnung


class JournalFenster(settings.DialogSizeMixin, QDialog):
    # Mapping: i18n-Schluessel-Item -> interner Belegtyp (Logikkonstante)
    _TYP_ITEMS = [
        ("journal.item.angebote",      "Angebotsbuch"),
        ("journal.item.auftraege",     "Auftragsbuch"),
        ("journal.item.lieferscheine", "Lieferscheinbuch"),
        ("journal.item.rechnungen",    "Rechnungsbuch"),
        ("journal.item.mahnungen",     "Mahnungsbuch"),
    ]

    _TYP_STATUSES = {
        "Angebotsbuch":     ["entwurf", "offen", "angenommen", "abgeschlossen"],
        "Auftragsbuch":     ["entwurf", "offen", "abgerechnet", "abgeschlossen"],
        "Lieferscheinbuch": ["entwurf", "offen", "geliefert", "abgerechnet"],
        "Rechnungsbuch":    ["entwurf", "offen", "bezahlt", "storniert", "storno"],
        "Mahnungsbuch":     ["offen", "bezahlt", "storniert"],
    }

    def __init__(self, parent, db, preset_typ=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle(_("journal.title"))
        self.setFixedSize(380, 230)
        self._build()
        # Belegtyp: erst preset, dann gespeicherter Wert, dann Standard
        typ_to_select = preset_typ or settings._get("journal.letzter_typ")
        if typ_to_select:
            for i, (_k, internal) in enumerate(self._TYP_ITEMS):
                if internal == typ_to_select:
                    self._typ_cb.setCurrentIndex(i)
                    break
        # Gespeicherte Parameter für den aktuellen Typ laden
        self._restore_typ_settings(self._typ_cb.currentData())

    def _build(self):
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)

        self._typ_cb = QComboBox()
        for key, internal in self._TYP_ITEMS:
            self._typ_cb.addItem(_(key), internal)
        self._typ_cb.currentIndexChanged.connect(self._on_typ_changed)
        form.addRow(_("journal.lbl.belegtyp"), self._typ_cb)

        self._status_cb = QComboBox()
        form.addRow(_("journal.lbl.status"), self._status_cb)
        self._on_typ_changed(0)

        firma = dict(self.db.get_firma()) if self.db.get_firma() else {}
        gj = str(firma.get("geschaeftsjahr") or "")
        buchungsmonat = None
        if gj:
            try:
                buchungsmonat = int(self.db.get_buchungsmonat_fuer_jahr(int(gj)) or 0) or None
            except (TypeError, ValueError):
                buchungsmonat = None

        jahre = self.db.get_jahre()
        self._jahr_cb = QComboBox()
        self._jahr_cb.addItem(_("journal.alle_monate"), None)
        for j in jahre:
            self._jahr_cb.addItem(j, j)
        if gj and gj in jahre:
            idx = self._jahr_cb.findData(gj)
            if idx >= 0:
                self._jahr_cb.setCurrentIndex(idx)
        elif jahre:
            self._jahr_cb.setCurrentIndex(1)
        form.addRow(_("journal.lbl.jahr"), self._jahr_cb)

        self._monat_cb = QComboBox()
        self._monat_cb.addItem(_("journal.alle_monate"), None)
        for i in range(1, 13):
            self._monat_cb.addItem(f"{i:02d} - {_(f'monat.{i}')}", f"{i:02d}")
        if buchungsmonat:
            idx = self._monat_cb.findData(f"{buchungsmonat:02d}")
            if idx >= 0:
                self._monat_cb.setCurrentIndex(idx)
        form.addRow(_("journal.lbl.monat"), self._monat_cb)

        lay.addLayout(form)
        lay.addStretch()
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("btn.drucken"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        btns.accepted.connect(self._drucken)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _restore_typ_settings(self, typ):
        for cb, field in [(self._jahr_cb, "jahr"),
                          (self._monat_cb, "monat"),
                          (self._status_cb, "status")]:
            saved = settings._get(f"journal.{typ}.{field}")
            if saved is not None:
                idx = cb.findData(saved)
                if idx >= 0:
                    cb.setCurrentIndex(idx)

    def _on_typ_changed(self, _flt):
        typ = self._typ_cb.currentData()
        self._status_cb.clear()
        self._status_cb.addItem(_("journal.alle_status"), None)
        for s in self._TYP_STATUSES.get(typ, []):
            self._status_cb.addItem(status_label(s), s)
        # Gespeicherte Parameter für diesen Typ wiederherstellen
        # (Guard: beim ersten _build-Aufruf existiert _jahr_cb noch nicht)
        if hasattr(self, "_jahr_cb"):
            self._restore_typ_settings(typ)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    _JOURNAL_FN = {
        "Angebotsbuch": druck_mod.drucke_angebotsbuch,
        "Auftragsbuch": druck_mod.drucke_auftragsbuch,
        "Lieferscheinbuch": druck_mod.drucke_lieferscheinbuch,
        "Rechnungsbuch": druck_mod.drucke_rechnungsbuch,
        "Mahnungsbuch": druck_mod.drucke_mahnungsbuch,
    }

    _TYP_DB_METHOD = {
        "Angebotsbuch":     "get_angebote",
        "Auftragsbuch":     "get_auftraege",
        "Lieferscheinbuch": "get_lieferscheine",
        "Rechnungsbuch":    "get_rechnungen",
        "Mahnungsbuch":     "get_mahnungen",
    }

    def _drucken(self):
        typ = self._typ_cb.currentData()
        jahr = self._jahr_cb.currentData()
        monat = self._monat_cb.currentData()
        status = self._status_cb.currentData()
        fn = self._JOURNAL_FN.get(typ)
        if not fn:
            zeige_fehler(self, _("msg.fehler"), _("journal.unbekannter_typ", typ=typ))
            return
        db_method = self._TYP_DB_METHOD.get(typ)
        belege = list(getattr(self.db, db_method)(monat, jahr, status=status))
        if not belege:
            zeige_warnung(self, _("msg.hinweis"), _("journal.keine_belege"))
            return
        try:
            settings._set("journal.letzter_typ", typ)
            settings._set(f"journal.{typ}.jahr", jahr)
            settings._set(f"journal.{typ}.monat", monat)
            settings._set(f"journal.{typ}.status", status)
            fn(self.db, monat, jahr, status=status)
        except Exception as e:
            zeige_fehler(self, _("msg.fehler"), _("journal.druckfehler", err=e))
