"""Variante A — In-App-Generator für zusätzliche App-Sprachen.

Admin-Dialog: erzeugt/aktualisiert eine `language.<code>.json` (siehe `lang_tools`),
indem die UI-Texte per KI der aktiven Firma aus der **aktuell eingestellten App-Sprache**
(`i18n.current()`) in die Zielsprache übersetzt werden. Wie im Drucktexte-Reiter wird jede
Übersetzung sofort **zurückübersetzt** (LLM 2) und mit dem Original verglichen; Abweichungen
erscheinen rot in einer fortlaufend gefüllten Tabelle und lassen sich per Häkchen
**bestätigen**. Rückübersetzungen + Bestätigungen werden in einer Begleitdatei
`language.<code>.review.json` festgehalten, sodass beim nächsten Lauf nur die noch offenen
Zeilen erneut übersetzt werden. Deutsch und Englisch bleiben im Hauptfile `language.json`.
"""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QComboBox, QLineEdit,
                             QCheckBox, QLabel, QHBoxLayout, QPushButton, QMessageBox,
                             QTableWidget, QTableWidgetItem, QApplication)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

import settings
import i18n
import lang_tools
import uebersetzung
import theme
from i18n import _
from ui_widgets import zeige_fehler, zeige_warnung
from modul.beleg_utils import _apply_saved_columns, _connect_save_columns

_KONTEXT = "App-Oberfläche (kurze UI-Beschriftung)"
_COLS_KEY = "sprachdatei_review"

# Spaltenindizes der Review-Tabelle
COL_KEY, COL_ORIG, COL_UEB, COL_RUECK, COL_OK = range(5)


