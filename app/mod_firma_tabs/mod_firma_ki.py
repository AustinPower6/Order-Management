"""Firmenstamm-Reiter „Anbindung KI".

Aktiviert/konfiguriert die KI-Anbindung je Firma (OpenRouter oder lokale,
OpenAI-kompatible KI). API-Key und Modell werden pro Anbieter getrennt
gespeichert, damit das Umschalten verlustfrei möglich ist. Über „Test KI"
öffnet sich ein Dialog, der System-Prompt + Prompt an das Modell schickt und
die Antwort anzeigt.
"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLineEdit, QCheckBox, QComboBox, QTextEdit, QLabel,
                             QSizePolicy, QPushButton, QDialog, QListWidget,
                             QListWidgetItem, QDialogButtonBox, QMessageBox, QGroupBox,
                             QScrollArea)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from spellcheck import SpellCheckHighlighter
from ui_widgets import SaveBar, zeige_fehler, zeige_warnung
from lock_manager import Module, ist_admin
from i18n import _
import settings
import ki_client
from .base_form_tab import SimpleFormTab

# Marker für den Test-Prompt (nur intern genutzt; Quelle: ki_client).
from ki_client import (  # noqa: E402
    MARKER_SPRACHE_KUNDE, MARKER_SPRACHE_FIRMA, MARKER_TEXT, MARKER_KONTEXT)

# Maskierung der API-Keys für Nicht-Admins (feste Länge, verrät die Key-Länge nicht).
KEY_MASKE = "********"


def _hoehe_zeilen(te, zeilen):
    """Feste Höhe eines QTextEdit für die angegebene Zeilenzahl (aus Schriftmetrik)."""
    fm = te.fontMetrics()
    return fm.lineSpacing() * zeilen + 2 * int(te.document().documentMargin()) + 14


class KiAnbindungTab(SimpleFormTab):
    HELP_ANCHOR = "firma-ki"

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

        # ── Gemeinsame Prompts und Einstellungen ──
        prompts_w = QWidget()
        prompts_w.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        pf = QFormLayout(prompts_w)
        pf.setVerticalSpacing(6)

        self._e_prompt_sprachen = QTextEdit()
        self._e_prompt_sprachen.setFixedHeight(_hoehe_zeilen(self._e_prompt_sprachen, 3))
        self._e_prompt_sprachen._spell_hl = SpellCheckHighlighter(
            self._e_prompt_sprachen.document())
        pf.addRow(_("firma.ki.prompt_sprachen"), self._e_prompt_sprachen)
        self._felder["ki_prompt_sprachen"] = self._e_prompt_sprachen

        self._e_system = QTextEdit()
        self._e_system.setFixedHeight(_hoehe_zeilen(self._e_system, 3))
        self._e_system._spell_hl = SpellCheckHighlighter(self._e_system.document())
        pf.addRow(_("firma.ki.system_prompt"), self._e_system)
        self._felder["ki_system_prompt"] = self._e_system

        self._e_prompt_rueck = QTextEdit()
        self._e_prompt_rueck.setFixedHeight(_hoehe_zeilen(self._e_prompt_rueck, 3))
        self._e_prompt_rueck._spell_hl = SpellCheckHighlighter(self._e_prompt_rueck.document())
        pf.addRow(_("firma.ki.prompt_rueckuebersetzung"), self._e_prompt_rueck)
        self._felder["ki_prompt_rueckuebersetzung"] = self._e_prompt_rueck

        marker_rueck = QWidget()
        mh_rueck = QHBoxLayout(marker_rueck)
        mh_rueck.setContentsMargins(0, 0, 0, 0)
        mh_rueck.setSpacing(6)
        mh_rueck.addWidget(QLabel(_("firma.ki.marker_label")))
        for marker in (MARKER_SPRACHE_KUNDE, MARKER_SPRACHE_FIRMA, MARKER_TEXT, MARKER_KONTEXT):
            b = QPushButton(marker)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setToolTip(_("firma.ki.marker_tip"))
            b.clicked.connect(lambda _c=False, m=marker: self._e_prompt_rueck.insertPlainText(m))
            mh_rueck.addWidget(b)
        mh_rueck.addStretch()
        pf.addRow("", marker_rueck)

        self._e_prompt_recht = QTextEdit()
        self._e_prompt_recht.setFixedHeight(_hoehe_zeilen(self._e_prompt_recht, 3))
        self._e_prompt_recht._spell_hl = SpellCheckHighlighter(self._e_prompt_recht.document())
        pf.addRow(_("firma.ki.prompt_rechtschreibung"), self._e_prompt_recht)
        self._felder["ki_prompt_rechtschreibung"] = self._e_prompt_recht

        self._e_prompt_ueber = QTextEdit()
        self._e_prompt_ueber.setFixedHeight(_hoehe_zeilen(self._e_prompt_ueber, 3))
        self._e_prompt_ueber._spell_hl = SpellCheckHighlighter(self._e_prompt_ueber.document())
        pf.addRow(_("firma.ki.prompt_uebersetzung"), self._e_prompt_ueber)
        self._felder["ki_prompt_uebersetzung"] = self._e_prompt_ueber

        marker_row = QWidget()
        mh = QHBoxLayout(marker_row)
        mh.setContentsMargins(0, 0, 0, 0)
        mh.setSpacing(6)
        mh.addWidget(QLabel(_("firma.ki.marker_label")))
        for marker in (MARKER_SPRACHE_KUNDE, MARKER_SPRACHE_FIRMA, MARKER_TEXT, MARKER_KONTEXT):
            b = QPushButton(marker)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setToolTip(_("firma.ki.marker_tip"))
            b.clicked.connect(lambda _c=False, m=marker: self._e_prompt_ueber.insertPlainText(m))
            mh.addWidget(b)
        mh.addStretch()
        pf.addRow("", marker_row)

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

    def _build_llm_gruppe(self, form: QFormLayout, nr: int):
        """Baut die LLM-Konfigurationszeilen für eine Gruppe (nr=1 oder nr=2).

        Drei Anbieter (openrouter/anthropic/lokal), pro Anbieter nur die eigenen
        Felder sichtbar. Speichert Widget-Referenzen auf self. Registriert die
        toggle-Funktion in self._toggle1 (nr=1) bzw. self._toggle_rueck (nr=2).
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

        # Lokal: API-Key vorab anlegen (Closure braucht es bereits beim URL-Button)
        e_lok_key = QLineEdit()
        self._felder[pfx + "lokal_api_key"] = e_lok_key

        # Lokal: Basis-URL + Test-Button
        e_lok_url = QLineEdit()
        e_lok_url.setPlaceholderText("http://localhost:1234")
        self._felder[pfx + "lokal_basis_url"] = e_lok_url
        row_lok_url = QWidget()
        url_lay = QHBoxLayout(row_lok_url)
        url_lay.setContentsMargins(0, 0, 0, 0)
        url_lay.addWidget(e_lok_url, 1)
        btn_lok_test = QPushButton(_("firma.ki.btn.url_testen"))
        btn_lok_test.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_lok_test.clicked.connect(
            lambda _c=False, u=e_lok_url, kf=pfx + "lokal_api_key", k=e_lok_key:
            self._lokal_url_testen_impl(u, kf, k))
        url_lay.addWidget(btn_lok_test)
        form.addRow(_("firma.ki.lokal_basis_url"), row_lok_url)
        form.addRow(_("firma.ki.lokal_api_key"), e_lok_key)

        # Modell-Combos (pro Anbieter eine, nur aktive sichtbar)
        cmb_or_modell = QComboBox()
        cmb_or_modell.setEditable(True)
        form.addRow(_("firma.ki.modell"), cmb_or_modell)
        self._felder[pfx + "openrouter_modell"] = cmb_or_modell

        cmb_anth_modell = QComboBox()
        cmb_anth_modell.setEditable(True)
        form.addRow(_("firma.ki.modell"), cmb_anth_modell)
        self._felder[pfx + "anthropic_modell"] = cmb_anth_modell

        cmb_lok_modell = QComboBox()
        cmb_lok_modell.setEditable(True)
        form.addRow(_("firma.ki.modell"), cmb_lok_modell)
        self._felder[pfx + "lokal_modell"] = cmb_lok_modell

        # Button-Zeile
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

        # Sprachen-Ergebnis (read-only)
        e_sprachen = QTextEdit()
        e_sprachen.setReadOnly(True)
        e_sprachen.setFixedHeight(_hoehe_zeilen(e_sprachen, 3))
        form.addRow(_("firma.ki.sprachen"), e_sprachen)

        # Label-Referenzen für Sichtbarkeits-Toggle
        lbl_or_key   = form.labelForField(e_or_key)
        lbl_anth_key = form.labelForField(e_anth_key)
        lbl_lok_url  = form.labelForField(row_lok_url)
        lbl_lok_key  = form.labelForField(e_lok_key)
        lbl_or_mod   = form.labelForField(cmb_or_modell)
        lbl_anth_mod = form.labelForField(cmb_anth_modell)
        lbl_lok_mod  = form.labelForField(cmb_lok_modell)

        def _set_vis(paare, sichtbar):
            for w, lbl in paare:
                w.setVisible(sichtbar)
                if lbl:
                    lbl.setVisible(sichtbar)

        def toggle():
            akt = cmb_anbieter.currentData()
            _set_vis([(e_or_key, lbl_or_key), (cmb_or_modell, lbl_or_mod)],
                     akt == "openrouter")
            _set_vis([(e_anth_key, lbl_anth_key), (cmb_anth_modell, lbl_anth_mod)],
                     akt == "anthropic")
            _set_vis([(row_lok_url, lbl_lok_url), (e_lok_key, lbl_lok_key),
                      (cmb_lok_modell, lbl_lok_mod)], akt == "lokal")
            e_sprachen.setPlainText(
                self._rueck_sprachen_wert if is2
                else self._sprachen_werte.get(akt, ""))

        cmb_anbieter.currentIndexChanged.connect(toggle)

        # Widget-Referenzen auf self ablegen
        if is2:
            self._cmb_rueck_anbieter   = cmb_anbieter
            self._e_rueck_or_key       = e_or_key
            self._e_rueck_anth_key     = e_anth_key
            self._e_rueck_lok_url      = e_lok_url
            self._e_rueck_lok_key      = e_lok_key
            self._cmb_rueck_or_modell  = cmb_or_modell
            self._cmb_rueck_anth_modell = cmb_anth_modell
            self._cmb_rueck_lok_modell = cmb_lok_modell
            self._e_rueck_sprachen     = e_sprachen
            self._toggle_rueck         = toggle
        else:
            self._cmb_anbieter    = cmb_anbieter
            self._e_or_key        = e_or_key
            self._e_anth_key      = e_anth_key
            self._e_lok_url       = e_lok_url
            self._e_lok_key       = e_lok_key
            self._cmb_or_modell   = cmb_or_modell
            self._cmb_anth_modell = cmb_anth_modell
            self._cmb_lok_modell  = cmb_lok_modell
            self._e_sprachen      = e_sprachen
            self._toggle1         = toggle

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

    def _lokal_url_testen_impl(self, e_url: QLineEdit, key_feld: str, e_key: QLineEdit):
        url = e_url.text().strip()
        if not url:
            zeige_warnung(self, _("msg.hinweis"), _("firma.ki.msg.keine_url"))
            return
        api_key = self._key_wert(key_feld, e_key)
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
            return ("lokal",
                    self._key_wert(pfx + "lokal_api_key", self._e_lok_key),
                    self._e_lok_url.text().strip(),
                    self._cmb_lok_modell.currentText().strip())
        anbieter = self._cmb_rueck_anbieter.currentData()
        if anbieter == "openrouter":
            return ("openrouter",
                    self._key_wert(pfx + "openrouter_api_key", self._e_rueck_or_key), "",
                    self._cmb_rueck_or_modell.currentText().strip())
        if anbieter == "anthropic":
            return ("anthropic",
                    self._key_wert(pfx + "anthropic_api_key", self._e_rueck_anth_key), "",
                    self._cmb_rueck_anth_modell.currentText().strip())
        return ("lokal",
                self._key_wert(pfx + "lokal_api_key", self._e_rueck_lok_key),
                self._e_rueck_lok_url.text().strip(),
                self._cmb_rueck_lok_modell.currentText().strip())

    def _alle_modell_combos(self, llm_nr: int = 1):
        """Alle drei Modell-Combos der LLM-Gruppe (openrouter/anthropic/lokal)."""
        if llm_nr == 1:
            return (self._cmb_or_modell, self._cmb_anth_modell, self._cmb_lok_modell)
        return (self._cmb_rueck_or_modell, self._cmb_rueck_anth_modell,
                self._cmb_rueck_lok_modell)

    def _aktive_modell_combo(self, llm_nr: int = 1):
        if llm_nr == 1:
            return {"openrouter": self._cmb_or_modell,
                    "anthropic": self._cmb_anth_modell,
                    }.get(self._cmb_anbieter.currentData(), self._cmb_lok_modell)
        return {"openrouter": self._cmb_rueck_or_modell,
                "anthropic": self._cmb_rueck_anth_modell,
                }.get(self._cmb_rueck_anbieter.currentData(), self._cmb_rueck_lok_modell)

    # ── Modelle abrufen ───────────────────────────────────────────────────

    def _modelle_abrufen(self, llm_nr: int = 1):
        anbieter, api_key, basis_url, _ignored = self._aktive_cfg(llm_nr)
        try:
            QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            modelle = ki_client.liste_modelle(anbieter, api_key, basis_url)
        except Exception as ex:
            QGuiApplication.restoreOverrideCursor()
            zeige_fehler(self, _("msg.fehler"),
                         _("firma.ki.msg.modelle_fehler", detail=str(ex)))
            return
        finally:
            QGuiApplication.restoreOverrideCursor()

        if not modelle:
            zeige_warnung(self, _("msg.hinweis"), _("firma.ki.msg.keine_modelle"))
            return

        combo = self._aktive_modell_combo(llm_nr)
        aktuell = combo.currentText().strip()
        dlg = ModellAuswahlDialog(self, modelle, aktuell)
        if not dlg.exec():
            return
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
        for other in self._alle_modell_combos(llm_nr):
            if other is combo:
                continue
            aktuell_other = other.currentText().strip()
            other.blockSignals(True)
            other.clear()
            other.addItems(modelle)
            if aktuell_other:
                other.setCurrentText(aktuell_other)
            other.blockSignals(False)

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
            ergebnis = ki_client.chat(anbieter, api_key, basis_url, modell, "", prompt)
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
            info = ki_client.teste_prompt_caching(anbieter, api_key, basis_url, modell)
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
        if isinstance(w, QTextEdit):
            w.setPlainText(str(v if v is not None else ""))
        elif isinstance(w, QLineEdit):
            w.setText(str(v if v is not None else ""))
        elif isinstance(w, QCheckBox):
            w.setChecked(bool(v) and str(v) not in ("0", "False"))
        elif isinstance(w, QComboBox):
            if getattr(w, '_data_mode', False):
                idx = w.findData(str(v or ""))
                w.setCurrentIndex(idx if idx >= 0 else 0)
            else:  # editierbare Modell-Combo
                w.setCurrentText(str(v or ""))

    def _connect_dirty(self):
        for w in self._felder.values():
            if isinstance(w, QLineEdit):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))
            elif isinstance(w, QTextEdit):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))
            elif isinstance(w, QCheckBox):
                w.stateChanged.connect(lambda: self._save_bar.set_dirty(True))
            elif isinstance(w, QComboBox):
                w.currentIndexChanged.connect(lambda: self._save_bar.set_dirty(True))
                if w.isEditable():
                    w.editTextChanged.connect(lambda: self._save_bar.set_dirty(True))

    def _snapshot(self):
        self._saved_data = {k: self._value(w) for k, w in self._felder.items()}

    def _restore(self):
        for k, w in self._felder.items():
            w.blockSignals(True)
            self._set_value(w, self._saved_data.get(k, ""))
            w.blockSignals(False)
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
        return data

    def _fill(self, f):
        for k, w in self._felder.items():
            if not self._admin and k in self._key_felder:
                real = str(f.get(k, "") or "")
                self._key_realwerte[k] = real
                self._set_masked(w, real)
            else:
                self._set_value(w, f.get(k, ""))
        self._sprachen_werte = {
            "openrouter": f.get("ki_openrouter_sprachen", "") or "",
            "anthropic": f.get("ki_anthropic_sprachen", "") or "",
            "lokal": f.get("ki_lokal_sprachen", "") or "",
        }
        self._rueck_sprachen_wert = f.get("ki_rueck_sprachen", "") or ""
        self._toggle1()
        self._toggle_rueck()


