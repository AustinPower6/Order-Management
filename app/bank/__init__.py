"""Bankdaten-Auflösung: IBAN → BIC/Bankname, offline für DE (schwifty), mit
Provider-Abstraktion für die spätere Auslandsaktivierung."""
from .iban import normalisiere, resolve_bankdaten, validiere_iban
from .modell import BankData, LandNichtUnterstuetzt, UngueltigeIBAN
from .provider import (ENABLED_FOREIGN_COUNTRIES, BankDataProvider,
                       ForeignProvider, GermanOfflineProvider, get_provider)

__all__ = [
    "BankData", "UngueltigeIBAN", "LandNichtUnterstuetzt",
    "normalisiere", "validiere_iban", "resolve_bankdaten",
    "BankDataProvider", "GermanOfflineProvider", "ForeignProvider",
    "get_provider", "ENABLED_FOREIGN_COUNTRIES",
]
