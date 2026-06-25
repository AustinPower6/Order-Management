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
                             QTableWidget, QTableWidgetItem, QApplication, QSpinBox,
                             QAbstractSpinBox)
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
        self._stamp_main_silent()   # ts in language.json beim Öffnen nachziehen
        self._fill_combo()

    def _stamp_main_silent(self):
        """Pflegt beim Öffnen die Zeitstempel in `language.json` (idempotent): geänderte
        oder neue de/en-Texte bekommen einen aktuellen `ts`, damit veraltete Übersetzungen
        ohne den CLI-Befehl `stamp` erkannt werden. Es wird **nur bei echten Änderungen**
        geschrieben; fehlende Schreibrechte (read-only Auslieferung beim Anwender — dort
        ändert sich `language.json` ohnehin nicht) werden still ignoriert."""
        try:
            main = lang_tools.load_main()
            main, n = lang_tools.stamp_main(main)
            if n:
                lang_tools.schreibe_main(main)
        except OSError:
            pass

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

        # Anzahl Übersetzungs-Durchläufe (Standard 1). Ab dem 2. Durchlauf werden nur
        # noch die Unstimmigkeiten erneut übersetzt. NoButtons → Pfeil hoch/runter
        # navigiert durch die Felder (Tastatur-Navigations-Regel).
        self._durchlaeufe_spin = QSpinBox()
        self._durchlaeufe_spin.setRange(1, 10)
        self._durchlaeufe_spin.setValue(1)
        self._durchlaeufe_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._durchlaeufe_spin.setMaximumWidth(80)
        self._durchlaeufe_spin.setToolTip(_("dlg.sprachdatei.durchlaeufe_tt"))
        # Hinter dem Feld: »nachzupflegende / gesamt« für die gewählte Sprache.
        durchl_zeile = QHBoxLayout()
        durchl_zeile.addWidget(self._durchlaeufe_spin)
        self._anzahl_label = QLabel("")
        self._anzahl_label.setStyleSheet(theme.hint_label_style())
        self._anzahl_label.setToolTip(_("dlg.sprachdatei.anzahl_tt"))
        durchl_zeile.addWidget(self._anzahl_label)
        durchl_zeile.addStretch()
        form.addRow(_("dlg.sprachdatei.durchlaeufe"), durchl_zeile)

        self._alle_cb = QCheckBox(_("dlg.sprachdatei.alle_neu"))
        form.addRow("", self._alle_cb)

        lay.addLayout(form)

        # Fortlaufend gefüllte Review-Tabelle. `_row_index` bildet key→Zeile ab, damit
        # spätere Durchläufe bestehende Zeilen aktualisieren statt duplizieren.
        self._row_index = {}
        self._table = QTableWidget(0, 5)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # Lange Texte vollständig zeigen: kein „…"-Abschneiden, stattdessen Zeilenumbruch
        # (die Zeilenhöhe wird je Zeile in _set_row an den Inhalt angepasst).
        self._table.setWordWrap(True)
        self._table.setTextElideMode(Qt.TextElideMode.ElideNone)
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
        self._alle_btn = QPushButton(_("dlg.sprachdatei.alle_anzeigen"))
        self._alle_btn.setToolTip(_("dlg.sprachdatei.alle_anzeigen_tt"))
        self._alle_btn.clicked.connect(self._zeige_alle)
        self._alle_btn.setEnabled(False)
        btns.addWidget(self._alle_btn)
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
        vorhanden = lang_tools.discover()
        for code, label in vorhanden:
            self._combo.addItem(f"{label}  ({code})", code)
        # Vorschläge aus den Länderkennzeichen des Firmenstamms: jedes Land mit
        # zugeordneter Sprache, das noch keine eigene Sprachdatei ist (Code = ISO,
        # Name = die dem Land zugeordnete Sprache).
        codes_da = {code for code, _label in vorhanden}
        for iso, sprache in self._laender_vorschlaege(codes_da):
            self._combo.addItem(f"➕ {sprache}  ({iso.upper()})",
                                {"iso": iso, "sprache": sprache})
        self._combo.addItem(_("dlg.sprachdatei.neu"), None)
        self._combo.setCurrentIndex(self._combo.count() - 1)   # Standard: „Neu"
        self._combo.blockSignals(False)
        self._on_combo()

    def _laender_vorschlaege(self, codes_da):
        """Länderkennzeichen aus dem Firmenstamm (`laender`) mit zugeordneter Sprache, die
        noch keine eigene Sprachdatei sind und nicht der Quell-/Basissprache entsprechen —
        als Vorschläge zum Neuanlegen. Rückgabe `[(iso_klein, sprachname)]`, nach
        Sprachname sortiert. Bei DB-Problemen leer (robust)."""
        if not self.db:
            return []
        try:
            namen = {s["id"]: s["bezeichnung"] for s in self.db.get_sprachen()}
            laender = [dict(x) for x in self.db.get_laender()]
        except Exception:                                       # noqa: BLE001
            return []
        gesehen, out = set(), []
        for land in laender:
            iso = (land.get("iso_code") or "").strip().lower()
            sprache = namen.get(land.get("sprache_id"))
            if not iso or not sprache:
                continue                       # nur Länder mit zugeordneter Sprache
            if (iso in lang_tools.BASIS_SPRACHEN or iso in codes_da
                    or iso == self._quellcode or iso in gesehen):
                continue
            gesehen.add(iso)
            out.append((iso, sprache))
        out.sort(key=lambda t: t[1].casefold())
        return out

    def _on_combo(self):
        data = self._combo.currentData()
        code = None
        if data is None:                       # „Neue Sprache" (freie Eingabe)
            self._code_edit.clear()
            self._code_edit.setReadOnly(False)
            self._name_edit.clear()
            ziel_label = ""
        elif isinstance(data, dict):           # Vorschlag aus Länderkennzeichen
            code = data["iso"]
            self._code_edit.setText(code)
            self._code_edit.setReadOnly(True)   # Code = Länderkennzeichen (fest)
            self._name_edit.setText(data["sprache"])
            ziel_label = data["sprache"]
        else:                                  # vorhandene Sprachdatei (code-String)
            code = data
            extra = lang_tools.load_extra(code)
            self._code_edit.setText(code)
            self._code_edit.setReadOnly(True)
            self._name_edit.setText(lang_tools.meta_label(extra, code))
            ziel_label = self._name_edit.text()
        self._update_headers(ziel_label)
        self._table.setRowCount(0)
        self._row_index = {}
        self._fortschritt.setText("")
        self._save_btn.setEnabled(False)
        self._alle_btn.setEnabled(bool(code))
        # Bereits gespeicherte, noch offene Zeilen ohne KI anzeigen (Nachbestätigung).
        if code:
            self._lade_offene_zeilen(code)
        self._update_anzahl(code)

    def _update_anzahl(self, code):
        """Zeigt hinter dem Durchläufe-Feld »nachzupflegende / gesamt« für `code`:
        wie viele Items fehlen, unstimmig oder veraltet sind (also in einem Lauf
        übersetzt würden), und wie viele übersetzbare Texte es insgesamt gibt. Bezieht
        sich auf den gespeicherten Stand der Dateien (aktualisiert sich nach dem
        Speichern erneut über `_on_combo`)."""
        if not code:
            self._anzahl_label.setText("")
            return
        main = lang_tools.load_main()
        extra = lang_tools.load_extra(code)
        review = lang_tools.load_review(code)
        offen = len(self._bestimme_keys(main, extra, review, False))
        gesamt = sum(1 for k in main if not lang_tools.ist_generator_ausgeschlossen(k))
        self._anzahl_label.setText(f"{offen} / {gesamt}")

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
        """Lädt bereits gespeicherte, noch **offene** Zeilen (Übersetzung vorhanden, aber
        Quelltext seit der Übersetzung geändert = **veraltet**, oder Rückübersetzung weicht
        ab und ist nicht bestätigt) ohne KI in die Tabelle, damit sie ohne neuen Lauf
        bearbeitet/nachbestätigt werden können."""
        ts_map = lang_tools.main_ts(lang_tools.load_main())
        extra = lang_tools.ohne_meta(lang_tools.load_extra(code))
        review = lang_tools.load_review(code)
        for key in sorted(extra):
            if lang_tools.ist_generator_ausgeschlossen(key):
                continue
            ueb = extra.get(key) or ""
            if not ueb:
                continue
            rev = review.get(key) or {}
            veraltet = lang_tools.ist_veraltet(ts_map, key, rev)
            if rev.get("ok") and not veraltet:
                continue
            rueck = rev.get("rueck") or ""
            orig = self._quellwerte.get(key, key)
            if veraltet or (rueck and self._unstimmig(orig, rueck)):
                self._set_row(key, orig, ueb, rueck, unstimmig=True, ok=False,
                              src_ts=rev.get(lang_tools.REVIEW_SRC_TS, ""))
        if self._table.rowCount():
            self._save_btn.setEnabled(True)

    def _zeige_alle(self):
        """„Alle anzeigen": lädt alle bereits übersetzten Items der gewählten Sprache zur
        Durchsicht in die Tabelle (ohne KI). Ersetzt den bisherigen Tabelleninhalt."""
        code = (self._code_edit.text() or "").strip().lower()
        if not code:
            return
        self._table.setRowCount(0)
        self._row_index = {}
        self._lade_alle_zeilen(code)
        self._fortschritt.setText(
            _("dlg.sprachdatei.alle_fortschritt", n=self._table.rowCount()))

    def _lade_alle_zeilen(self, code):
        """Lädt **alle** bereits übersetzten (nicht ausgeschlossenen) Items der Sprache
        ohne KI in die Tabelle — auch stimmige und bestätigte. Unstimmige **oder veraltete**
        (Quelltext geändert) Zeilen werden rot dargestellt; bestätigte behalten ihr
        gesetztes Häkchen."""
        ts_map = lang_tools.main_ts(lang_tools.load_main())
        extra = lang_tools.ohne_meta(lang_tools.load_extra(code))
        review = lang_tools.load_review(code)
        for key in sorted(extra):
            if lang_tools.ist_generator_ausgeschlossen(key):
                continue
            ueb = extra.get(key) or ""
            if not ueb:
                continue
            rev = review.get(key) or {}
            rueck = rev.get("rueck") or ""
            ok = bool(rev.get("ok"))
            orig = self._quellwerte.get(key, key)
            unstimmig = lang_tools.ist_veraltet(ts_map, key, rev) or (
                bool(rueck) and self._unstimmig(orig, rueck))
            self._set_row(key, orig, ueb, rueck, unstimmig=unstimmig, ok=ok,
                          src_ts=rev.get(lang_tools.REVIEW_SRC_TS, ""))
        if self._table.rowCount():
            self._save_btn.setEnabled(True)

    def _set_row(self, key, orig, ueb, rueck, unstimmig, ok, src_ts=""):
        """Aktualisiert die Zeile zu `key` (falls vorhanden) oder hängt sie neu an;
        unstimmige Zeilen werden rot dargestellt und erhalten ein aktivierbares
        Bestätigungs-Häkchen. Items werden immer frisch gesetzt, damit ein Wechsel
        unstimmig→stimmig Farbe und Häkchen sauber zurücknimmt. `src_ts` (Quell-Stand,
        gegen den übersetzt wurde) wird in der Schlüsselzelle hinterlegt und beim
        Speichern wieder ausgelesen."""
        row = self._row_index.get(key)
        if row is None:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._row_index[key] = row
        rot = QColor(theme.color("error_fg")) if unstimmig else None
        for col, text in ((COL_KEY, key), (COL_ORIG, orig),
                          (COL_UEB, ueb), (COL_RUECK, rueck)):
            item = QTableWidgetItem(text)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            if rot is not None:
                item.setForeground(rot)
            if col == COL_KEY:
                item.setData(Qt.ItemDataRole.UserRole, src_ts)
            self._table.setItem(row, col, item)
        chk = QTableWidgetItem()
        if unstimmig:
            chk.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            chk.setCheckState(Qt.CheckState.Checked if ok else Qt.CheckState.Unchecked)
            chk.setToolTip(_("dlg.sprachdatei.bestaetigt_tt"))
        else:
            chk.setFlags(Qt.ItemFlag.NoItemFlags)   # stimmig → keine Bestätigung nötig
        self._table.setItem(row, COL_OK, chk)
        self._table.resizeRowToContents(row)        # Höhe an umgebrochenen Text anpassen

    # ── Keys bestimmen (nur Offene / alle) ────────────────────────────
    def _bestimme_keys(self, main, extra, review, alle):
        """Zu übersetzende Keys: bei `alle` alle UI-Keys; sonst nur **offene** (fehlend,
        **veraltet** durch geänderten Quelltext, oder Übersetzung mit abweichender, nicht
        bestätigter Rückübersetzung). Kundengerichtete Vorlagen (`firma.neu.*`) werden
        generell ausgeschlossen — sie werden pro Firma im Drucktext-System gepflegt."""
        if alle:
            return [k for k in main if not lang_tools.ist_generator_ausgeschlossen(k)]
        ts_map = lang_tools.main_ts(main)
        extra_m = lang_tools.ohne_meta(extra)
        out = []
        for key in main:
            if lang_tools.ist_generator_ausgeschlossen(key):
                continue
            ueb = extra_m.get(key) or ""
            if not ueb:
                out.append(key)                     # fehlt
                continue
            rev = review.get(key) or {}
            if lang_tools.ist_veraltet(ts_map, key, rev):
                out.append(key)                     # Quelltext geändert → neu übersetzen
                continue
            if rev.get("ok"):
                continue                            # bestätigt (und nicht veraltet)
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

        durchlaeufe = self._durchlaeufe_spin.value()
        frage = _("dlg.sprachdatei.confirm", n=len(keys),
                  quelle=self._quelllabel, sprache=label)
        if durchlaeufe > 1:
            frage += "\n\n" + _("dlg.sprachdatei.confirm_runden", d=durchlaeufe)
        antwort = QMessageBox.question(self, _("dlg.sprachdatei.titel"), frage)
        if antwort != QMessageBox.StandardButton.Yes:
            return

        self._lauf(firma, label, keys, durchlaeufe, lang_tools.main_ts(main))

    def _lauf(self, firma, label, keys, durchlaeufe, ts_map):
        """Übersetzt Key für Key vorwärts (LLM 1) und sofort rückwärts (LLM 2) in bis zu
        `durchlaeufe` Durchläufen; jede Zeile wird live aktualisiert. Der erste Durchlauf
        nimmt alle übergebenen Keys, jeder weitere nur noch die verbliebenen
        Unstimmigkeiten (Frühstopp, sobald keine mehr offen sind). Bricht beim ersten
        KI-Fehler oder per „Abbrechen" ab; bereits gefüllte Zeilen bleiben erhalten."""
        self._table.setRowCount(0)
        self._row_index = {}
        self._update_headers(label)
        ctx = uebersetzung.baue_ctx(firma, self._quelllabel, label, kontext=_KONTEXT)
        self._abbruch = False
        self._set_running(True)
        i, n, abgebrochen = 0, 0, False
        aktuelle_keys = list(keys)
        try:
            for runde in range(1, durchlaeufe + 1):
                if not aktuelle_keys:               # keine Unstimmigkeiten mehr → fertig
                    break
                unstimmige, n, i = [], len(aktuelle_keys), 0
                for key in aktuelle_keys:
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
                    except Exception as ex:                              # noqa: BLE001
                        zeige_fehler(self, _("msg.fehler"),
                                     _("uebersetzung.abbruch", detail=str(ex)))
                        abgebrochen = True
                        break
                    ist_unstimmig = self._unstimmig(orig, rueck)
                    self._set_row(key, orig, ueb, rueck, unstimmig=ist_unstimmig, ok=False,
                                  src_ts=ts_map.get(key, ""))
                    if ist_unstimmig:
                        unstimmige.append(key)
                    i += 1
                    if durchlaeufe > 1:
                        self._fortschritt.setText(_("dlg.sprachdatei.lauf_fortschritt_runde",
                                                    r=runde, d=durchlaeufe, i=i, n=n))
                    else:
                        self._fortschritt.setText(_("dlg.sprachdatei.lauf_fortschritt", i=i, n=n))
                    self._table.scrollToBottom()
                    QApplication.processEvents()
                if abgebrochen:
                    break
                aktuelle_keys = unstimmige         # nächster Durchlauf nur Unstimmigkeiten
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
                  self._code_edit, self._name_edit, self._alle_cb,
                  self._durchlaeufe_spin, self._alle_btn):
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
            key_item = self._table.item(row, COL_KEY)
            key = key_item.text()
            ueb = self._table.item(row, COL_UEB).text()
            rueck = self._table.item(row, COL_RUECK).text()
            chk = self._table.item(row, COL_OK)
            ok = bool(chk and (chk.flags() & Qt.ItemFlag.ItemIsUserCheckable)
                      and chk.checkState() == Qt.CheckState.Checked)
            mapping[key] = ueb
            # src_ts (Quell-Stand, gegen den übersetzt wurde) bleibt zeilengenau erhalten:
            # neu übersetzte Zeilen tragen den aktuellen Quell-ts, nur angezeigte Zeilen
            # ihren bisherigen — so wird Veraltetes nicht versehentlich „aktuell" gestempelt.
            src_ts = key_item.data(Qt.ItemDataRole.UserRole) or ""
            review[key] = {"rueck": rueck, "ok": ok, lang_tools.REVIEW_SRC_TS: src_ts}
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
