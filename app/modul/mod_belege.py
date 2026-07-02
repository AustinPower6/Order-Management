"""Gemeinsame Basisklassen für alle Belegtypen (PyQt6) — Fassade.

Der Inhalt wurde in Teilmodule aufgeteilt (Aufteilung 2026-07-02; frühere
Zerlegung: beleg_utils/beleg_kette/beleg_dialoge):

- beleg_liste.py    BelegListeFenster + Belegtyp-Zuordnungstabellen
- beleg_edit.py     BelegEditDialog
- beleg_igl.py      gemeinsame igL-Logik (Liste + Dialog, UI-frei)
- beleg_utils.py    Widgets/Helfer (DatumEdit, Spalten speichern, Locks, …)
- beleg_kette.py    Belegketten-Aufbau + BelegketteDialog
- beleg_dialoge.py  PositionenEditor, KundeAuswahlDialog

Diese Fassade re-exportiert alle bisherigen Namen, damit bestehende Aufrufer
(`from .mod_belege import …`) unverändert funktionieren. Neue Aufrufer sollen
direkt aus den Teilmodulen importieren.
"""
from .beleg_utils import (
    MarkerTextEdit as MarkerTextEdit,
    _id_col_visible as _id_col_visible,
    _locks_col_visible as _locks_col_visible,
    _format_lock as _format_lock,
    _apply_lock_style as _apply_lock_style,
    _check_beleg_stale as _check_beleg_stale,
    _beleg_stale_info as _beleg_stale_info,
    _frage_ungespeicherte_anderungen as _frage_ungespeicherte_anderungen,
    _apply_saved_columns as _apply_saved_columns,
    _connect_save_columns as _connect_save_columns,
    DatumEdit as DatumEdit,
    _EscRejectFilter as _EscRejectFilter,
)
from .beleg_kette import (
    build_chain_data as build_chain_data,
    lebende_nachfolger as lebende_nachfolger,
    BelegketteDialog as BelegketteDialog,
)
from .beleg_dialoge import (
    PositionenEditor as PositionenEditor,
    KundeAuswahlDialog as KundeAuswahlDialog,
)
from .beleg_igl import (
    igl_klasse as igl_klasse,
    IglBelegKontext as IglBelegKontext,
    kunde_qualifiziert_fuer_igl as kunde_qualifiziert_fuer_igl,
)
from .beleg_liste import (
    _save_sort as _save_sort,
    _restore_sort as _restore_sort,
    _TABLE_FROM_GET_ALL as _TABLE_FROM_GET_ALL,
    _MODUL_FROM_TABLE as _MODUL_FROM_TABLE,
    BELEG_TYPS as BELEG_TYPS,
    _DB_GET_ALL_MAP as _DB_GET_ALL_MAP,
    BelegListeFenster as BelegListeFenster,
)
from .beleg_edit import BelegEditDialog as BelegEditDialog
