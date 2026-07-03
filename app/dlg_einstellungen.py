"""Einstellungen-Dialog des Hauptfensters (Hamburger-Menü → Einstellungen).

1:1 aus `main.py::_open_settings` ausgelagert (Refactoring 2026-07, Schritt 6).
`open_settings(win)` arbeitet auf dem `MainWindow` (`win`): es liest/schreibt die
Benutzer-Einstellungen (`settings.py`), den Test-Modus (DB) und aktualisiert bei
Bedarf offene Tabs des Fensters.
"""
from PyQt6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
                             QLabel, QLineEdit, QVBoxLayout)

from database import _get_test_mode, _set_test_mode
from modul.mod_belege import _EscRejectFilter
from i18n import _
import lock_manager
import settings


def open_settings(win):
    """Einstellungen-Dialog: Admin-Einstellungen."""
    dlg = QDialog(win)
    dlg.setWindowTitle(_("dlg.settings.title"))
    dlg.setFixedSize(360, 435)
    lay = QVBoxLayout(dlg)

    form = QFormLayout()
    form.setVerticalSpacing(6)

    satz_id_cb = QCheckBox(_("settings.satz_id"))
    satz_id_cb.setChecked(settings.get_satz_id_anzeigen())
    form.addRow("", satz_id_cb)

    locks_cb = QCheckBox(_("settings.locks"))
    locks_cb.setChecked(settings.get_locks_anzeigen())
    form.addRow("", locks_cb)

    gel_cb = QCheckBox(_("settings.show_deleted"))
    gel_cb.setChecked(settings.get_show_deleted_firmen())
    form.addRow("", gel_cb)

    test_cb = QCheckBox(_("settings.test_mode"))
    test_cb.setToolTip(_("settings.test_mode.tip"))
    test_cb.setChecked(_get_test_mode())
    form.addRow("", test_cb)

    # Nur Admins: Firma löschen/kopieren + Lade-Anzeige
    if lock_manager.ist_admin():
        form.addRow(QLabel(""))  # Abstand
        loeschen_cb = QCheckBox(_("settings.loeschen_aktiv"))
        loeschen_cb.setChecked(settings.get_loeschen_aktiv())
        form.addRow("", loeschen_cb)

        kopieren_cb = QCheckBox(_("settings.kopieren_aktiv"))
        kopieren_cb.setChecked(settings.get_kopieren_aktiv())
        form.addRow("", kopieren_cb)

        lade_overlay_cb = QCheckBox(_("settings.lade_overlay"))
        lade_overlay_cb.setChecked(settings.get_lade_overlay_aktiv())
        form.addRow("", lade_overlay_cb)

        uebersetzungstest_cb = QCheckBox(_("settings.uebersetzungstest"))
        uebersetzungstest_cb.setChecked(settings.get_uebersetzungstest_aktiv())
        form.addRow("", uebersetzungstest_cb)

        form.addRow(QLabel(""))  # Abstand
        redir_cb = QCheckBox(_("settings.email_redir"))
        redir_cb.setChecked(settings.get_email_redir_test())
        form.addRow("", redir_cb)

        redir_adr_edit = QLineEdit(settings.get_email_redir_testadresse())
        redir_adr_edit.setPlaceholderText("test@example.com")
        redir_adr_edit.setEnabled(redir_cb.isChecked())
        redir_cb.toggled.connect(redir_adr_edit.setEnabled)
        form.addRow(_("settings.email_redir_adr"), redir_adr_edit)

        form.addRow(QLabel(""))  # Abstand
        dev_email_edit = QLineEdit(settings.get_developer_email())
        dev_email_edit.setPlaceholderText("entwickler@example.com")
        form.addRow(_("settings.developer_email"), dev_email_edit)

    lay.addLayout(form)

    btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                            QDialogButtonBox.StandardButton.Cancel)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    lay.addWidget(btns)
    _EscRejectFilter(dlg).installEventFilter(dlg)

    old_satz_id = settings.get_satz_id_anzeigen()
    old_locks = settings.get_locks_anzeigen()
    old_gel = settings.get_show_deleted_firmen()
    accepted = dlg.exec()
    dlg.deleteLater()          # Dialog freigeben (sonst bleibt er als Kind am Leben)
    if accepted:
        # Satz-ID
        new_satz_id = satz_id_cb.isChecked()
        settings.set_satz_id_anzeigen(new_satz_id)

        # Locks
        new_locks = locks_cb.isChecked()
        settings.set_locks_anzeigen(new_locks)

        # Gelöschte Firmen
        new_gel = gel_cb.isChecked()
        settings.set_show_deleted_firmen(new_gel)

        # Test-Modus
        new_test = test_cb.isChecked()
        _set_test_mode(new_test)
        win._test_plus10_btn.setVisible(new_test)

        # Admin: Firma löschen/kopieren + Lade-Anzeige + E-Mail-Testumleitung
        if lock_manager.ist_admin():
            settings.set_loeschen_aktiv(loeschen_cb.isChecked())
            settings.set_kopieren_aktiv(kopieren_cb.isChecked())
            settings.set_lade_overlay_aktiv(lade_overlay_cb.isChecked())
            settings.set_uebersetzungstest_aktiv(uebersetzungstest_cb.isChecked())
            settings.set_email_redir_test(redir_cb.isChecked())
            settings.set_email_redir_testadresse(redir_adr_edit.text().strip())
            settings.set_developer_email(dev_email_edit.text().strip())

            # Firmenstamm-Buttons aktualisieren (falls offen)
            if "firma" in win._tab_mgr._keys:
                idx = win._tab_mgr._keys["firma"]
                firma_widget = win._tabs.widget(idx)
                if firma_widget and hasattr(firma_widget, "refresh_button_visibility"):
                    firma_widget.refresh_button_visibility()

        # Wenn sich die Tabelleneinstellung geändert hat, Tabs schließen
        # damit sie beim nächsten Öffnen die korrekte Tabellenstruktur haben
        if new_satz_id != old_satz_id or new_locks != old_locks:
            for i in range(win._tabs.count() - 1, -1, -1):
                win._tab_mgr.remove(i)
            if not win._tab_mgr.has_tabs():
                win._stack.setCurrentIndex(0)
