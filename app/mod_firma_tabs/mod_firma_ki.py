"""Firmenstamm-Reiter „Anbindung KI".

Aktiviert/konfiguriert die KI-Anbindung je Firma (OpenRouter oder lokale,
OpenAI-kompatible KI). API-Key und Modell werden pro Anbieter getrennt
gespeichert, damit das Umschalten verlustfrei möglich ist. Über „Test KI"
öffnet sich ein Dialog, der System-Prompt + Prompt an das Modell schickt und
die Antwort anzeigt.
"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLineEdit, QCheckBox, QComboBox, QTextEdit, QLabel,
                             QSizePolicy, QPushButton, QMessageBox, QGroupBox,
                             QScrollArea, QSpinBox, QAbstractSpinBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from ui_widgets import SaveBar, zeige_fehler, zeige_warnung
from lock_manager import Module, ist_admin
from i18n import _
import theme
import ki_client
from .base_form_tab import SimpleFormTab
from .mod_firma_ki_dialoge import (_hoehe_zeilen, _PromptFeld, PromptMarkdownDialog,
                                   ModellAuswahlDialog)

# Marker für den Test-Prompt (nur intern genutzt; Quelle: ki_client).
from ki_client import (  # noqa: E402
    MARKER_SPRACHE_KUNDE, MARKER_SPRACHE_FIRMA, MARKER_TEXT, MARKER_KONTEXT,
    MARKER_QUELLSPRACHE, MARKER_ZIELSPRACHE, MARKER_ANZAHL,
    MARKER_AUSGANGSTEXT, MARKER_UEBERSETZUNG)

# Maskierung der API-Keys für Nicht-Admins (feste Länge, verrät die Key-Länge nicht).
KEY_MASKE = "********"

# Anthropic-Effort je App-Übersetzungs-Aufgabe (ki_anthropic_effort_<task>): (Wert, i18n-Key).
# Leerer Wert = adaptives Thinking ohne Effort-Override (Anthropic-Standard).
_EFFORT_OPTIONEN = (
    ("", "firma.ki.effort_opt_adaptiv"),
    ("low", "firma.ki.effort_opt_low"),
    ("medium", "firma.ki.effort_opt_medium"),
    ("high", "firma.ki.effort_opt_high"),
    ("xhigh", "firma.ki.effort_opt_xhigh"),
    ("max", "firma.ki.effort_opt_max"),
)


class KiAnbindungTab(SimpleFormTab):
    RECHT_KEY = "firma_ki"
    # Wählt nur aus, welcher lokale Slot im Formular angezeigt wird (die Slot-Combos
    # der LLM-Gruppen sind dagegen echte Datenfelder und bleiben gesperrt).
    READONLY_AUSNAHMEN = ("_cmb_lok_edit",)
    HELP_ANCHOR = "firma-ki"

    def _firma_nr(self) -> str:
        f = self._db.get_firma(self._firma_id) if self._db and self._firma_id else None
        return (dict(f).get("firmen_nr") if f else "") or ""

    def _build(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # Sprachen-Werte initialisieren (werden in den toggle-Closures referenziert)
        self._sprachen_werte = {"openrouter": "", "anthropic": "", "lokal": ""}
        self._rueck_sprachen_wert = ""

        # API-Keys dürfen nur Administratoren sehen/ändern. Nicht-Admins bekommen
        # die Felder maskiert (Sterne) und read-only; der echte Wert wird nie ins
        # Widget geladen, sondern hier zwischengehalten (Erhalt beim Speichern).
        self._admin = ist_admin()
        self._key_realwerte = {}

        # Scrollbereich: Wird das Fenster verkleinert, bleibt der 6-px-Abstand
        # zwischen den Feldern erhalten (es wird gescrollt, statt die Felder
        # zusammenzuquetschen).
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(0)

        # ── Aktiv-Checkbox (einzelne Zeile über dem Tabellen-Bereich) ──
        aktiv_w = QWidget()
        aktiv_w.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        aktiv_form = QFormLayout(aktiv_w)
        aktiv_form.setVerticalSpacing(6)
        self._cb_aktiv = QCheckBox()
        aktiv_form.addRow(_("firma.ki.aktiv"), self._cb_aktiv)
        self._felder["ki_aktiv"] = self._cb_aktiv
        content_lay.addWidget(aktiv_w)

        # ── Gemeinsamer Abschnitt: 5 lokale KI-Server (firmenweite Liste) ──
        self._build_lokal_server(content_lay)

        # ── Zweispaltiger LLM-Bereich ──
        llm_w = QWidget()
        llm_w.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        llm_lay = QHBoxLayout(llm_w)
        llm_lay.setContentsMargins(0, 4, 0, 0)
        llm_lay.setSpacing(8)

        grp1 = QGroupBox(_("firma.ki.grp_uebersetzung"))
        form1 = QFormLayout(grp1)
        form1.setVerticalSpacing(6)
        self._build_llm_gruppe(form1, 1)

        grp2 = QGroupBox(_("firma.ki.grp_rueck"))
        form2 = QFormLayout(grp2)
        form2.setVerticalSpacing(6)
        self._build_llm_gruppe(form2, 2)

        # API-Key-Felder beider Gruppen ermitteln; für Nicht-Admins sperren.
        self._key_felder = {k for k in self._felder if k.endswith("api_key")}
        if not self._admin:
            for k in self._key_felder:
                self._felder[k].setReadOnly(True)

        llm_lay.addWidget(grp1, 1)
        llm_lay.addWidget(grp2, 1)
        content_lay.addWidget(llm_w)

        # ── App-Übersetzung: Aufgaben → LLM-Zuordnung ──
        self._build_llm_zuordnung(content_lay)

        # ── Gemeinsame Prompts und Einstellungen ──
        prompts_w = QWidget()
        prompts_w.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        pf = QFormLayout(prompts_w)
        pf.setVerticalSpacing(6)

        # Prompt-Felder: zweizeilige read-only Anzeige; ein Klick öffnet den Markdown-Editor
        # mit Live-Vorschau (Marker werden dort eingefügt). Reihenfolge: Sprachen + System
        # zuerst, danach die Übersetzungs-Prompts im Ablauf der Verarbeitung.
        self._e_prompt_sprachen = self._prompt_feld(
            "ki_prompt_sprachen", "firma.ki.prompt_sprachen")
        pf.addRow(_("firma.ki.prompt_sprachen"), self._e_prompt_sprachen)

        self._e_system = self._prompt_feld(
            "ki_system_prompt", "firma.ki.system_prompt")
        pf.addRow(_("firma.ki.system_prompt"), self._e_system)

        # 1. Übersetzung
        self._e_prompt_ueber = self._prompt_feld(
            "ki_prompt_uebersetzung", "firma.ki.prompt_uebersetzung",
            marker=(MARKER_SPRACHE_KUNDE, MARKER_SPRACHE_FIRMA, MARKER_TEXT, MARKER_KONTEXT))
        pf.addRow(_("firma.ki.prompt_uebersetzung"), self._e_prompt_ueber)

        # 2. Rückübersetzung
        self._e_prompt_rueck = self._prompt_feld(
            "ki_prompt_rueckuebersetzung", "firma.ki.prompt_rueckuebersetzung",
            marker=(MARKER_SPRACHE_KUNDE, MARKER_SPRACHE_FIRMA, MARKER_TEXT, MARKER_KONTEXT))
        pf.addRow(_("firma.ki.prompt_rueckuebersetzung"), self._e_prompt_rueck)

        # 3. Massen-/Batch-Prompt: mehrere nummerierte Items je LLM-Aufruf (App-Sprachen-
        # Generator). Richtungsneutral – {Quellsprache}/{Zielsprache} werden je Aufruf
        # gesetzt, {Anzahl} = Anzahl Items im Batch.
        self._e_prompt_massen = self._prompt_feld(
            "ki_prompt_massen", "firma.ki.prompt_massen",
            marker=(MARKER_QUELLSPRACHE, MARKER_ZIELSPRACHE, MARKER_ANZAHL, MARKER_KONTEXT))
        pf.addRow(_("firma.ki.prompt_massen"), self._e_prompt_massen)

        # 4. Übereinstimmungs-/Korrektur-Prompt: prüft per LLM, ob Ausgangstext und
        # Übersetzung sinngemäß übereinstimmen, und liefert bei nicht-perfekter Übersetzung
        # gleich eine verbesserte Fassung mit (App-Sprachen-Generator). Ersetzt den früheren
        # separaten Wiederholungs-Übersetzungs-Prompt.
        self._e_prompt_aehnlichkeit = self._prompt_feld(
            "ki_prompt_aehnlichkeit", "firma.ki.prompt_aehnlichkeit",
            marker=(MARKER_AUSGANGSTEXT, MARKER_UEBERSETZUNG, MARKER_QUELLSPRACHE,
                    MARKER_ZIELSPRACHE, MARKER_KONTEXT))
        pf.addRow(_("firma.ki.prompt_aehnlichkeit"), self._e_prompt_aehnlichkeit)

        # 5. Rechtschreibprüfung — genutzt vom Artikelstamm (Beschreibung/Sicherheitshinweise
        # per KI korrigieren), NICHT von der App-Sprachen-Erstellung (dort übernimmt die
        # Grammatikprüfung im Bewertungs-/Korrektur-Prompt diese Aufgabe mit).
        self._e_prompt_recht = self._prompt_feld(
            "ki_prompt_rechtschreibung", "firma.ki.prompt_rechtschreibung")
        pf.addRow(_("firma.ki.prompt_rechtschreibung"), self._e_prompt_recht)

        box = QGroupBox(_("firma.ki.uebersetzen_von"))
        box_lay = QHBoxLayout(box)
        for key, lbl_key in [
            ("ki_uebersetze_bezeichnung",         "firma.ki.uebersetze.bezeichnung"),
            ("ki_uebersetze_beschreibung",         "firma.ki.uebersetze.beschreibung"),
            ("ki_uebersetze_sicherheitshinweise",  "firma.ki.uebersetze.sicherheitshinweise"),
            ("ki_uebersetze_herstellerinfo",        "firma.ki.uebersetze.herstellerinfo"),
        ]:
            cb = QCheckBox(_(lbl_key))
            box_lay.addWidget(cb)
            self._felder[key] = cb
        box_lay.addStretch()
        pf.addRow(box)

        content_lay.addWidget(prompts_w)
        content_lay.addStretch()

        scroll.setWidget(content)
        main_lay.addWidget(scroll)

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    # ── App-Übersetzung: Aufgaben → LLM-Zuordnung ─────────────────────────
    def _build_llm_zuordnung(self, content_lay):
        """Gruppe mit je einem Auswahlfeld LLM 1 / LLM 2 sowie einem Anthropic-Effort-Feld
        pro App-Übersetzungs-Aufgabe (gebunden an die ki_llm_*- bzw. ki_anthropic_effort_*-
        Spalten über self._felder — Laden/Speichern/Dirty laufen unverändert über das
        bestehende _value/_set_value-Muster). Die Belegverarbeitung nutzt unabhängig davon
        immer LLM 1. Das Effort-Feld gilt aufgabenweit (nicht je LLM 1/2) und wirkt nur,
        wenn für die Aufgabe tatsächlich Anthropic als Anbieter konfiguriert ist — ohne
        Auswahl („Adaptiv") sendet Anthropic ohnehin immer adaptives Thinking."""
        box = QGroupBox(_("firma.ki.gbx_llm_zuordnung"))
        box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form = QFormLayout(box)
        form.setVerticalSpacing(6)
        for key, lbl_key, task in (
            ("ki_llm_uebersetzung",      "firma.ki.llm_task.uebersetzung", "uebersetzung"),
            ("ki_llm_rueckuebersetzung", "firma.ki.llm_task.rueckuebersetzung", "rueckuebersetzung"),
            ("ki_llm_bewertung",         "firma.ki.llm_task.bewertung", "bewertung"),
        ):
            cmb = QComboBox()
            cmb._data_mode = True
            cmb.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            cmb.addItem(_("firma.ki.llm_opt_1"), "1")
            cmb.addItem(_("firma.ki.llm_opt_2"), "2")
            self._felder[key] = cmb

            cmb_effort = QComboBox()
            cmb_effort._data_mode = True
            cmb_effort.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            for wert, opt_key in _EFFORT_OPTIONEN:
                cmb_effort.addItem(_(opt_key), wert)
            self._felder[f"ki_anthropic_effort_{task}"] = cmb_effort

            zeile = QWidget()
            zeile_lay = QHBoxLayout(zeile)
            zeile_lay.setContentsMargins(0, 0, 0, 0)
            zeile_lay.setSpacing(6)
            zeile_lay.addWidget(cmb)
            zeile_lay.addSpacing(12)
            zeile_lay.addWidget(QLabel(_("firma.ki.effort_label")))
            zeile_lay.addWidget(cmb_effort)
            zeile_lay.addStretch()
            form.addRow(_(lbl_key), zeile)
        hinweis = QLabel(_("firma.ki.llm_zuordnung_hinweis"))
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet(theme.hint_label_style())
        form.addRow(hinweis)
        effort_hinweis = QLabel(_("firma.ki.effort_hinweis"))
        effort_hinweis.setWordWrap(True)
        effort_hinweis.setStyleSheet(theme.hint_label_style())
        form.addRow(effort_hinweis)
        content_lay.addWidget(box)

    # ── Prompt-Felder (zweizeilig, Klick öffnet Markdown-Editor) ──────────
    def _prompt_feld(self, key, label_key, marker=()):
        """Zweizeiliges, read-only Prompt-Anzeigefeld; Klick öffnet den Markdown-Editor.
        Registriert das Feld unter `key` in self._felder (→ Werte/Dirty/Save unverändert)."""
        te = _PromptFeld()
        te.setFixedHeight(_hoehe_zeilen(te, 2))
        te.setToolTip(_("firma.ki.prompt_klick_tip"))
        te.clicked.connect(
            lambda k=key, lk=label_key, m=tuple(marker): self._edit_prompt(k, lk, m))
        self._felder[key] = te
        return te

    def _edit_prompt(self, key, label_key, marker):
        """Öffnet den Markdown-Editor für das Prompt-Feld und übernimmt geänderten Text
        (die textChanged→_recompute_dirty-Kette setzt den Dirty-Status)."""
        te = self._felder[key]
        neu = PromptMarkdownDialog.bearbeite(
            self, _("firma.ki.prompt_edit_titel", feld=_(label_key)),
            te.toPlainText(), marker)
        if neu is not None and neu != te.toPlainText():
            te.setPlainText(neu)

    # ── Reasoning-/Budget-Bedienelemente (eine Zeile je Modell-Stelle) ────
    def _baue_reason_widgets(self):
        """Erzeugt die vier Reasoning-/Budget-Widgets (Haken+Combo / Haken+SpinBox) und
        liefert sie als Tupel `(cb_reason, cmb_reason, cb_budget, spin_budget)` zurück.
        Reines Widget-Bauen — Registrierung (firma-Spalten vs. lokaler Slot) erfolgt beim
        Aufrufer."""
        cb_reason = QCheckBox(_("firma.ki.reasoning_verwenden"))
        cmb_reason = QComboBox()
        cmb_reason._data_mode = True
        cmb_reason.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        cmb_reason.addItem(_("firma.ki.reasoning_an"), "1")
        cmb_reason.addItem(_("firma.ki.reasoning_aus"), "0")
        cb_budget = QCheckBox(_("firma.ki.budget_verwenden"))
        spin_budget = QSpinBox()
        spin_budget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        spin_budget.setRange(0, 200000)
        spin_budget.setValue(1000)
        return cb_reason, cmb_reason, cb_budget, spin_budget

    def _reason_box(self, key_prefix: str) -> QWidget:
        """Container mit den vier Reasoning-/Budget-Widgets in einer Zeile; registriert sie
        unter `<key_prefix>reason_aktiv|reason_an|budget_aktiv|budget` in self._felder
        (→ Laden/Speichern/Dirty laufen über das vorhandene _felder-Muster)."""
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        cb_r, cmb_r, cb_b, spin_b = self._baue_reason_widgets()
        lay.addWidget(cb_r)
        lay.addWidget(cmb_r)
        lay.addSpacing(12)
        lay.addWidget(cb_b)
        lay.addWidget(spin_b)
        lay.addSpacing(12)
        hinweis = QLabel(_("firma.ki.reasoning_hinweis"))
        hinweis.setStyleSheet(theme.hint_label_style())
        lay.addWidget(hinweis)
        lay.addStretch()
        self._felder[key_prefix + "reason_aktiv"] = cb_r
        self._felder[key_prefix + "reason_an"] = cmb_r
        self._felder[key_prefix + "budget_aktiv"] = cb_b
        self._felder[key_prefix + "budget"] = spin_b
        return box

    # ── Gemeinsame Liste der 5 lokalen KI-Server ──────────────────────────
    def _lokal_label(self, slot: int, modell: str) -> str:
        """Anzeige-Bezeichnung eines lokalen Servers: „Lokal - {Modell}" sobald ein Modell
        gesetzt ist, sonst „Lokal - {n}"."""
        modell = (modell or "").strip()
        if modell:
            return _("firma.ki.lokal_slot_modell", model=modell)
        return _("firma.ki.lokal_slot_leer", n=slot)

    def _build_lokal_server(self, content_lay):
        """Einziger Editier-Ort der 5 lokalen Server (single source of truth:
        self._lokal_slots). Die LLM-Gruppen referenzieren nur per Slot-Auswahl."""
        self._lokal_slots = {s: {"basis_url": "", "api_key": "", "modell": "", "sprachen": "",
                                 "reason_aktiv": 0, "reason_an": 1, "budget_aktiv": 0,
                                 "budget": 1000}
                             for s in range(1, 6)}
        self._lokal_loading = False   # Guard beim Slot-Laden (kein Dirty/Rückschreiben)

        box = QGroupBox(_("firma.ki.grp_lokal_server"))
        box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form = QFormLayout(box)
        form.setVerticalSpacing(6)

        # Welcher der 5 Server wird gerade bearbeitet?
        self._cmb_lok_edit = QComboBox()
        self._cmb_lok_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        for s in range(1, 6):
            self._cmb_lok_edit.addItem(self._lokal_label(s, ""), str(s))
        self._cmb_lok_edit.currentIndexChanged.connect(self._load_lok_edit_felder)
        form.addRow(_("firma.ki.lokal_slot_auswahl"), self._cmb_lok_edit)

        # Basis-URL + „URL testen"
        self._e_ls_url = QLineEdit()
        self._e_ls_url.setPlaceholderText("http://localhost:1234")
        row_url = QWidget()
        url_lay = QHBoxLayout(row_url)
        url_lay.setContentsMargins(0, 0, 0, 0)
        url_lay.addWidget(self._e_ls_url, 1)
        btn_url = QPushButton(_("firma.ki.btn.url_testen"))
        btn_url.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_url.clicked.connect(self._ls_url_testen)
        url_lay.addWidget(btn_url)
        form.addRow(_("firma.ki.lokal_basis_url"), row_url)

        # API-Key (Admin-Schutz wie bei den übrigen Keys)
        self._e_ls_key = QLineEdit()
        if not self._admin:
            self._e_ls_key.setReadOnly(True)
        form.addRow(_("firma.ki.lokal_api_key"), self._e_ls_key)

        # Modell + Buttons
        self._cmb_ls_modell = QComboBox()
        self._cmb_ls_modell.setEditable(True)
        form.addRow(_("firma.ki.modell"), self._cmb_ls_modell)
        btn_modelle = QPushButton(_("firma.ki.btn.modelle_abrufen"))
        btn_modelle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_modelle.clicked.connect(self._ls_modelle_abrufen)
        btn_test = QPushButton(_("firma.ki.btn.test"))
        btn_test.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_test.clicked.connect(self._ls_test)
        btn_sprachen = QPushButton(_("firma.ki.btn.sprachen_ermitteln"))
        btn_sprachen.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_sprachen.clicked.connect(self._ls_sprachen)
        btn_row = QWidget()
        btn_row_lay = QHBoxLayout(btn_row)
        btn_row_lay.setContentsMargins(0, 0, 0, 0)
        btn_row_lay.addWidget(btn_modelle)
        btn_row_lay.addWidget(btn_test)
        btn_row_lay.addWidget(btn_sprachen)
        btn_row_lay.addStretch()
        form.addRow("", btn_row)

        # Reasoning/Token-Budget je Slot (nicht in _felder — manuell in _lokal_slots gepflegt)
        (self._cb_ls_reason, self._cmb_ls_reason,
         self._cb_ls_budget, self._spin_ls_budget) = self._baue_reason_widgets()
        reason_row = QWidget()
        reason_lay = QHBoxLayout(reason_row)
        reason_lay.setContentsMargins(0, 0, 0, 0)
        reason_lay.setSpacing(6)
        reason_lay.addWidget(self._cb_ls_reason)
        reason_lay.addWidget(self._cmb_ls_reason)
        reason_lay.addSpacing(12)
        reason_lay.addWidget(self._cb_ls_budget)
        reason_lay.addWidget(self._spin_ls_budget)
        reason_lay.addSpacing(12)
        ls_hinweis = QLabel(_("firma.ki.reasoning_hinweis"))
        ls_hinweis.setStyleSheet(theme.hint_label_style())
        reason_lay.addWidget(ls_hinweis)
        reason_lay.addStretch()
        form.addRow(_("firma.ki.reasoning_label"), reason_row)

        # Sprachen-Ergebnis (read-only, je Slot)
        self._e_ls_sprachen = QTextEdit()
        self._e_ls_sprachen.setReadOnly(True)
        self._e_ls_sprachen.setFixedHeight(_hoehe_zeilen(self._e_ls_sprachen, 3))
        form.addRow(_("firma.ki.sprachen"), self._e_ls_sprachen)

        # Editier-Signale → ins Modell zurückschreiben (außer beim Laden)
        self._e_ls_url.textChanged.connect(self._on_lok_feld_geaendert)
        self._e_ls_key.textChanged.connect(self._on_lok_feld_geaendert)
        self._cmb_ls_modell.editTextChanged.connect(self._on_lok_feld_geaendert)
        self._cb_ls_reason.stateChanged.connect(self._on_lok_feld_geaendert)
        self._cmb_ls_reason.currentIndexChanged.connect(self._on_lok_feld_geaendert)
        self._cb_ls_budget.stateChanged.connect(self._on_lok_feld_geaendert)
        self._spin_ls_budget.valueChanged.connect(self._on_lok_feld_geaendert)

        content_lay.addWidget(box)

    def _load_lok_edit_felder(self, *args):
        """Editierfelder mit dem aktuell gewählten Bearbeitungs-Slot füllen."""
        slot = int(self._cmb_lok_edit.currentData() or 1)
        d = self._lokal_slots.get(slot, {})
        self._lokal_loading = True
        self._e_ls_url.setText(d.get("basis_url", ""))
        if self._admin:
            self._e_ls_key.setText(d.get("api_key", ""))
        else:
            self._set_masked(self._e_ls_key, d.get("api_key", ""))
        self._cmb_ls_modell.blockSignals(True)
        self._cmb_ls_modell.clear()
        self._cmb_ls_modell.setCurrentText(d.get("modell", ""))
        self._cmb_ls_modell.blockSignals(False)
        self._e_ls_sprachen.setPlainText(d.get("sprachen", ""))
        self._cb_ls_reason.setChecked(bool(d.get("reason_aktiv", 0)))
        idx = self._cmb_ls_reason.findData("1" if d.get("reason_an", 1) else "0")
        self._cmb_ls_reason.setCurrentIndex(idx if idx >= 0 else 0)
        self._cb_ls_budget.setChecked(bool(d.get("budget_aktiv", 0)))
        self._spin_ls_budget.setValue(int(d.get("budget", 1000) or 1000))
        self._lokal_loading = False

    def _on_lok_feld_geaendert(self, *args):
        """Editierfeld geändert → in den gewählten Slot zurückschreiben, Bezeichnungen
        überall nachführen und Dirty neu berechnen."""
        if self._lokal_loading:
            return
        slot = int(self._cmb_lok_edit.currentData() or 1)
        d = self._lokal_slots[slot]
        d["basis_url"] = self._e_ls_url.text().strip()
        if self._admin:   # Nicht-Admins können den Key nicht ändern (read-only)
            d["api_key"] = self._e_ls_key.text().strip()
        d["modell"] = self._cmb_ls_modell.currentText().strip()
        d["reason_aktiv"] = 1 if self._cb_ls_reason.isChecked() else 0
        d["reason_an"] = 1 if (self._cmb_ls_reason.currentData() == "1") else 0
        d["budget_aktiv"] = 1 if self._cb_ls_budget.isChecked() else 0
        d["budget"] = self._spin_ls_budget.value()
        self._refresh_lokal_labels()
        self._recompute_dirty()

    def _refresh_lokal_labels(self):
        """Slot-Bezeichnungen in allen drei Combos (Bearbeiten + beide LLM-Gruppen)
        aus den aktuellen Modellnamen aktualisieren."""
        for combo in (self._cmb_lok_edit, getattr(self, "_cmb_lok_slot", None),
                      getattr(self, "_cmb_rueck_lok_slot", None)):
            if combo is None:
                continue
            combo.blockSignals(True)
            for i in range(combo.count()):
                slot = int(combo.itemData(i) or (i + 1))
                modell = self._lokal_slots.get(slot, {}).get("modell", "")
                combo.setItemText(i, self._lokal_label(slot, modell))
            combo.blockSignals(False)

    def _aktiver_lokal_slot(self, llm_nr: int) -> int:
        """Vom jeweiligen LLM (1/2) gewählter lokaler Slot (1..5)."""
        cmb = self._cmb_lok_slot if llm_nr == 1 else self._cmb_rueck_lok_slot
        try:
            return int(cmb.currentData() or 1)
        except (TypeError, ValueError):
            return 1

    def _ls_key_wert(self) -> str:
        """Echter API-Key des Bearbeitungs-Slots (Admins aus dem Feld, Nicht-Admins aus
        dem Modell, da das Feld nur Sterne zeigt)."""
        if self._admin:
            return self._e_ls_key.text().strip()
        slot = int(self._cmb_lok_edit.currentData() or 1)
        return self._lokal_slots[slot].get("api_key", "")

    def _ls_url_testen(self):
        self._lokal_url_testen(self._e_ls_url, self._ls_key_wert())

    def _ls_modelle_abrufen(self):
        gewaehlt = self._modelle_in_combo(
            "lokal", self._ls_key_wert(), self._e_ls_url.text().strip(),
            self._cmb_ls_modell)
        if gewaehlt is not None:
            self._on_lok_feld_geaendert()

    def _ls_test(self):
        modell = self._cmb_ls_modell.currentText().strip()
        if not modell:
            zeige_warnung(self, _("msg.hinweis"), _("firma.ki.msg.kein_modell"))
            return
        try:
            QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            info = ki_client.teste_prompt_caching(
                "lokal", self._ls_key_wert(), self._e_ls_url.text().strip(), modell,
                reasoning=self._ls_reasoning())
        except Exception as ex:
            QGuiApplication.restoreOverrideCursor()
            zeige_fehler(self, _("msg.fehler"),
                         _("firma.ki.msg.test_fehler", detail=str(ex)))
            return
        finally:
            QGuiApplication.restoreOverrideCursor()
        QMessageBox.information(self, _("msg.hinweis"), self._cache_test_text(info))

    def _ls_sprachen(self):
        modell = self._cmb_ls_modell.currentText().strip()
        if not modell:
            zeige_warnung(self, _("msg.hinweis"), _("firma.ki.msg.kein_modell"))
            return
        slot = int(self._cmb_lok_edit.currentData() or 1)
        prompt = self._e_prompt_sprachen.toPlainText().strip() or ki_client.SPRACHEN_PROMPT
        self._e_ls_sprachen.setPlainText(_("firma.ki.dlg.sende"))
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QGuiApplication.processEvents()
        try:
            ergebnis = ki_client.chat("lokal", self._ls_key_wert(),
                                      self._e_ls_url.text().strip(), modell, "", prompt,
                                      reasoning=self._ls_reasoning(),
                                      firma_nr=self._firma_nr(), task="test")
        except Exception as ex:
            QGuiApplication.restoreOverrideCursor()
            self._e_ls_sprachen.setPlainText(self._lokal_slots[slot].get("sprachen", ""))
            zeige_fehler(self, _("msg.fehler"),
                         _("firma.ki.msg.test_fehler", detail=str(ex)))
            return
        finally:
            QGuiApplication.restoreOverrideCursor()
        self._e_ls_sprachen.setPlainText(ergebnis)
        self._lokal_slots[slot]["sprachen"] = ergebnis
        self._recompute_dirty()

    def _build_llm_gruppe(self, form: QFormLayout, nr: int):
        """Baut die LLM-Konfigurationszeilen für eine Gruppe (nr=1 oder nr=2).

        Anbieter openrouter/anthropic/lokal; pro Anbieter nur die eigenen Felder
        sichtbar. Für „lokal" wird kein eigenes Profil mehr editiert, sondern nur einer
        der 5 zentral gepflegten Server gewählt (Slot-Combo) + die API-Zeile angezeigt.
        Registriert die toggle-Funktion in self._toggle1 (nr=1) bzw. self._toggle_rueck.
        """
        is2 = (nr == 2)
        pfx = "ki_rueck_" if is2 else "ki_"

        # Anbieter
        cmb_anbieter = QComboBox()
        cmb_anbieter._data_mode = True
        for val, key in ki_client.ANBIETER:
            cmb_anbieter.addItem(_(key), val)
        form.addRow(_("firma.ki.anbieter"), cmb_anbieter)
        self._felder[pfx + "anbieter"] = cmb_anbieter

        # Lokal: Auswahl eines der 5 zentral gepflegten Server (kein eigenes Profil).
        cmb_lok_slot = QComboBox()
        cmb_lok_slot._data_mode = True
        cmb_lok_slot.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        for s in range(1, 6):
            cmb_lok_slot.addItem(self._lokal_label(s, ""), str(s))
        form.addRow(_("firma.ki.lokal_server"), cmb_lok_slot)
        self._felder[pfx + "lokal_slot"] = cmb_lok_slot

        # API-Endpunkt (ergibt sich aus dem Anbieter; bei „lokal" aus dem Slot).
        # Read-only Anzeige, per Maus markier-/kopierbar.
        lbl_api = QLabel()
        lbl_api.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow(_("firma.ki.api"), lbl_api)

        # OpenRouter: API-Key
        e_or_key = QLineEdit()
        e_or_key.setPlaceholderText("sk-or-...")
        form.addRow(_("firma.ki.openrouter_api_key"), e_or_key)
        self._felder[pfx + "openrouter_api_key"] = e_or_key

        # Anthropic: API-Key
        e_anth_key = QLineEdit()
        e_anth_key.setPlaceholderText("sk-ant-...")
        form.addRow(_("firma.ki.anthropic_api_key"), e_anth_key)
        self._felder[pfx + "anthropic_api_key"] = e_anth_key

        # Modell-Combos (openrouter/anthropic; das lokale Modell kommt aus dem Slot)
        cmb_or_modell = QComboBox()
        cmb_or_modell.setEditable(True)
        form.addRow(_("firma.ki.modell"), cmb_or_modell)
        self._felder[pfx + "openrouter_modell"] = cmb_or_modell

        cmb_anth_modell = QComboBox()
        cmb_anth_modell.setEditable(True)
        form.addRow(_("firma.ki.modell"), cmb_anth_modell)
        self._felder[pfx + "anthropic_modell"] = cmb_anth_modell

        # Reasoning/Token-Budget nur noch für openrouter/lokal (lokal kommt aus dem Slot).
        # Anthropic sendet immer adaptives Thinking — Effort wird je App-Übersetzungs-Aufgabe
        # in der Gruppe „App-Übersetzung: LLM-Zuordnung" eingestellt (s. _build_llm_zuordnung),
        # nicht hier je LLM-Stelle (budget_tokens wird von neueren Anthropic-Modellen abgelehnt).
        reason_or = self._reason_box(pfx + "openrouter_")
        form.addRow(_("firma.ki.reasoning_label"), reason_or)

        # Button-Zeile (nur openrouter/anthropic; lokal pflegt man im Server-Abschnitt)
        btn_modelle = QPushButton(_("firma.ki.btn.modelle_abrufen"))
        btn_modelle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_modelle.clicked.connect(lambda _c=False, n=nr: self._modelle_abrufen(n))
        btn_test = QPushButton(_("firma.ki.btn.test"))
        btn_test.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_test.clicked.connect(lambda _c=False, n=nr: self._ki_erreichbar_testen(n))
        btn_sprachen = QPushButton(_("firma.ki.btn.sprachen_ermitteln"))
        btn_sprachen.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_sprachen.clicked.connect(lambda _c=False, n=nr: self._sprachen_ermitteln(n))
        btn_row = QWidget()
        btn_row_lay = QHBoxLayout(btn_row)
        btn_row_lay.setContentsMargins(0, 0, 0, 0)
        btn_row_lay.addWidget(btn_modelle)
        btn_row_lay.addWidget(btn_test)
        btn_row_lay.addWidget(btn_sprachen)
        btn_row_lay.addStretch()
        form.addRow("", btn_row)

        # Sprachen-Ergebnis (read-only; openrouter/anthropic)
        e_sprachen = QTextEdit()
        e_sprachen.setReadOnly(True)
        e_sprachen.setFixedHeight(_hoehe_zeilen(e_sprachen, 3))
        form.addRow(_("firma.ki.sprachen"), e_sprachen)

        # Label-Referenzen für Sichtbarkeits-Toggle
        lbl_slot     = form.labelForField(cmb_lok_slot)
        lbl_or_key   = form.labelForField(e_or_key)
        lbl_anth_key = form.labelForField(e_anth_key)
        lbl_or_mod   = form.labelForField(cmb_or_modell)
        lbl_anth_mod = form.labelForField(cmb_anth_modell)
        lbl_reason_or   = form.labelForField(reason_or)
        lbl_sprachen = form.labelForField(e_sprachen)

        def _set_vis(paare, sichtbar):
            for w, lbl in paare:
                w.setVisible(sichtbar)
                if lbl:
                    lbl.setVisible(sichtbar)

        def toggle():
            akt = cmb_anbieter.currentData()
            ist_lokal = (akt == "lokal")
            _set_vis([(e_or_key, lbl_or_key), (cmb_or_modell, lbl_or_mod),
                      (reason_or, lbl_reason_or)],
                     akt == "openrouter")
            _set_vis([(e_anth_key, lbl_anth_key), (cmb_anth_modell, lbl_anth_mod)],
                     akt == "anthropic")
            # Lokal: nur Slot-Auswahl; Buttons/Sprachen entfallen (Pflege zentral).
            _set_vis([(cmb_lok_slot, lbl_slot)], ist_lokal)
            _set_vis([(btn_row, None), (e_sprachen, lbl_sprachen)], not ist_lokal)
            lbl_api.setText(self._api_text_aktiv(akt, is2))
            if not ist_lokal:
                e_sprachen.setPlainText(
                    self._rueck_sprachen_wert if is2
                    else self._sprachen_werte.get(akt, ""))

        cmb_anbieter.currentIndexChanged.connect(toggle)
        # Slot-Wechsel: API-Zeile (Endpunkt des gewählten Servers) live nachführen.
        cmb_lok_slot.currentIndexChanged.connect(
            lambda *_: lbl_api.setText(
                self._api_text_aktiv(cmb_anbieter.currentData(), is2)))

        # Widget-Referenzen auf self ablegen
        if is2:
            self._cmb_rueck_anbieter   = cmb_anbieter
            self._cmb_rueck_lok_slot   = cmb_lok_slot
            self._e_rueck_or_key       = e_or_key
            self._e_rueck_anth_key     = e_anth_key
            self._cmb_rueck_or_modell  = cmb_or_modell
            self._cmb_rueck_anth_modell = cmb_anth_modell
            self._e_rueck_sprachen     = e_sprachen
            self._lbl_rueck_api        = lbl_api
            self._toggle_rueck         = toggle
        else:
            self._cmb_anbieter    = cmb_anbieter
            self._cmb_lok_slot    = cmb_lok_slot
            self._e_or_key        = e_or_key
            self._e_anth_key      = e_anth_key
            self._cmb_or_modell   = cmb_or_modell
            self._cmb_anth_modell = cmb_anth_modell
            self._e_sprachen      = e_sprachen
            self._lbl_api         = lbl_api
            self._toggle1         = toggle

    def _api_text(self, anbieter: str, basis_url: str = "") -> str:
        """Anzeige der API-Zeile eines LLMs: „<Endpunkt>  ·  <API-Typ>".
        Bei „lokal" ohne Basis-URL ein Hinweis statt einer URL."""
        url = ki_client.api_endpunkt(anbieter, basis_url)
        if not url:
            return _("firma.ki.api_keine_url")
        typ = (_("firma.ki.api_typ.anthropic") if anbieter == "anthropic"
               else _("firma.ki.api_typ.openai"))
        return f"{url}  ·  {typ}"

    def _api_text_aktiv(self, anbieter: str, is2: bool) -> str:
        """API-Zeile für den aktuellen Anbieter. Bei „lokal" wird die Basis-URL aus dem
        vom jeweiligen LLM (1/2) gewählten Slot gezogen."""
        if anbieter == "lokal":
            slot = self._aktiver_lokal_slot(2 if is2 else 1)
            return self._api_text(
                "lokal", self._lokal_slots.get(slot, {}).get("basis_url", ""))
        return self._api_text(anbieter)

    # ── API-Key-Schutz (Nicht-Admins) ─────────────────────────────────────

    def _set_masked(self, w, real: str):
        """Maskierte Anzeige eines API-Keys: Sterne wenn gesetzt, sonst leer.
        Der echte Wert wird nie ins Widget geladen."""
        w.blockSignals(True)
        w.setText(KEY_MASKE if (real or "").strip() else "")
        w.blockSignals(False)

    def _key_wert(self, feld: str, w) -> str:
        """Echter API-Key (für Tests/Modellabruf): Nicht-Admins aus dem
        geschützten Speicher (Widget zeigt nur Sterne), Admins aus dem Feld."""
        if not self._admin and feld in self._key_felder:
            return self._key_realwerte.get(feld, "")
        return w.text().strip()

    # ── Lokal-URL-Test ────────────────────────────────────────────────────

    def _lokal_url_testen(self, e_url: QLineEdit, api_key: str):
        url = e_url.text().strip()
        if not url:
            zeige_warnung(self, _("msg.hinweis"), _("firma.ki.msg.keine_url"))
            return
        try:
            QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            modelle = ki_client.liste_modelle("lokal", api_key, url)
        except Exception as ex:
            QGuiApplication.restoreOverrideCursor()
            zeige_fehler(self, _("msg.fehler"),
                         _("firma.ki.msg.url_fehler", detail=str(ex)))
            return
        finally:
            QGuiApplication.restoreOverrideCursor()
        QMessageBox.information(self, _("msg.hinweis"),
                                _("firma.ki.msg.url_ok", anzahl=len(modelle)))

    # ── Aktive Konfiguration ──────────────────────────────────────────────

    def _aktive_cfg(self, llm_nr: int = 1):
        """(anbieter, api_key, basis_url, modell) des gewählten LLMs.

        Der API-Key wird über `_key_wert` geholt — für Nicht-Admins der echte
        Wert aus dem geschützten Speicher (Widget zeigt nur Sterne)."""
        pfx = "ki_" if llm_nr == 1 else "ki_rueck_"
        if llm_nr == 1:
            anbieter = self._cmb_anbieter.currentData()
            if anbieter == "openrouter":
                return ("openrouter",
                        self._key_wert(pfx + "openrouter_api_key", self._e_or_key), "",
                        self._cmb_or_modell.currentText().strip())
            if anbieter == "anthropic":
                return ("anthropic",
                        self._key_wert(pfx + "anthropic_api_key", self._e_anth_key), "",
                        self._cmb_anth_modell.currentText().strip())
            d = self._lokal_slots.get(self._aktiver_lokal_slot(1), {})
            return ("lokal", d.get("api_key", ""), d.get("basis_url", ""),
                    d.get("modell", ""))
        anbieter = self._cmb_rueck_anbieter.currentData()
        if anbieter == "openrouter":
            return ("openrouter",
                    self._key_wert(pfx + "openrouter_api_key", self._e_rueck_or_key), "",
                    self._cmb_rueck_or_modell.currentText().strip())
        if anbieter == "anthropic":
            return ("anthropic",
                    self._key_wert(pfx + "anthropic_api_key", self._e_rueck_anth_key), "",
                    self._cmb_rueck_anth_modell.currentText().strip())
        d = self._lokal_slots.get(self._aktiver_lokal_slot(2), {})
        return ("lokal", d.get("api_key", ""), d.get("basis_url", ""), d.get("modell", ""))

    def _alle_modell_combos(self, llm_nr: int = 1):
        """Modell-Combos der LLM-Gruppe (openrouter/anthropic; lokal kommt aus dem Slot)."""
        if llm_nr == 1:
            return (self._cmb_or_modell, self._cmb_anth_modell)
        return (self._cmb_rueck_or_modell, self._cmb_rueck_anth_modell)

    def _aktive_modell_combo(self, llm_nr: int = 1):
        if llm_nr == 1:
            return {"openrouter": self._cmb_or_modell,
                    "anthropic": self._cmb_anth_modell,
                    }.get(self._cmb_anbieter.currentData(), self._cmb_or_modell)
        return {"openrouter": self._cmb_rueck_or_modell,
                "anthropic": self._cmb_rueck_anth_modell,
                }.get(self._cmb_rueck_anbieter.currentData(), self._cmb_rueck_or_modell)

    # ── Reasoning für Test-Aufrufe (aktuell eingestellte, evtl. ungespeicherte Werte) ──
    def _reason_dict(self, reason_aktiv, reason_an, budget_aktiv, budget):
        """Baut das Reasoning-Dict (Form wie ki_client.firma_reasoning) oder `None`, wenn
        kein Haken gesetzt ist."""
        if not int(reason_aktiv or 0) and not int(budget_aktiv or 0):
            return None
        return {"reason_aktiv": int(reason_aktiv or 0), "reason_an": int(reason_an or 0),
                "budget_aktiv": int(budget_aktiv or 0), "budget": int(budget or 1000)}

    def _aktive_reasoning(self, llm_nr: int = 1):
        """Reasoning-Dict des aktuell im Reiter gewählten Modells (openrouter/anthropic aus
        den Widgets, lokal aus dem gewählten Slot)."""
        anbieter = (self._cmb_anbieter if llm_nr == 1
                    else self._cmb_rueck_anbieter).currentData()
        if anbieter == "lokal":
            d = self._lokal_slots.get(self._aktiver_lokal_slot(llm_nr), {})
            return self._reason_dict(d.get("reason_aktiv", 0), d.get("reason_an", 1),
                                     d.get("budget_aktiv", 0), d.get("budget", 1000))
        if anbieter == "anthropic":
            # Kein Reasoning-/Budget-Haken mehr für Anthropic — Testaufrufe hier haben
            # keinen konkreten App-Übersetzungs-Aufgabenbezug, daher reines adaptives
            # Thinking ohne Effort-Override (ki_client._apply_reasoning setzt es ohnehin
            # immer, unabhängig von diesem Rückgabewert).
            return None
        pfx = ("ki_" if llm_nr == 1 else "ki_rueck_") + anbieter + "_"
        return self._reason_dict(
            self._value(self._felder[pfx + "reason_aktiv"]),
            1 if self._value(self._felder[pfx + "reason_an"]) == "1" else 0,
            self._value(self._felder[pfx + "budget_aktiv"]),
            self._value(self._felder[pfx + "budget"]))

    def _ls_reasoning(self):
        """Reasoning-Dict des aktuell bearbeiteten lokalen Slots (für „Test"/„Sprachen")."""
        d = self._lokal_slots.get(int(self._cmb_lok_edit.currentData() or 1), {})
        return self._reason_dict(d.get("reason_aktiv", 0), d.get("reason_an", 1),
                                 d.get("budget_aktiv", 0), d.get("budget", 1000))

    # ── Modelle abrufen ───────────────────────────────────────────────────

    def _modelle_abrufen(self, llm_nr: int = 1):
        anbieter, api_key, basis_url, _ignored = self._aktive_cfg(llm_nr)
        self._modelle_in_combo(anbieter, api_key, basis_url,
                               self._aktive_modell_combo(llm_nr),
                               weitere=self._alle_modell_combos(llm_nr))

    def _modelle_in_combo(self, anbieter, api_key, basis_url, combo, weitere=()):
        """Modelle des Anbieters abrufen, per Dialog auswählen und in `combo` setzen
        (zusätzlich die `weitere`-Combos mit der Liste befüllen; deren Text bleibt).
        Rückgabe: gewähltes Modell, oder None bei Fehler/keinen Modellen/Abbruch."""
        try:
            QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            modelle = ki_client.liste_modelle(anbieter, api_key, basis_url)
        except Exception as ex:
            QGuiApplication.restoreOverrideCursor()
            zeige_fehler(self, _("msg.fehler"),
                         _("firma.ki.msg.modelle_fehler", detail=str(ex)))
            return None
        finally:
            QGuiApplication.restoreOverrideCursor()

        if not modelle:
            zeige_warnung(self, _("msg.hinweis"), _("firma.ki.msg.keine_modelle"))
            return None

        aktuell = combo.currentText().strip()
        dlg = ModellAuswahlDialog(self, modelle, aktuell)
        if not dlg.exec():
            return None
        gewaehlt = dlg.gewaehltes_modell()

        combo.blockSignals(True)
        combo.clear()
        combo.addItems(modelle)
        if gewaehlt:
            combo.setCurrentText(gewaehlt)
        elif aktuell:
            combo.setCurrentText(aktuell)
        combo.blockSignals(False)

        # Auch die inaktiven Modell-Combos desselben LLMs befüllen (Text erhalten)
        for other in weitere:
            if other is combo:
                continue
            aktuell_other = other.currentText().strip()
            other.blockSignals(True)
            other.clear()
            other.addItems(modelle)
            if aktuell_other:
                other.setCurrentText(aktuell_other)
            other.blockSignals(False)
        return gewaehlt or aktuell

    # ── Sprachen ermitteln ────────────────────────────────────────────────

    def _sprachen_ermitteln(self, llm_nr: int = 1):
        anbieter, api_key, basis_url, modell = self._aktive_cfg(llm_nr)
        if not modell:
            zeige_warnung(self, _("msg.hinweis"), _("firma.ki.msg.kein_modell"))
            return
        prompt = self._e_prompt_sprachen.toPlainText().strip() or ki_client.SPRACHEN_PROMPT
        result_w = self._e_sprachen if llm_nr == 1 else self._e_rueck_sprachen
        result_w.setPlainText(_("firma.ki.dlg.sende"))
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QGuiApplication.processEvents()
        try:
            ergebnis = ki_client.chat(anbieter, api_key, basis_url, modell, "", prompt,
                                      reasoning=self._aktive_reasoning(llm_nr),
                                      firma_nr=self._firma_nr(), task="test")
        except Exception as ex:
            QGuiApplication.restoreOverrideCursor()
            if llm_nr == 1:
                result_w.setPlainText(self._sprachen_werte.get(anbieter, ""))
            else:
                result_w.setPlainText(self._rueck_sprachen_wert)
            zeige_fehler(self, _("msg.fehler"),
                         _("firma.ki.msg.test_fehler", detail=str(ex)))
            return
        finally:
            QGuiApplication.restoreOverrideCursor()
        result_w.setPlainText(ergebnis)
        if llm_nr == 1:
            self._sprachen_werte[anbieter] = ergebnis
            spalte = {"openrouter": "ki_openrouter_sprachen",
                      "anthropic": "ki_anthropic_sprachen",
                      }.get(anbieter, "ki_lokal_sprachen")
        else:
            self._rueck_sprachen_wert = ergebnis
            spalte = "ki_rueck_sprachen"
        if self._db and self._firma_id is not None:
            self._db.save_firma({"id": self._firma_id, spalte: ergebnis,
                                 "_modul": Module.FIRMA})

    # ── LLM testen ───────────────────────────────────────────────────────

    def _ki_erreichbar_testen(self, llm_nr: int = 1):
        anbieter, api_key, basis_url, modell = self._aktive_cfg(llm_nr)
        if not modell:
            zeige_warnung(self, _("msg.hinweis"), _("firma.ki.msg.kein_modell"))
            return
        # Erreichbarkeit + Prompt-Caching in einem: die Probe schickt denselben
        # langen Prompt zweimal; der 1. Aufruf prüft zugleich die Erreichbarkeit.
        try:
            QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            info = ki_client.teste_prompt_caching(anbieter, api_key, basis_url, modell,
                                                  reasoning=self._aktive_reasoning(llm_nr))
        except Exception as ex:
            QGuiApplication.restoreOverrideCursor()
            zeige_fehler(self, _("msg.fehler"),
                         _("firma.ki.msg.test_fehler", detail=str(ex)))
            return
        finally:
            QGuiApplication.restoreOverrideCursor()
        QMessageBox.information(self, _("msg.hinweis"), self._cache_test_text(info))

    def _cache_test_text(self, info: dict) -> str:
        """Erreichbarkeits- + Prompt-Caching-Meldung aus dem Probe-Ergebnis."""
        status = info.get("status")
        gesamt = info.get("prompt_tokens")
        gesamt_txt = str(gesamt) if gesamt is not None else "?"
        if status == "aktiv":
            return _("firma.ki.msg.cache_aktiv",
                     tokens=info.get("cached_tokens") or 0, gesamt=gesamt_txt)
        if status == "kein_treffer":
            return _("firma.ki.msg.cache_kein_treffer", gesamt=gesamt_txt)
        # keine_info → Latenz-Heuristik (lokale Server cachen oft ohne Meldung)
        return _("firma.ki.msg.cache_keine_info",
                 d1=f"{info.get('dauer1') or 0.0:.2f}",
                 d2=f"{info.get('dauer2') or 0.0:.2f}")

    # ── Werte / Dirty / Snapshot ──────────────────────────────────────────

    def _value(self, w):
        if isinstance(w, QSpinBox):
            return w.value()
        if isinstance(w, QTextEdit):
            return w.toPlainText()
        if isinstance(w, QLineEdit):
            return w.text().strip()
        if isinstance(w, QCheckBox):
            return 1 if w.isChecked() else 0
        if isinstance(w, QComboBox):
            if getattr(w, '_data_mode', False):
                return w.currentData() or ""
            return w.currentText().strip()
        return ""

    def _set_value(self, w, v):
        if isinstance(w, QSpinBox):
            try:
                w.setValue(int(v))
            except (TypeError, ValueError):
                w.setValue(1000)
        elif isinstance(w, QTextEdit):
            w.setPlainText(str(v if v is not None else ""))
        elif isinstance(w, QLineEdit):
            w.setText(str(v if v is not None else ""))
        elif isinstance(w, QCheckBox):
            w.setChecked(bool(v) and str(v) not in ("0", "False"))
        elif isinstance(w, QComboBox):
            if getattr(w, '_data_mode', False):
                # str(v) statt str(v or "") — sonst würde der Wert 0 (z. B. reason_an=disabled)
                # zu "" und fälschlich auf den ersten Eintrag (enabled) fallen.
                idx = w.findData(str(v) if v is not None else "")
                w.setCurrentIndex(idx if idx >= 0 else 0)
            else:  # editierbare Modell-Combo
                w.setCurrentText(str(v or ""))

    def _connect_dirty(self):
        # Dirty wird gegen den Snapshot verglichen (nicht blind gesetzt): der
        # SpellCheckHighlighter auf den QTextEdits löst textChanged auch ohne
        # echte Textänderung aus (Qt-Highlighter-Verhalten). Ein reiner
        # Vergleich verhindert dadurch den falschen roten Punkt beim Öffnen und
        # nach dem Speichern.
        for w in self._felder.values():
            if isinstance(w, QSpinBox):
                w.valueChanged.connect(self._recompute_dirty)
            elif isinstance(w, (QLineEdit, QTextEdit)):
                w.textChanged.connect(self._recompute_dirty)
            elif isinstance(w, QCheckBox):
                w.stateChanged.connect(self._recompute_dirty)
            elif isinstance(w, QComboBox):
                w.currentIndexChanged.connect(self._recompute_dirty)
                if w.isEditable():
                    w.editTextChanged.connect(self._recompute_dirty)

    def _recompute_dirty(self, *args):
        dirty = any(self._value(w) != self._saved_data.get(k, "")
                    for k, w in self._felder.items())
        dirty = dirty or (self._lokal_slots
                          != getattr(self, "_saved_lokal", self._lokal_slots))
        self._save_bar.set_dirty(dirty)

    def _snapshot(self):
        self._saved_data = {k: self._value(w) for k, w in self._felder.items()}
        self._saved_lokal = {s: dict(d) for s, d in self._lokal_slots.items()}

    def _restore(self):
        for k, w in self._felder.items():
            w.blockSignals(True)
            self._set_value(w, self._saved_data.get(k, ""))
            w.blockSignals(False)
        self._lokal_slots = {s: dict(d) for s, d in self._saved_lokal.items()}
        self._refresh_lokal_labels()
        self._load_lok_edit_felder()
        self._toggle1()
        self._toggle_rueck()
        self._save_bar.reset_dirty()

    def _collect_data(self):
        data = {"id": self._firma_id}
        for k, w in self._felder.items():
            if not self._admin and k in self._key_felder:
                data[k] = self._key_realwerte.get(k, "")  # echten Key unverändert erhalten
            else:
                data[k] = self._value(w)
        # Spiegelung: aktiven lokalen Slot je LLM in die Kompat-Spalten schreiben, damit
        # ki_client.firma_cfg / _firma_fuer_rueck unverändert die ki_lokal_*/ki_rueck_lokal_*
        # lesen (die 5 Profile selbst speichert _save über save_firma_ki_lokal).
        p1 = self._lokal_slots.get(self._aktiver_lokal_slot(1), {})
        p2 = self._lokal_slots.get(self._aktiver_lokal_slot(2), {})
        data["ki_lokal_basis_url"] = p1.get("basis_url", "")
        data["ki_lokal_api_key"]   = p1.get("api_key", "")
        data["ki_lokal_modell"]    = p1.get("modell", "")
        data["ki_lokal_sprachen"]  = p1.get("sprachen", "")
        data["ki_rueck_lokal_basis_url"] = p2.get("basis_url", "")
        data["ki_rueck_lokal_api_key"]   = p2.get("api_key", "")
        data["ki_rueck_lokal_modell"]    = p2.get("modell", "")
        # Reasoning/Budget des aktiven Slots in die Spiegel-Spalten (firma_reasoning liest sie)
        for ziel, p in (("ki_lokal_", p1), ("ki_rueck_lokal_", p2)):
            data[ziel + "reason_aktiv"] = int(p.get("reason_aktiv", 0))
            data[ziel + "reason_an"]    = int(p.get("reason_an", 1))
            data[ziel + "budget_aktiv"] = int(p.get("budget_aktiv", 0))
            data[ziel + "budget"]       = int(p.get("budget", 1000))
        return data

    def _save(self):
        # Erst die firma-Spalten (inkl. Slot-Auswahl + gespiegelter Slot-Werte) über die
        # Basisklasse, dann die 5 lokalen Server in die eigene Tabelle.
        super()._save()
        if self._db and self._firma_id is not None:
            self._db.save_firma_ki_lokal(self._firma_id, self._lokal_slots)

    def _fill(self, f):
        for k, w in self._felder.items():
            if not self._admin and k in self._key_felder:
                real = str(f.get(k, "") or "")
                self._key_realwerte[k] = real
                self._set_masked(w, real)
            else:
                self._set_value(w, f.get(k, ""))
        # 5 lokale Server (gemeinsame Liste) laden + Bezeichnungen/Editierfelder setzen
        if self._db and self._firma_id is not None:
            self._lokal_slots = self._db.get_firma_ki_lokal(self._firma_id)
        else:
            self._lokal_slots = {s: {"basis_url": "", "api_key": "", "modell": "",
                                     "sprachen": "", "reason_aktiv": 0, "reason_an": 1,
                                     "budget_aktiv": 0, "budget": 1000}
                                 for s in range(1, 6)}
        self._refresh_lokal_labels()
        self._load_lok_edit_felder()
        self._sprachen_werte = {
            "openrouter": f.get("ki_openrouter_sprachen", "") or "",
            "anthropic": f.get("ki_anthropic_sprachen", "") or "",
            "lokal": f.get("ki_lokal_sprachen", "") or "",
        }
        self._rueck_sprachen_wert = f.get("ki_rueck_sprachen", "") or ""
        self._toggle1()
        self._toggle_rueck()
