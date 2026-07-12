"""IBAN-Normalisierung, MOD-97-Validierung (länderunabhängig, offline) und die
Orchestrierung der Bankdaten-Auflösung."""
from schwifty import IBAN as _SchwiftyIBAN

from .modell import BankData, UngueltigeIBAN
from .provider import get_provider


def normalisiere(iban: str) -> str:
    """Leerzeichen/Tabs entfernen, Großbuchstaben. Leerer Eingabe → ''."""
    return "".join((iban or "").split()).upper()


def validiere_iban(iban: str) -> bool:
    """Länderunabhängige MOD-97-Prüfziffernvalidierung (offline). Vorstufe vor jeder
    Provider-Anfrage — filtert Tippfehler ab. Leere/kaputte Eingabe → False."""
    n = normalisiere(iban)
    if not n:
        return False
    try:
        return bool(_SchwiftyIBAN(n, allow_invalid=True).is_valid)
    except Exception:                                              # noqa: BLE001
        return False


def resolve_bankdaten(iban: str) -> "BankData | None":
    """IBAN normalisieren → MOD-97 prüfen → Provider des Landes befragen.

    Wirft `UngueltigeIBAN` (Prüfziffer falsch) bzw. `LandNichtUnterstuetzt` (kein aktiver
    Provider für das Land). Rückgabe `None` = gültige, unterstützte IBAN **ohne**
    Registry-Zuordnung (z. B. Bank nicht in der Datei)."""
    n = normalisiere(iban)
    if not validiere_iban(n):
        raise UngueltigeIBAN(n)
    return get_provider(n[:2]).resolve(n)
