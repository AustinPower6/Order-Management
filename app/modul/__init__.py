"""Modulpaket fuer Auftragsabwicklung.

Lazy Imports, um zirkulaere Abhaengigkeiten zu vermeiden."""

__all__ = []


def __getattr__(name):
    """Importiert Symbole beim ersten Zugriff, nicht beim Modul-Load."""
    # Fenster-Klassen
    if name == "FirmaFenster":
        from .mod_firma import FirmaFenster
        return FirmaFenster
    if name == "KundenFenster":
        from .mod_kunden import KundenFenster
        return KundenFenster
    if name == "ArtikelFenster":
        from .mod_artikel import ArtikelFenster
        return ArtikelFenster
    if name == "AngeboteFenster":
        from .mod_angebote import AngeboteFenster
        return AngeboteFenster
    if name == "AuftrageFenster":
        from .mod_auftraege import AuftrageFenster
        return AuftrageFenster
    if name == "LieferscheineFenster":
        from .mod_lieferscheine import LieferscheineFenster
        return LieferscheineFenster
    if name == "RechnungenFenster":
        from .mod_rechnungen import RechnungenFenster
        return RechnungenFenster
    if name == "MahnungenFenster":
        from .mod_mahnungen import MahnungenFenster
        return MahnungenFenster
    if name == "JournalFenster":
        from .mod_journal import JournalFenster
        return JournalFenster

    # Symbole aus mod_belege
    if name in ("BelegListeFenster", "BelegEditDialog", "build_chain_data",
                "_EscRejectFilter", "_frage_ungespeicherte_anderungen",
                "_id_col_visible", "_locks_col_visible", "_format_lock",
                "_apply_lock_style", "_apply_saved_columns",
                "_connect_save_columns", "DatumEdit"):
        from . import mod_belege
        return getattr(mod_belege, name)

    # Symbole aus mod_mwst
    if name in ("KlasseDialog", "SatzDialog"):
        from . import mod_mwst
        return getattr(mod_mwst, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
