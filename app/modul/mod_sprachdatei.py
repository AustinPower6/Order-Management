"""Variante A — In-App-Generator für zusätzliche App-Sprachen.

Admin-Dialog: erzeugt/aktualisiert eine `language.<code>.json` (siehe `lang_tools`),
indem die UI-Texte per KI der aktiven Firma aus der **aktuell eingestellten App-Sprache**
(`i18n.current()`) in die Zielsprache übersetzt werden. Wie im Drucktexte-Reiter wird jede
Übersetzung sofort **zurückübersetzt** (LLM 2) und mit dem Original verglichen; Abweichungen
erscheinen rot in einer fortlaufend gefüllten Tabelle und lassen sich per Häkchen
**bestätigen**. Rückübersetzungen + Bestätigungen werden in einer Begleitdatei
`language.<code>.review.json` festgehalten, sodass beim nächsten Lauf nur die noch offenen
Zeilen erneut übersetzt werden. Deutsch und Englisch bleiben im Hauptfile `language.json`.

Seit dem Refactoring 2026-07 (Schritt 5) liegt die Qt-freie Lauf-Pipeline in
`sprachdatei_lauf.py` (Anbindung über `LaufUmgebung`-Callbacks, siehe `_lauf_umgebung`);
die Hilfsdialoge/-Delegates liegen in `sprachdatei_dialoge.py`. Hier verbleiben der
Dialog-Aufbau, das Laden/Anzeigen der Review-Tabelle und die dünnen Lauf-Wrapper.
"""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QComboBox, QLineEdit,
                             QCheckBox, QLabel, QHBoxLayout, QPushButton, QMessageBox,
                             QTableWidget, QTableWidgetItem, QApplication, QSpinBox,
                             QAbstractSpinBox, QWidget, QFrame)
from PyQt6.QtCore import Qt, QEventLoop
from PyQt6.QtGui import QColor

import html
import threading
import settings
import i18n
import fonts
import lang_tools
import uebersetzung
import theme
import token_log
from i18n import _
from ui_widgets import zeige_fehler, zeige_warnung
from modul.beleg_utils import _apply_saved_columns, _connect_save_columns
from modul import sprachdatei_lauf
from modul.sprachdatei_dialoge import (_TextEditDialog, _AntwortDialog,
                                       _FortschrittDialog, _MarkerHighlightDelegate)

# Neuer Schlüssel seit Einführung der Nummern-Spalte (sonst macht die alte gespeicherte
# 6-Spalten-Breite die erste Spalte überbreit / verschiebt die Spalten).
_COLS_KEY = "sprachdatei_review3"

# Sentinel-Datenwert des Combo-Eintrags „Alle Sprachen" (Massenaktualisierung). Kein gültiger
# Sprachcode, damit er nicht mit einer echten Zusatzsprache verwechselt wird.
ALLE_SPRACHEN = "__alle__"

# Spaltenindizes der Review-Tabelle (erste Spalte: laufende Nummer)
COL_NR, COL_KEY, COL_ORIG, COL_UEB, COL_RUECK, COL_OK, COL_AKTION = range(7)

# Bewertungsstufe → Theme-Farbschlüssel für den Stern hinter dem Bestätigt-Häkchen
# (Ampel: identisch/sehr gut = grün, gut = gelb, schlecht = rot; helle Töne in beiden Themes).
_BEWERTUNG_FARBE = {"identisch": "rating_sehr_gut", "sehr_gut": "rating_sehr_gut",
                    "gut": "rating_gut", "schlecht": "rating_schlecht"}
# Tooltip-Breite des Bewertungssterns (~10 cm bei 96 dpi); längere Begründungen brechen um.
_STERN_TOOLTIP_BREITE = 380
# Anzeigedauer des Feld-Tooltips: bewusst sehr lang (10 min), damit der Hint nicht nach einer
# Zeitspanne von selbst schließt, sondern erst beim Verlassen des Feldes verschwindet.
_TOOLTIP_DAUER_MS = 600000


