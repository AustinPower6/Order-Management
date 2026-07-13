"""Adressvalidierung: Betreiber-Attestierungen (DSGVO-Gate) als Mixin + Store-Adapter.

Die Tabelle `adress_attestierungen` ist bewusst global (ohne firma_id —
Betreiber-Ebene wie db_version) und append-only ("lock instead of delete"):
es gibt nur INSERT/SELECT, ein Widerruf ist ein neuer ungültiger Eintrag
(Rechenschaftspflicht, Art. 5 Abs. 2 DSGVO).
"""
from datetime import datetime, timezone


class DBAdressMixin:
    def add_adress_attestierung(self, provider: str, confirmed_by: str, *,
                                dpa_confirmed: bool, vvt_confirmed: bool) -> None:
        """Hängt eine neue Attestierung an (append-only, nie UPDATE/DELETE)."""
        self.conn.execute(
            "INSERT INTO adress_attestierungen "
            "(provider, confirmed_by, dpa_confirmed, vvt_confirmed, confirmed_at) "
            "VALUES (?,?,?,?,?)",
            (provider, confirmed_by, int(dpa_confirmed), int(vvt_confirmed),
             datetime.now(timezone.utc).isoformat(timespec="seconds")))
        self.conn.commit()

    def get_adress_attestierung_latest(self, provider: str):
        """Die jüngste Attestierungszeile des Providers (sqlite3.Row) oder None."""
        return self.conn.execute(
            "SELECT provider, confirmed_by, dpa_confirmed, vvt_confirmed, confirmed_at "
            "FROM adress_attestierungen WHERE provider=? ORDER BY id DESC LIMIT 1",
            (provider,)).fetchone()


class DbAttestationStore:
    """DB-Repository mit der Schnittstelle von address_validation.AttestationStore.

    Adapter über die Database-Facade, damit `create_validator(config, store)`
    unverändert bleibt; die JSON-Variante in address_validation.py bleibt als
    Referenz-/Test-Implementierung bestehen.
    """

    def __init__(self, db):
        self._db = db

    def attest(self, provider: str, confirmed_by: str, *,
               dpa_confirmed: bool, vvt_confirmed: bool):
        from address_validation import Attestation
        self._db.add_adress_attestierung(
            provider, confirmed_by,
            dpa_confirmed=dpa_confirmed, vvt_confirmed=vvt_confirmed)
        row = self._db.get_adress_attestierung_latest(provider)
        return Attestation(
            provider=row["provider"], confirmed_by=row["confirmed_by"],
            dpa_confirmed=bool(row["dpa_confirmed"]),
            vvt_confirmed=bool(row["vvt_confirmed"]),
            confirmed_at=row["confirmed_at"])

    def latest_valid(self, provider: str):
        """Die jüngste Attestierung — nur wenn sie gültig ist (Widerruf zählt)."""
        from address_validation import Attestation
        row = self._db.get_adress_attestierung_latest(provider)
        if row is None:
            return None
        latest = Attestation(
            provider=row["provider"], confirmed_by=row["confirmed_by"],
            dpa_confirmed=bool(row["dpa_confirmed"]),
            vvt_confirmed=bool(row["vvt_confirmed"]),
            confirmed_at=row["confirmed_at"])
        return latest if latest.is_valid else None
