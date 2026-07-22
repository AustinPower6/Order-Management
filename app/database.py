"""Datenbankschicht — Facade ueber Mixin-Module.

Importiert die Module-level Funktionen und Konstanten aus db.db_utils,
so dass bestehende Importe weiter funktionieren:
    from database import Database, DB_PATH, heute, ...
"""
# Module-level exports (Kompatibilitaet)
from db.db_utils import (
    DB_PATH,
    _LOCK_TABELLEN,
    heute,
    _get_beleg_datum,
    _set_beleg_datum,
    _get_test_mode,
    _set_test_mode,
)

from db.db_core import DBCoreMixin
from db.db_firma import DBFirmaMixin
from db.db_kunden import DBKundenMixin
from db.db_artikel import DBArtikelMixin
from db.db_config import DBConfigMixin
from db.db_belegzaehler import DBBelegzaehlerMixin
from db.db_belege import DBBelegeMixin
from db.db_emails import DBEmailsMixin
from db.db_buchungsexport import DBBuchungsExportMixin
from db.db_laender import DBLaenderMixin
from db.db_adress import DBAdressMixin
from db.db_benutzer import DBBenutzerMixin
from db.db_kommunikation import DBKommunikationMixin

# Re-Exporte fuer bestehende `from database import ...`-Aufrufe
__all__ = [
    "Database", "DB_PATH", "_LOCK_TABELLEN", "heute",
    "_get_beleg_datum", "_set_beleg_datum", "_get_test_mode", "_set_test_mode",
]


class Database(DBCoreMixin, DBFirmaMixin, DBKundenMixin,
               DBArtikelMixin, DBConfigMixin,
               DBBelegzaehlerMixin, DBBelegeMixin, DBEmailsMixin,
               DBBuchungsExportMixin, DBLaenderMixin, DBAdressMixin,
               DBBenutzerMixin, DBKommunikationMixin):
    def __init__(self):
        self._init_db()
