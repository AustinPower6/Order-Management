"""Firma-Tabs fuer den Firmenstamm-Dialog.

Exportiert die gleichen Symbole wie das alte mod_firma_tabs_einfach Modul,
damit bestehende Imports weiterhin funktionieren."""

from .mod_firma_adresse import AdresseTab
from .mod_firma_email import EmailTab, ParameterTab
from .mod_firma_geschaeftsjahre import GeschaeftjahresTab
from .mod_firma_unterschriften import UnterschriftenTab
from .mod_firma_exemplare import ExemplareTab
from .mod_firma_pfade import PfadeTab
from .mod_firma_nummernkreise import NummernkreiseTab

__all__ = [
    "AdresseTab", "EmailTab", "ParameterTab", "GeschaeftjahresTab",
    "UnterschriftenTab", "ExemplareTab", "PfadeTab", "NummernkreiseTab",
]
