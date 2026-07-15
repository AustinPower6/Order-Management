"""Rechteprüfung: Stufenmodell je Benutzer, Firma und Programmteil.

Stufenmodell — jede Stufe schließt die niedrigeren ein:

    0 KEIN     kein Zugriff, der Programmteil ist nicht sichtbar
    1 LESEN    öffnen, ansehen, drucken
    2 AENDERN  zusätzlich neu anlegen und bearbeiten
    3 LOESCHEN zusätzlich löschen

Administratoren umgehen die Matrix (Kurzschluss in `darf`) — das verhindert,
dass sich der letzte Admin selbst aussperrt.

**Ohne aktive Anmeldung liefert `darf` immer True.** Headless-Kontexte
(DB-Pflege, Skripte, Tests) haben keine Session und sollen unverändert laufen;
die Rechteprüfung ist eine UI-Schicht, keine DB-seitige Absicherung
(bewusster Scope: lokale Desktop-App).
"""
import session
from i18n import _
from ui_widgets import zeige_warnung

KEIN = 0
LESEN = 1
AENDERN = 2
LOESCHEN = 3

STUFEN = (KEIN, LESEN, AENDERN, LOESCHEN)

# Reiter des Firmenstamms mit eigenem Recht — Reihenfolge wie im Firmenstamm.
# Der Schlüssel nach `firma_` ist zugleich der Reiter-Key in language.json
# (`firma.tab.<x>`); daraus baut `modul_label` die Beschriftung.
#
# Nicht enthalten: der MwSt-Reiter (hängt am eigenständigen Programmteil "mwst")
# und der Reiter Sperren (bleibt Administratoren vorbehalten).
FIRMA_TAB_KEYS = (
    "firma_adresse",
    "firma_steuern",
    "firma_email",
    "firma_geschaeftsjahre",
    "firma_unterschriften",
    "firma_exemplare",
    "firma_zahlungskonditionen",
    "firma_pfade",
    "firma_mahnkonditionen",
    "firma_basiszinssatz",
    "firma_parameter",
    "firma_anbindung_fibu",
    "firma_ki",
    "firma_kontenrahmen",
    "firma_layout",
    "firma_drucktexte",
    "firma_standardtexte",
    "firma_email_texte",
)

# Alle einzeln aufrufbaren Programmteile. Reihenfolge = Anzeigereihenfolge in der
# Rechte-Matrix der Benutzerverwaltung.
MODUL_KEYS = (
    "firma",
    *FIRMA_TAB_KEYS,
    "kunden",
    "artikel",
    "mwst",
    "angebote",
    "auftraege",
    "lieferscheine",
    "rechnungen",
    "mahnungen",
    "auswertungen",
    "e_rechnung_spool",
    "buchungsexport",
    "emails",
    "fallback_protokoll",
    "token_verbrauch",
    "einstellungen",
)


def stufe(db, modul_key, firma_id=None) -> int:
    """Rechtestufe des angemeldeten Benutzers für einen Programmteil.

    Ohne Session bzw. für Admins die höchste Stufe.
    """
    if session.benutzer() is None or session.ist_admin():
        return LOESCHEN
    if firma_id is None:
        import settings
        firma_id = settings.get_current_firma_id()
    return int(session.rechte(db, firma_id).get(modul_key, KEIN))


def darf(db, modul_key, mindest_stufe=LESEN, firma_id=None) -> bool:
    """True, wenn der angemeldete Benutzer mindestens `mindest_stufe` hat."""
    return stufe(db, modul_key, firma_id) >= mindest_stufe


def pruefe_mit_hinweis(parent, db, modul_key, mindest_stufe=LESEN, firma_id=None) -> bool:
    """Wie `darf`, zeigt bei fehlendem Recht zusätzlich eine Meldung.

    Für Aktionen, die der Benutzer trotz ausgegrautem/verstecktem Button
    auslösen kann (Doppelklick, Tastenkürzel, Kontextmenü).
    """
    if darf(db, modul_key, mindest_stufe, firma_id):
        return True
    if mindest_stufe <= LESEN:
        zeige_warnung(parent, _("msg.kein_recht_titel"), _("msg.kein_recht"))
    else:
        zeige_warnung(parent, _("msg.kein_recht_titel"),
                      _("msg.nur_lesen", modul=modul_label(modul_key)))
    return False


def firmenstamm_sichtbar(db, firma_id=None) -> bool:
    """True, wenn der Firmenstamm überhaupt geöffnet werden darf.

    Das Recht `firma` steuert nur noch das Anlegen/Kopieren/Löschen von Firmen —
    welche Reiter erscheinen, entscheiden die Reiter-Rechte. Das Fenster geht auf,
    sobald mindestens ein Reiter lesbar ist; zusätzlich für den, der Firmen anlegen
    darf (der „Neu"-Button sitzt im Firmenstamm, sonst käme er nicht an ihn heran).
    """
    if darf(db, "firma", AENDERN, firma_id):
        return True
    return any(darf(db, k, LESEN, firma_id)
               for k in FIRMA_TAB_KEYS + ("mwst",))


def modul_label(modul_key) -> str:
    """Anzeigename eines Programmteils (für Meldungen und die Rechte-Matrix).

    Firmenstamm-Reiter erben die Beschriftung des Reiters selbst (`firma.tab.*`),
    damit Matrix und Reiter nicht auseinanderlaufen.
    """
    if modul_key.startswith("firma_"):
        return (_("rechte.modul.firma_praefix") + " → "
                + _(f"firma.tab.{modul_key[len('firma_'):]}"))
    return _(f"rechte.modul.{modul_key}")


def stufe_label(wert) -> str:
    """Anzeigename einer Rechtestufe."""
    return _(f"rechte.stufe.{int(wert)}")
