"""Standardtexte für neu angelegte Firmen (Texte Belege + Texte E-Mail).

Liest die Werte aus language.json über i18n._() — die aktive Sprache
(i18n.current()) bestimmt automatisch, welches Textpaket verwendet wird.
"""
from i18n import _

_TYPEN = (
    "angebot", "auftrag", "lieferschein", "rechnung",
    "mahnung", "mahnung_1", "mahnung_2", "mahnung_letzte",
)


def get_firma_defaults() -> dict:
    """Gibt das Standardtext-Dict für die aktuell aktive Sprache zurück."""
    result = {}
    for typ in _TYPEN:
        result[f"default_text_oben_{typ}"]  = _(f"firma.neu.std.oben.{typ}")
        result[f"default_text_unten_{typ}"] = _(f"firma.neu.std.unten.{typ}")
        result[f"email_betreff_{typ}"]      = _(f"firma.neu.email.betreff.{typ}")
        result[f"email_text_{typ}"]         = _(f"firma.neu.email.text.{typ}")
    for utyp in ("angebot", "auftrag", "lieferschein", "rechnung", "mahnung"):
        result[f"unterschrift_ortdatum_{utyp}"] = _("firma.unterschriften.ortdatum_default")
    result["grussformel_hoeflich"]   = _("firma.neu.grussformel.hoeflich")
    result["grussformel_streitfall"] = _("firma.neu.grussformel.streitfall")
    return result