class _LaufAbbruch(Exception):
    """Wird von `_ki_call` geworfen, wenn „Abbrechen" während eines noch laufenden
    KI-Aufrufs geklickt wird (s. `_ki_call`) — der Worker-Thread läuft als Daemon im
    Hintergrund aus, sein Ergebnis wird verworfen."""


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
        self._massen_aktiv = False
        self._abbruch = False
        # Sprachbeherrschungs-Prüfung: Cache je Ziel-Label (Session) + Gate-Status.
        self._beherrschung_cache = {}
        self._beherrschung_ok = True
        self.setWindowTitle(_("dlg.sprachdatei.titel"))
        # Windows-übliche Fensterknöpfe: Minimieren/Maximieren auch für diesen Dialog
        # (QDialog blendet sie standardmäßig aus).
        self.setWindowFlags(self.windowFlags()
                            | Qt.WindowType.WindowMinimizeButtonHint
                            | Qt.WindowType.WindowMaximizeButtonHint)
        self._build()
        # Live-Token-Zähler: Basiswert beim Öffnen des Dialogs einfrieren, damit die
        # Anzeige den Verbrauch **seit Dialogöffnung** zeigt (nicht die gesamte
        # Firmenhistorie aus TOKENS.DB) — wächst live über alle Läufe dieser Sitzung.
        self._token_basis = self._token_summe_gesamt()
        self._token_tick()
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

    # ── Live-Token-Zähler (Rahmen vor der Farberklärung) ───────────────
    def _firma_nr(self) -> str:
        try:
            f = self.db.get_firma() if self.db else None
        except Exception:                                       # noqa: BLE001
            f = None
        return (dict(f).get("firmen_nr") if f else "") or ""

    def _token_summe_gesamt(self) -> dict:
        """Summiert `token_log.summe()` (je Anbieter/Modell/Aufgabe) zu einem
        Gesamtwert der aktiven Firma zusammen — Grundlage für den Live-Zähler."""
        gesamt = {"aufrufe": 0, "eingabe_tokens": 0, "ausgabe_tokens": 0,
                  "cache_lese_tokens": 0, "cache_schreib_tokens": 0}
        for r in token_log.summe(self._firma_nr()):
            for k in gesamt:
                gesamt[k] += r.get(k) or 0
        return gesamt

    def _token_tick(self):
        """Aktualisiert die Live-Token-Anzeige: Differenz zwischen dem aktuellen
        Firmen-Gesamtstand in TOKENS.DB und dem beim Dialogöffnen eingefrorenen
        `_token_basis` — zeigt also den Verbrauch **dieser Dialogsitzung**, über alle
        Läufe hinweg fortlaufend wachsend. Wird nach jedem KI-Aufruf(-Batch) aufgerufen;
        DB-Fehler dürfen die Anzeige nie zum Absturz bringen (still auf „–")."""
        try:
            aktuell = self._token_summe_gesamt()
            basis = self._token_basis or {}
            delta = {k: aktuell.get(k, 0) - basis.get(k, 0) for k in aktuell}
            self._token_label.setText(_(
                "dlg.sprachdatei.token_wert", aufrufe=delta["aufrufe"],
                eingabe=delta["eingabe_tokens"], ausgabe=delta["ausgabe_tokens"],
                cache=delta["cache_lese_tokens"]))
        except Exception:                                        # noqa: BLE001
            self._token_label.setText("–")

    def _ki_call(self, func, *args, **kwargs):
        """Führt einen blockierenden KI-Aufruf aus, ohne die GUI einzufrieren: der Aufruf
        läuft in einem Worker-Thread, währenddessen pumpt der GUI-Thread die
        Ereignisschleife — frisch gesetzte Statuszeilen/Tabellenzeilen/Token-Zähler werden
        also **sofort** gezeichnet statt erst nach Rückkehr des (teils minutenlangen)
        HTTP-Aufrufs. Während eines Stapellaufs (`_lauf_aktiv`, Buttons bereits gesperrt)
        laufen volle Events — „Abbrechen" ist damit auch mitten im Netzwerk-Wait klickbar
        UND wird **sofort** wirksam: erkennt die Warteschleife währenddessen
        `self._abbruch`, wirft sie `_LaufAbbruch` statt auf das Ende des laufenden (u. U.
        minutenlangen) HTTP-Aufrufs zu warten — der Worker-Thread läuft als Daemon im
        Hintergrund aus, sein Ergebnis wird verworfen. Außerhalb eines Laufs nur Repaints
        (ExcludeUserInputEvents), damit Einzelzeilen-Aktionen nicht per Doppelklick
        re-entrant werden — dort gibt es kein „Abbrechen", `self._abbruch` bleibt also
        irrelevant. Im Übersetzungstest-Modus wird direkt (blockierend) aufgerufen, weil
        die uebersetzung-Funktionen dort selbst Qt-Protokoll-Dialoge zeigen (GUI nur im
        Hauptthread erlaubt). Exceptions des Aufrufs werden unverändert im GUI-Thread neu
        geworfen."""
        if settings.get_uebersetzungstest_aktiv():
            return func(*args, **kwargs)
        ergebnis = {}

        def _runner():
            try:
                ergebnis["wert"] = func(*args, **kwargs)
            except BaseException as ex:                          # noqa: BLE001
                ergebnis["fehler"] = ex

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        flags = (QEventLoop.ProcessEventsFlag.AllEvents if self._lauf_aktiv
                 else QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        while t.is_alive():
            QApplication.processEvents(flags)
            if self._lauf_aktiv and self._abbruch:
                raise _LaufAbbruch()
            t.join(0.03)
        if "fehler" in ergebnis:
            raise ergebnis["fehler"]
        return ergebnis.get("wert")

    def _token_status(self, aufgabe: str):
        """Zeigt unter dem Token-Zähler, welcher Prompt gerade läuft (z. B. „Übersetzung",
        „Rückübersetzung", „Bewertung / Prüfung") — vor jedem KI-Aufruf im Dialog
        aufgerufen. `aufgabe=""` blendet auf den Leer-Zustand zurück (Lauf beendet)."""
        self._token_status_label.setText(
            _("dlg.sprachdatei.token_status", aufgabe=aufgabe) if aufgabe
            else _("dlg.sprachdatei.token_status_leer"))

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

        # Live-Token-Zähler als eigener Rahmen **vor** der Farberklärung, gleicher Stil.
        # Zeigt den KI-Tokenverbrauch dieser Dialogsitzung (seit dem Öffnen), wächst
        # während laufender Übersetzungs-/Prüf-Läufe live mit (siehe `_token_tick`).
        token_rahmen = QFrame()
        token_rahmen.setFrameShape(QFrame.Shape.StyledPanel)
        token_lay = QVBoxLayout(token_rahmen)
        token_lay.setSpacing(2)
        token_lay.addWidget(QLabel(f"<b>{_('dlg.sprachdatei.token_titel')}</b>"))
        self._token_label = QLabel("")
        token_lay.addWidget(self._token_label)
        # Aktuell laufender KI-Aufruf (Bezeichnung des Prompts) — live nachgeführt über
        # `_token_status`, direkt vor jedem KI-Aufruf im Dialog aufgerufen.
        self._token_status_label = QLabel(_("dlg.sprachdatei.token_status_leer"))
        token_lay.addWidget(self._token_status_label)

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
        # Kursiv-Fett: gleiche Kennzeichnung wie in der Übersetzungsspalte für Zeilen,
        # die die KI im Rahmen der Übereinstimmungsprüfung/Korrektur geändert hat
        # (siehe `_set_row`, Parameter `ki_geaendert`).
        legende_lay.addWidget(QLabel(f"<i><b>{_('dlg.sprachdatei.legende_kursiv')}</b></i>"))
        # Hellgrauer Hintergrund der Original-Spalte: Quelltext seit der Übersetzung
        # geändert (Inhalts-Hash stimmt nicht mehr → Übersetzung veraltet).
        legende_lay.addWidget(QLabel(
            f"<span style='background-color:{theme.color('veraltet_bg')}'>"
            f"&nbsp;&nbsp;&nbsp;</span> {_('dlg.sprachdatei.legende_veraltet')}"))

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

        # Token-Verbrauch + Programmerklärung als eigene (linke) Unterspalte, links neben
        # der Farberklärung — statt alle drei Rahmen untereinander zu stapeln.
        rechte_unterspalte = QVBoxLayout()
        rechte_unterspalte.addWidget(token_rahmen)
        rechte_unterspalte.addWidget(info_rahmen)

        rechte_spalte = QHBoxLayout()
        rechte_spalte.addLayout(rechte_unterspalte)
        rechte_spalte.addWidget(legende)

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
        # Massenaktualisierung: nur im „Alle Sprachen"-Modus sichtbar (siehe _set_massen_modus);
        # aktualisiert alle bereits übersetzten Sprachen nacheinander.
        self._massen_btn = QPushButton(_("dlg.sprachdatei.btn_massen"))
        self._massen_btn.setToolTip(_("dlg.sprachdatei.btn_massen_tt"))
        self._massen_btn.clicked.connect(lambda: self._massenaktualisierung())
        self._massen_btn.setVisible(False)
        btns.addWidget(self._massen_btn)
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
            self._token_status(_("dlg.sprachdatei.token_status_sprachbeherrschung"))
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            QApplication.processEvents()
            try:
                res = self._ki_call(uebersetzung.pruefe_sprachbeherrschung, firma, label)
            except Exception as ex:                              # noqa: BLE001
                res = {"fehler": str(ex), "ok": False}
            finally:
                QApplication.restoreOverrideCursor()
                self._fortschritt.setText("")
                self._token_status("")
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
        # Sammel-Eintrag „Alle Sprachen": schaltet in den Massenaktualisierungs-Modus
        # (Button „Massenaktualisierung"). Nur sinnvoll, wenn es bereits Zusatzsprachen gibt.
        if vorhanden:
            self._combo.addItem(_("dlg.sprachdatei.alle_sprachen"), ALLE_SPRACHEN)
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

    def _set_massen_modus(self, on):
        """Schaltet die Buttonleiste zwischen Einzelsprachen-Modus und
        Massenaktualisierungs-Modus um: bei `on=True` werden die einzelsprachlichen
        Aktions-Buttons ausgeblendet und stattdessen „Massenaktualisierung" gezeigt."""
        self._massen_btn.setVisible(on)
        for b in (self._run_btn, self._fehlende_btn, self._aehnl_btn,
                  self._schlecht_btn, self._gut_btn, self._save_btn):
            b.setVisible(not on)

    def _on_combo(self):
        data = self._combo.currentData()
        code = None
        if data == ALLE_SPRACHEN:              # Sammel-Eintrag → Massenaktualisierungs-Modus
            self._set_massen_modus(True)
            self._code_edit.clear()
            self._code_edit.setReadOnly(True)
            self._name_edit.clear()
            self._update_headers("")
            self._table.setRowCount(0)
            self._row_index = {}
            self._fortschritt.setText("")
            self._save_btn.setEnabled(False)
            self._alle_anzeigen_cb.setEnabled(False)
            self._anzahl_label.setText("")
            self._beherrschung_label.setText("")
            return
        self._set_massen_modus(False)
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
        offen = len(sprachdatei_lauf.bestimme_keys(
            self._quellwerte, main, extra, review, False))
        gesamt = sum(1 for k in main if not lang_tools.ist_generator_ausgeschlossen(k))
        self._anzahl_label.setText(f"{offen} / {gesamt}")

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
        offene = sorted(sprachdatei_lauf.bestimme_keys(
                            self._quellwerte, main, extra, review, False),
                        key=lambda k: (bool(extra.get(k)), k))
        for key in offene:
            ueb = extra.get(key) or ""
            rev = review.get(key) or {}
            veraltet = lang_tools.ist_veraltet(ts_map, key, rev)
            ok = bool(rev.get("ok"))
            rueck = rev.get("rueck") or ""
            orig = self._quellwerte.get(key, key)
            unstimmig = (not ueb) or veraltet or sprachdatei_lauf.unstimmig(orig, rueck)
            self._set_row(key, orig, ueb, rueck, unstimmig=unstimmig, ok=ok,
                          src_ts=rev.get(lang_tools.REVIEW_SRC_TS, ""),
                          bewertung=rev.get("bewertung"),
                          begruendung=rev.get("begruendung", ""),
                          korrektur=rev.get("korrektur", ""), veraltet=veraltet)
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
        for key in sorted(sprachdatei_lauf.bestimme_keys(
                self._quellwerte, main, extra, review, True)):
            ueb = extra.get(key) or ""
            rev = review.get(key) or {}
            rueck = rev.get("rueck") or ""
            ok = bool(rev.get("ok"))
            orig = self._quellwerte.get(key, key)
            # Erledigte (ok) Items nach einem Quellwechsel nicht fälschlich rot färben —
            # ihre Rückübersetzung wurde gegen ihre eigene Quelle geprüft. Veraltung und
            # fehlende Übersetzung bleiben rot (Nachpflege nötig).
            veraltet = lang_tools.ist_veraltet(ts_map, key, rev)
            unstimmig = (not ueb) or veraltet or (
                not ok and bool(rueck) and sprachdatei_lauf.unstimmig(orig, rueck))
            self._set_row(key, orig, ueb, rueck, unstimmig=unstimmig, ok=ok,
                          src_ts=rev.get(lang_tools.REVIEW_SRC_TS, ""),
                          bewertung=rev.get("bewertung"),
                          begruendung=rev.get("begruendung", ""),
                          korrektur=rev.get("korrektur", ""), veraltet=veraltet)
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
                 begruendung="", korrektur="", ki_geaendert=False, quelle_geaendert=False,
                 veraltet=False):
        """Aktualisiert die Zeile zu `key` (falls vorhanden) oder hängt sie neu an;
        unstimmige Zeilen werden rot dargestellt und erhalten ein aktivierbares
        Bestätigungs-Häkchen. Items werden immer frisch gesetzt, damit ein Wechsel
        unstimmig→stimmig Farbe und Häkchen sauber zurücknimmt. `src_ts` (Quell-Stand,
        gegen den übersetzt wurde) wird in der Schlüsselzelle hinterlegt und beim
        Speichern wieder ausgelesen. `bewertung` (identisch/sehr_gut/gut/schlecht) setzt
        hinter dem Häkchen einen farbigen Stern; `begruendung` erscheint als dessen Tooltip;
        `korrektur` (vom LLM vorgeschlagene, noch nicht übernommene Verbesserung) wird in der
        Bewertungs-Anzeige mit gezeigt. Alle werden in der COL_OK-Zelle hinterlegt.
        `ki_geaendert=True` (Übersetzung wurde im Rahmen der Übereinstimmungsprüfung + Korrektur
        von der KI verändert) stellt die Übersetzungs-Zelle kursiv-fett dar;
        `quelle_geaendert=True` (Grammatik-Korrektur des Ausgangstexts wurde übernommen)
        ebenso die Quell-Zelle — beides nur für den laufenden Lauf, keine Persistierung.
        `veraltet=True` (Quelltext seit der Übersetzung geändert, Inhalts-Hash stimmt nicht
        mehr) hinterlegt die Original-Zelle hellgrau, damit die geänderte Quelle sofort
        auffällt."""
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
                if ki_geaendert:
                    font = item.font()
                    font.setBold(True)
                    font.setItalic(True)
                    item.setFont(font)
            if col == COL_ORIG and quelle_geaendert:
                font = item.font()
                font.setBold(True)
                font.setItalic(True)
                item.setFont(font)
            if col == COL_ORIG and veraltet:
                # Quelltext seit der Übersetzung geändert (Hash stimmt nicht mehr) →
                # Original-Zelle hellgrau hinterlegen als sofortiger Hinweis.
                item.setBackground(QColor(theme.color("veraltet_bg")))
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
        # Liegt bereits eine Bewertung vor, zusätzlich „Bewertung ansehen".
        if bewertung in _BEWERTUNG_FARBE:
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
            keys = sprachdatei_lauf.fehlende_keys(main, extra)
        else:
            keys = sprachdatei_lauf.bestimme_keys(
                self._quellwerte, main, extra, review, self._alle_cb.isChecked())
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

    def _massenaktualisierung(self):
        """Aktualisiert **alle bereits übersetzten Zusatzsprachen** nacheinander: je Sprache
        wird der komplette Übersetzungslauf (wie „Erstellen/Aktualisieren") ausgeführt und
        anschließend gespeichert, dann folgt die nächste Sprache. Es gibt genau **eine**
        Rückfrage vorab; abgelehnte Sprachen (Sprachbeherrschung < Schwelle) werden
        übersprungen. Das Häkchen „alle neu übersetzen" wirkt auch hier (sonst nur offene
        Items). Abbruch zwischen Sprachen/Batches möglich."""
        if self._lauf_aktiv:
            return
        firma_row = self.db.get_firma()
        firma = dict(firma_row) if firma_row else {}
        if not firma.get("ki_aktiv"):
            QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                    _("dlg.sprachdatei.ki_inaktiv"))
            return
        sprachen = [(c, lbl) for c, lbl in lang_tools.discover() if c != self._quellcode]
        if not sprachen:
            QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                    _("dlg.sprachdatei.massen_keine"))
            return
        if QMessageBox.question(
                self, _("dlg.sprachdatei.titel"),
                _("dlg.sprachdatei.massen_confirm", n=len(sprachen),
                  quelle=self._quelllabel)
        ) != QMessageBox.StandardButton.Yes:
            return

        main = lang_tools.load_main()
        ts_map = lang_tools.main_ts(main)
        uebersetzung.reset_test_protokoll()
        self._abbruch = False
        self._massen_aktiv = True
        self._set_running(True)
        verarbeitet = uebersprungen = 0
        try:
            for i, (code, label) in enumerate(sprachen, start=1):
                if self._abbruch:
                    break
                # Zielsprache einstellen: bestimmt das Schreibziel von `_persist_still`
                # und den Tabellen-Header (Spalte „Übersetzung (<Sprache>)").
                self._code_edit.setText(code)
                self._name_edit.setText(label)
                self._fortschritt.setText(
                    _("dlg.sprachdatei.massen_fortschritt", i=i, n=len(sprachen),
                      sprache=label))
                QApplication.processEvents()
                # Sprachbeherrschung prüfen; bei Ablehnung diese Sprache überspringen
                # (kein blockierender Dialog wie im Einzelmodus).
                if not self._ensure_beherrschung(label, firma):
                    uebersprungen += 1
                    continue
                extra = lang_tools.load_extra(code)
                review = lang_tools.load_review(code)
                keys = sprachdatei_lauf.bestimme_keys(
                    self._quellwerte, main, extra, review, self._alle_cb.isChecked())
                if not keys:
                    continue                    # nichts nachzupflegen für diese Sprache
                weiter = self._lauf(firma, label, keys, ts_map, manage_running=False)
                # Nach dem Lauf sicher speichern (der Lauf persistiert bereits je Batch;
                # dieser Aufruf garantiert den gespeicherten Endstand je Sprache).
                try:
                    self._persist_still()
                except OSError as e:
                    zeige_fehler(self, _("dlg.sprachdatei.titel"),
                                 _("dlg.sprachdatei.schreibfehler", err=e))
                    break
                verarbeitet += 1
                if not weiter:                  # Lauf wurde abgebrochen → Massenlauf beenden
                    break
        finally:
            self._massen_aktiv = False
            self._set_running(False)
            i18n.reload()
        self._fortschritt.setText("")
        QMessageBox.information(
            self, _("dlg.sprachdatei.titel"),
            _("dlg.sprachdatei.massen_fertig", n=verarbeitet, m=uebersprungen))

    def _lauf_umgebung(self, firma):
        """Baut die Callback-Umgebung (`sprachdatei_lauf.LaufUmgebung`) für die Qt-freie
        Lauf-Pipeline: KI-Aufrufe über `_ki_call` (Event-Pumping), Zeilen über `_set_row`,
        Persistierung über `_persist_still`, Prompt-Anzeige/Token-Zähler über
        `_token_status`/`_token_tick`. Der Fortschritts-Callback setzt je Phase den
        passenden Text, scrollt in Phase „vor" ans Tabellenende und pumpt die
        Ereignisschleife, damit frische Zeilen sofort gezeichnet werden."""
        def _fortschritt(phase, i, n):
            if phase == "vor":
                self._fortschritt.setText(self._phase_fortschritt(
                    _("dlg.sprachdatei.phase_vor"), i, n))
                self._table.scrollToBottom()
            elif phase == "rueck":
                self._fortschritt.setText(self._phase_fortschritt(
                    _("dlg.sprachdatei.phase_rueck"), i, n))
            elif phase == "pruefung":
                self._fortschritt.setText(self._phase_fortschritt(
                    _("dlg.sprachdatei.phase_pruefung"), i, n))
            elif phase == "aehnlichkeit":
                self._fortschritt.setText(
                    _("dlg.sprachdatei.aehnlichkeit_fortschritt", i=i, n=n))
            else:                                   # "retry"
                self._fortschritt.setText(
                    _("dlg.sprachdatei.retry_fortschritt", i=i, n=n))
            QApplication.processEvents()

        zweit = self._zweite_quelle()
        return sprachdatei_lauf.LaufUmgebung(
            firma=firma, quellcode=self._quellcode, quelllabel=self._quelllabel,
            quellwerte=self._quellwerte,
            ki_call=self._ki_call,
            set_row=self._set_row,
            persist=self._persist_still,
            token_status=lambda task: self._token_status(_(task) if task else ""),
            token_tick=self._token_tick,
            fortschritt=_fortschritt,
            ist_abbruch=lambda: self._abbruch,
            frage_quelle_korrektur=self._frage_quelle_korrektur,
            zweitcode=zweit or "", zweitlabel=i18n.label(zweit) if zweit else "")

    def _frage_quelle_korrektur(self, alt, neu, antwort=""):
        """Zeigt bisherigen und von der KI vorgeschlagenen Ausgangstext (Grammatik-
        Korrektur der Quellsprache) an und fragt, ob die Änderung übernommen werden
        soll. Ein zusätzlicher Button zeigt bei Bedarf die vollständige LLM-Rohantwort
        `antwort` (eigenes Fenster, bleibt die Rückfrage offen). Rückgabe: True bei
        Zustimmung."""
        frage = _("dlg.sprachdatei.quelle_korrektur_frage",
                  sprache=self._quelllabel, alt=alt, neu=neu)
        while True:
            box = QMessageBox(self)
            box.setWindowTitle(_("dlg.sprachdatei.titel"))
            box.setText(frage)
            ja_btn = box.addButton(QMessageBox.StandardButton.Yes)
            box.addButton(QMessageBox.StandardButton.No)
            antwort_btn = box.addButton(_("btn.vollstaendige_antwort"),
                                        QMessageBox.ButtonRole.ActionRole)
            box.exec()
            if box.clickedButton() is antwort_btn:
                _AntwortDialog(self, _("btn.vollstaendige_antwort"), antwort).exec()
                continue
            return box.clickedButton() is ja_btn

    def _lauf(self, firma, label, keys, ts_map, manage_running=True):
        """Startet den kompletten Lauf (`sprachdatei_lauf.lauf`: Vorwärts- und
        Rückübersetzung + sinngemäße Prüfung, batchweise, abbruchsicher persistiert)
        und übernimmt die UI-Klammer: Tabelle leeren, Bedienelemente sperren,
        Fehler-/Abbruchmeldungen anzeigen.

        `manage_running=False` (Aufruf aus der Massenaktualisierung): die Running-/Abbruch-
        Klammer wird **nicht** hier gesetzt, sondern von der Massen-Schleife über den
        gesamten Lauf gehalten — so bleibt „Abbrechen" durchgängig sichtbar und der
        Abbruch-Status wird nicht pro Sprache zurückgesetzt."""
        self._table.setRowCount(0)
        self._row_index = {}
        self._update_headers(label)
        uebersetzung.reset_test_protokoll()        # neuer Lauf → Protokoll-Dialoge wieder zeigen
        if manage_running:
            self._abbruch = False
            self._set_running(True)
        abgebrochen = False
        try:
            abgebrochen = sprachdatei_lauf.lauf(
                self._lauf_umgebung(firma), label, keys, ts_map,
                self._batch_spin.value())
        except _LaufAbbruch:
            abgebrochen = True
        except uebersetzung.UebersetzungAbbruch as ab:
            zeige_fehler(self, _("msg.fehler"),
                         _("uebersetzung.abbruch_komplett", detail=str(ab)))
            abgebrochen = True
        except Exception as ex:                              # noqa: BLE001
            zeige_fehler(self, _("msg.fehler"),
                         _("uebersetzung.abbruch", detail=str(ex)))
            abgebrochen = True
        finally:
            if manage_running:
                self._set_running(False)
        if abgebrochen:
            zeige_warnung(self, _("dlg.sprachdatei.titel"),
                          _("dlg.sprachdatei.abgebrochen",
                            i=self._table.rowCount(), n=len(keys)))
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
        for w in (self._run_btn, self._massen_btn, self._fehlende_btn, self._aehnl_btn,
                  self._close_btn, self._schlecht_btn, self._gut_btn,
                  self._combo, self._quelle_combo, self._code_edit, self._name_edit,
                  self._alle_cb, self._batch_spin,
                  self._alle_anzeigen_cb):
            w.setEnabled(not running)
        if running:
            self._save_btn.setEnabled(False)
        else:
            # Nach dem Lauf die Übersetzungs-Buttons gemäß Sprachbeherrschung sperren.
            self._apply_beherrschung_gate()
            self._token_status("")

    def _abbrechen(self):
        # Bricht auch einen noch laufenden KI-Aufruf sofort ab (s. _ki_call/_LaufAbbruch).
        self._abbruch = True

    def _retranslate_row(self, key):
        """Übersetzt eine einzelne Zeile (per Zeilen-Button „Neu übersetzen") komplett
        neu: (1) Vorwärts-Übersetzung, (2) Rückübersetzung, (3) bei Übereinstimmung
        fertig, (4) sonst sinngemäße KI-Bewertung, (5) ein gelieferter
        Übersetzungs-Korrekturvorschlag wird übernommen und die Rückübersetzung erneut
        geprüft, (6) ein gemeldeter Grammatikfehler im Ausgangstext wird übernommen
        (`language.json` sofort aktualisiert) und der komplette Ablauf beginnt von
        vorn — maximal eine Wiederholung (`sprachdatei_lauf.neu_uebersetze_zeile`).
        Ersetzt die frühere separate Aktion „Neue Bewertung" (jetzt hier integriert).
        Während eines laufenden Stapellaufs gesperrt. Bei KI-Fehler bleibt die
        bisherige Zeile erhalten."""
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
        src_ts = lang_tools.main_ts(lang_tools.load_main()).get(key, "")
        uebersetzung.reset_test_protokoll()        # Einzel-Neuübersetzung → Protokoll wieder zeigen
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            orig, ueb, rueck, ist_unstimmig, bewertung, begruendung, src_ts, \
                ki_geaendert, quelle_geaendert = sprachdatei_lauf.neu_uebersetze_zeile(
                    self._lauf_umgebung(firma), key, label, orig, src_ts)
        except uebersetzung.UebersetzungAbbruch as ab:
            QApplication.restoreOverrideCursor()
            self._token_status("")
            zeige_fehler(self, _("msg.fehler"),
                         _("uebersetzung.abbruch_komplett", detail=str(ab)))
            return
        except Exception as ex:                                  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            self._token_status("")
            zeige_fehler(self, _("msg.fehler"),
                         _("uebersetzung.abbruch", detail=str(ex)))
            return
        QApplication.restoreOverrideCursor()
        self._token_status("")
        angewendet = ki_geaendert or quelle_geaendert
        ok = (not ist_unstimmig) if angewendet else (bewertung in uebersetzung.BEWERTUNG_OK)
        self._set_row(key, orig, ueb, rueck, unstimmig=(not ok), ok=ok, src_ts=src_ts,
                      bewertung=bewertung, begruendung=begruendung or "",
                      ki_geaendert=ki_geaendert, quelle_geaendert=quelle_geaendert)
        self._token_tick()
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

        def _schritt(code):
            """Schritt-Code der Pipeline → Text im Fortschritts-Fenster."""
            if code == "zweite_quelle":
                dlg.schritt(_("dlg.sprachdatei.fortschritt_zweite_quelle",
                              sprache=zweite_label))
            elif code == "quelle_speichern":
                dlg.schritt(_("dlg.sprachdatei.fortschritt_quelle_speichern"))
            elif code == "uebersetzen":
                dlg.schritt(_("dlg.sprachdatei.fortschritt_uebersetzen", sprache=label))
            elif code == "rueck":
                dlg.schritt(_("dlg.sprachdatei.fortschritt_rueck"))
            else:                                   # "bewerten"
                dlg.schritt(_("dlg.sprachdatei.fortschritt_bewerten"))

        try:
            # Schritte (1)–(5) laufen in der Qt-freien Pipeline; `_quellwerte` wird dort
            # nach dem Speichern von language.json in place aufgefrischt (geteiltes dict).
            ergebnis = sprachdatei_lauf.quelltext_uebernehmen(
                self._lauf_umgebung(firma), key, neu, zweite, zweite_label, label,
                _schritt)
        except uebersetzung.UebersetzungAbbruch as ab:
            dlg.close()
            dlg.deleteLater()
            self._token_status("")
            zeige_fehler(self, _("msg.fehler"),
                         _("uebersetzung.abbruch_komplett", detail=str(ab)))
            return
        except OSError as e:
            dlg.close()
            dlg.deleteLater()
            self._token_status("")
            zeige_fehler(self, _("dlg.sprachdatei.titel"),
                         _("dlg.sprachdatei.schreibfehler", err=e))
            return
        except Exception as ex:                                  # noqa: BLE001
            dlg.close()
            dlg.deleteLater()
            self._token_status("")
            zeige_fehler(self, _("msg.fehler"), _("uebersetzung.abbruch", detail=str(ex)))
            return

        dlg.close()
        dlg.deleteLater()
        self._token_status("")
        if ergebnis is None:                       # Key existiert nicht (mehr)
            zeige_fehler(self, _("dlg.sprachdatei.titel"),
                         _("dlg.sprachdatei.edit_key_fehlt", schluessel=key))
            return
        ueb, rueck, ist_unstimmig, bewertung, begruendung, src_ts = ergebnis
        ok = (not ist_unstimmig) or (bewertung in uebersetzung.BEWERTUNG_OK)
        self._set_row(key, neu, ueb, rueck, unstimmig=ist_unstimmig, ok=ok,
                      src_ts=src_ts, bewertung=bewertung, begruendung=begruendung or "")
        self._table.resizeRowToContents(row)
        self._token_tick()
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
        try:
            sprachdatei_lauf.phase3_kern(self._lauf_umgebung(firma), label, zeilen)
        except _LaufAbbruch:
            pass
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

    # ── Aktion: Batch-Neuübersetzung bewerteter Zeilen (Stufe) ────────
    def _batch_retry(self, stufe: str):
        """Übersetzt alle **nicht bestätigten** Zeilen mit der Bewertung `stufe`
        („schlecht" / „gut") per `sprachdatei_lauf.batch_retry_lauf` neu (bis zu
        `MAX_RETRY` Versuche mit Einbezug der Bewertung, Ziel »sehr gut«, bestes Ergebnis
        behalten). Für die gezielte Nachbearbeitung nach einem Bewertungslauf. Abbruch
        zwischen den Zeilen möglich."""
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
                _("dlg.sprachdatei.batch_retry_confirm", n=len(zeilen),
                  max=sprachdatei_lauf.MAX_RETRY)
        ) != QMessageBox.StandardButton.Yes:
            return

        uebersetzung.reset_test_protokoll()        # neuer Lauf → Protokoll-Dialoge wieder zeigen
        self._abbruch = False
        self._set_running(True)
        try:
            sprachdatei_lauf.batch_retry_lauf(self._lauf_umgebung(firma), label, zeilen)
        except _LaufAbbruch:
            pass
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
