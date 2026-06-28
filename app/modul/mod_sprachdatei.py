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
                             QAbstractSpinBox, QWidget, QTextEdit, QStyledItemDelegate,
                             QStyle, QStyleOptionViewItem)
from PyQt6.QtCore import Qt, QSize, QRectF
from PyQt6.QtGui import QColor, QTextDocument, QPalette

import html
import re
import settings
import i18n
import lang_tools
import uebersetzung
import theme
import spellcheck
from i18n import _
from ui_widgets import zeige_fehler, zeige_warnung
from modul.beleg_utils import _apply_saved_columns, _connect_save_columns

_KONTEXT = "App-Oberfläche (kurze UI-Beschriftung)"
# Neuer Schlüssel seit Einführung der Nummern-Spalte (sonst macht die alte gespeicherte
# 6-Spalten-Breite die erste Spalte überbreit / verschiebt die Spalten).
_COLS_KEY = "sprachdatei_review3"

# Spaltenindizes der Review-Tabelle (erste Spalte: laufende Nummer)
COL_NR, COL_KEY, COL_ORIG, COL_UEB, COL_RUECK, COL_OK, COL_AKTION = range(7)

# Bewertungsstufe → Theme-Farbschlüssel für den Stern hinter dem Bestätigt-Häkchen
# (Ampel: sehr gut = grün, gut = gelb, schlecht = rot; helle Töne in beiden Themes).
_BEWERTUNG_FARBE = {"sehr_gut": "rating_sehr_gut", "gut": "rating_gut",
                    "schlecht": "rating_schlecht"}
# Maximale Wiederholungen eines Übersetzungsversuchs mit Bewertung (Ziel: sehr_gut).
_MAX_RETRY = 3
# Tooltip-Breite des Bewertungssterns (~10 cm bei 96 dpi); längere Begründungen brechen um.
_STERN_TOOLTIP_BREITE = 380
# Anzeigedauer des Feld-Tooltips: bewusst sehr lang (10 min), damit der Hint nicht nach einer
# Zeitspanne von selbst schließt, sondern erst beim Verlassen des Feldes verschwindet.
_TOOLTIP_DAUER_MS = 600000


