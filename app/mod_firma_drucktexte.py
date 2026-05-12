from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
                             QScrollArea, QGroupBox, QLabel)
from spellcheck import SpellCheckLineEdit


class DrucktexteTab(QWidget):
    def __init__(self):
        super().__init__()
        self._felder = {}
        self._build()

    def _txt_row(self, layout, key, lbl, default=""):
        e = SpellCheckLineEdit()
        e.setPlaceholderText(default)
        layout.addRow(lbl, e)
        self._felder[key] = e

    def _build(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(8, 8, 8, 8)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(10)

        def grp(title):
            g = QGroupBox(title)
            l = QFormLayout(g)
            scroll_layout.addWidget(g)
            return g, l

        # Beleginfo
        g, l = grp("Beleginfo")
        self._txt_row(l, "txt_erstellungsdatum", "Erstellungsdatum:", "Erstellungsdatum:")
        self._txt_row(l, "txt_lieferdatum", "Lieferdatum:", "Lieferdatum:")
        self._txt_row(l, "txt_gueltig_bis", "Gültig bis:", "Gültig bis:")
        self._txt_row(l, "txt_fallig_am", "Fällig am:", "Fällig am:")
        self._txt_row(l, "txt_zahlungskondition", "Zahlungskondition:", "Zahlungskondition:")
        self._txt_row(l, "txt_mahnstufe", "Mahnstufe:", "Mahnstufe:")
        self._txt_row(l, "txt_betreff", "Betreff:", "Betreff:")

        # Positionentabelle
        g, l = grp("Positionentabelle")
        self._txt_row(l, "txt_pos_pos", "Pos.-Nr.:", "Pos.")
        self._txt_row(l, "txt_pos_bez", "Bezeichnung:", "Bezeichnung")
        self._txt_row(l, "txt_pos_menge", "Menge:", "Menge")
        self._txt_row(l, "txt_pos_einh", "Einheit:", "Einh.")
        self._txt_row(l, "txt_pos_einzelpreis", "Einzelpreis:", "Einzelpreis")
        self._txt_row(l, "txt_pos_mwst", "MwSt-Spalte:", "MwSt %")
        self._txt_row(l, "txt_pos_betrag", "Betrag:", "Betrag")
        self._txt_row(l, "txt_pos_rabatt", "Rabatt:", "(Rabatt {pct} %)")

        # MwSt-Zusammenfassung
        g, l = grp("MwSt-Zusammenfassung")
        self._txt_row(l, "txt_netto_gesamt", "Netto gesamt:", "Nettobetrag gesamt:")
        self._txt_row(l, "txt_netto_satz", "Netto pro Satz:", "Netto ({satz} % {bez}):")
        self._txt_row(l, "txt_mwst_satz", "MwSt pro Satz:", "MwSt. {satz} %:")
        self._txt_row(l, "txt_mwst_steuerfrei", "Steuerfrei:", "MwSt. 0 % (steuerfrei):")
        self._txt_row(l, "txt_brutto_gesamt", "Brutto gesamt:", "Gesamtbetrag (brutto):")

        # Fußzeile
        g, l = grp("Fußzeile")
        self._txt_row(l, "txt_bankverbindung", "Bank:", "Bankverbindung:")
        self._txt_row(l, "txt_iban", "IBAN:", "IBAN:")
        self._txt_row(l, "txt_bic", "BIC:", "BIC:")
        self._txt_row(l, "txt_ust_id", "USt-IdNr.:", "USt.-ID-Nr.:")

        # Header
        g, l = grp("Header")
        self._txt_row(l, "txt_telefon", "Telefon-Label:", "Telefon")
        self._txt_row(l, "txt_telefax", "Telefax-Label:", "Telefax")

        # Unterschrift
        g, l = grp("Unterschrift")
        self._txt_row(l, "txt_ort_datum", "Ort/Datum:", "Ort, Datum")

        # Journal-Spalten
        g, l = grp("Journal-Spalten")
        self._txt_row(l, "txt_journal_nr", "Beleg-Nr.:", "Nr.")
        self._txt_row(l, "txt_journal_datum", "Datum:", "Datum")
        self._txt_row(l, "txt_journal_kunde", "Kunde:", "Kunde")
        self._txt_row(l, "txt_journal_netto", "Netto:", "Netto")
        self._txt_row(l, "txt_journal_mwst", "MwSt:", "MwSt")
        self._txt_row(l, "txt_journal_brutto", "Brutto:", "Brutto")
        self._txt_row(l, "txt_journal_status", "Status:", "Status")
        self._txt_row(l, "txt_journal_summe", "Summe:", "Summe")

        # Exemplare
        g, l = grp("Exemplare")
        self._txt_row(l, "txt_ex_kundenkopie", "Kundenkopie:", "Kundenkopie")
        self._txt_row(l, "txt_ex_original", "Original:", "Original")
        self._txt_row(l, "txt_ex_kopie", "Kopie:", "{n}. Kopie")

        # Belegtypen-Namen
        g, l = grp("Belegtypen-Namen")
        self._txt_row(l, "txt_typ_angebot", "Angebot:", "Angebot")
        self._txt_row(l, "txt_typ_auftrag", "Auftrag:", "Auftrag")
        self._txt_row(l, "txt_typ_lieferschein", "Lieferschein:", "Lieferschein")
        self._txt_row(l, "txt_typ_rechnung", "Rechnung:", "Rechnung")
        self._txt_row(l, "txt_typ_mahnung", "Mahnung:", "Mahnung")

        # Journal-Namen
        g, l = grp("Journal-Namen")
        self._txt_row(l, "txt_journal_typ_angebot", "Angebotsbuch:", "Angebotsbuch")
        self._txt_row(l, "txt_journal_typ_auftrag", "Auftragsbuch:", "Auftragsbuch")
        self._txt_row(l, "txt_journal_typ_lieferschein", "Lieferscheinbuch:", "Lieferscheinbuch")
        self._txt_row(l, "txt_journal_typ_rechnung", "Rechnungsbuch:", "Rechnungsbuch")
        self._txt_row(l, "txt_journal_typ_mahnung", "Mahnungsbuch:", "Mahnungsbuch")

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        main_lay.addWidget(scroll)

    def load(self, f):
        for key, e in self._felder.items():
            e.setText(f.get(key, "") or "")
