"""Datenbank-Mixin-Pakete.

Exportiert die gleichen Symbole wie die ehemaligen Root-Module,
damit bestehende Imports weiter funktionieren."""

from .db_utils import (
    DB_PATH,
    _LOCK_TABELLEN,
    heute,
    _get_beleg_datum,
    _set_beleg_datum,
    _get_test_mode,
    _set_test_mode,
)
from .db_core import DBCoreMixin
from .db_firma import DBFirmaMixin
from .db_kunden import DBKundenMixin
from .db_artikel import DBArtikelMixin
from .db_config import DBConfigMixin
from .db_belegzaehler import DBBelegzaehlerMixin
from .db_belege import DBBelegeMixin
from .db_emails import DBEmailsMixin

__all__ = [
    "DB_PATH", "_LOCK_TABELLEN", "heute",
    "_get_beleg_datum", "_set_beleg_datum",
    "_get_test_mode", "_set_test_mode",
    "DBCoreMixin", "DBFirmaMixin", "DBKundenMixin",
    "DBArtikelMixin", "DBConfigMixin",
    "DBBelegzaehlerMixin", "DBBelegeMixin", "DBEmailsMixin",
]
