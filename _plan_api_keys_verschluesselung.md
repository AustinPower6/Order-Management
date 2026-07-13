# Plan: API-Keys/Secrets aus der DB in verschlüsselte Pro-Firma-Dateien verlagern (Key-Store + DB v71)

## Kontext

Das GitHub-Repo ist **öffentlich** (bleibt so, Walter-Entscheidung). Die Secrets (API-Keys,
Passwörter) liegen heute im Klartext in der DB — und damit auch im JSON-DB-Export. Walter will
sie in **je Firma eine eigene, verschlüsselte Datei** verlagern, die nie auf GitHub landen kann.

**Sicherheits-Befund (verifiziert):** Die 2026-06-01–03 committete `auftragsabwicklung.db` war
in allen Commits der **leere 0-Byte-Blob** — es sind nie Keys/Kundendaten auf GitHub gelangt.
**Keine Key-Rotation nötig.**

**Walter-Entscheidungen (2026-07-13):**
- **Alle** Secrets verlagern (11 firma-Spalten + `firma_ki_lokal.api_key`, Liste unten).
- **Je Firma eine Datei**, **verschlüsselt**.
- Verschlüsselungs-Passwort: **auto-generiert**, Ablage in neuer DB-Spalte
  **`firma.api_keys_passwort`** (Muster Signatur-Zertifikat-Passwort), **nie in der UI sichtbar**.
- **Reset nur über Löschen der Datei:** fehlt die Datei, wird beim nächsten Speichern ein
  **neues** Passwort erzeugt, eine leere Datei verschlüsselt angelegt und anschließend wieder
  mit (neu erfassten) Keys gefüllt.
- Dateien dürfen nicht auf GitHub gepusht werden (.gitignore).

## Umfang: die 12 Secret-Speicherorte

Tabelle `firma` (Spalten bleiben als leere Alt-Spalten im Schema):
`brevo_api_key`, `gmail_app_password`, `signatur_cert_passwort`, `smtp_password`,
`adress_google_api_key`, `ki_openrouter_api_key`, `ki_lokal_api_key`, `ki_anthropic_api_key`,
`ki_rueck_openrouter_api_key`, `ki_rueck_lokal_api_key`, `ki_rueck_anthropic_api_key`
— plus `firma_ki_lokal.api_key` (5 Slots je Firma).

## 1. Neues Modul `app/key_store.py`

(Name bewusst nicht `secrets.py` — Kollision mit Python-stdlib, das `pdf_signatur.py` nutzt.)

- **Datei je Firma:** `app/daten/api_keys_{firmen_nr}.json` (firmen_nr = unveränderliche
  Geschäftsnummer, wie bei den Pfad-Konventionen). Geteilt für alle Benutzer (liegt wie die DB
  im gemeinsamen `app/daten/`).
- **Verschlüsselung:** `cryptography` (bereits Dependency) — **Fernet** (AES-128-CBC + HMAC),
  Schlüssel per **PBKDF2-HMAC-SHA256** aus dem Firmen-Passwort abgeleitet; Salt zufällig je
  Datei. Dateiformat: `{"salt": "<base64>", "token": "<fernet-token>"}`; der entschlüsselte
  Payload ist JSON: `{"firma": {feld: wert}, "lokal": {"1": key, …}}`.
- **API:** `neues_passwort()` (secrets.token_urlsafe), `lade(firmen_nr, passwort) -> dict`,
  `speichere(firmen_nr, passwort, daten)` (atomar: tmp + `os.replace`, Verzeichnis anlegen),
  `datei_existiert(firmen_nr)`, `loesche_datei(firmen_nr)`. `SECRET_FELDER` = frozenset der
  11 firma-Spalten (Single Source für db_firma, db_importexport, Migration).
