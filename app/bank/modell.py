"""Datenmodell + Fehlertypen der Bankdaten-Auflösung (IBAN → BIC/Bankname)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class BankData:
    """Aus einer IBAN aufgelöste Bankdaten."""
    bic: str
    bank_name: str
    country_code: str


class UngueltigeIBAN(ValueError):
    """IBAN besteht die (länderunabhängige) MOD-97-Prüfziffernvalidierung nicht."""


class LandNichtUnterstuetzt(Exception):
    """Für das Land der IBAN ist (noch) keine BIC/Bank-Auflösung aktiviert."""

    def __init__(self, country_code: str):
        self.country_code = country_code
        super().__init__(
            f"Bankdaten-Auflösung für Land '{country_code}' ist nicht aktiviert.")