class SprachdateiDialog(settings.DialogSizeMixin, QDialog):
    """Erstellt/aktualisiert eine zusätzliche App-Sprachdatei per KI-Übersetzung mit
    Rückübersetzungs-Kontrolle (rote Unstimmigkeiten, bestätigbar)."""

    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        # Quelle = wählbar zwischen den Basissprachen Deutsch/Englisch (Umschalter im
        # Dialog, unabhängig von der App-Sprache). Standard = aktuelle App-Sprache, falls
        # sie eine Basissprache ist, sonst Deutsch.
        self._quellcode = (i18n.current() if i18n.current() in lang_tools.BASIS_SPRACHEN
                           else "de")
        self._quelllabel = i18n.label(self._quellcode)
        self._quellwerte = i18n.werte(self._quellcode)   # {key: text}
        self._lauf_aktiv = False
        self._abbruch = False
        self.setWindowTitle(_("dlg.sprachdatei.titel"))
        self._build()
        self._stamp_main_silent()   # ts in language.json beim Öffnen nachziehen
        self._backfill_ok_silent()  # stimmige Altbestände einmalig auf ok=True heben
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

    def _backfill_ok_silent(self):
        """Hebt beim Öffnen bestehende, **stimmige** Übersetzungen aller Zusatzsprachen
        einmalig auf `ok=True` (siehe `lang_tools.backfill_ok`), damit der nun
        quellsprachenneutrale Erledigt-Status Altbestände nicht erneut übersetzt.
        Idempotent; Schreibfehler (read-only Auslieferung) werden still ignoriert."""
        try:
            main = lang_tools.load_main()
            for code, _label in lang_tools.discover():
                lang_tools.backfill_ok(code, main)
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

        # Quellsprache: Umschalter zwischen den Basissprachen (Deutsch/Englisch),
        # unabhängig von der App-Sprache. Nicht editierbar → Pfeil links/rechts wechselt
        # (globaler ComboArrowNavFilter). Index vor dem Verbinden setzen, damit beim
        # Aufbau kein Wechsel-Slot feuert.
        self._quelle_combo = QComboBox()
        for basis in lang_tools.BASIS_SPRACHEN:
            self._quelle_combo.addItem(i18n.label(basis), basis)
        idx = self._quelle_combo.findData(self._quellcode)
        if idx >= 0:
            self._quelle_combo.setCurrentIndex(idx)
        self._quelle_combo.currentIndexChanged.connect(self._on_quelle_changed)
        form.addRow(_("dlg.sprachdatei.quelle"), self._quelle_combo)

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
        self._anzahl_label.setStyleSheet(f"color: {theme.color('hint_fg')};")
        self._anzahl_label.setToolTip(_("dlg.sprachdatei.anzahl_tt"))
        durchl_zeile.addWidget(self._anzahl_label)
        # Hinter der Anzahl: das aktuell für die Übersetzung verwendete KI-Modell.
        self._llm_label = QLabel("")
        self._llm_label.setStyleSheet(f"color: {theme.color('hint_fg')};")
        self._llm_label.setToolTip(_("dlg.sprachdatei.llm_tt"))
        durchl_zeile.addSpacing(16)
        durchl_zeile.addWidget(self._llm_label)
        durchl_zeile.addStretch()
        form.addRow(_("dlg.sprachdatei.durchlaeufe"), durchl_zeile)

        # Batch-Größe: Anzahl Items je LLM-Aufruf. Übersetzt werden alle Items zuerst
        # vorwärts (Quell→Ziel), dann rückwärts — jeweils batchweise statt einzeln, was
        # die Last des LLM stark reduziert. Klein genug, dass das Modell keine Items
        # verschluckt. NoButtons → Pfeil hoch/runter navigiert (Tastatur-Regel).
        self._batch_spin = QSpinBox()
        self._batch_spin.setRange(5, 50)
        self._batch_spin.setValue(20)
        self._batch_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._batch_spin.setMaximumWidth(80)
        self._batch_spin.setToolTip(_("dlg.sprachdatei.batchgroesse_tt"))
        form.addRow(_("dlg.sprachdatei.batchgroesse"), self._batch_spin)

        self._alle_cb = QCheckBox(_("dlg.sprachdatei.alle_neu"))
        form.addRow("", self._alle_cb)

        # Ansichts-Umschalter: aus = nur offene Zeilen, an = alle übersetzten Items.
        self._alle_anzeigen_cb = QCheckBox(_("dlg.sprachdatei.alle_anzeigen"))
        self._alle_anzeigen_cb.setToolTip(_("dlg.sprachdatei.alle_anzeigen_tt"))
        self._alle_anzeigen_cb.toggled.connect(self._on_alle_toggle)
        form.addRow("", self._alle_anzeigen_cb)

        lay.addLayout(form)

        # Filter auf die Spalte „Original": mehrere Begriffe (durch Leerzeichen getrennt)
        # werden mit logischem UND verknüpft — eine Zeile bleibt nur sichtbar, wenn ihr
        # Originaltext alle Begriffe enthält (case-insensitiv). Wirkt rein visuell
        # (Ein-/Ausblenden) und greift nicht in Laden/Speichern/Übersetzen ein.
        filter_zeile = QHBoxLayout()
        filter_zeile.addWidget(QLabel(_("dlg.sprachdatei.filter")))
        self._filter_edit = QLineEdit()
        self._filter_edit.setClearButtonEnabled(True)
        self._filter_edit.setPlaceholderText(_("dlg.sprachdatei.filter_ph"))
        self._filter_edit.setToolTip(_("dlg.sprachdatei.filter_tt"))
        self._filter_edit.textChanged.connect(self._apply_filter)
        filter_zeile.addWidget(self._filter_edit, 1)
        lay.addLayout(filter_zeile)

        # Fortlaufend gefüllte Review-Tabelle. `_row_index` bildet key→Zeile ab, damit
        # spätere Durchläufe bestehende Zeilen aktualisieren statt duplizieren.
        self._row_index = {}
        self._table = QTableWidget(0, 7)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # Lange Texte vollständig zeigen: kein „…"-Abschneiden, stattdessen Zeilenumbruch
        # (die Zeilenhöhe wird je Zeile in _set_row an den Inhalt angepasst).
        self._table.setWordWrap(True)
        self._table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self._update_headers("")
        # Doppelklick auf eine Zelle öffnet ein Bearbeitungsfenster: Spalte „Übersetzung"
        # immer, Spalte „Original" nur im Entwicklermodus (CLAUDE_ENTWICKLER=Austin).
        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        lay.addWidget(self._table, 1)
        self._table.setColumnWidth(COL_NR, 44)   # schmale Vorgabe (von gespeicherter Breite überschrieben)
        # Übersetzungsspalte: Delegate hebt fehlerhafte Marker invers rot hervor.
        self._table.setItemDelegateForColumn(
            COL_UEB, _MarkerHighlightDelegate(self._table, theme.color("error_fg")))
        _apply_saved_columns(self._table, _COLS_KEY)
        _connect_save_columns(self._table, _COLS_KEY)

        self._fortschritt = QLabel("")
        self._fortschritt.setStyleSheet(theme.hint_label_style())
        lay.addWidget(self._fortschritt)

        # Button-Reihenfolge signalisiert die typische Bearbeitungsabfolge:
        # Erstellen/Aktualisieren → Nur fehlende → Sinngemäße prüfen → Schlecht → Gut →
        # Speichern → Schließen. (Abbrechen erscheint nur während eines Laufs.)
        btns = QHBoxLayout()
        btns.addStretch()
        self._run_btn = QPushButton(_("btn.erstellen_aktualisieren"))
        self._run_btn.clicked.connect(lambda: self._run())
        btns.addWidget(self._run_btn)
        self._fehlende_btn = QPushButton(_("dlg.sprachdatei.btn_fehlende"))
        self._fehlende_btn.setToolTip(_("dlg.sprachdatei.btn_fehlende_tt"))
        self._fehlende_btn.clicked.connect(lambda: self._run(nur_fehlende=True))
        btns.addWidget(self._fehlende_btn)
        self._aehnl_btn = QPushButton(_("dlg.sprachdatei.btn_aehnlichkeit"))
        self._aehnl_btn.setToolTip(_("dlg.sprachdatei.btn_aehnlichkeit_tt"))
        self._aehnl_btn.clicked.connect(lambda: self._pruefe_aehnlichkeit())
        btns.addWidget(self._aehnl_btn)
        self._schlecht_btn = QPushButton(_("dlg.sprachdatei.btn_schlecht_neu"))
        self._schlecht_btn.setToolTip(_("dlg.sprachdatei.btn_schlecht_neu_tt"))
        self._schlecht_btn.clicked.connect(lambda: self._batch_retry("schlecht"))
        btns.addWidget(self._schlecht_btn)
        self._gut_btn = QPushButton(_("dlg.sprachdatei.btn_gut_neu"))
        self._gut_btn.setToolTip(_("dlg.sprachdatei.btn_gut_neu_tt"))
        self._gut_btn.clicked.connect(lambda: self._batch_retry("gut"))
        btns.addWidget(self._gut_btn)
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

        self._update_llm_label()

    def _update_llm_label(self):
        """Zeigt hinter dem Durchläufe-Feld das für die Übersetzung verwendete KI-Modell
        (LLM 1; nach „/“ das LLM 2 für die Rückübersetzung, falls abweichend). Das Modell
        hängt nur an der KI-Anbindung der Firma, nicht an der Zielsprache — daher einmalig
        beim Aufbau gesetzt. Bei fehlender DB/Firma bleibt das Label leer (robust)."""
        try:
            firma_row = self.db.get_firma() if self.db else None
        except Exception:                                       # noqa: BLE001
            firma_row = None
        if not firma_row:
            self._llm_label.setText("")
            return
        firma = dict(firma_row)
        vor = (uebersetzung.vorwaerts_modell(firma) or "").strip()
        rueck = (uebersetzung.rueck_modell(firma) or "").strip()
        modell = vor if (not rueck or rueck == vor) else f"{vor} / {rueck}"
        self._llm_label.setText(_("dlg.sprachdatei.llm", modell=modell) if modell else "")

    def _update_headers(self, ziel_label):
        self._table.setHorizontalHeaderLabels([
            _("dlg.sprachdatei.col_nr"),
            _("dlg.sprachdatei.col_schluessel"),
            _("dlg.sprachdatei.col_original", sprache=self._quelllabel),
            _("dlg.sprachdatei.col_uebersetzung", sprache=ziel_label or "…"),
            _("dlg.sprachdatei.col_rueck", sprache=self._quelllabel),
            _("dlg.sprachdatei.col_bestaetigt"),
            _("dlg.sprachdatei.col_aktion"),
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
        self._alle_anzeigen_cb.setEnabled(bool(code))
        # Gespeicherte Zeilen ohne KI anzeigen — je nach „Alle anzeigen"-Schalter alle
        # übersetzten oder nur die offenen (Nachbestätigung).
        if code:
            if self._alle_anzeigen_cb.isChecked():
                self._lade_alle_zeilen(code)
            else:
                self._lade_offene_zeilen(code)
        self._update_anzahl(code)

    def _on_quelle_changed(self):
        """Wechselt die Quellsprache (Deutsch/Englisch) ohne die App-Sprache zu ändern und
        lädt die Ansicht neu. Der Erledigt-Status ist quellsprachenneutral (allein über
        `ok` + Veraltung), daher bleiben bereits erledigte Items erledigt; nur offene oder
        fehlende werden aus der neuen Quelle übersetzt."""
        if self._lauf_aktiv:
            return
        code_data = self._quelle_combo.currentData()
        if not code_data:
            return
        self._quellcode = code_data
        self._quelllabel = i18n.label(code_data)
        self._quellwerte = i18n.werte(code_data)
        self._update_headers((self._name_edit.text() or "").strip())
        code = (self._code_edit.text() or "").strip().lower()
        self._table.setRowCount(0)
        self._row_index = {}
        self._fortschritt.setText("")
        if code:
            if self._alle_anzeigen_cb.isChecked():
                self._lade_alle_zeilen(code)
            else:
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
    def _unstimmig(self, orig: str, rueck: str) -> bool:
        """True, wenn Original und Rückübersetzung abweichen. Leere Werte gelten als nicht
        vergleichbar → keine Unstimmigkeit. Nutzt die Qt-freie Vergleichslogik aus
        `lang_tools` (Single Source, kein Drift zum Backfill)."""
        o, r = (orig or "").strip(), (rueck or "").strip()
        if not o or not r:
            return False
        return not lang_tools.stimmig(o, r)

    def _lade_offene_zeilen(self, code):
        """Lädt die noch **offenen** Zeilen ohne KI in die Tabelle, damit sie ohne neuen Lauf
        bearbeitet/nachbestätigt werden können. Offen = **fehlende** Übersetzung, **veraltet**
        (Quelltext seit der Übersetzung geändert) oder **nicht erledigt** (`ok=False`). Die
        Schlüsselmenge ist identisch mit `_bestimme_keys(..., False)` und damit mit dem
        Zähler »offen« — fehlende (noch nicht übersetzte) Keys erscheinen als leere, rote
        Zeile. Rot bei fehlender Übersetzung, Veraltung oder abweichender Rückübersetzung."""
        main = lang_tools.load_main()
        ts_map = lang_tools.main_ts(main)
        extra = lang_tools.ohne_meta(lang_tools.load_extra(code))
        review = lang_tools.load_review(code)
        # Leere (noch nicht übersetzte) Zeilen zuerst, dann alphabetisch nach Schlüssel.
        offene = sorted(self._bestimme_keys(main, extra, review, False),
                        key=lambda k: (bool(extra.get(k)), k))
        for key in offene:
            ueb = extra.get(key) or ""
            rev = review.get(key) or {}
            veraltet = lang_tools.ist_veraltet(ts_map, key, rev)
            ok = bool(rev.get("ok"))
            rueck = rev.get("rueck") or ""
            orig = self._quellwerte.get(key, key)
            unstimmig = (not ueb) or veraltet or self._unstimmig(orig, rueck)
            self._set_row(key, orig, ueb, rueck, unstimmig=unstimmig, ok=ok,
                          src_ts=rev.get(lang_tools.REVIEW_SRC_TS, ""),
                          bewertung=rev.get("bewertung"),
                          begruendung=rev.get("begruendung", ""))
        if self._table.rowCount():
            self._save_btn.setEnabled(True)
        self._apply_filter()

    def _on_alle_toggle(self):
        """Schaltet die Tabellen-Ansicht um: an = alle übersetzten Items zur Durchsicht,
        aus = nur die offenen Zeilen. Lädt ohne KI neu."""
        if self._lauf_aktiv:
            return
        code = (self._code_edit.text() or "").strip().lower()
        self._table.setRowCount(0)
        self._row_index = {}
        self._fortschritt.setText("")
        if not code:
            return
        if self._alle_anzeigen_cb.isChecked():
            self._lade_alle_zeilen(code)
            self._fortschritt.setText(
                _("dlg.sprachdatei.alle_fortschritt", n=self._table.rowCount()))
        else:
            self._lade_offene_zeilen(code)

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
            # Erledigte (ok) Items nach einem Quellwechsel nicht fälschlich rot färben —
            # ihre Rückübersetzung wurde gegen ihre eigene Quelle geprüft. Veraltung bleibt
            # rot (Quelltext geändert → Nachpflege nötig).
            unstimmig = lang_tools.ist_veraltet(ts_map, key, rev) or (
                not ok and bool(rueck) and self._unstimmig(orig, rueck))
            self._set_row(key, orig, ueb, rueck, unstimmig=unstimmig, ok=ok,
                          src_ts=rev.get(lang_tools.REVIEW_SRC_TS, ""),
                          bewertung=rev.get("bewertung"),
                          begruendung=rev.get("begruendung", ""))
        if self._table.rowCount():
            self._save_btn.setEnabled(True)
        self._apply_filter()

    def _apply_filter(self):
        """Blendet Zeilen aus, deren Originaltext (Spalte COL_ORIG) nicht **alle** im
        Filterfeld eingegebenen Begriffe enthält (Leerzeichen-getrennt, case-insensitiv,
        UND-Verknüpfung). Leeres Feld → alle Zeilen sichtbar."""
        begriffe = (self._filter_edit.text() or "").lower().split()
        for row in range(self._table.rowCount()):
            item = self._table.item(row, COL_ORIG)
            orig = (item.text() if item is not None else "").lower()
            sichtbar = all(b in orig for b in begriffe)
            self._table.setRowHidden(row, not sichtbar)

    def _set_row(self, key, orig, ueb, rueck, unstimmig, ok, src_ts="", bewertung=None,
                 begruendung=""):
        """Aktualisiert die Zeile zu `key` (falls vorhanden) oder hängt sie neu an;
        unstimmige Zeilen werden rot dargestellt und erhalten ein aktivierbares
        Bestätigungs-Häkchen. Items werden immer frisch gesetzt, damit ein Wechsel
        unstimmig→stimmig Farbe und Häkchen sauber zurücknimmt. `src_ts` (Quell-Stand,
        gegen den übersetzt wurde) wird in der Schlüsselzelle hinterlegt und beim
        Speichern wieder ausgelesen. `bewertung` (sehr_gut/gut/schlecht) setzt hinter dem
        Häkchen einen farbigen Stern; `begruendung` erscheint als dessen Tooltip. Beide
        werden in der COL_OK-Zelle hinterlegt."""
        row = self._row_index.get(key)
        if row is None:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._row_index[key] = row
        # Marker-Prüfung: {…}-Format-Platzhalter müssen unverändert in der Übersetzung
        # stehen (i18n._ ersetzt sie zur Laufzeit). Weicht die Marker-Menge ab, ist die
        # Übersetzung kaputt (str.format → Rückfall auf den Quelltext) → harte
        # Unstimmigkeit, nie automatisch erledigt. Nur prüfen, wenn beide Texte gefüllt
        # sind (leere Übersetzung = „noch nicht übersetzt", kein Marker-Fehler).
        marker_fehlend, marker_fremd = [], []
        if (orig or "").strip() and (ueb or "").strip():
            marker_fehlend, marker_fremd = lang_tools.marker_diff(orig, ueb)
        if marker_fehlend or marker_fremd:
            unstimmig = True
            ok = False
        rot = QColor(theme.color("error_fg")) if unstimmig else None
        # Erste Spalte: laufende Nummer (Zeilenindex + 1), zentriert, nicht eingefärbt.
        nr_item = QTableWidgetItem(str(row + 1))
        nr_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        nr_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, COL_NR, nr_item)
        for col, text in ((COL_KEY, key), (COL_ORIG, orig),
                          (COL_UEB, ueb), (COL_RUECK, rueck)):
            item = QTableWidgetItem(text)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            if rot is not None:
                item.setForeground(rot)
            if col == COL_KEY:
                item.setData(Qt.ItemDataRole.UserRole, src_ts)
            if col == COL_UEB:
                # Liste der invers rot zu hebenden falschen Marker für den Delegate;
                # bei Marker-Fehler zusätzlich ein erklärender Tooltip (nennt auch rein
                # fehlende Marker, die im Text nichts zum Einfärben haben).
                item.setData(Qt.ItemDataRole.UserRole, marker_fremd)
                if marker_fehlend or marker_fremd:
                    item.setToolTip(_("dlg.sprachdatei.marker_fehler_tt",
                                      fremd=", ".join(marker_fremd) or "—",
                                      fehlend=", ".join(marker_fehlend) or "—"))
            self._table.setItem(row, col, item)
        # Bestätigt-Spalte: eine **zentrierte** echte Checkbox als Cell-Widget (nur bei
        # unstimmigen Zeilen). Vermeidet den toten Klickbereich rechts einer linksbündigen
        # Item-Checkbox, der wie ein wirkungsloser Button wirkt. Der ok-Wert wird zusätzlich
        # in der Zelle hinterlegt, damit stimmige (checkbox-lose) Zeilen ihren Erledigt-
        # Status beim Speichern behalten — auch über einen Quellsprachenwechsel hinweg.
        ok_item = QTableWidgetItem()
        ok_item.setData(Qt.ItemDataRole.UserRole, bool(ok))
        ok_item.setData(Qt.ItemDataRole.UserRole + 1, bewertung or "")
        ok_item.setData(Qt.ItemDataRole.UserRole + 2, begruendung or "")
        self._table.setItem(row, COL_OK, ok_item)
        if unstimmig:
            cb = QCheckBox()
            cb.setChecked(ok)
            cont = QWidget()
            h = QHBoxLayout(cont)
            h.setContentsMargins(0, 0, 0, 0)
            h.addStretch()
            h.addWidget(cb)
            # Feld-Tooltip: bei vorliegender Bewertung die Bewertungsstufe + (falls vorhanden)
            # die KI-Begründung, sonst die Erklärung des Häkchens. Er wird auf das gesamte
            # Bestätigungsfeld gelegt (Container + Checkbox + Stern), damit der Hint überall im
            # Feld erscheint — nicht nur direkt über dem kleinen Stern.
            if bewertung in _BEWERTUNG_FARBE:
                stufe_txt = _(f"dlg.sprachdatei.bewertung_{bewertung}")
                roh = f"{stufe_txt}\n{begruendung}" if begruendung else stufe_txt
                # Tooltip in normaler (uneingefärbter) Schrift, ~10 cm breit, mit Umbruch.
                inner = html.escape(roh).replace("\n", "<br>")
                feld_tt = (f"<table width='{_STERN_TOOLTIP_BREITE}'>"
                           f"<tr><td>{inner}</td></tr></table>")
                farbe = theme.color(_BEWERTUNG_FARBE[bewertung])
                # Farbe über Rich-Text im Label-Text (nicht via setStyleSheet), damit sie
                # nicht in den Tooltip „durchblutet" — der bleibt so in normaler Schriftfarbe.
                stern = QLabel(f"<span style='font-size:14px; color:{farbe}'>★</span>")
                stern.setTextFormat(Qt.TextFormat.RichText)
                stern.setToolTip(feld_tt)
                stern.setToolTipDuration(_TOOLTIP_DAUER_MS)
                h.addSpacing(4)
                h.addWidget(stern)
            else:
                feld_tt = _("dlg.sprachdatei.bestaetigt_tt")
            cb.setToolTip(feld_tt)
            cb.setToolTipDuration(_TOOLTIP_DAUER_MS)
            cont.setToolTip(feld_tt)
            cont.setToolTipDuration(_TOOLTIP_DAUER_MS)
            h.addStretch()
            self._table.setCellWidget(row, COL_OK, cont)
        else:
            self._table.removeCellWidget(row, COL_OK)   # stimmig → keine Bestätigung nötig
        # Aktion-Spalte: Button, der genau diese Zeile neu übersetzt (Vorwärts- +
        # Rückübersetzung). Der Schlüssel wird mitgebunden, damit der Button auch nach
        # späteren Zeilen-Aktualisierungen die richtige Zeile trifft.
        self._table.setItem(row, COL_AKTION, QTableWidgetItem())
        neu_btn = QPushButton(_("dlg.sprachdatei.btn_neu"))
        neu_btn.setToolTip(_("dlg.sprachdatei.btn_neu_tt"))
        neu_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        neu_btn.clicked.connect(lambda _checked=False, k=key: self._retranslate_row(k))
        cont = QWidget()
        h = QHBoxLayout(cont)
        h.setContentsMargins(2, 2, 2, 2)
        h.setSpacing(4)
        h.addWidget(neu_btn)
        # Liegt bereits eine Bewertung vor, zusätzlich „Neu mit Bewertung": zweiter
        # Übersetzungsversuch, der die Bewertung in den Prompt einbezieht.
        if bewertung in _BEWERTUNG_FARBE:
            fb_btn = QPushButton(_("dlg.sprachdatei.btn_neu_bewertung"))
            fb_btn.setToolTip(_("dlg.sprachdatei.btn_neu_bewertung_tt"))
            fb_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            fb_btn.clicked.connect(
                lambda _checked=False, k=key: self._retranslate_row_feedback(k))
            h.addWidget(fb_btn)
        h.addStretch()
        self._table.setCellWidget(row, COL_AKTION, cont)
        self._table.resizeRowToContents(row)        # Höhe an umgebrochenen Text anpassen

    # ── Keys bestimmen (nur Offene / alle) ────────────────────────────
    def _bestimme_keys(self, main, extra, review, alle):
        """Zu übersetzende Keys: bei `alle` alle UI-Keys; sonst nur **offene** (fehlend,
        **veraltet** durch geänderten Quelltext, oder noch nicht erledigt). »Erledigt« ist
        quellsprachenneutral: `ok=True` (stimmige Rückübersetzung **oder** manuell
        bestätigt) — ein Wechsel der Quellsprache übersetzt Erledigtes daher nicht erneut.
        Kundengerichtete Vorlagen (`firma.neu.*`) werden generell ausgeschlossen — sie
        werden pro Firma im Drucktext-System gepflegt."""
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
            if not rev.get("ok"):
                out.append(key)                     # noch nicht erledigt
        return out

    def _fehlende_keys(self, main, extra):
        """Keys mit **leerer** Übersetzung — für »Nur fehlende übersetzen«. Veraltete oder
        unstimmige (aber vorhandene) Übersetzungen bleiben außen vor; generator-
        ausgeschlossene (kundengerichtete) Keys ebenfalls."""
        extra_m = lang_tools.ohne_meta(extra)
        return [k for k in main
                if not lang_tools.ist_generator_ausgeschlossen(k)
                and not (extra_m.get(k) or "")]

    # ── Aktion: Übersetzen + Rückübersetzen (Lauf) ────────────────────
    def _run(self, nur_fehlende=False):
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
        if nur_fehlende:
            keys = self._fehlende_keys(main, extra)
        else:
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

        erfolg = self._lauf(firma, label, keys, durchlaeufe, lang_tools.main_ts(main))
        # Nach dem Übersetzen der fehlenden Items sofort die KI-Bewertung (sinngemäße
        # Übereinstimmung) der offenen roten Zeilen anschließen — ohne erneute Rückfrage.
        if nur_fehlende and erfolg:
            self._pruefe_aehnlichkeit(auto=True)

    def _lauf(self, firma, label, keys, durchlaeufe, ts_map):
        """Übersetzt **batchweise** in bis zu `durchlaeufe` Durchläufen: je Durchlauf erst
        alle Vorwärts-Übersetzungen (LLM 1, Quell→Ziel), dann alle Rückübersetzungen
        (LLM 2). Mehrere Items je LLM-Aufruf (Batch-Größe), was die Last gegenüber der
        Einzelübersetzung stark senkt; jede Zeile wird live aktualisiert. Der erste
        Durchlauf nimmt alle Keys, jeder weitere nur noch die Unstimmigkeiten (Frühstopp,
        sobald keine offen). Bricht beim ersten KI-Fehler oder per „Abbrechen" (zwischen
        Batches) ab; bereits gefüllte Zeilen bleiben erhalten."""
        self._table.setRowCount(0)
        self._row_index = {}
        self._update_headers(label)
        uebersetzung.reset_test_protokoll()        # neuer Lauf → Protokoll-Dialoge wieder zeigen
        self._abbruch = False
        self._set_running(True)
        batch_size = self._batch_spin.value()
        n, abgebrochen = 0, False
        aktuelle_keys = list(keys)
        try:
            for runde in range(1, durchlaeufe + 1):
                if not aktuelle_keys:               # keine Unstimmigkeiten mehr → fertig
                    break
                n = len(aktuelle_keys)
                werte = {k: self._quellwerte.get(k, k) for k in aktuelle_keys}
                zaehler = {"vor": 0, "rueck": 0}

                # Phase 1: Vorwärts-Übersetzung (batchweise); füllt die Übersetzungsspalte,
                # Rückübersetzung bleibt zunächst leer.
                def _on_vor(teil):
                    for key, ueb in teil.items():
                        self._set_row(key, werte.get(key, key), ueb, "",
                                      unstimmig=False, ok=False,
                                      src_ts=ts_map.get(key, ""))
                    zaehler["vor"] += len(teil)
                    self._fortschritt.setText(self._phase_fortschritt(
                        _("dlg.sprachdatei.phase_vor"), runde, durchlaeufe,
                        zaehler["vor"], n))
                    self._table.scrollToBottom()
                    QApplication.processEvents()

                ueb_map = uebersetzung.uebersetze_werte_batch(
                    firma, self._quelllabel, label, werte, kontext=_KONTEXT,
                    batch_size=batch_size, rueck=False,
                    on_batch=_on_vor, abbruch=lambda: self._abbruch)
                if self._abbruch:
                    abgebrochen = True
                    break

                # Phase 2: Rückübersetzung (batchweise) der eben erzeugten Übersetzungen;
                # aktualisiert die Zeilen, färbt Unstimmigkeiten rot und sammelt sie für
                # den nächsten Durchlauf.
                unstimmige = []

                def _on_rueck(teil):
                    for key, rueck in teil.items():
                        orig = werte.get(key, key)
                        ist = self._unstimmig(orig, rueck)
                        self._set_row(key, orig, ueb_map.get(key, ""), rueck,
                                      unstimmig=ist, ok=(not ist), src_ts=ts_map.get(key, ""))
                        if ist:
                            unstimmige.append(key)
                    zaehler["rueck"] += len(teil)
                    self._fortschritt.setText(self._phase_fortschritt(
                        _("dlg.sprachdatei.phase_rueck"), runde, durchlaeufe,
                        zaehler["rueck"], n))
                    QApplication.processEvents()

                uebersetzung.uebersetze_werte_batch(
                    firma, label, self._quelllabel, ueb_map, kontext=_KONTEXT,
                    batch_size=batch_size, rueck=True,
                    on_batch=_on_rueck, abbruch=lambda: self._abbruch)
                if self._abbruch:
                    abgebrochen = True
                    break
                aktuelle_keys = unstimmige         # nächster Durchlauf nur Unstimmigkeiten
        except uebersetzung.UebersetzungAbbruch as ab:
            zeige_fehler(self, _("msg.fehler"),
                         _("uebersetzung.abbruch_komplett", detail=str(ab)))
            abgebrochen = True
        except Exception as ex:                              # noqa: BLE001
            zeige_fehler(self, _("msg.fehler"),
                         _("uebersetzung.abbruch", detail=str(ex)))
            abgebrochen = True
        finally:
            self._set_running(False)
        if abgebrochen:
            zeige_warnung(self, _("dlg.sprachdatei.titel"),
                          _("dlg.sprachdatei.abgebrochen", i=self._table.rowCount(), n=n))
        if self._table.rowCount():
            self._save_btn.setEnabled(True)
        self._apply_filter()
        return not abgebrochen

    def _phase_fortschritt(self, phase_label, runde, durchlaeufe, i, n):
        """Fortschrittstext einer Lauf-Phase: »<Phase>: i/n« (bzw. mit Runde r/d bei
        mehreren Durchläufen)."""
        if durchlaeufe > 1:
            rest = _("dlg.sprachdatei.lauf_fortschritt_runde",
                     r=runde, d=durchlaeufe, i=i, n=n)
        else:
            rest = _("dlg.sprachdatei.lauf_fortschritt", i=i, n=n)
        return f"{phase_label}: {rest}"

    def _set_running(self, running: bool):
        """UI während des Laufs sperren (nur „Abbrechen" bleibt aktiv)."""
        self._lauf_aktiv = running
        self._cancel_btn.setVisible(running)
        for w in (self._run_btn, self._fehlende_btn, self._aehnl_btn, self._close_btn,
                  self._schlecht_btn, self._gut_btn,
                  self._combo, self._quelle_combo, self._code_edit, self._name_edit,
                  self._alle_cb, self._durchlaeufe_spin, self._batch_spin,
                  self._alle_anzeigen_cb):
            w.setEnabled(not running)
        if running:
            self._save_btn.setEnabled(False)

    def _abbrechen(self):
        # Lauf beim nächsten Key beenden (kein hartes Abbrechen mitten im KI-Aufruf).
        self._abbruch = True

    def _retranslate_row(self, key):
        """Übersetzt eine einzelne Zeile (per Zeilen-Button) neu: vorwärts (LLM 1) und
        sofort rückwärts (LLM 2), dann wird die Zeile live aktualisiert. Während eines
        laufenden Stapellaufs gesperrt. Bei KI-Fehler bleibt die bisherige Zeile erhalten."""
        if self._lauf_aktiv:
            return
        firma_row = self.db.get_firma()
        firma = dict(firma_row) if firma_row else {}
        if not firma.get("ki_aktiv"):
            QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                    _("dlg.sprachdatei.ki_inaktiv"))
            return
        label = (self._name_edit.text() or "").strip()
        if not label:
            QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                    _("dlg.sprachdatei.name_fehlt"))
            return
        orig = self._quellwerte.get(key, key)
        ts_map = lang_tools.main_ts(lang_tools.load_main())
        uebersetzung.reset_test_protokoll()        # Einzel-Neuübersetzung → Protokoll wieder zeigen
        ctx = uebersetzung.baue_ctx(firma, self._quelllabel, label, kontext=_KONTEXT,
                                    kein_split=True)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            ueb = uebersetzung.uebersetze_einen(ctx, orig)
            rueck = uebersetzung.uebersetze_rueck(
                firma, label, self._quelllabel, ueb, kontext=_KONTEXT)
            # Bei unstimmiger Neuübersetzung gleich im Anschluss die KI-Bewertung
            # (sinngemäße Übereinstimmung) ausführen — wie ein Klick auf „Ähnlichkeit prüfen"
            # für genau diese Zeile. Stimmige Zeilen sind bereits bestätigt (kein Bedarf).
            ist_unstimmig = self._unstimmig(orig, rueck)
            bewertung = begruendung = None
            if ist_unstimmig:
                bewertung, begruendung = uebersetzung.bewerte_aehnlichkeit(
                    firma, self._quelllabel, label, orig, ueb, kontext=_KONTEXT)
        except uebersetzung.UebersetzungAbbruch as ab:
            QApplication.restoreOverrideCursor()
            zeige_fehler(self, _("msg.fehler"),
                         _("uebersetzung.abbruch_komplett", detail=str(ab)))
            return
        except Exception as ex:                                  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            zeige_fehler(self, _("msg.fehler"),
                         _("uebersetzung.abbruch", detail=str(ex)))
            return
        QApplication.restoreOverrideCursor()
        ok = (not ist_unstimmig) or (bewertung == "sehr_gut")
        self._set_row(key, orig, ueb, rueck, unstimmig=ist_unstimmig, ok=ok,
                      src_ts=ts_map.get(key, ""), bewertung=bewertung,
                      begruendung=begruendung or "")
        self._save_btn.setEnabled(True)

    @staticmethod
    def _bewertung_rang(stufe) -> int:
        """Vergleichsrang einer Bewertungsstufe (höher = besser); unbekannt/None = -1."""
        return {"schlecht": 0, "gut": 1, "sehr_gut": 2}.get(stufe, -1)

    def _retry_zeile(self, firma, label, orig, alt_ueb, alt_rueck, alt_bew, alt_begr):
        """Wiederholt den Übersetzungsversuch unter Einbezug der jeweils aktuellen Bewertung
        (bis zu `_MAX_RETRY` mal): übersetzt neu (LLM 1), rückübersetzt (LLM 2) und bewertet
        erneut. Bricht ab, sobald „sehr_gut" erreicht ist; jeder Versuch baut auf dem bisher
        **besten** Ergebnis auf und es wird über alle Versuche das beste behalten (Rang
        sehr_gut > gut > schlecht; bei Gleichstand das ältere). Liefert
        `(ueb, rueck, bewertung, begruendung)`. KI-Fehler propagieren an den Aufrufer."""
        best_ueb, best_rueck, best_bew, best_begr = alt_ueb, alt_rueck, alt_bew, alt_begr
        for _versuch in range(_MAX_RETRY):
            if best_bew == "sehr_gut" or self._abbruch:
                break
            bew_text = (best_begr or "").strip() or (best_bew or "")
            neu_ueb = uebersetzung.uebersetze_mit_bewertung(
                firma, self._quelllabel, label, orig, best_ueb, bew_text, kontext=_KONTEXT)
            neu_rueck = uebersetzung.uebersetze_rueck(
                firma, label, self._quelllabel, neu_ueb, kontext=_KONTEXT)
            neu_bew, neu_begr = uebersetzung.bewerte_aehnlichkeit(
                firma, self._quelllabel, label, orig, neu_ueb, kontext=_KONTEXT)
            if self._bewertung_rang(neu_bew) > self._bewertung_rang(best_bew):
                best_ueb, best_rueck, best_bew, best_begr = neu_ueb, neu_rueck, neu_bew, neu_begr
        return best_ueb, best_rueck, best_bew, best_begr

    def _retranslate_row_feedback(self, key):
        """Zeilen-Button „Neu mit Bewertung": startet für eine bereits bewertete Zeile einen
        zweiten Übersetzungsversuch, der die Bewertung in den Prompt einbezieht, und behält
        das bessere Ergebnis (siehe `_retry_zeile`). Während eines Stapellaufs gesperrt; bei
        KI-Fehler bleibt die bisherige Zeile erhalten."""
        if self._lauf_aktiv:
            return
        firma_row = self.db.get_firma()
        firma = dict(firma_row) if firma_row else {}
        if not firma.get("ki_aktiv"):
            QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                    _("dlg.sprachdatei.ki_inaktiv"))
            return
        label = (self._name_edit.text() or "").strip()
        if not label:
            QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                    _("dlg.sprachdatei.name_fehlt"))
            return
        row = self._row_index.get(key)
        if row is None:
            return
        orig = self._quellwerte.get(key, key)
        alt_ueb = self._table.item(row, COL_UEB).text()
        alt_rueck = self._table.item(row, COL_RUECK).text()
        ok_item = self._table.item(row, COL_OK)
        alt_bew = (ok_item.data(Qt.ItemDataRole.UserRole + 1) if ok_item else "") or ""
        alt_begr = (ok_item.data(Qt.ItemDataRole.UserRole + 2) if ok_item else "") or ""
        src_ts = self._table.item(row, COL_KEY).data(Qt.ItemDataRole.UserRole) or ""
        self._abbruch = False                      # Retry-Schleife nicht durch Alt-Status stoppen
        uebersetzung.reset_test_protokoll()        # Einzel-Neuübersetzung → Protokoll wieder zeigen
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            ueb, rueck, bewertung, begruendung = self._retry_zeile(
                firma, label, orig, alt_ueb, alt_rueck, alt_bew, alt_begr)
        except uebersetzung.UebersetzungAbbruch as ab:
            QApplication.restoreOverrideCursor()
            zeige_fehler(self, _("msg.fehler"),
                         _("uebersetzung.abbruch_komplett", detail=str(ab)))
            return
        except Exception as ex:                                  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            zeige_fehler(self, _("msg.fehler"),
                         _("uebersetzung.abbruch", detail=str(ex)))
            return
        QApplication.restoreOverrideCursor()
        self._set_row(key, orig, ueb, rueck, unstimmig=(bewertung != "sehr_gut"),
                      ok=(bewertung == "sehr_gut"), src_ts=src_ts,
                      bewertung=bewertung, begruendung=begruendung or "")
        self._save_btn.setEnabled(True)

    # ── Inline-Editierung (Doppelklick: Quell-/Zieltext) ──────────────
    def _on_cell_double_clicked(self, row, col):
        """Doppelklick auf eine Zelle: Spalte „Übersetzung" immer editierbar, Spalte
        „Original" nur im Entwicklermodus (CLAUDE_ENTWICKLER=Austin). Während eines
        laufenden Stapellaufs gesperrt."""
        if self._lauf_aktiv:
            return
        if col == COL_UEB:
            self._edit_ziel(row)
        elif col == COL_ORIG and settings.entwickler_modus():
            self._edit_quelle(row)

    def _edit_ziel(self, row):
        """Editiert den Übersetzungstext (Zielsprache) der Zeile per Bearbeitungsfenster.
        Eine manuell korrigierte Übersetzung gilt als **bestätigt** (`ok=True`) und – gegen
        den aktuellen Quelltext – als **aktuell** (frischer `src_ts`). Die Zeile wird daher
        ohne rote Markierung (weder unstimmig noch veraltet) neu gerendert; die
        Rückübersetzung wird bewusst nicht neu berechnet, sondern unverändert mitgeführt."""
        ueb_item = self._table.item(row, COL_UEB)
        if ueb_item is None:
            return
        orig_item = self._table.item(row, COL_ORIG)
        ziel_label = (self._name_edit.text() or "").strip()
        ziel_code = (self._code_edit.text() or "").strip().lower()
        neu = _TextEditDialog.bearbeite(
            self, _("dlg.sprachdatei.edit_ziel_titel", sprache=ziel_label or "…"),
            kontext_label=self._quelllabel,
            kontext_text=orig_item.text() if orig_item is not None else "",
            feld_label=ziel_label or "…", text=ueb_item.text(), spell_lang=ziel_code)
        if neu is None or neu == ueb_item.text():
            return
        key_item = self._table.item(row, COL_KEY)
        key = key_item.text()
        orig = orig_item.text() if orig_item is not None else self._quellwerte.get(key, key)
        rueck_item = self._table.item(row, COL_RUECK)
        rueck = rueck_item.text() if rueck_item is not None else ""
        ts_map = lang_tools.main_ts(lang_tools.load_main())
        src_ts = ts_map.get(key) or (key_item.data(Qt.ItemDataRole.UserRole) or "")
        self._set_row(key, orig, neu, rueck, unstimmig=False, ok=True, src_ts=src_ts)
        self._table.resizeRowToContents(row)
        self._save_btn.setEnabled(True)

    def _edit_quelle(self, row):
        """Editiert den Quelltext (Quellsprache) der Zeile — nur im Entwicklermodus. Nach der
        Änderung läuft alles in einem selbst-schließenden Fortschritts-Fenster ohne weitere
        Rückfrage: (1) zweite Quellsprache (das andere von de/en) per aktivem LLM anpassen,
        (2) `language.json` speichern, (3) Übersetzung in die Zielsprache, (4) Rückübersetzung,
        (5) bei Abweichung die KI-Bewertung. Die Zeile wird am Ende mit frischem Quell-Stand
        (gegen den neuen Quelltext „aktuell") neu gerendert. Erfordert aktive KI und eine
        gewählte Zielsprache."""
        if self._lauf_aktiv:
            return
        key_item = self._table.item(row, COL_KEY)
        if key_item is None:
            return
        key = key_item.text()
        zweite = self._zweite_quelle()
        if not zweite:
            return
        firma_row = self.db.get_firma()
        firma = dict(firma_row) if firma_row else {}
        if not firma.get("ki_aktiv"):
            QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                    _("dlg.sprachdatei.ki_inaktiv"))
            return
        label = (self._name_edit.text() or "").strip()
        if not label:
            QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                    _("dlg.sprachdatei.name_fehlt"))
            return
        aktuell = self._quellwerte.get(key, key)
        neu = _TextEditDialog.bearbeite(
            self, _("dlg.sprachdatei.edit_quelle_titel", sprache=self._quelllabel),
            kontext_label=_("dlg.sprachdatei.col_schluessel"), kontext_text=key,
            feld_label=self._quelllabel, text=aktuell, spell_lang=self._quellcode)
        if neu is None or not neu.strip() or neu.strip() == aktuell.strip():
            return
        neu = neu.strip()
        zweite_label = i18n.label(zweite)

        uebersetzung.reset_test_protokoll()
        dlg = _FortschrittDialog(self, _("dlg.sprachdatei.fortschritt_titel"))
        dlg.show()
        QApplication.processEvents()
        try:
            # (1) Zweite Quellsprache (de/en) per KI an den neuen Quelltext anpassen.
            dlg.schritt(_("dlg.sprachdatei.fortschritt_zweite_quelle", sprache=zweite_label))
            ctx_zweite = uebersetzung.baue_ctx(firma, self._quelllabel, zweite_label,
                                               kontext=_KONTEXT, kein_split=True)
            zweite_text = uebersetzung.uebersetze_einen(ctx_zweite, neu)

            # (2) Beide Quellsprachen in language.json speichern (kein Vorschau-Dialog mehr).
            dlg.schritt(_("dlg.sprachdatei.fortschritt_quelle_speichern"))
            main = lang_tools.load_main()
            item = main.get(key)
            if not isinstance(item, dict):
                dlg.close()
                dlg.deleteLater()
                zeige_fehler(self, _("dlg.sprachdatei.titel"),
                             _("dlg.sprachdatei.edit_key_fehlt", schluessel=key))
                return
            item[self._quellcode] = neu
            item[zweite] = zweite_text
            lang_tools.stamp_main(main)
            lang_tools.schreibe_main(main)
            i18n.reload()
            self._quellwerte = i18n.werte(self._quellcode)
            src_ts = lang_tools.main_ts(main).get(key, "")

            # (3) Vorwärts-Übersetzung in die Zielsprache.
            dlg.schritt(_("dlg.sprachdatei.fortschritt_uebersetzen", sprache=label))
            ctx_ziel = uebersetzung.baue_ctx(firma, self._quelllabel, label,
                                             kontext=_KONTEXT, kein_split=True)
            ueb = uebersetzung.uebersetze_einen(ctx_ziel, neu)

            # (4) Rückübersetzung zur Kontrolle.
            dlg.schritt(_("dlg.sprachdatei.fortschritt_rueck"))
            rueck = uebersetzung.uebersetze_rueck(
                firma, label, self._quelllabel, ueb, kontext=_KONTEXT)

            # (5) Bei Abweichung gleich die KI-Bewertung (sinngemäße Übereinstimmung).
            ist_unstimmig = self._unstimmig(neu, rueck)
            bewertung = begruendung = None
            if ist_unstimmig:
                dlg.schritt(_("dlg.sprachdatei.fortschritt_bewerten"))
                bewertung, begruendung = uebersetzung.bewerte_aehnlichkeit(
                    firma, self._quelllabel, label, neu, ueb, kontext=_KONTEXT)
        except uebersetzung.UebersetzungAbbruch as ab:
            dlg.close()
            dlg.deleteLater()
            zeige_fehler(self, _("msg.fehler"),
                         _("uebersetzung.abbruch_komplett", detail=str(ab)))
            return
        except OSError as e:
            dlg.close()
            dlg.deleteLater()
            zeige_fehler(self, _("dlg.sprachdatei.titel"),
                         _("dlg.sprachdatei.schreibfehler", err=e))
            return
        except Exception as ex:                                  # noqa: BLE001
            dlg.close()
            dlg.deleteLater()
            zeige_fehler(self, _("msg.fehler"), _("uebersetzung.abbruch", detail=str(ex)))
            return

        dlg.close()
        dlg.deleteLater()
        ok = (not ist_unstimmig) or (bewertung == "sehr_gut")
        self._set_row(key, neu, ueb, rueck, unstimmig=ist_unstimmig, ok=ok,
                      src_ts=src_ts, bewertung=bewertung, begruendung=begruendung or "")
        self._table.resizeRowToContents(row)
        self._save_btn.setEnabled(True)

    def _zweite_quelle(self):
        """Die zweite Quellsprache: das andere Element aus `BASIS_SPRACHEN` (nicht die aktuell
        gewählte). `None`, falls es keine zweite Basissprache gibt."""
        for code in lang_tools.BASIS_SPRACHEN:
            if code != self._quellcode:
                return code
        return None

    # ── Aktion: Sinngemäße Übereinstimmung per LLM bewerten ───────────
    def _pruefe_aehnlichkeit(self, auto=False):
        """Lässt je **offener roter** Zeile (unstimmig + nicht bestätigt) per LLM bewerten,
        ob Ausgangstext und Übersetzung sinngemäß übereinstimmen (ein Aufruf je Zeile).
        Setzt hinter dem Häkchen einen farbigen Stern (grün/gelb/rot); bei „sehr gut" wird
        das Bestätigt-Häkchen automatisch gesetzt. Abbruch zwischen den Zeilen möglich.

        `auto=True` (Anschluss an »Nur fehlende übersetzen«): ohne Bestätigungsfrage und
        ohne Hinweis-Dialoge — KI/Name sind dann schon geprüft, fehlt etwas, wird still
        nichts getan."""
        if self._lauf_aktiv:
            return
        firma_row = self.db.get_firma()
        firma = dict(firma_row) if firma_row else {}
        if not firma.get("ki_aktiv"):
            if not auto:
                QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                        _("dlg.sprachdatei.ki_inaktiv"))
            return
        label = (self._name_edit.text() or "").strip()
        if not label:
            if not auto:
                QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                        _("dlg.sprachdatei.name_fehlt"))
            return
        # Offene rote Zeilen einsammeln: COL_OK trägt eine nicht gesetzte Checkbox.
        zeilen = []
        for row in range(self._table.rowCount()):
            cont = self._table.cellWidget(row, COL_OK)
            cb = cont.findChild(QCheckBox) if cont else None
            if cb is None or cb.isChecked():
                continue
            if not self._table.item(row, COL_UEB).text().strip():
                continue                            # leere (noch nicht übersetzte) Zeile
            key_item = self._table.item(row, COL_KEY)
            zeilen.append((
                key_item.text(),
                self._table.item(row, COL_ORIG).text(),
                self._table.item(row, COL_UEB).text(),
                self._table.item(row, COL_RUECK).text(),
                key_item.data(Qt.ItemDataRole.UserRole) or "",
            ))
        if not zeilen:
            if not auto:
                QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                        _("dlg.sprachdatei.aehnlichkeit_nichts"))
            return
        if not auto and QMessageBox.question(
                self, _("dlg.sprachdatei.titel"),
                _("dlg.sprachdatei.aehnlichkeit_confirm", n=len(zeilen))
        ) != QMessageBox.StandardButton.Yes:
            return

        uebersetzung.reset_test_protokoll()        # neuer Lauf → Protokoll-Dialoge wieder zeigen
        self._abbruch = False
        self._set_running(True)
        n = len(zeilen)
        try:
            for i, (key, orig, ueb, rueck, src_ts) in enumerate(zeilen, start=1):
                if self._abbruch:
                    break
                bewertung, begruendung = uebersetzung.bewerte_aehnlichkeit(
                    firma, self._quelllabel, label, orig, ueb, kontext=_KONTEXT)
                # Nur bei „schlecht" automatisch einen zweiten Versuch starten, der die
                # Bewertung einbezieht, und das bessere Ergebnis behalten.
                if bewertung == "schlecht" and not self._abbruch:
                    self._fortschritt.setText(
                        _("dlg.sprachdatei.retry_fortschritt", i=i, n=n))
                    QApplication.processEvents()
                    ueb, rueck, bewertung, begruendung = self._retry_zeile(
                        firma, label, orig, ueb, rueck, bewertung, begruendung)
                self._set_row(key, orig, ueb, rueck, unstimmig=(bewertung != "sehr_gut"),
                              ok=(bewertung == "sehr_gut"), src_ts=src_ts,
                              bewertung=bewertung, begruendung=begruendung)
                self._fortschritt.setText(
                    _("dlg.sprachdatei.aehnlichkeit_fortschritt", i=i, n=n))
                QApplication.processEvents()
        except uebersetzung.UebersetzungAbbruch as ab:
            zeige_fehler(self, _("msg.fehler"),
                         _("uebersetzung.abbruch_komplett", detail=str(ab)))
        except Exception as ex:                                  # noqa: BLE001
            zeige_fehler(self, _("msg.fehler"),
                         _("uebersetzung.abbruch", detail=str(ex)))
        finally:
            self._set_running(False)
        if self._table.rowCount():
            self._save_btn.setEnabled(True)

    # ── Aktion: Batch-Neuübersetzung bewerteter Zeilen (Stufe) ────────
    def _batch_retry(self, stufe: str):
        """Übersetzt alle **nicht bestätigten** Zeilen mit der Bewertung `stufe`
        („schlecht" / „gut") per `_retry_zeile` neu (bis zu `_MAX_RETRY` Versuche mit
        Einbezug der Bewertung, Ziel »sehr gut«, bestes Ergebnis behalten). Für die gezielte
        Nachbearbeitung nach einem Bewertungslauf. Abbruch zwischen den Zeilen möglich."""
        if self._lauf_aktiv:
            return
        firma_row = self.db.get_firma()
        firma = dict(firma_row) if firma_row else {}
        if not firma.get("ki_aktiv"):
            QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                    _("dlg.sprachdatei.ki_inaktiv"))
            return
        label = (self._name_edit.text() or "").strip()
        if not label:
            QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                    _("dlg.sprachdatei.name_fehlt"))
            return
        zeilen = []
        for row in range(self._table.rowCount()):
            ok_item = self._table.item(row, COL_OK)
            if ok_item is None:
                continue
            if (ok_item.data(Qt.ItemDataRole.UserRole + 1) or "") != stufe:
                continue
            cont = self._table.cellWidget(row, COL_OK)
            cb = cont.findChild(QCheckBox) if cont else None
            if cb is not None and cb.isChecked():
                continue                            # bereits bestätigt → nicht anfassen
            if not self._table.item(row, COL_UEB).text().strip():
                continue
            key_item = self._table.item(row, COL_KEY)
            zeilen.append((
                key_item.text(),
                self._table.item(row, COL_ORIG).text(),
                self._table.item(row, COL_UEB).text(),
                self._table.item(row, COL_RUECK).text(),
                ok_item.data(Qt.ItemDataRole.UserRole + 1) or "",
                ok_item.data(Qt.ItemDataRole.UserRole + 2) or "",
                key_item.data(Qt.ItemDataRole.UserRole) or "",
            ))
        if not zeilen:
            QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                    _("dlg.sprachdatei.batch_retry_nichts"))
            return
        if QMessageBox.question(
                self, _("dlg.sprachdatei.titel"),
                _("dlg.sprachdatei.batch_retry_confirm", n=len(zeilen), max=_MAX_RETRY)
        ) != QMessageBox.StandardButton.Yes:
            return

        uebersetzung.reset_test_protokoll()        # neuer Lauf → Protokoll-Dialoge wieder zeigen
        self._abbruch = False
        self._set_running(True)
        n = len(zeilen)
        try:
            for i, (key, orig, ueb, rueck, bew, begr, src_ts) in enumerate(zeilen, start=1):
                if self._abbruch:
                    break
                self._fortschritt.setText(
                    _("dlg.sprachdatei.retry_fortschritt", i=i, n=n))
                QApplication.processEvents()
                ueb, rueck, bewertung, begruendung = self._retry_zeile(
                    firma, label, orig, ueb, rueck, bew, begr)
                self._set_row(key, orig, ueb, rueck, unstimmig=(bewertung != "sehr_gut"),
                              ok=(bewertung == "sehr_gut"), src_ts=src_ts,
                              bewertung=bewertung, begruendung=begruendung)
                QApplication.processEvents()
        except uebersetzung.UebersetzungAbbruch as ab:
            zeige_fehler(self, _("msg.fehler"),
                         _("uebersetzung.abbruch_komplett", detail=str(ab)))
        except Exception as ex:                                  # noqa: BLE001
            zeige_fehler(self, _("msg.fehler"),
                         _("uebersetzung.abbruch", detail=str(ex)))
        finally:
            self._set_running(False)
        if self._table.rowCount():
            self._save_btn.setEnabled(True)

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
            # Noch nicht übersetzte (leere) Zeilen — z. B. fehlende Keys, die nur zur Ansicht
            # geladen wurden — nicht als leere Einträge persistieren.
            if not ueb.strip():
                continue
            rueck = self._table.item(row, COL_RUECK).text()
            cont = self._table.cellWidget(row, COL_OK)
            cb = cont.findChild(QCheckBox) if cont else None
            # Unstimmige Zeilen tragen die Checkbox (manuelle Bestätigung); stimmige Zeilen
            # haben keine — ihr Erledigt-Status steckt im hinterlegten Flag der COL_OK-Zelle.
            ok_item = self._table.item(row, COL_OK)
            if cb is not None:
                ok = cb.isChecked()
            else:
                ok = bool(ok_item.data(Qt.ItemDataRole.UserRole)) if ok_item else False
            # Bewertung (Stern) + Begründung (Stern-Tooltip) zeilengenau persistieren.
            bewertung = (ok_item.data(Qt.ItemDataRole.UserRole + 1) if ok_item else "") or ""
            begruendung = (ok_item.data(Qt.ItemDataRole.UserRole + 2) if ok_item else "") or ""
            mapping[key] = ueb
            # src_ts (Quell-Stand, gegen den übersetzt wurde) bleibt zeilengenau erhalten:
            # neu übersetzte Zeilen tragen den aktuellen Quell-ts, nur angezeigte Zeilen
            # ihren bisherigen — so wird Veraltetes nicht versehentlich „aktuell" gestempelt.
            src_ts = key_item.data(Qt.ItemDataRole.UserRole) or ""
            review[key] = {"rueck": rueck, "ok": ok, lang_tools.REVIEW_SRC_TS: src_ts,
                           "bewertung": bewertung, "begruendung": begruendung}
            n_ueb += 1
            n_ok += 1 if ok else 0
        base = lang_tools.meta_base(extra, self._quellcode)
        try:
            lang_tools.schreibe_extra(code, label, base, mapping)
            lang_tools.schreibe_review(code, review)
            # Sprachliste für den Wörterbuch-Installer aktuell halten.
            lang_tools.schreibe_installed_languages()
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
