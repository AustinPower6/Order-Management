# Auftragsabwicklung - Anwenderhandbuch

**Benutzermanual fuer die tägliche Arbeit mit der Auftragsabwicklung**

---

## Inhaltsuebersicht

1. [Programm starten und stoppen](#1-programm-starten-und-stoppen)
2. [Hauptfenster - Erste orientation](#2-hauptfenster)
3. [Stammdaten pflegen](#3-stammdaten-pflegen)
4. [Workflow: Angebot -> Auftrag -> Rechnung](#4-workflow)
5. [Belege bearbeiten](#5-belege-bearbeiten)
6. [Lieferscheine](#6-lieferscheine)
7. [Mahnungen](#7-mahnungen)
8. [PDF drucken](#8-pdf-drucken)
9. [Journal / Auswertungen](#9-journal--auswertungen)
10. [Marker in Standardtexten](#10-marker)
11. [Daten importieren / exportieren](#11-daten-importieren--exportieren)
12. [Häufige Fragen](#12-häufige-fragen)

---

## 1. Programm starten und stoppen

### Starten
- Doppelklick auf `Auftragsabwicklung.bat`, oder
- `python Auftragsabwicklung.py` im Terminal

### Stoppen
- Programm wie gewohnt mit dem X-Button schliessen.
- Wenn ungespeicherte Aenderungen offen sind, werden Sie vor dem Schliessen darauf hingewiesen.

---

## 2. Hauptfenster

Das Hauptfenster besteht aus zwei Bereichen:

**Links (Sidebar):** Navigationsmenue mit allen Funktionen
- Stammdaten: Firmenstamm, Kunden, Artikel
- Belege: Angebote, Auftraege, Lieferscheine, Rechnungen, Mahnungen
- Auswertungen: Journal

**Rechts (Tab-Bereich):** Hieroeffnen sich die gewaehlten Module als Tabs.
- Mehrere Module koennen gleichzeitig offen sein.
- Tab schliessen: X-Button oder Doppelklick auf den Tab.

**Oberes Menu:** Datei-Menue mit Import/Export, Einstellungen und Exit.

---

## 3. Stammdaten pflegen

### 3.1 Firmenstamm (Stammdaten -> Firmenstamm)

Hiertragen Sie die Daten Ihres Unternehmens ein:

- **Adresse:** Firmenname, Strasse, PLZ, Ort, Telefon, E-Mail, Website
- **Steuer & Bank:** USt-IdNr., Steuernummer, Kontoinhaber, IBAN, BIC, Bankname
- **Belegnummern:** Konfiguration der Belegnummern-Zaehler fuer Angebote, Auftraege, Rechnungen usw.
- **Zahlungskonditionen:** Standardkonditionen (z. B. "30 Tage netto")
- **Mahnkonditionen:** Einstellungen fuer Mahnstufen (Frist, costs, Zinssatz)
- **MwSt-Klassen:** Steuersaetze verwalten (z. B. 19 %, 7 %)
- **Basiszinssatz:** Historische Basiszinssaetze der Bundesbank
- **Drucktexte:** Footer-Text fuer PDF-Ausdrucke
- **Standardtexte:** Vorlagen fuer Angebotstext, Rechnungstext usw. (mit Marker-Unterstuetzung)
- **Sperren:** Zugriffs-Sperren fuer einzelne Module

**Wichtig:** Firmendaten sind Pflicht vor dem Erstellen der ersten Belege.

### 3.2 Kunden (Stammdaten -> Kunden)

- **Neuer Kunde:** Button "Neuer Kunde"
- **Felder:** Anrede, Titel, Vorname, Nachname, Firmenname, Strasse, PLZ, Ort, Land, Telefon, E-Mail, Kundennummer
- **Suche:** Suchfeld oben, filtert live nach Name/Firma
- **Bearbeiten:** Zeile anklicken, Felder aendern, "Speichern"
- **Loeschen:** Zeile markieren, "Entfernen" (Soft-Delete — kann wiederhergestellt werden)

### 3.3 Artikel (Stammdaten -> Artikel)

- **Neuer Artikel:** Button "Neuer Artikel"
- **Felder:** Artikelnummer, Bezeichnung, Beschreibung, Einheitspreis, MwSt-Satz, Einheit (St, ST, KG, ML, etc.)
- **Suche:** Live-Suche im Suchfeld

---

## 4. Workflow

### Schritt 1: Angebot erstellen

1. Gehen Sie zu **Angebote** in der Sidebar.
2. Klicken Sie **"Neues Angebot"**.
3. Waehlen Sie den Kunden aus dem Dropdown.
4. Fügen Sie Positionen hinzu (Artikel auswaehlen, Menge, Preis anpassen).
5. Optional: Freitext fuer das Angebot eingeben.
6. **Speichern**.
7. Optional: **PDF drucken** — das Angebot als PDF exportieren.

### Schritt 2: Angebot zu Auftrag machen

1. Oeffnen Sie die **Angeboteliste**.
2. Markieren Sie das angenommene Angebot.
3. Klicken Sie **"-> Auftrag"**.
4. Der Angebotsstatus wechselt zu "angenommen".
5. Ein neuer Auftrag wird mit allen Positionen angelegt.
6. Im Auftrag koennen Sie die Positionen ggf. anpassen.

### Schritt 3: Auftrag zu Lieferschein

1. Oeffnen Sie die **Auftragsliste**.
2. Markieren Sie den auszuliefernden Auftrag.
3. Klicken Sie **"-> Lieferschein"**.
4. Ein Lieferschein wird mit den Auftragspositionen erstellt.

### Schritt 4: Rechnung erstellen

1. Oeffnen Sie die **Auftragsliste** (oder Lieferscheinliste).
2. Markieren Sie den abzuschliessenden Auftrag.
3. Klicken Sie **"-> Rechnung"**.
4. Der Auftragsstatus wechselt zu "abgeschlossen".
5. Die Rechnung wird mit allen Positionen erstellt.
6. **PDF drucken** — das PDF wird automatisch generiert und geoeffnet.

---

## 5. Belege bearbeiten

### Beleg oeffnen und bearbeiten

- Doppelklick auf eine Zeile in der Listenansicht, um den Beleg zu oeffnen.
- Positionen hinzufuegen: Artikel auswaehlen, Menge eingeben.
- Positionen entfernen: Zeile markieren, Loeschen-Taste oder Entfernungs-Button.
- Freitext bearbeiten: Textfeld fuer individuelle Hinweise.
- Speichern: "Speichern"-Button oder STRG+S.

### Belegnummern

- Die Belegnummer wird beim **Speichern** automatisch vergabe.
- Die angezeigte Vorschau zeigt die Nummer, die Sie erhalten werden.
- Die Zähler werden im Firmenstamm konfiguriert.

### MwSt bei Positionen

- Der MwSt-Satz wird zum Zeitpunkt des Erstellens des Belegs eingefroren.
- Wenn sich der MwSt-Satz spaeter aendert, bleiben historische Dokumente korrekt.

---

## 6. Lieferscheine

Lieferscheine werden aus Auftraegen erstellt (siehe Workflow). Auf dem Lieferschein werden keine Preise angezeigt.

- Oeffnen Sie **Lieferscheine** in der Sidebar.
- Lieferschein oeffnen, bei Bedarf anpassen.
- **PDF drucken** — Lieferschein als PDF exportieren.

---

## 7. Mahnungen

Wenn eine Rechnung nicht bezahlt wurde:

1. Gehen Sie zu **Mahnungen** in der Sidebar.
2. Suchen Sie die ausstehende Rechnung.
3. Klicken Sie **"Mahnung erstellen"**.
4. Die Mahnung wird mit der konfigurierten Mahnstufe erstellt.
5. Mahnkosten und Zinsen werden automatisch berechnet (basierend auf den Mahnkonditionen im Firmenstamm).
6. **PDF drucken** — Mahnung per E-Mail oder Post versenden.

Mehrere Mahnstufen sind moeglich (1., 2., 3. Mahnung).

---

## 8. PDF drucken

Jeder Belegtyp unterstuetzt den PDF-Druck:

- Klicken Sie den **Drucken**-Button in der Belegansicht.
- Das PDF wird automatisch im Verzeichnis `Ausdrucke/` gespeichert.
- Die Datei oeffnet sich in Ihrem Standard-PDF-Viewer.
- Dateiname: `{Typ}_{Belegnummer}.pdf`

---

## 9. Journal / Auswertungen

Uebersicht aller Belege nach Zeitraum:

1. Gehen Sie zu **Auswertungen -> Journal** in der Sidebar.
2. Waehlen Sie den Belegtyp (Angebote, Auftraege, Rechnungen, etc.).
3. Waehlen Sie Monat und Jahr.
4. Das Journal zeigt alle Belege des gewaehlten Zeitraums.
5. **PDF drucken** — das gesamte Journal als PDF exportieren.

---

## 10. Marker

In den Standardtexten (Firmenstamm -> Standardtexte) koennen Sie Platzhalter verwenden, die beim Druck automatisch ersetzt werden:

| Marker | Wird ersetzt durch |
|---|---|
| `{AN+NR}` |Angebotsnummer |
| `{AN+DATUM}` |Angebotsdatum |
| `{AU+NR}` |Auftragsnummer |
| `{AU+DATUM}` |Auftragsdatum |
| `{RE+NR}` |Rechnungsnummer |
| `{RE+DATUM}` |Rechnungsdatum |
| `{RE+GESAMT}` |Rechnungsbetrag (Gesamt) |
| `{RE+FÄLLIG}` |Faelligkeitsdatum |
| `{RE+FTAGE}` |Faelligkeitsfrist in Tagen |
| `{LS+NR}` |Lieferscheinnummer |
| `{LS+DATUM}` |Lieferschein-Datum |
| `{MA+NR}` |Mahnungsnummer |
| `{MA+DATUM}` |Mahnungsdatum |

Beispiel: "Bezugnahme auf unser Angebot `{AN+NR}` vom `{AN+DATUM}`."

---

## 11. Daten importieren / exportieren

### Exportieren (Menue -> Datei -> Daten exportieren)

- Alle Daten werden in eine JSON-Datei geschrieben.
- Verwenden Sie dies fuer Backups oder zum Uebertragen auf ein anderes System.

### Importieren (Menue -> Datei -> Daten importieren)

- Wahlen Sie eine vorher exportierte JSON-Datei aus.
- **Achtung:** Importierte Daten werden hinzugefuegt — bestehende Daten werden nicht automatisch geloescht.

---

## 12. Häufige Fragen

**Wo werden meine Daten gespeichert?**
Die Daten liegen in der Datei `app/auftragsabwicklung.db` (SQLite). Diese Datei liegt im Installationsverzeichnis.

**Kann ich Daten wiederherstellen, die ich geloeschet habe?**
Loeschungen sind "Soft-Delete" — die Daten bleiben in der Datenbank. Wenden Sie sich an den Administrator fuer eine Wiederherstellung.

**Was passiert, wenn sich der MwSt-Satz aendert?**
Jede Position speichert den MwSt-Satz zum Zeitpunkt ihrer Entstehung. Eine Aenderung des Satzes betrifft nur neue Positionen.

**Wie richte ich ein Backup ein?**
Kopieren Sie die Datei `app/auftragsabwicklung.db` an einen sicheren Ort. Nutzen Sie alternativ die Export-Funktion im Menu.

**Warum erscheint die Rechtschreibpruefung nicht?**
Die Rechtschreibpruefung benoetigt Hunspell-Dictionaries. Wenn keine installiert sind, funktioniert die Anwendung trotzdem — nur ohne Unterstreichung von Fehlern.
