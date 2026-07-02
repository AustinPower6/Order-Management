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
                             QStyle, QStyleOptionViewItem, QFrame)
from PyQt6.QtCore import Qt, QSize, QRectF
from PyQt6.QtGui import QColor, QTextDocument, QPalette

import html
import re
import settings
import i18n
import fonts
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
# (Ampel: identisch/sehr gut = grün, gut = gelb, schlecht = rot; helle Töne in beiden Themes).
_BEWERTUNG_FARBE = {"identisch": "rating_sehr_gut", "sehr_gut": "rating_sehr_gut",
                    "gut": "rating_gut", "schlecht": "rating_schlecht"}
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
        # Sprachbeherrschungs-Prüfung: Cache je Ziel-Label (Session) + Gate-Status.
        self._beherrschung_cache = {}
        self._beherrschung_ok = True
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

        form = QFormLayout()
        form.setVerticalSpacing(6)
        # Felder bleiben auf ihrer natürlichen (Standard-)Breite, statt sich über die
        # volle, von der breiten Tabelle vorgegebene Dialogbreite zu strecken.
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)

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

        # KI-Modell (Anzeige, kein Eingabefeld) — hängt nur an der KI-Anbindung der
        # Firma, nicht an der Zielsprache (siehe `_update_llm_label`). Gleiche Zeile
        # (Formular) wie die übrigen Felder, damit die Anzeige auf gleicher Position
        # (Label-/Feldspalte) steht.
        self._llm_label = QLabel("")
        self._llm_label.setToolTip(_("dlg.sprachdatei.llm_tt"))
        form.addRow(_("dlg.sprachdatei.kimodell"), self._llm_label)

        # Batch-Größe: Anzahl Items je LLM-Aufruf. Übersetzt werden alle Items zuerst
        # vorwärts (Quell→Ziel), dann rückwärts — jeweils batchweise statt einzeln, was
        # die Last des LLM stark reduziert. Klein genug, dass das Modell keine Items
        # verschluckt. NoButtons → Pfeil hoch/runter navigiert (Tastatur-Regel). (Die
        # frühere „Durchläufe"-Einstellung entfiel — ein Durchlauf hat in der Praxis
        # immer gereicht, siehe `_lauf`.)
        self._batch_spin = QSpinBox()
        self._batch_spin.setRange(5, 50)
        self._batch_spin.setValue(20)
        self._batch_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._batch_spin.setMaximumWidth(80)
        self._batch_spin.setToolTip(_("dlg.sprachdatei.batchgroesse_tt"))
        form.addRow(_("dlg.sprachdatei.batchgroesse"), self._batch_spin)

        # Optionen direkt im Anschluss an die Feldbeschreibungen (gleiches Formular,
        # gleicher Zeilenabstand). Beschriftung als Zeilenlabel am linken Rand (wie bei
        # den übrigen Feldern) statt als Text neben der Checkbox — die Checkbox selbst
        # (ohne eigenen Text) steht dadurch auf derselben Feldspalten-Position.
        self._alle_cb = QCheckBox()
        form.addRow(_("dlg.sprachdatei.alle_neu"), self._alle_cb)

        # Ansichts-Umschalter: aus = nur offene Zeilen, an = alle übersetzten Items.
        self._alle_anzeigen_cb = QCheckBox()
        self._alle_anzeigen_cb.setToolTip(_("dlg.sprachdatei.alle_anzeigen_tt"))
        self._alle_anzeigen_cb.toggled.connect(self._on_alle_toggle)
        form.addRow(_("dlg.sprachdatei.alle_anzeigen"), self._alle_anzeigen_cb)

        # Filter auf die Spalte „Original": mehrere Begriffe (durch Leerzeichen getrennt)
        # werden mit logischem UND verknüpft — eine Zeile bleibt nur sichtbar, wenn ihr
        # Originaltext alle Begriffe enthält (case-insensitiv). Wirkt rein visuell
        # (Ein-/Ausblenden) und greift nicht in Laden/Speichern/Übersetzen ein. Gleiches
        # Formular wie die übrigen Felder, damit das Eingabefeld auf derselben
        # Feldspalten-Position beginnt.
        self._filter_edit = QLineEdit()
        self._filter_edit.setClearButtonEnabled(True)
        self._filter_edit.setPlaceholderText(_("dlg.sprachdatei.filter_ph"))
        self._filter_edit.setToolTip(_("dlg.sprachdatei.filter_tt"))
        self._filter_edit.textChanged.connect(self._apply_filter)
        form.addRow(_("dlg.sprachdatei.filter"), self._filter_edit)

        # Hinweiszeile: »nachzupflegende / gesamt« für die gewählte Sprache und wie gut
        # das/die Modell(e) die Zielsprache beherrschen (Skala 1=sehr gut … 10=kenne ich
        # nicht; rot bei Ablehnung > 6).
        hinweis_zeile = QHBoxLayout()
        self._anzahl_label = QLabel("")
        self._anzahl_label.setStyleSheet(f"color: {theme.color('hint_fg')};")
        self._anzahl_label.setToolTip(_("dlg.sprachdatei.anzahl_tt"))
        hinweis_zeile.addWidget(self._anzahl_label)
        self._beherrschung_label = QLabel("")
        self._beherrschung_label.setToolTip(_("dlg.sprachdatei.beherrschung_tt"))
        hinweis_zeile.addSpacing(16)
        hinweis_zeile.addWidget(self._beherrschung_label)
        hinweis_zeile.addStretch()

        links_spalte = QVBoxLayout()
        links_spalte.addLayout(form)
        links_spalte.addLayout(hinweis_zeile)

        # Farberklärung als Rahmen am rechten Rand, damit sie die linke Spalte (Formular
        # + Hinweiszeile + Batchgröße) nicht in die Breite zieht und deren Felder auf
        # Standardbreite bleiben. Farben stammen aus demselben Theme-Farbschema wie die
        # Tabelle (theme.color), damit sie in Hell- und Dunkelmodus zur tatsächlichen
        # Darstellung passen.
        legende = QFrame()
        legende.setFrameShape(QFrame.Shape.StyledPanel)
        legende_lay = QVBoxLayout(legende)
        legende_lay.setSpacing(2)
        legende_lay.addWidget(QLabel(f"<b>{_('dlg.sprachdatei.legende_titel')}</b>"))
        for farbe, text_key in (
                (theme.color("error_fg"), "dlg.sprachdatei.legende_rot"),
                (theme.color("rating_sehr_gut"), "dlg.sprachdatei.legende_gruen"),
                (theme.color("rating_gut"), "dlg.sprachdatei.legende_stern_gut"),
                (theme.color("rating_schlecht"), "dlg.sprachdatei.legende_stern_schlecht")):
            zeile = QLabel(f"<span style='color:{farbe}'>&#9632;</span> {_(text_key)}")
            legende_lay.addWidget(zeile)
        # Standardfarbe (kein farbiges Quadrat, da theme-abhängig schwarz/hellgrau):
        # stimmige Zeile ohne Spitzenbewertung „identisch".
        legende_lay.addWidget(QLabel(_("dlg.sprachdatei.legende_normal")))
        legende_lay.addWidget(QLabel(_("dlg.sprachdatei.legende_marker")))

        # Programmerklärung (früher als Fließtext im Kopfbereich über dem Formular) —
        # jetzt als eigener Rahmen unter der Farberklärung, im selben Stil.
        info_rahmen = QFrame()
        info_rahmen.setFrameShape(QFrame.Shape.StyledPanel)
        info_lay = QVBoxLayout(info_rahmen)
        info_lay.setSpacing(2)
        info_lay.addWidget(QLabel(f"<b>{_('dlg.sprachdatei.intro_titel')}</b>"))
        intro_label = QLabel(_("dlg.sprachdatei.intro"))
        intro_label.setWordWrap(True)
        info_lay.addWidget(intro_label)

        rechte_spalte = QVBoxLayout()
        rechte_spalte.addWidget(legende)
        rechte_spalte.addWidget(info_rahmen)

        kopf_zeile = QHBoxLayout()
        kopf_zeile.addLayout(links_spalte, 1)
        kopf_zeile.addLayout(rechte_spalte, 0)
        lay.addLayout(kopf_zeile)

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
        """Zeigt in der Formularzeile „KI-Modell" das für die Übersetzung verwendete
        Modell (LLM 1; nach „/“ das LLM 2 für die Rückübersetzung, falls abweichend). Das
        Modell hängt nur an der KI-Anbindung der Firma, nicht an der Zielsprache — daher
        einmalig beim Aufbau gesetzt. Bei fehlender DB/Firma bleibt das Feld leer
        (robust)."""
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
        self._llm_label.setText(modell)

    # ── Sprachbeherrschungs-Prüfung ───────────────────────────────────
    def _ensure_beherrschung(self, label, firma) -> bool:
        """Prüft (mit Session-Cache je Ziel-Label), wie gut LLM 1/LLM 2 die Zielsprache
        `label` beherrschen, zeigt das Ergebnis hinter dem Modell an und setzt den
        Gate-Status (`_beherrschung_ok`). Liefert True, wenn die Übersetzung erlaubt ist
        (alle Noten ≤ Schwelle). Ohne Ziel/aktive KI keine Sperre (True, Anzeige leer)."""
        label = (label or "").strip()
        if not label or not firma.get("ki_aktiv"):
            self._beherrschung_label.setText("")
            self._beherrschung_ok = True
            self._apply_beherrschung_gate()
            return True
        res = self._beherrschung_cache.get(label)
        if res is None:
            self._fortschritt.setText(_("dlg.sprachdatei.beherrschung_pruefe", sprache=label))
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            QApplication.processEvents()
            try:
                res = uebersetzung.pruefe_sprachbeherrschung(firma, label)
            except Exception as ex:                              # noqa: BLE001
                res = {"fehler": str(ex), "ok": False}
            finally:
                QApplication.restoreOverrideCursor()
                self._fortschritt.setText("")
            self._beherrschung_cache[label] = res
        self._zeige_beherrschung(res)
        self._beherrschung_ok = bool(res.get("ok"))
        self._apply_beherrschung_gate()
        return self._beherrschung_ok

    def _zeige_beherrschung(self, res):
        """Schreibt das Prüfergebnis hinter das Modell: Note(n) bzw. Fehlertext; rot bei
        Ablehnung (> Schwelle / unklar / Fehler), sonst dezent."""
        if res.get("fehler"):
            self._beherrschung_label.setText(_("dlg.sprachdatei.beherrschung_fehler"))
            self._beherrschung_label.setStyleSheet(f"color: {theme.color('error_fg')};")
            self._beherrschung_label.setToolTip(res["fehler"])
            return
        def _teil(eintrag):
            return "?" if (eintrag is None or eintrag[1] is None) else str(eintrag[1])
        noten = _teil(res.get("llm1"))
        if res.get("llm2"):
            noten = f"{noten} / {_teil(res['llm2'])}"
        self._beherrschung_label.setText(_("dlg.sprachdatei.beherrschung", wert=noten))
        farbe = theme.color("rating_sehr_gut") if res.get("ok") else theme.color("error_fg")
        self._beherrschung_label.setStyleSheet(f"color: {farbe};")
        # Tooltip mit den Roh-Antworten je Modell.
        teile = []
        for eintrag in (res.get("llm1"), res.get("llm2")):
            if eintrag:
                teile.append(f"{eintrag[0]}: {eintrag[2]}")
        self._beherrschung_label.setToolTip("\n".join(teile) or _("dlg.sprachdatei.beherrschung_tt"))

    def _apply_beherrschung_gate(self):
        """Sperrt/entsperrt die übersetzungsauslösenden Buttons gemäß `_beherrschung_ok`.
        Während eines Laufs nicht eingreifen (dort regelt `_set_running` die Buttons)."""
        if self._lauf_aktiv:
            return
        erlaubt = self._beherrschung_ok
        for b in (self._run_btn, self._fehlende_btn, self._aehnl_btn,
                  self._schlecht_btn, self._gut_btn):
            b.setEnabled(erlaubt)

    def _beherrschung_gate(self, firma) -> bool:
        """Harte Sperre vor einem Übersetzungsvorgang: prüft die aktuelle Zielsprache und
        zeigt bei Ablehnung eine Meldung. Liefert True, wenn fortgefahren werden darf."""
        label = (self._name_edit.text() or "").strip()
        if self._ensure_beherrschung(label, firma):
            return True
        QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                _("dlg.sprachdatei.beherrschung_abgelehnt",
                                  sprache=label,
                                  schwelle=uebersetzung.SPRACHBEHERRSCHUNG_SCHWELLE))
        return False

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
        # Nach Auswahl einer echten Zielsprache die Sprachbeherrschung prüfen (Anzeige
        # hinter dem Modell + Button-Sperre bei Note > Schwelle). „Neu"/leer überspringt.
        try:
            firma_row = self.db.get_firma() if self.db else None
        except Exception:                                       # noqa: BLE001
            firma_row = None
        self._ensure_beherrschung(ziel_label if code else "",
                                  dict(firma_row) if firma_row else {})

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
        """Zeigt in der Hinweiszeile »nachzupflegende / gesamt« für `code`:
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
                          begruendung=rev.get("begruendung", ""),
                          korrektur=rev.get("korrektur", ""))
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
        """Lädt **alle** nicht ausgeschlossenen Items der Sprache ohne KI in die Tabelle —
        übersetzte (auch stimmige und bestätigte) UND noch fehlende (leere, rote Zeile).
        Unstimmige, veraltete (Quelltext geändert) oder fehlende Zeilen werden rot
        dargestellt; bestätigte behalten ihr gesetztes Häkchen."""
        main = lang_tools.load_main()
        ts_map = lang_tools.main_ts(main)
        extra = lang_tools.ohne_meta(lang_tools.load_extra(code))
        review = lang_tools.load_review(code)
        for key in sorted(self._bestimme_keys(main, extra, review, True)):
            ueb = extra.get(key) or ""
            rev = review.get(key) or {}
            rueck = rev.get("rueck") or ""
            ok = bool(rev.get("ok"))
            orig = self._quellwerte.get(key, key)
            # Erledigte (ok) Items nach einem Quellwechsel nicht fälschlich rot färben —
            # ihre Rückübersetzung wurde gegen ihre eigene Quelle geprüft. Veraltung und
            # fehlende Übersetzung bleiben rot (Nachpflege nötig).
            unstimmig = (not ueb) or lang_tools.ist_veraltet(ts_map, key, rev) or (
                not ok and bool(rueck) and self._unstimmig(orig, rueck))
            self._set_row(key, orig, ueb, rueck, unstimmig=unstimmig, ok=ok,
                          src_ts=rev.get(lang_tools.REVIEW_SRC_TS, ""),
                          bewertung=rev.get("bewertung"),
                          begruendung=rev.get("begruendung", ""),
                          korrektur=rev.get("korrektur", ""))
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
                 begruendung="", korrektur=""):
        """Aktualisiert die Zeile zu `key` (falls vorhanden) oder hängt sie neu an;
        unstimmige Zeilen werden rot dargestellt und erhalten ein aktivierbares
        Bestätigungs-Häkchen. Items werden immer frisch gesetzt, damit ein Wechsel
        unstimmig→stimmig Farbe und Häkchen sauber zurücknimmt. `src_ts` (Quell-Stand,
        gegen den übersetzt wurde) wird in der Schlüsselzelle hinterlegt und beim
        Speichern wieder ausgelesen. `bewertung` (identisch/sehr_gut/gut/schlecht) setzt
        hinter dem Häkchen einen farbigen Stern; `begruendung` erscheint als dessen Tooltip;
        `korrektur` (vom LLM vorgeschlagene, noch nicht übernommene Verbesserung) wird in der
        Bewertungs-Anzeige mit gezeigt. Alle werden in der COL_OK-Zelle hinterlegt."""
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
        # Zeilenfarbe: unstimmig → rot; sonst „identisch" (höchste KI-Stufe) → grün;
        # alle übrigen (inkl. „sehr gut" und reine Round-Trip-Treffer) → Standard (schwarz).
        if unstimmig:
            fg = QColor(theme.color("error_fg"))
        elif bewertung == "identisch":
            fg = QColor(theme.color("rating_sehr_gut"))
        else:
            fg = None
        # Erste Spalte: laufende Nummer (Zeilenindex + 1), zentriert, nicht eingefärbt.
        nr_item = QTableWidgetItem(str(row + 1))
        nr_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        nr_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, COL_NR, nr_item)
        # Zielsprache kann ein Schriftsystem nutzen, das Windows-Schriften nicht abdecken
        # (z. B. Khmer) → passende mitgelieferte Noto-Schrift lazy registrieren, bevor das
        # Item gezeichnet wird. Qt fällt danach automatisch auf sie zurück.
        fonts.ensure_for_text(ueb)
        for col, text in ((COL_KEY, key), (COL_ORIG, orig),
                          (COL_UEB, ueb), (COL_RUECK, rueck)):
            item = QTableWidgetItem(text)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            if fg is not None:
                item.setForeground(fg)
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
        ok_item.setData(Qt.ItemDataRole.UserRole + 3, korrektur or "")
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
                # Liegt ein (noch nicht übernommener) Verbesserungsvorschlag vor, mit anzeigen.
                if korrektur:
                    roh = f"{roh}\n\n{_('dlg.sprachdatei.bewertung_korrektur')}\n{korrektur}"
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
        # Liegt bereits eine Bewertung vor, zusätzlich „Neue Bewertung": bewertet die
        # vorhandene Übersetzung erneut (ohne sie neu zu übersetzen).
        if bewertung in _BEWERTUNG_FARBE:
            fb_btn = QPushButton(_("dlg.sprachdatei.btn_neu_bewertung"))
            fb_btn.setToolTip(_("dlg.sprachdatei.btn_neu_bewertung_tt"))
            fb_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            fb_btn.clicked.connect(
                lambda _checked=False, k=key: self._bewerte_row(k))
            h.addWidget(fb_btn)
            # Bewertung ansehen: Stufe + Begründung in einem Hinweis-Dialog. Nötig, weil der
            # Stern-Tooltip der Bestätigt-Spalte nur bei unstimmigen Zeilen erscheint — eine
            # stimmige „sehr gut"-Zeile hätte sonst keine sichtbare Begründung.
            ans_btn = QPushButton(_("dlg.sprachdatei.btn_bewertung"))
            ans_btn.setToolTip(_("dlg.sprachdatei.btn_bewertung_tt"))
            ans_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            ans_btn.clicked.connect(
                lambda _checked=False, b=bewertung, g=begruendung, k=korrektur:
                self._zeige_bewertung(b, g, k))
            h.addWidget(ans_btn)
        h.addStretch()
        self._table.setCellWidget(row, COL_AKTION, cont)
        self._table.resizeRowToContents(row)        # Höhe an umgebrochenen Text anpassen

    @staticmethod
    def _bewertung_kopf_html(bewertung):
        """HTML-Kopfzeile »★ Stufe« (Stern in der Ampelfarbe der Stufe) für Bewertungs-
        Anzeigen; ohne bekannte Stufe nur der Stufentext fett."""
        stufe_txt = _(f"dlg.sprachdatei.bewertung_{bewertung}")
        farbe = theme.color(_BEWERTUNG_FARBE[bewertung]) if bewertung in _BEWERTUNG_FARBE else None
        return (f"<b><span style='color:{farbe}'>★</span> {html.escape(stufe_txt)}</b>"
                if farbe else f"<b>{html.escape(stufe_txt)}</b>")

    def _zeige_bewertung(self, bewertung, begruendung, korrektur=""):
        """Zeigt Stufe, Begründung und – falls vorhanden – den (noch nicht übernommenen)
        Verbesserungsvorschlag der KI-Bewertung dieser Zeile in einem Hinweis-Dialog
        (Aktion-Spalte → „Bewertung"). Die Stufe wird mit dem Ampel-Stern eingefärbt; fehlt
        eine Begründung, erscheint ein entsprechender Hinweis."""
        kopf = self._bewertung_kopf_html(bewertung)
        info = begruendung or _("dlg.sprachdatei.bewertung_keine_begruendung")
        if korrektur:
            info = (f"{info}<br><br><b>{html.escape(_('dlg.sprachdatei.bewertung_korrektur'))}</b>"
                    f"<br>{html.escape(korrektur)}")
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(_("dlg.sprachdatei.bewertung_titel"))
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(kopf)
        box.setInformativeText(info)
        box.exec()
        box.deleteLater()

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
                continue
            if not lang_tools.marker_stimmig(self._quellwerte.get(key, ""), ueb):
                out.append(key)                     # erledigt, aber {…}-Platzhalter kaputt
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
        if not self._beherrschung_gate(firma):
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

        frage = _("dlg.sprachdatei.confirm", n=len(keys),
                  quelle=self._quelllabel, sprache=label)
        antwort = QMessageBox.question(self, _("dlg.sprachdatei.titel"), frage)
        if antwort != QMessageBox.StandardButton.Yes:
            return

        # Der Lauf führt jetzt selbst die drei Phasen aus (Vorwärts, Rückübersetzung und
        # zum Abschluss die sinngemäße Prüfung + Neuübersetzung); kein separater Anschluss
        # mehr nötig.
        self._lauf(firma, label, keys, lang_tools.main_ts(main))

    def _lauf(self, firma, label, keys, ts_map):
        """Führt den Lauf **batchweise vollständig** aus: jeder Batch durchläuft erst die
        Vorwärts-Übersetzung (LLM 1), dann die Rückübersetzung (LLM 2), dann die sinngemäße
        Prüfung seiner auffälligen Zeilen (LLM-Bewertung) — bei „gut"/„schlecht" mit
        **einer** Neuübersetzung mit Bewertung (+ frischer Rückübersetzung), die als
        Ergebnis stehen bleibt. Erst danach folgt der nächste Batch. **Nach jeder Phase
        bzw. Zeile wird gespeichert** (`_persist_still`), sodass ein Abbruch/Absturz alle
        fertigen Batches vollständig erledigt zurücklässt. Bricht beim ersten KI-Fehler
        oder per „Abbrechen" (zwischen Batches/Phasen/Zeilen) ab; gesicherte Zeilen bleiben
        erhalten. (Frühere „Durchläufe"-Wiederholung entfernt — ein Durchlauf hat in der
        Praxis immer gereicht; offen gebliebene Zeilen lassen sich über „Nur fehlende
        übersetzen"/„Sinngemäße Übereinstimmung prüfen" gezielt nachbearbeiten.)"""
        self._table.setRowCount(0)
        self._row_index = {}
        self._update_headers(label)
        uebersetzung.reset_test_protokoll()        # neuer Lauf → Protokoll-Dialoge wieder zeigen
        self._abbruch = False
        self._set_running(True)
        batch_size = self._batch_spin.value()
        # Aufgaben → LLM-Zuordnung der Firma (App-Übersetzung) einmal auflösen.
        llm_ueb = uebersetzung.llm_nr_fuer_task(firma, uebersetzung.TASK_UEBERSETZUNG, 1)
        llm_rueck = uebersetzung.llm_nr_fuer_task(firma, uebersetzung.TASK_RUECK, 2)
        llm_bew = uebersetzung.llm_nr_fuer_task(firma, uebersetzung.TASK_BEWERTUNG, 1)
        n = len(keys)
        abgebrochen = False

        def _quell(key):
            return self._quellwerte.get(key, key)

        try:
            for start in range(0, n, batch_size):
                if self._abbruch:
                    abgebrochen = True
                    break
                batch_keys = keys[start:start + batch_size]
                ende = start + len(batch_keys)
                werte = {k: _quell(k) for k in batch_keys}

                # Phase 1: Vorwärts-Übersetzung dieses Batches (ein LLM-Batch-Aufruf; bei
                # unsicherer Antwort Wiederholung/Einzel-Fallback in
                # uebersetze_werte_batch).
                ueb_map = uebersetzung.uebersetze_werte_batch(
                    firma, self._quelllabel, label, werte, kontext=_KONTEXT,
                    batch_size=len(werte), rueck=False, llm_nr=llm_ueb)
                for key in batch_keys:
                    self._set_row(key, _quell(key), ueb_map.get(key, ""), "",
                                  unstimmig=False, ok=False, src_ts=ts_map.get(key, ""))
                self._fortschritt.setText(self._phase_fortschritt(
                    _("dlg.sprachdatei.phase_vor"), ende, n))
                self._table.scrollToBottom()
                QApplication.processEvents()
                self._persist_still()
                if self._abbruch:
                    abgebrochen = True
                    break

                # Phase 2: Rückübersetzung dieses Batches; markiert die Unstimmigkeiten,
                # die anschließend die sinngemäße Prüfung durchlaufen.
                rueck_map = uebersetzung.uebersetze_werte_batch(
                    firma, label, self._quelllabel, ueb_map, kontext=_KONTEXT,
                    batch_size=len(ueb_map), rueck=True, llm_nr=llm_rueck)
                auffaellig = []
                for key in batch_keys:
                    orig, ueb, rueck = _quell(key), ueb_map.get(key, ""), rueck_map.get(key, "")
                    ist = self._unstimmig(orig, rueck)
                    self._set_row(key, orig, ueb, rueck, unstimmig=ist, ok=(not ist),
                                  src_ts=ts_map.get(key, ""))
                    if ist:
                        auffaellig.append(key)
                self._fortschritt.setText(self._phase_fortschritt(
                    _("dlg.sprachdatei.phase_rueck"), ende, n))
                QApplication.processEvents()
                self._persist_still()
                if self._abbruch:
                    abgebrochen = True
                    break

                # Phase 3: Sinngemäße Prüfung der auffälligen Zeilen dieses Batches. Der
                # Bewertungs-Aufruf liefert bei „gut"/„schlecht" gleich eine verbesserte
                # Übersetzung mit (ein Aufruf statt Bewertung + Neuübersetzung); **liegt
                # ein Verbesserungsvorschlag vor, wird er übernommen** (mit frischer
                # Rückübersetzung). Liefert die KI bei bereits „sehr gut" bewerteter
                # Übersetzung einen Grammatik-/Stil-Vorschlag, wird dieser NICHT
                # automatisch übernommen — die Bedeutung stimmt schon, daher wird die
                # Zeile im KI-Korrektur-Dialog zur Bestätigung geöffnet
                # (`_frage_verbesserung`). Meldet der Prompt einen Grammatikfehler im
                # Ausgangstext (GRAMMATIK_QUELLE, erweiterter Prompt wie Firma 990),
                # ebenso über `_frage_grammatik_quelle`; bei Übernahme ändert sich der
                # Quelltext in `language.json`.
                for key in auffaellig:
                    if self._abbruch:
                        abgebrochen = True
                        break
                    orig, ueb, rueck = _quell(key), ueb_map.get(key, ""), rueck_map.get(key, "")
                    bewertung, begruendung, korrektur, grammatik, grammatik_korrektur = \
                        uebersetzung.bewerte_und_korrigiere(
                            firma, self._quelllabel, label, orig, ueb, kontext=_KONTEXT,
                            llm_nr=llm_bew)
                    quelle_geaendert = False
                    if grammatik == "quelle" and grammatik_korrektur and not self._abbruch:
                        neuer_quelltext, neuer_src_ts = self._frage_grammatik_quelle(
                            key, orig, grammatik_korrektur, bewertung=bewertung,
                            begruendung=begruendung or "")
                        if neuer_quelltext:
                            orig, quelle_geaendert = neuer_quelltext, True
                            ts_map[key] = neuer_src_ts
                    if korrektur and bewertung in ("gut", "schlecht") and not self._abbruch:
                        ueb = korrektur
                        rueck = uebersetzung.uebersetze_rueck(
                            firma, label, self._quelllabel, ueb, kontext=_KONTEXT,
                            llm_nr=llm_rueck)
                    elif korrektur and bewertung == "sehr_gut" and not self._abbruch:
                        uebernommen = self._frage_verbesserung(
                            ueb, korrektur, bewertung=bewertung, begruendung=begruendung or "")
                        if uebernommen:
                            ueb = uebernommen
                            rueck = uebersetzung.uebersetze_rueck(
                                firma, label, self._quelllabel, ueb, kontext=_KONTEXT,
                                llm_nr=llm_rueck)
                    ok = (not quelle_geaendert) and (bewertung in uebersetzung.BEWERTUNG_OK)
                    self._set_row(key, orig, ueb, rueck, unstimmig=(not ok), ok=ok,
                                  src_ts=ts_map.get(key, ""), bewertung=bewertung,
                                  begruendung=begruendung or "")
                    self._fortschritt.setText(self._phase_fortschritt(
                        _("dlg.sprachdatei.phase_pruefung"), ende, n))
                    QApplication.processEvents()
                    self._persist_still()
                if self._abbruch:
                    abgebrochen = True
                    break
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

    def _phase_fortschritt(self, phase_label, i, n):
        """Fortschrittstext einer Lauf-Phase: »<Phase>: i/n«."""
        return f"{phase_label}: {_('dlg.sprachdatei.lauf_fortschritt', i=i, n=n)}"

    def _set_running(self, running: bool):
        """UI während des Laufs sperren (nur „Abbrechen" bleibt aktiv)."""
        self._lauf_aktiv = running
        self._cancel_btn.setVisible(running)
        for w in (self._run_btn, self._fehlende_btn, self._aehnl_btn, self._close_btn,
                  self._schlecht_btn, self._gut_btn,
                  self._combo, self._quelle_combo, self._code_edit, self._name_edit,
                  self._alle_cb, self._batch_spin,
                  self._alle_anzeigen_cb):
            w.setEnabled(not running)
        if running:
            self._save_btn.setEnabled(False)
        else:
            # Nach dem Lauf die Übersetzungs-Buttons gemäß Sprachbeherrschung sperren.
            self._apply_beherrschung_gate()

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
        if not self._beherrschung_gate(firma):
            return
        orig = self._quellwerte.get(key, key)
        ts_map = lang_tools.main_ts(lang_tools.load_main())
        uebersetzung.reset_test_protokoll()        # Einzel-Neuübersetzung → Protokoll wieder zeigen
        ctx = uebersetzung.baue_ctx(
            firma, self._quelllabel, label, kontext=_KONTEXT, kein_split=True,
            llm_nr=uebersetzung.llm_nr_fuer_task(firma, uebersetzung.TASK_UEBERSETZUNG, 1))
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            ueb = uebersetzung.uebersetze_einen(ctx, orig)
            rueck = uebersetzung.uebersetze_rueck(
                firma, label, self._quelllabel, ueb, kontext=_KONTEXT,
                llm_nr=uebersetzung.llm_nr_fuer_task(firma, uebersetzung.TASK_RUECK, 2))
            # Bei unstimmiger Neuübersetzung gleich im Anschluss die KI-Bewertung
            # (sinngemäße Übereinstimmung) ausführen — wie ein Klick auf „Ähnlichkeit prüfen"
            # für genau diese Zeile. Stimmige Zeilen sind bereits bestätigt (kein Bedarf).
            ist_unstimmig = self._unstimmig(orig, rueck)
            bewertung = begruendung = None
            if ist_unstimmig:
                bewertung, begruendung = uebersetzung.bewerte_aehnlichkeit(
                    firma, self._quelllabel, label, orig, ueb, kontext=_KONTEXT,
                    llm_nr=uebersetzung.llm_nr_fuer_task(firma, uebersetzung.TASK_BEWERTUNG, 1))
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
        ok = (not ist_unstimmig) or (bewertung in uebersetzung.BEWERTUNG_OK)
        self._set_row(key, orig, ueb, rueck, unstimmig=ist_unstimmig, ok=ok,
                      src_ts=ts_map.get(key, ""), bewertung=bewertung,
                      begruendung=begruendung or "")
        self._save_btn.setEnabled(True)

    @staticmethod
    def _bewertung_rang(stufe) -> int:
        """Vergleichsrang einer Bewertungsstufe (höher = besser); unbekannt/None = -1."""
        return {"schlecht": 0, "gut": 1, "sehr_gut": 2, "identisch": 3}.get(stufe, -1)

    def _frage_verbesserung(self, aktuell, vorschlag, bewertung=None, begruendung=""):
        """Zeigt einen bei bereits „sehr gut" bewerteter Übersetzung gelieferten Grammatik-/
        Stil-Verbesserungsvorschlag (``##BESSER:``) im KI-Korrektur-Dialog an und lässt ihn
        bestätigen (ggf. angepasst) oder verwerfen. Anders als bei „gut"/„schlecht" — dort
        stimmt die Bedeutung bereits, daher **keine automatische Übernahme**. Zeigt zusätzlich
        die zugehörige Bewertungsstufe (Ampel-Stern) + Begründung, damit der Vorschlag nicht
        ohne Kontext erscheint. Liefert den bestätigten Text oder `""` bei Abbruch/Verwerfen."""
        from modul.mod_artikel import KiKorrekturDialog
        hinweis = self._bewertung_kopf_html(bewertung)
        if begruendung:
            hinweis += f"<br>{html.escape(begruendung)}"
        dlg = KiKorrekturDialog(self, aktuell, vorschlag, hinweis_html=hinweis)
        dlg.setWindowTitle(_("dlg.sprachdatei.verbesserung_titel"))
        if dlg.exec():
            neu = (dlg.korrigierter_text() or "").strip()
            if neu and neu != aktuell.strip():
                return neu
        return ""

    def _frage_grammatik_quelle(self, key, aktuell, vorschlag, bewertung=None, begruendung=""):
        """Zeigt einen von der KI gemeldeten Grammatikfehler im **Ausgangstext**
        (Quellsprache, ``GRAMMATIK_QUELLE``) im KI-Korrektur-Dialog an und lässt die
        Korrektur bestätigen (ggf. angepasst) oder verwerfen. Zeigt zusätzlich die im
        selben Bewertungs-Aufruf ermittelte Genauigkeits-Stufe (Ampel-Stern) + Begründung,
        damit der Grammatik-Vorschlag nicht ohne Kontext erscheint. Bei Bestätigung wird der
        Quelltext in `language.json` (Basis-Sprachdatei) sofort aktualisiert; die
        aufrufende Stelle markiert die Zeile danach als unstimmig (die Übersetzung passt
        ggf. nicht mehr zum neuen Quelltext). Liefert `(neuer_quelltext, neuer_src_ts)`
        oder `("", "")` bei Abbruch/Verwerfen."""
        from modul.mod_artikel import KiKorrekturDialog
        hinweis = self._bewertung_kopf_html(bewertung)
        if begruendung:
            hinweis += f"<br>{html.escape(begruendung)}"
        dlg = KiKorrekturDialog(self, aktuell, vorschlag, hinweis_html=hinweis)
        dlg.setWindowTitle(_("dlg.sprachdatei.grammatik_titel"))
        if not dlg.exec():
            return "", ""
        neu = (dlg.korrigierter_text() or "").strip()
        if not neu or neu == aktuell.strip():
            return "", ""
        main = lang_tools.load_main()
        item = main.get(key)
        if not isinstance(item, dict):
            return "", ""
        item[self._quellcode] = neu
        lang_tools.stamp_main(main)
        lang_tools.schreibe_main(main)
        self._quellwerte[key] = neu
        return neu, lang_tools.main_ts(main).get(key, "")

    def _retry_zeile(self, firma, label, orig, best_ueb, start_kandidat, best_bew, best_begr):
        """Verbessert eine bereits als »schlecht« bewertete Zeile iterativ (bis zu
        `_MAX_RETRY` Bewertungs-/Korrektur-Aufrufe): bewertet den jeweils aktuellen
        Korrektur-Kandidaten und erhält im **selben** Aufruf den nächsten
        Verbesserungsvorschlag (`bewerte_und_korrigiere`). Über alle Versuche wird das
        bestbewertete Ergebnis behalten (Rang identisch > sehr_gut > gut > schlecht); **bei
        Gleichstand wird der neuere Verbesserungsvorschlag übernommen**, damit eine vom LLM
        gelieferte Korrektur auch ohne Rang-Verbesserung sichtbar greift (nur eine echte
        Verschlechterung des Rangs wird verworfen). Die Rückübersetzung wird **nur einmal am Ende** für das beste Ergebnis
        berechnet (sie fließt nicht in die Entscheidung, dient nur der Anzeige). `best_*` ist
        das bisher beste Ergebnis (i. d. R. die vorhandene Übersetzung), `start_kandidat` der
        erste zu bewertende Verbesserungsvorschlag. Liefert
        `(ueb, rueck, bewertung, begruendung)`. KI-Fehler propagieren an den Aufrufer."""
        llm_rueck = uebersetzung.llm_nr_fuer_task(firma, uebersetzung.TASK_RUECK, 2)
        llm_bew = uebersetzung.llm_nr_fuer_task(firma, uebersetzung.TASK_BEWERTUNG, 1)
        kandidat = start_kandidat
        for _versuch in range(_MAX_RETRY):
            if best_bew in uebersetzung.BEWERTUNG_OK or self._abbruch or not kandidat:
                break
            stufe, begr, korrektur, _grammatik, _grammatik_korrektur = uebersetzung.bewerte_und_korrigiere(
                firma, self._quelllabel, label, orig, kandidat, kontext=_KONTEXT,
                llm_nr=llm_bew)
            if self._bewertung_rang(stufe) >= self._bewertung_rang(best_bew):
                best_ueb, best_bew, best_begr = kandidat, stufe, begr
            if stufe in uebersetzung.BEWERTUNG_OK:
                break
            kandidat = korrektur
        best_rueck = uebersetzung.uebersetze_rueck(
            firma, label, self._quelllabel, best_ueb, kontext=_KONTEXT, llm_nr=llm_rueck)
        return best_ueb, best_rueck, best_bew, best_begr

    def _bewerte_row(self, key):
        """Zeilen-Button „Neue Bewertung": bewertet die **vorhandene** Übersetzung dieser
        Zeile erneut (KI-Bewertung), ohne sie neu zu übersetzen. Übersetzung und
        Rückübersetzung bleiben unverändert; Bewertungsstufe und -begründung werden
        aktualisiert. Liefert das LLM dabei einen Verbesserungsvorschlag, wird dieser
        **nicht automatisch übernommen**, sondern gespeichert und in der Bewertungs-Anzeige
        (Button „Bewertung" / Stern-Tooltip) mit gezeigt. Während eines Stapellaufs gesperrt;
        bei KI-Fehler bleibt die bisherige Zeile erhalten."""
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
        if not self._beherrschung_gate(firma):
            return
        row = self._row_index.get(key)
        if row is None:
            return
        orig = self._quellwerte.get(key, key)
        ueb = self._table.item(row, COL_UEB).text()
        rueck = self._table.item(row, COL_RUECK).text()
        src_ts = self._table.item(row, COL_KEY).data(Qt.ItemDataRole.UserRole) or ""
        uebersetzung.reset_test_protokoll()        # Einzel-Bewertung → Protokoll wieder zeigen
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            bewertung, begruendung, korrektur, _grammatik, _grammatik_korrektur = \
                uebersetzung.bewerte_und_korrigiere(
                    firma, self._quelllabel, label, orig, ueb, kontext=_KONTEXT,
                    llm_nr=uebersetzung.llm_nr_fuer_task(firma, uebersetzung.TASK_BEWERTUNG, 1))
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
        # Verbesserungsvorschlag NICHT automatisch übernehmen (reine Neubewertung), nur
        # speichern → er erscheint in der Bewertungs-Anzeige; übernehmen kann der Anwender
        # über „Neu" oder manuelles Bearbeiten.
        self._set_row(key, orig, ueb, rueck, unstimmig=(bewertung not in uebersetzung.BEWERTUNG_OK),
                      ok=(bewertung in uebersetzung.BEWERTUNG_OK), src_ts=src_ts,
                      bewertung=bewertung, begruendung=begruendung or "", korrektur=korrektur or "")
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
        if not self._beherrschung_gate(firma):
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
            ctx_zweite = uebersetzung.baue_ctx(
                firma, self._quelllabel, zweite_label, kontext=_KONTEXT, kein_split=True,
                llm_nr=uebersetzung.llm_nr_fuer_task(firma, uebersetzung.TASK_UEBERSETZUNG, 1))
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
            ctx_ziel = uebersetzung.baue_ctx(
                firma, self._quelllabel, label, kontext=_KONTEXT, kein_split=True,
                llm_nr=uebersetzung.llm_nr_fuer_task(firma, uebersetzung.TASK_UEBERSETZUNG, 1))
            ueb = uebersetzung.uebersetze_einen(ctx_ziel, neu)

            # (4) Rückübersetzung zur Kontrolle.
            dlg.schritt(_("dlg.sprachdatei.fortschritt_rueck"))
            rueck = uebersetzung.uebersetze_rueck(
                firma, label, self._quelllabel, ueb, kontext=_KONTEXT,
                llm_nr=uebersetzung.llm_nr_fuer_task(firma, uebersetzung.TASK_RUECK, 2))

            # (5) Bei Abweichung gleich die KI-Bewertung (sinngemäße Übereinstimmung).
            ist_unstimmig = self._unstimmig(neu, rueck)
            bewertung = begruendung = None
            if ist_unstimmig:
                dlg.schritt(_("dlg.sprachdatei.fortschritt_bewerten"))
                bewertung, begruendung = uebersetzung.bewerte_aehnlichkeit(
                    firma, self._quelllabel, label, neu, ueb, kontext=_KONTEXT,
                    llm_nr=uebersetzung.llm_nr_fuer_task(firma, uebersetzung.TASK_BEWERTUNG, 1))
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
        ok = (not ist_unstimmig) or (bewertung in uebersetzung.BEWERTUNG_OK)
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
        # Manuell (nicht im Auto-Anschluss an einen Lauf, der das Gate schon passiert
        # hat): Sprachbeherrschung prüfen und bei Ablehnung abbrechen.
        if not auto and not self._beherrschung_gate(firma):
            return
        zeilen = self._offene_rote_zeilen()
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

        def _fort(i, n):
            self._fortschritt.setText(
                _("dlg.sprachdatei.aehnlichkeit_fortschritt", i=i, n=n))

        def _retry(i, n):
            self._fortschritt.setText(
                _("dlg.sprachdatei.retry_fortschritt", i=i, n=n))
            QApplication.processEvents()

        try:
            self._phase3_kern(firma, label, zeilen, _fort, _retry)
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

    def _offene_rote_zeilen(self):
        """Sammelt die noch **offenen, unstimmigen** Zeilen (nicht gesetzte Bestätigt-
        Checkbox in COL_OK, nicht-leere Übersetzung) als Tupel
        `(key, orig, ueb, rueck, src_ts)` — Grundlage der sinngemäßen Prüfung (Phase 3)."""
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
        return zeilen

    def _phase3_kern(self, firma, label, zeilen, fortschritt, retry_hinweis):
        """Phase 3 — sinngemäße Prüfung + gezielte Verbesserung. Bewertet je Zeile per LLM
        die Übereinstimmung und erhält bei „gut"/„schlecht" im selben Aufruf gleich eine
        Verbesserung (`bewerte_und_korrigiere`); **liegt ein Verbesserungsvorschlag vor,
        wird er übernommen** und über `_retry_zeile` iterativ weiterverbessert (bestes
        Ergebnis behalten). Liefert die KI bei bereits „sehr gut" bewerteter Übersetzung
        einen Grammatik-/Stil-Vorschlag, wird dieser **nicht automatisch übernommen** —
        die Zeile wird stattdessen im KI-Korrektur-Dialog zur Bestätigung geöffnet
        (`_frage_verbesserung`), da die Bedeutung bereits stimmt. Meldet der Prompt
        zusätzlich einen Grammatikfehler im **Ausgangstext** (``GRAMMATIK_QUELLE``,
        erweiterter Prompt wie Firma 990), wird auch dafür ein Bestätigungsdialog
        geöffnet (`_frage_grammatik_quelle`); bei Übernahme ändert sich der Quelltext in
        `language.json`, die Zeile gilt danach als unstimmig. **Nach jeder Zeile wird
        persistiert** (abbruchsicher). Respektiert `self._abbruch` (Stopp zwischen
        Zeilen); KI-Fehler propagieren an den Aufrufer. `fortschritt(i, n)` nach jeder
        Zeile, `retry_hinweis(i, n)` vor einer automatischen Verbesserung."""
        n = len(zeilen)
        for i, (key, orig, ueb, rueck, src_ts) in enumerate(zeilen, start=1):
            if self._abbruch:
                break
            bewertung, begruendung, korrektur, grammatik, grammatik_korrektur = \
                uebersetzung.bewerte_und_korrigiere(
                    firma, self._quelllabel, label, orig, ueb, kontext=_KONTEXT,
                    llm_nr=uebersetzung.llm_nr_fuer_task(firma, uebersetzung.TASK_BEWERTUNG, 1))
            quelle_geaendert = False
            if grammatik == "quelle" and grammatik_korrektur and not self._abbruch:
                neuer_quelltext, neuer_src_ts = self._frage_grammatik_quelle(
                    key, orig, grammatik_korrektur, bewertung=bewertung,
                    begruendung=begruendung or "")
                if neuer_quelltext:
                    orig, src_ts, quelle_geaendert = neuer_quelltext, neuer_src_ts, True
            # Sobald das LLM einen Verbesserungsvorschlag liefert (gut/schlecht), wird er
            # übernommen und iterativ weiterverbessert (die erste Korrektur kam bereits aus
            # dem Bewertungs-Aufruf). Bei identisch ist korrektur leer → keine Änderung.
            if korrektur and bewertung in ("gut", "schlecht") and not self._abbruch:
                retry_hinweis(i, n)
                ueb, rueck, bewertung, begruendung = self._retry_zeile(
                    firma, label, orig, ueb, korrektur, bewertung, begruendung)
            elif korrektur and bewertung == "sehr_gut" and not self._abbruch:
                uebernommen = self._frage_verbesserung(
                    ueb, korrektur, bewertung=bewertung, begruendung=begruendung or "")
                if uebernommen:
                    ueb = uebernommen
                    rueck = uebersetzung.uebersetze_rueck(
                        firma, label, self._quelllabel, ueb, kontext=_KONTEXT,
                        llm_nr=uebersetzung.llm_nr_fuer_task(firma, uebersetzung.TASK_RUECK, 2))
            # Bei geänderter Quelle gilt die Zeile immer als unstimmig, auch wenn die
            # Übersetzung gegen den ALTEN Quelltext noch als stimmig bewertet wurde.
            unstimmig = quelle_geaendert or bewertung not in uebersetzung.BEWERTUNG_OK
            self._set_row(key, orig, ueb, rueck, unstimmig=unstimmig, ok=(not unstimmig),
                          src_ts=src_ts, bewertung=bewertung, begruendung=begruendung)
            self._persist_still()      # Zeile sofort sichern (abbruchsicher)
            fortschritt(i, n)
            QApplication.processEvents()

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
        if not self._beherrschung_gate(firma):
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
            for i, (key, orig, ueb, _rueck, _bew, _begr, src_ts) in enumerate(zeilen, start=1):
                if self._abbruch:
                    break
                self._fortschritt.setText(
                    _("dlg.sprachdatei.retry_fortschritt", i=i, n=n))
                QApplication.processEvents()
                # Vorhandene Übersetzung frisch bewerten + erste Korrektur holen, dann
                # iterativ weiterverbessern (bestes Ergebnis behalten).
                stufe, begr, korrektur, _grammatik, _grammatik_korrektur = \
                    uebersetzung.bewerte_und_korrigiere(
                        firma, self._quelllabel, label, orig, ueb, kontext=_KONTEXT,
                        llm_nr=uebersetzung.llm_nr_fuer_task(firma, uebersetzung.TASK_BEWERTUNG, 1))
                ueb, rueck, bewertung, begruendung = self._retry_zeile(
                    firma, label, orig, ueb, korrektur, stufe, begr)
                self._set_row(key, orig, ueb, rueck, unstimmig=(bewertung not in uebersetzung.BEWERTUNG_OK),
                              ok=(bewertung in uebersetzung.BEWERTUNG_OK), src_ts=src_ts,
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
    def _persist_still(self):
        """Schreibt den aktuellen Tabellenstand **still** in `language.<code>.json` +
        `.review.json` (ohne Erfolgsmeldung, Reload oder Combo-Neuaufbau). Während eines
        Laufs nach jedem Batch aufgerufen, damit ein Abbruch/Absturz keinen Fortschritt
        mehr verliert. Liefert `(n_ueb, n_ok)`; OSError propagiert an den Aufrufer."""
        code = (self._code_edit.text() or "").strip().lower()
        label = (self._name_edit.text() or "").strip()
        if not code or not label:
            return 0, 0
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
            # Bewertung (Stern) + Begründung (Stern-Tooltip) + Verbesserungsvorschlag
            # zeilengenau persistieren.
            bewertung = (ok_item.data(Qt.ItemDataRole.UserRole + 1) if ok_item else "") or ""
            begruendung = (ok_item.data(Qt.ItemDataRole.UserRole + 2) if ok_item else "") or ""
            korrektur = (ok_item.data(Qt.ItemDataRole.UserRole + 3) if ok_item else "") or ""
            mapping[key] = ueb
            # src_ts (Quell-Stand, gegen den übersetzt wurde) bleibt zeilengenau erhalten:
            # neu übersetzte Zeilen tragen den aktuellen Quell-ts, nur angezeigte Zeilen
            # ihren bisherigen — so wird Veraltetes nicht versehentlich „aktuell" gestempelt.
            src_ts = key_item.data(Qt.ItemDataRole.UserRole) or ""
            review[key] = {"rueck": rueck, "ok": ok, lang_tools.REVIEW_SRC_TS: src_ts,
                           "bewertung": bewertung, "begruendung": begruendung,
                           "korrektur": korrektur}
            n_ueb += 1
            n_ok += 1 if ok else 0
        base = lang_tools.meta_base(extra, self._quellcode)
        lang_tools.schreibe_extra(code, label, base, mapping)
        lang_tools.schreibe_review(code, review)
        # Sprachliste für den Wörterbuch-Installer aktuell halten.
        lang_tools.schreibe_installed_languages()
        return n_ueb, n_ok

    def _save(self):
        code = (self._code_edit.text() or "").strip().lower()
        label = (self._name_edit.text() or "").strip()
        if not code or not label:
            return
        try:
            n_ueb, n_ok = self._persist_still()
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