class ModellAuswahlDialog(settings.DialogSizeMixin, QDialog):
    """Auswahl eines Modells aus der vollständigen Anbieter-Liste (mit Filter).
    Bestätigung per OK, Doppelklick oder Enter (Listen-Dialog-Regel)."""
    HELP_ANCHOR = "firma-ki"

    def __init__(self, parent, modelle, aktuell=""):
        super().__init__(parent)
        self._modelle = list(modelle)
        self._gewaehlt = None
        self.setWindowTitle(_("firma.ki.dlg.modell_auswahl.titel"))
        self.setMinimumSize(420, 460)

        lay = QVBoxLayout(self)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText(_("firma.ki.dlg.modell_auswahl.filter"))
        self._filter.textChanged.connect(self._refresh)
        lay.addWidget(self._filter)

        self.table = QListWidget()
        self.table.doubleClicked.connect(self._ok)
        lay.addWidget(self.table, 1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("btn.ok"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self._refresh()
        self._select_aktuell(aktuell)

    def _refresh(self):
        flt = self._filter.text().strip().lower()
        self.table.clear()
        for m in self._modelle:
            if not flt or flt in m.lower():
                self.table.addItem(QListWidgetItem(m))
        if self.table.count() > 0 and self.table.currentRow() < 0:
            self.table.setCurrentRow(0)

    def _select_aktuell(self, aktuell):
        if not aktuell:
            return
        treffer = self.table.findItems(aktuell, Qt.MatchFlag.MatchExactly)
        if treffer:
            self.table.setCurrentItem(treffer[0])

    def _ok(self):
        item = self.table.currentItem()
        if item is None:
            return
        self._gewaehlt = item.text()
        self.accept()

    def gewaehltes_modell(self):
        return self._gewaehlt

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._ok()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)