class SprachdateiDialog(settings.DialogSizeMixin, QDialog):
    """Erstellt/aktualisiert eine zusätzliche App-Sprachdatei per KI-Übersetzung mit
    Rückübersetzungs-Kontrolle (rote Unstimmigkeiten, bestätigbar)."""

    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        # Quelle = aktuell eingestellte App-Sprache (mit i18n-Fallbackkette en→de→Key).
        self._quellcode = i18n.current()
        self._quelllabel = i18n.label(self._quellcode)
        self._quellwerte = i18n.werte(self._quellcode)   # {key: text}
        self._lauf_aktiv = False
        self._abbruch = False
        self.setWindowTitle(_("dlg.sprachdatei.titel"))
        self._build()
        self._fill_combo()

    # ── Aufbau ────────────────────────────────────────────────────────
    def _build(self):
        lay = QVBoxLayout(self)

        intro = QLabel(_("dlg.sprachdatei.intro"))
        intro.setWordWrap(True)
        lay.addWidget(intro)

        form = QFormLayout()
        form.setVerticalSpacing(6)

        # Quellsprache (read-only Anzeige) — die aktuell eingestellte App-Sprache.
        self._quelle_edit = QLineEdit(self._quelllabel)
        self._quelle_edit.setReadOnly(True)
        form.addRow(_("dlg.sprachdatei.quelle"), self._quelle_edit)

        self._combo = QComboBox()
        self._combo.currentIndexChanged.connect(self._on_combo)
        form.addRow(_("dlg.sprachdatei.sprache"), self._combo)

        self._code_edit = QLineEdit()
        self._code_edit.setMaximumWidth(120)
        form.addRow(_("dlg.sprachdatei.code"), self._code_edit)

        self._name_edit = QLineEdit()
        form.addRow(_("dlg.sprachdatei.name"), self._name_edit)

        self._alle_cb = QCheckBox(_("dlg.sprachdatei.alle_neu"))
        form.addRow("", self._alle_cb)

        lay.addLayout(form)

        # Fortlaufend gefüllte Review-Tabelle
        self._table = QTableWidget(0, 5)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._update_headers("")
        lay.addWidget(self._table, 1)
        _apply_saved_columns(self._table, _COLS_KEY)
        _connect_save_columns(self._table, _COLS_KEY)

        self._fortschritt = QLabel("")
        self._fortschritt.setStyleSheet(theme.hint_label_style())
        lay.addWidget(self._fortschritt)

        btns = QHBoxLayout()
        btns.addStretch()
        self._run_btn = QPushButton(_("btn.erstellen_aktualisieren"))
        self._run_btn.clicked.connect(self._run)
        btns.addWidget(self._run_btn)
        self._cancel_btn = QPushButton(_("btn.abbrechen"))
        self._cancel_btn.clicked.connect(self._abbrechen)
        self._cancel_btn.setVisible(False)
        btns.addWidget(self._cancel_btn)
        self._save_btn = QPushButton(_("btn.speichern"))
        self._save_btn.clicked.connect(self._save)
        self._save_btn.setEnabled(False)
        btns.addWidget(self._save_btn)
        self._close_btn = QPushButton(_("btn.schliessen"))
        self._close_btn.clicked.connect(self.reject)
        btns.addWidget(self._close_btn)
        lay.addLayout(btns)

    def _update_headers(self, ziel_label):
        self._table.setHorizontalHeaderLabels([
            _("dlg.sprachdatei.col_schluessel"),
            _("dlg.sprachdatei.col_original", sprache=self._quelllabel),
            _("dlg.sprachdatei.col_uebersetzung", sprache=ziel_label or "…"),
            _("dlg.sprachdatei.col_rueck", sprache=self._quelllabel),
            _("dlg.sprachdatei.col_bestaetigt"),
        ])

    def _fill_combo(self):
        self._combo.blockSignals(True)
        self._combo.clear()
        # Vorhandene Zusatzsprachen (de/en bleiben im Hauptfile)
        for code, label in lang_tools.discover():
            self._combo.addItem(f"{label}  ({code})", code)
        self._combo.addItem(_("dlg.sprachdatei.neu"), None)
        self._combo.setCurrentIndex(self._combo.count() - 1)   # Standard: „Neu"
        self._combo.blockSignals(False)
        self._on_combo()

    def _on_combo(self):
        code = self._combo.currentData()
        if code is None:                       # „Neue Sprache"
            self._code_edit.clear()
            self._code_edit.setReadOnly(False)
            self._name_edit.clear()
            ziel_label = ""
        else:                                  # vorhandene Sprache
            extra = lang_tools.load_extra(code)
            self._code_edit.setText(code)
            self._code_edit.setReadOnly(True)
            self._name_edit.setText(lang_tools.meta_label(extra, code))
            ziel_label = self._name_edit.text()
        self._update_headers(ziel_label)
        self._table.setRowCount(0)
        self._fortschritt.setText("")
        self._save_btn.setEnabled(False)
        # Bereits gespeicherte, noch offene Zeilen ohne KI anzeigen (Nachbestätigung).
        if code is not None:
            self._lade_offene_zeilen(code)

    # ── Vergleich / Unstimmigkeit ─────────────────────────────────────
    @staticmethod
    def _norm(s: str) -> str:
        """Vergleichs-Normalisierung: Kleinschreibung + Whitespace zusammengefasst."""
        return " ".join((s or "").casefold().split())

    def _unstimmig(self, orig: str, rueck: str) -> bool:
        """True, wenn Original und Rückübersetzung (normalisiert) abweichen. Leere Werte
        gelten als nicht vergleichbar → keine Unstimmigkeit."""
        o, r = (orig or "").strip(), (rueck or "").strip()
        if not o or not r:
            return False
        return self._norm(r) != self._norm(o)

    def _lade_offene_zeilen(self, code):
        """Lädt bereits gespeicherte, noch **offene** Zeilen (Übersetzung vorhanden,
        Rückübersetzung weicht ab und ist nicht bestätigt) ohne KI in die Tabelle, damit
        sie ohne neuen Lauf nachbestätigt werden können."""
        extra = lang_tools.ohne_meta(lang_tools.load_extra(code))
        review = lang_tools.load_review(code)
        for key in sorted(extra):
            ueb = extra.get(key) or ""
            if not ueb:
                continue
            rev = review.get(key) or {}
            if rev.get("ok"):
                continue
            rueck = rev.get("rueck") or ""
            orig = self._quellwerte.get(key, key)
            if rueck and self._unstimmig(orig, rueck):
                self._add_row(key, orig, ueb, rueck, unstimmig=True, ok=False)
        if self._table.rowCount():
            self._save_btn.setEnabled(True)

    def _add_row(self, key, orig, ueb, rueck, unstimmig, ok):
        """Hängt eine Zeile an; unstimmige Zeilen werden rot dargestellt und erhalten ein
        aktivierbares Bestätigungs-Häkchen."""
        row = self._table.rowCount()
        self._table.insertRow(row)
        rot = QColor(theme.color("error_fg")) if unstimmig else None
        for col, text in ((COL_KEY, key), (COL_ORIG, orig),
                          (COL_UEB, ueb), (COL_RUECK, rueck)):
            item = QTableWidgetItem(text)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            if rot is not None:
                item.setForeground(rot)
            self._table.setItem(row, col, item)
        chk = QTableWidgetItem()
        if unstimmig:
            chk.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            chk.setCheckState(Qt.CheckState.Checked if ok else Qt.CheckState.Unchecked)
            chk.setToolTip(_("dlg.sprachdatei.bestaetigt_tt"))
        else:
            chk.setFlags(Qt.ItemFlag.NoItemFlags)   # stimmig → keine Bestätigung nötig
        self._table.setItem(row, COL_OK, chk)

    # ── Keys bestimmen (nur Offene / alle) ────────────────────────────
    def _bestimme_keys(self, main, extra, review, alle):
        """Zu übersetzende Keys: bei `alle` alle UI-Keys; sonst nur **offene** (fehlend
        oder Übersetzung mit abweichender, nicht bestätigter Rückübersetzung)."""
        if alle:
            return list(main.keys())
        extra_m = lang_tools.ohne_meta(extra)
        out = []
        for key in main:
            ueb = extra_m.get(key) or ""
            if not ueb:
                out.append(key)                     # fehlt
                continue
            rev = review.get(key) or {}
            if rev.get("ok"):
                continue                            # bestätigt
            rueck = rev.get("rueck") or ""
            orig = self._quellwerte.get(key, key)
            if not rueck or self._unstimmig(orig, rueck):
                out.append(key)                     # ungeprüft oder unstimmig
        return out

    # ── Aktion: Übersetzen + Rückübersetzen (Lauf) ────────────────────
    def _run(self):
        code = (self._code_edit.text() or "").strip().lower()
        label = (self._name_edit.text() or "").strip()
        if not code or code in lang_tools.BASIS_SPRACHEN or not code.replace("-", "").isalnum():
            QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                    _("dlg.sprachdatei.code_ungueltig"))
            return
        if not label:
            QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                    _("dlg.sprachdatei.name_fehlt"))
            return
        if code == self._quellcode:
            QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                    _("dlg.sprachdatei.quelle_identisch", sprache=self._quelllabel))
            return

        firma_row = self.db.get_firma()
        firma = dict(firma_row) if firma_row else {}
        if not firma.get("ki_aktiv"):
            QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                    _("dlg.sprachdatei.ki_inaktiv"))
            return

        main = lang_tools.load_main()
        extra = lang_tools.load_extra(code)
        review = lang_tools.load_review(code)
        keys = self._bestimme_keys(main, extra, review, self._alle_cb.isChecked())
        if not keys:
            QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                    _("dlg.sprachdatei.nichts_zu_tun"))
            return

        antwort = QMessageBox.question(
            self, _("dlg.sprachdatei.titel"),
            _("dlg.sprachdatei.confirm", n=len(keys),
              quelle=self._quelllabel, sprache=label))
        if antwort != QMessageBox.StandardButton.Yes:
            return

        self._lauf(firma, label, keys)

    def _lauf(self, firma, label, keys):
        """Übersetzt Key für Key vorwärts (LLM 1) und sofort rückwärts (LLM 2); jede Zeile
        wird live angehängt. Bricht beim ersten KI-Fehler oder per „Abbrechen" ab; bereits
        gefüllte Zeilen bleiben zum Speichern erhalten."""
        self._table.setRowCount(0)
        self._update_headers(label)
        ctx = uebersetzung.baue_ctx(firma, self._quelllabel, label, kontext=_KONTEXT)
        self._abbruch = False
        self._set_running(True)
        n, i, abgebrochen = len(keys), 0, False
        try:
            for key in keys:
                if self._abbruch:
                    abgebrochen = True
                    break
                orig = self._quellwerte.get(key, key)
                try:
                    ueb = uebersetzung.uebersetze_einen(ctx, orig)
                except uebersetzung.UebersetzungAbbruch as ab:
                    zeige_fehler(self, _("msg.fehler"),
                                 _("uebersetzung.abbruch_komplett", detail=str(ab)))
                    abgebrochen = True
                    break
                try:
                    rueck = uebersetzung.uebersetze_rueck(
                        firma, label, self._quelllabel, ueb, kontext=_KONTEXT)
                except Exception as ex:                                  # noqa: BLE001
                    zeige_fehler(self, _("msg.fehler"),
                                 _("uebersetzung.abbruch", detail=str(ex)))
                    abgebrochen = True
                    break
                self._add_row(key, orig, ueb, rueck,
                              unstimmig=self._unstimmig(orig, rueck), ok=False)
                i += 1
                self._fortschritt.setText(_("dlg.sprachdatei.lauf_fortschritt", i=i, n=n))
                self._table.scrollToBottom()
                QApplication.processEvents()
        finally:
            self._set_running(False)
        if abgebrochen:
            zeige_warnung(self, _("dlg.sprachdatei.titel"),
                          _("dlg.sprachdatei.abgebrochen", i=i, n=n))
        if self._table.rowCount():
            self._save_btn.setEnabled(True)

    def _set_running(self, running: bool):
        """UI während des Laufs sperren (nur „Abbrechen" bleibt aktiv)."""
        self._lauf_aktiv = running
        self._cancel_btn.setVisible(running)
        for w in (self._run_btn, self._close_btn, self._combo,
                  self._code_edit, self._name_edit, self._alle_cb):
            w.setEnabled(not running)
        if running:
            self._save_btn.setEnabled(False)

    def _abbrechen(self):
        # Lauf beim nächsten Key beenden (kein hartes Abbrechen mitten im KI-Aufruf).
        self._abbruch = True

    # ── Speichern (Sprachdatei + Review-Begleitdatei) ─────────────────
    def _save(self):
        code = (self._code_edit.text() or "").strip().lower()
        label = (self._name_edit.text() or "").strip()
        if not code or not label:
            return
        extra = lang_tools.load_extra(code)
        mapping = lang_tools.ohne_meta(extra)
        review = lang_tools.load_review(code)
        n_ueb = n_ok = 0
        for row in range(self._table.rowCount()):
            key = self._table.item(row, COL_KEY).text()
            ueb = self._table.item(row, COL_UEB).text()
            rueck = self._table.item(row, COL_RUECK).text()
            chk = self._table.item(row, COL_OK)
            ok = bool(chk and (chk.flags() & Qt.ItemFlag.ItemIsUserCheckable)
                      and chk.checkState() == Qt.CheckState.Checked)
            mapping[key] = ueb
            review[key] = {"rueck": rueck, "ok": ok}
            n_ueb += 1
            n_ok += 1 if ok else 0
        base = lang_tools.meta_base(extra, self._quellcode)
        try:
            lang_tools.schreibe_extra(code, label, base, mapping)
            lang_tools.schreibe_review(code, review)
        except OSError as e:
            zeige_fehler(self, _("dlg.sprachdatei.titel"),
                         _("dlg.sprachdatei.schreibfehler", err=e))
            return

        i18n.reload()
        QMessageBox.information(
            self, _("dlg.sprachdatei.titel"),
            _("dlg.sprachdatei.gespeichert", sprache=label, n=n_ueb, m=n_ok))
        # Combo neu aufbauen und die gerade bearbeitete Sprache wieder einstellen
        # (lädt verbleibende offene Zeilen frisch aus den Dateien).
        self._fill_combo()
        idx = self._combo.findData(code)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)

    def reject(self):
        # ESC/X während eines Laufs bricht den Lauf ab, schließt aber nicht den Dialog.
        if self._lauf_aktiv:
            self._abbruch = True
            return
        super().reject()
