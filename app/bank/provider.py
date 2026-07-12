"""Provider-Abstraktion für die IBAN→BIC/Bank-Auflösung.

DE läuft rein **offline** über `schwifty` (die BLZ steckt in einer deutschen IBAN,
Stellen 5–12; schwifty bündelt die Bank-Registry). Für die spätere Auslandsaktivierung
gibt es einen austauschbaren Provider hinter einem gemeinsamen Interface — dann muss
nur ein zweiter Provider dazugeschaltet werden (Länder-Whitelist), ohne Umbau.

Hinweis: schwiftys Registry deckt offline auch etliche Nicht-DE-Länder ab. Bewusst wird
hier trotzdem nur DE über den Offline-Provider bedient; weitere Länder laufen erst nach
Freischaltung über `ENABLED_FOREIGN_COUNTRIES` (und eine konkrete Provider-Implementierung).
"""
from typing import Protocol

from schwifty import IBAN as _SchwiftyIBAN

from .modell import BankData, LandNichtUnterstuetzt

# Länder (ISO-3166-1-alpha-2), für die die Auslandsauflösung aktiv ist. Leer = keine.
ENABLED_FOREIGN_COUNTRIES: set = set()


class BankDataProvider(Protocol):
    def resolve(self, iban: str) -> "BankData | None":
        ...


class GermanOfflineProvider:
    """Rein lokale DE-Auflösung über schwifty (kein Datenabfluss, keine Kosten)."""

    def resolve(self, iban: str) -> "BankData | None":
        try:
            i = _SchwiftyIBAN(iban)
        except Exception:                                          # noqa: BLE001
            return None
        return BankData(
            bic=(str(i.bic) if i.bic else ""),
            bank_name=(i.bank_name or ""),
            country_code=(i.country_code or ""))


class ForeignProvider:
    """Platzhalter/Seam für die spätere Auslandsauflösung (z. B. selbst gehostetes
    openiban/goiban oder eine REST-API, per `ENABLED_FOREIGN_COUNTRIES` aktivierbar).
    Aktuell nicht implementiert → liefert `None`."""

    def resolve(self, iban: str) -> "BankData | None":
        return None


def get_provider(country_code: str) -> BankDataProvider:
    """Passenden Provider zum Länderkürzel liefern. Unbekanntes/inaktives Land →
    `LandNichtUnterstuetzt`."""
    cc = (country_code or "").upper()
    if cc == "DE":
        return GermanOfflineProvider()
    if cc in ENABLED_FOREIGN_COUNTRIES:
        return ForeignProvider()
    raise LandNichtUnterstuetzt(cc)
