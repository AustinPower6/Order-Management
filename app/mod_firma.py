# Refaktoriert: FirmaFenster und Tabs in separate Module ausgelagert.
# Dieses Modul exportiert weiter die gleichen Symbole für Abwärtskompatibilität.

from mod_firma_base import FirmaFenster

__all__ = ["FirmaFenster"]