- **Fehlerfälle (Fallback-Tracking-Regel — nie still):**
  - Datei fehlt → leere Secrets (kein Fehler; Reset-Weg).
  - Entschlüsselung schlägt fehl (falsches Passwort/defekt, `InvalidToken`) → leere Secrets
    **plus** `fallback_log.melde(...)`-Eintrag (Modul „Key-Store") mit Hinweis: Datei löschen =
    Reset, Keys danach im Firmenstamm neu erfassen. **Niemals** automatisch löschen.

## 2. Lebenszyklus des Passworts (automatisch, nie sichtbar)

- **Beim Schreiben** (`save_firma`/`save_firma_ki_lokal` mit Secret-Feldern, sowie Migration):
  Existiert kein Passwort in `firma.api_keys_passwort` **oder fehlt die Datei** → neues
  Passwort erzeugen, in die DB-Spalte schreiben, Datei frisch verschlüsselt anlegen
  (Walter-Reset-Weg: gelöschte Datei ⇒ neues Passwort ⇒ leere Datei ⇒ neu befüllen).
- **Beim Lesen**: nie schreiben; fehlende Datei = leere Keys.
- Das Passwort erscheint **nirgends** in der UI; es gibt keinen Anzeige-/Kopierweg.

## 3. Transparente Umleitung in `app/db/db_firma.py` (Aufrufer bleiben unverändert)

Verifiziert: alle ~90 `get_firma`-Aufrufer greifen per Spaltenname zu (`dict(f)`/`f.get`) →
Rückgabe darf von `sqlite3.Row` auf **dict** wechseln.

- **`get_firma`** (`db_firma.py:10`): Row → dict; mit `firmen_nr` + `api_keys_passwort` aus der
  Zeile `key_store.lade(...)` und die Secrets hineinmergen. `api_keys_passwort` selbst wird aus
  dem zurückgegebenen dict **entfernt** (kein Leser braucht es; UI-Tabs zeigen es so nie).
- **`save_firma`** (`db_firma.py:29`): Secret-Felder poppen → Passwort-Lebenszyklus (oben) →
  `key_store.speichere(...)` (Merge mit Bestandsdaten der Datei); DB-Spalten bleiben ''.
  `api_keys_passwort` wird nie von außen gesetzt (aus data strippen).
- **`get_firma_ki_lokal`** / **`save_firma_ki_lokal`** (`db_firma.py:50/67`): `api_key` je Slot
  aus dem `lokal`-Teil der Datei mergen bzw. dorthin abzweigen; DB-Spalte bleibt ''.
- **`copy_firma`** (`db_firma.py:399`): Quell-Datei mit Quell-Passwort entschlüsseln, für die
  neue Firma **neues Passwort** erzeugen und neu verschlüsselt schreiben; die Spalte
  `api_keys_passwort` nicht 1:1 mitkopieren.
- **Firma hart löschen**: `key_store.loesche_datei(firmen_nr)` ergänzen.

Damit funktionieren **ohne Änderung** weiter: `ki_client.firma_cfg` (ki_client.py:107-116),
Rück-LLM-Remap (uebersetzung.py:645-653), Brevo/Gmail/SMTP (email_provider_mixin.py:314/489/512),
PDF-Signatur (pdf_signatur.py:130/193), Adressprüfung (mod_kunden.py, mod_firma_adresspruefung.py),
alle Firmenstamm-Tabs inkl. Admin-Maskierung (mod_firma_ki.py, mod_firma_email.py,
mod_firma_steuerung.py — schreibt `signatur_cert_passwort` via save_firma → landet in der Datei).

## 4. Status-Anzeige im Firmenstamm (kein Passwort, nur Zustand)

Firmenstamm → Parameter → **Steuerung** (neben dem Zertifikat-Status, gleiche Optik): eine
Status-Zeile **„Schlüsseldatei (API-Keys)"** — `vorhanden (verschlüsselt)` /
`fehlt — wird beim nächsten Speichern eines Keys neu angelegt` / `defekt — Datei löschen und
Keys neu erfassen` (rot, `theme.error_text_style()`). Neue i18n-Keys `firma.steuerung.keydatei_*`
(DE+EN, language.json-Formatregeln).

## 5. JSON-Import/Export absichern (`app/db_importexport.py`)

- **Export** (`:46-50`): die 11 Secret-Felder **und** `api_keys_passwort` auf `''` setzen →
  Export ist garantiert secret-frei (Datei + Passwort wandern nie zusammen).
- **Import** (`:88-94`): dieselben Felder aus Import-Daten strippen (alte Exporte mit Keys
  legen nichts zurück in die DB; das vorhandene Passwort der Ziel-DB bleibt erhalten).

## 6. Migration DB v71 (`app/DB-Pflege.py` + `app/db/db_schema.py` — STRENGE REGEL: beide Stellen)

- **Schema:** neue Spalte `firma.api_keys_passwort TEXT DEFAULT ''` (beide Stellen).
- **Daten** (in `_to_v70`-Manier idempotent): je Firma mit mindestens einem nicht-leeren
  Secret: Passwort erzeugen → `api_keys_{firmen_nr}.json` verschlüsselt schreiben (firma- +
  lokal-Teil aus `firma_ki_lokal`) → alle 12 Quell-Spalten per UPDATE auf `''`.
  Zweiter Lauf = No-op (alles leer).
- `CURRENT_VERSION = 71`, MIGRATIONEN-Eintrag, Header-Changelog („Nächste freie: v72").
- **Hinweis:** Das Auto-DB-Backup vor der Migration (`…db.70`) enthält letztmals Klartext-Keys —
  lokal + gitignoriert; im DEVLOG vermerken.

## 7. `.gitignore` + Doku

- `.gitignore`: **`app/daten/api_keys_*.json`** ergänzen (bestehende Muster decken .json nicht ab).
- **`Readme.admin.de.md`/`.en.md`:** neuer Abschnitt — Secrets liegen seit v71 verschlüsselt in
  `app/daten/api_keys_{firmen_nr}.json` (nicht versioniert): in die **Datensicherung** aufnehmen
  (zusammen mit der DB — Datei ohne DB-Passwort ist nutzlos, DB ohne Datei hat keine Keys),
  bei Umzug mitkopieren; **Reset**: Datei löschen → neues Passwort + leere Datei beim nächsten
  Speichern, Keys neu erfassen; nach JSON-Import Keys ggf. neu erfassen.
- **`DOKU-TODO.md`:** Punkt für `doku.de.html` (KI-Anbindung, E-Mail-Einrichtung, Datenbank &
  Sicherung, Firmenstamm→Steuerung-Status).

## 8. Tests (`app/test_key_store.py`, Muster test_pruefung_parser — Temp-Verzeichnis)

Roundtrip verschlüsseln/entschlüsseln (firma- + lokal-Teil), falsches Passwort → leere Keys
(kein Crash), fehlende Datei → leer, defekte Datei → leer, `speichere` mergt mit Bestand,
atomares Schreiben (gültiges JSON mit salt/token, Klartext-Key taucht **nicht** im Dateiinhalt
auf), zwei `neues_passwort()` sind verschieden. (Redirect-Logik in db_firma wird über die
App-Verifikation geprüft — `Database` ist fest auf DB_PATH verdrahtet.)

## 9. Ablauf / Kadenz

1. Kein Anfangs-Commit (Working Tree sauber).
2. key_store → db_firma-Umleitung → Import/Export → Migration v71 (beide Stellen) →
   Steuerung-Status + i18n → .gitignore → Readme → Tests.
3. **Migration nie manuell** — läuft beim App-Start (`python Order-Management.py`).
4. End-Commit + DEVLOG + DOKU-TODO, danach push.

## Verifikation

- `python -m ruff check app`; `py_compile`; `python app/audit_firma_id.py` unverändert sauber
- `python app/test_key_store.py` grün; `test_address_validation.py` weiter 22/22
- App-Start → Migration v71; Prüfskript (read-only, gibt keine Werte aus): alle 12
  Secret-Spalten in allen Firmen leer; je Firma mit Keys existiert `api_keys_{firmen_nr}.json`;
  Dateiinhalt enthält **keinen** Klartext-Key (nur salt/token); `api_keys_passwort` gefüllt
- Funktions-Smoke (Firma 990): Firmenstamm→KI zeigt Keys (maskiert für Nicht-Admins), „Test
  LLM" läuft; Key speichern → landet verschlüsselt in der Datei, DB-Spalte bleibt leer;
  **Reset-Weg**: Datei löschen → Status „fehlt" in Steuerung → Key neu speichern → neue Datei
  mit neuem Passwort; JSON-Export: keine Secret-Werte, kein Passwort
- `git check-ignore app/daten/api_keys_990.json` → ignoriert
