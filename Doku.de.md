# Order Management System — Anwenderhandbuch

Dieses Handbuch beschreibt alle Funktionen des Order Management Systems aus Anwendersicht.

> English version: [doku.en.md](doku.en.md)

Technische Details (Installation, Systemvoraussetzungen) finden sich in der [README.de.md](README.de.md) und der [ADMIN-EINRICHTUNG.md](ADMIN-EINRICHTUNG.md). Die HTML-Variante mit Diagrammen ist `app/doku.de.html` (Deutsch) bzw. `app/doku.en.html` (Englisch) — auch über die Taste **F1** im Programm kontextsensitiv erreichbar.

---

## Inhaltsverzeichnis

1. [Start und Navigation](#1-start-und-navigation)
2. [Tastenkombinationen](#2-tastenkombinationen)
3. [Sidebar und Belegdatum](#3-sidebar-und-belegdatum)
4. [Stammdaten](#4-stammdaten)
   - [Firmenstamm](#41-firmenstamm)
   - [Kundenstamm](#42-kundenstamm)
   - [Artikelstamm](#43-artikelstamm)
5. [Workflow und Belegkette](#5-workflow-und-belegkette)
   - [Typischer Workflow](#51-typischer-workflow)
   - [Belegkette im Detail](#52-belegkette-im-detail)
   - [Löschen und Wiederherstellen](#53-loeschen-und-wiederherstellen)
   - [Lösch-Schutz](#54-loesch-schutz)
6. [Belegnummern und Geschäftsjahre](#6-belegnummern-und-geschaeftsjahre)
7. [Mehrwertsteuer-System](#7-mehrwertsteuer-system)
8. [Belege bearbeiten](#8-belege-bearbeiten)
   - [Allgemeiner Ablauf](#80-allgemeiner-ablauf)
   - [Positionen-Editor](#80b-positionen-editor)
   - [Angebote](#81-angebote)
   - [Aufträge](#82-auftraege)
   - [Lieferscheine](#83-lieferscheine)
   - [Rechnungen](#84-rechnungen)
   - [Mahnungen](#85-mahnungen)
9. [Konditionen](#9-konditionen)
   - [Zahlungskonditionen](#91-zahlungskonditionen)
   - [Mahnkonditionen](#92-mahnkonditionen)
   - [Basiszinssatz](#93-basiszinssatz)
10. [Standardtexte und Marker](#10-standardtexte-und-marker)
    - [Standardtexte](#101-standardtexte)
    - [Marker-System](#102-marker-system)
11. [Drucken und Journale](#11-drucken-und-journale)
    - [Einzelbelege drucken](#111-einzelbelege-drucken)
    - [Testdruck](#112-testdruck)
    - [Journale drucken](#113-journale-drucken)
12. [Sperren-System](#12-sperren-system)
    - [E-Mail-Postausgang](#121-e-mail-postausgang)
    - [E-Rechnung-Spool](#122-e-rechnung-spool)
13. [Firmenverwaltung (Admin)](#13-firmenverwaltung-admin)
    - [Firma kopieren](#131-firma-kopieren)
    - [Firma löschen](#132-firma-loeschen)
14. [Import und Export](#14-import-und-export)
15. [Rechtschreibprüfung](#15-rechtschreibpruefung)
16. [Einstellungen](#16-einstellungen)
17. [Datenbank und Sicherung](#17-datenbank-und-sicherung)
18. [Test-Modus](#18-test-modus)
19. [Hinweise und FAQ](#19-hinweise-und-faq)

---

## 1. Start und Navigation

Die Anwendung startet mit einer **Startseite** und einer **Seitenleiste** links. Über die Seitenleiste gelangen Sie schnell zu allen Funktionen.

Jeder Klick auf einen Button in der Seitenleiste oder im Menü öffnet das entsprechende Modul als **Tab** rechts. Mehrere Tabs können gleichzeitig offen sein.

**Tabs verwalten:**

- Tab schließen: Klick auf das **X** am Tab
- Tab schließen (Alternative): **Doppelklick** auf den Tab
- Tab wechseln: Klick auf den entsprechenden Tab

Das Hauptfenster speichert automatisch seine Position und Größe. Beim nächsten Start wird es am selben Ort wiederhergestellt.

---

## 2. Tastenkombinationen

| Taste(n) | Wirkung |
|---|---|
| **F1** | Kontextbezogene Hilfe öffnen (springt zum Kapitel des aktiven Tabs) |
| **F5** | Liste im aktuellen Modul aktualisieren |
| **Strg + N** | Neuen Eintrag erstellen (im aktiven Modul) |
| **Entf** | Ausgewählten Eintrag löschen (Soft-Delete) |
| **Strg + P** | Ausgewählten Beleg drucken |
| **Esc** | Dialog / Bearbeitungsfenster schließen |

---

## 3. Sidebar und Belegdatum

In der Sidebar links wird unter dem Benutzernamen das aktuelle **Belegdatum** angezeigt. Dieses Datum wird als Standardwert bei neuen Belegen (Angebot, Auftrag, Lieferschein, Rechnung, Mahnung) verwendet.

### Ersatzdatum setzen

Standardmäßig entspricht das Belegdatum dem heutigen Datum. Sie können jedoch ein beliebiges Ersatzdatum setzen:

- **Linksklick** auf das Datum öffnet einen Kalender-Dialog, in dem Sie ein beliebiges Datum wählen können.
- **Rechtsklick** auf das Datum zeigt ein Kontextmenü:
  - **Auf heutiges Datum setzen** — setzt das Belegdatum zurück auf den aktuellen Tag.
  - **Ersatzdatum entfernen** — entfernt das manuell gesetzte Datum; ab sofort wird wieder das heutige Datum verwendet.

Das Ersatzdatum ist **nicht persistent** — bei einem Neustart der Anwendung wird es automatisch auf das aktuelle Datum zurückgesetzt. So entsteht kein Fehler, wenn Sie am nächsten Tag versehentlich mit dem alten Datum arbeiten.

> **Tipp:** Das Ersatzdatum ist praktisch, wenn Sie einen Beleg rückwirkend erstellen müssen (z. B. eine Rechnung am 5. März für eine Lieferung vom 28. Februar).

---

## 4. Stammdaten

Die Stammdaten bilden das Fundament aller Belege. Ohne korrekte Stammdaten funktionieren keine PDF-Ausdrucke und keine Belegketten korrekt.

Die drei Stammdaten-Module sind miteinander verknüpft:

- **Firmenstamm** — Ihr Unternehmen: Adresse, Bankdaten, MwSt-Klassen, Konditionen, Standardtexte, Marker
- **Kundenstamm** — Empfänger aller Belege; jeder Beleg verweist auf einen Kunden
- **Artikelstamm** — Produkte und Dienstleistungen; jede Position auf einem Beleg verweist auf einen Artikel

### 4.1 Firmenstamm

Der Firmenstamm ist das zentrale Konfigurationsmodul und besteht aus mehreren Reitern (Tabs).

#### Adresse und Kontakt

Name, Zusatz, Straße, PLZ, Ort, Telefon, Telefax, E-Mail, Webseite. Diese Daten erscheinen auf **jedem** PDF-Ausdruck als Absender.

#### Parameter

Steuernummer, USt.-IdNr., IBAN, BIC, Bankname, Währung, Ländercode. Diese Daten erscheinen im Footer jeder Rechnung und jeder Mahnung. Zusätzlich konfigurieren Sie hier:

- **E-Rechnung erstellen:** Aktiviert die automatische Erzeugung maschinenlesbarer XML-Dateien beim ersten Druck einer Rechnung (EN 16931).
- **E-Mail-Client:** Legt fest, über welchen Dienst E-Mails versendet werden (Brevo, Gmail, Outlook 365 Classic, New Outlook). Details siehe [E-Mail-Postausgang](#121-e-mail-postausgang).
- **E-Mail Signatur & Datenschutzerklärung:** Werden automatisch an den E-Mail-Text angehängt.

#### Geschäftsjahre und Belegnummern

Hier verwalten Sie Geschäftsjahre und konfigurieren die Zähler für alle Belegtypen. Details siehe [Belegnummern und Geschäftsjahre](#6-belegnummern-und-geschaeftsjahre).

#### Zahlungskonditionen

Definieren Sie hier, welche Zahlungsbedingungen Kunden standardmäßig erhalten. Details siehe [Zahlungskonditionen](#91-zahlungskonditionen).

#### Mahnkonditionen

Stufenweise Mahnungskonfiguration: Frist, Zinssatz, Mahnkosten pro Stufe. Details siehe [Mahnkonditionen](#92-mahnkonditionen).

#### MwSt-Klassen

Legen Sie hier Steuerklassen an (z. B. "Normalsatz", "Reduzierter Satz", "Steuerfrei") und weisen Sie zeitabhängige Sätze zu. Details siehe [Mehrwertsteuer-System](#7-mehrwertsteuer-system).

#### Basiszinssatz

Historische Basiszinssätze der Bundesbank für die Berechnung von Säumniszinsen. Details siehe [Basiszinssatz](#93-basiszinssatz).

#### Drucktexte

Konfigurierbare Label und Bezeichnungen in den PDF-Belegen (z. B. "Rechnungs-Nr.:", "Fällig am:", "Gesamtbetrag:"). So passen Sie die Belege an Ihre Anforderungen an.

#### Unterschriften

Standardunterschriften für die verschiedenen Belegtypen.

#### Standardtexte

Textbausteine für Angebote, Aufträge, Rechnungen, Lieferscheine und Mahnungen. Sie können **Marker** verwenden, die beim Drucken automatisch ersetzt werden. Details siehe [Standardtexte und Marker](#10-standardtexte-und-marker).

#### Exemplare

Anzahl der Exemplare pro Belegtyp (z. B. doppelte Rechnungen).

#### Pfade

Export-Pfade für PDFs (optional) und andere Dateieinstellungen.

#### Sperren

Module können vor ungewollten Änderungen gesperrt werden. Details siehe [Sperren-System](#12-sperren-system).

> **Wichtig:** Der Firmenstamm muss als **erstes** gepflegt werden. Ohne Firmendaten sind keine korrekten PDF-Ausdrucke möglich.

#### Speichern und Abbrechen

Jeder Reiter hat eigene **Speichern**- und **Abbrechen**-Buttons unten. Änderungen werden erst beim Klicken auf "Speichern" übernommen. Mit "Abbrechen" werfen Sie alle ausstehenden Änderungen in diesem Reiter wieder weg.

Ein roter Punkt am Reiter signalisiert ungespeicherte Änderungen.

### 4.2 Kundenstamm

Alle Kunden und Ansprechpartner werden hier angelegt.

#### Felder

| Feld | Beschreibung | Verwendung |
|---|---|---|
| Anrede | "Herr", "Frau", "Sehr geehrte Damen und Herren" | Briefanfang im PDF |
| Titel | Dr., Dipl.-Ing., usw. | Briefanfang im PDF |
| Vorname / Nachname | Ansprechpartner | Briefanfang, Adressblock |
| Firmenname | Unternehmensname | Adressblock im PDF |
| Straße, PLZ, Ort | Liefer- und Rechnungsadresse | Adressblock im PDF |
| Land | Staatszugehörigkeit | Adressblock (für internationale Kunden) |
| Telefon | Kontakttelefon | Adressblock |
| E-Mail | E-Mail-Adresse | Empfängeradresse für den automatischen E-Mail-Versand |
| Briefanrede | Persönliche Anrede im E-Mail-Text | Wird automatisch an den Anfang des E-Mail-Textes gesetzt |
| E-Mail-Versand Rechnung | 0 = kein, 1 = nur PDF, 2 = nur E-Rechnung XML, 3 = beides | Steuert, was beim Rechnungsdruck in den Postausgang gelegt wird |
| E-Mail-Versand Angebot / Auftrag / Mahnung | Gleiche Optionen | Pro Belegtyp separat konfigurierbar |
| E-Rechnung erstellen | Checkbox | Aktiviert XML-Erzeugung beim Rechnungsdruck |
| Kundennummer | Ihre interne Referenz | Optional, wird auf Belegen angezeigt |
| Zahlungskondition | Standard-Zahlungsbedingungen | Wird bei neuen Rechnungen übernommen |
| Mahnkondition | Mahnstufen-Konfiguration | Wird bei Mahnungen verwendet |

#### Kunde und Belege

Wenn Sie einen Kunden ändern (z. B. Adresse), wirkt dies **nur auf zukünftige** Belege. Bereits erstellte Belege behalten die Adresse, die zum Zeitpunkt der Erstellung gespeichert wurde.

### 4.3 Artikelstamm

Alle Produkte und Dienstleistungen. Pro Artikel:

| Feld | Beschreibung | Verwendung |
|---|---|---|
| Artikelnummer | Eindeutige Kennung | Wird auf allen Belegen angezeigt |
| Bezeichnung | Kurzbezeichnung | Wird in der Positionstabelle auf Belegen angezeigt |
| Beschreibung | Ausführliche Beschreibung | Optional, kann auf Belegen erscheinen |
| Einheitspreis | Standardpreis | Wird bei neuen Positionen übernommen (kann pro Beleg angepasst werden) |
| MwSt-Klasse | Steuerklasse (z. B. Normalsatz) | Bestimmt den MwSt-Satz für neue Positionen |
| Einheit | Mengeneinheit (St, Std., kg, ml, usw.) | Wird in der Positionstabelle auf Belegen angezeigt |

> **Wichtig:** Der Einheitspreis wird bei einer neuen Position übernommen, aber Sie können ihn pro Beleg ändern. Eine Änderung des Artikelpreises später betrifft nur neue Positionen.

---

## 5. Workflow und Belegkette

### 5.1 Typischer Workflow

Der typische Workflow verläuft in Stufen:

**Angebot → Auftrag → Lieferschein → Rechnung → Mahnung**

Nicht alle Stufen sind Pflicht. Sie können z. B. direkt von Angebot zu Auftrag und von Auftrag zu Rechnung gehen (ohne Lieferschein).

### 5.2 Belegkette im Detail

Jeder Beleg ist mit seinen Vorgängern und Nachfolgern verknüpft. Diese Verknüpfung nennt sich **Belegkette**.

**So wird die Kette aufgebaut:**

- **Angebot → Auftrag:** Der Auftrag speichert die Angebots-ID.
- **Auftrag → Lieferschein:** Der Lieferschein speichert die Auftrags-ID.
- **Auftrag → Rechnung:** Die Rechnung speichert die Auftrags-ID.
- **Lieferschein → Rechnung:** Die Rechnung speichert optional die Lieferschein-ID.
- **Rechnung → Mahnung:** Jede Mahnung speichert die Rechnungs-ID und die Mahnstufe.
- **Mahnung → nächste Stufe:** Höhere Mahnungen verweisen auf die vorherige Mahnung.

**Belegkette im Dialog:** Wenn Sie einen Beleg öffnen, sehen Sie oben die gesamte Kette — vom ersten Angebot bis zur letzten Mahnung. Gelöschte Belege werden mit einem Marker angezeigt, damit die Kette auch nach Löschungen nachvollziehbar bleibt.

**Rückwärts und vorwärts durch die Kette:**

- **Rückwärts:** Vom aktuellen Beleg bis zum ersten Vorgänger (meist das Angebot). So sehen Sie immer, auf welchem Angebot eine Rechnung basiert.
- **Vorwärts:** Vom aktuellen Beleg bis zum letzten Nachfolger (z. B. von der Rechnung zur höchsten Mahnstufe). So sehen Sie, wie weit eine Zahlung verzögert ist.

### 5.3 Löschen und Wiederherstellen <a id="53-loeschen-und-wiederherstellen"></a>

Belege werden nie wirklich gelöscht, sondern als **gelöscht markiert** (Soft-Delete). Dies hat folgende Auswirkungen:

- Gelöschte Belege tauchen **nicht** in den normalen Listen auf.
- Gelöschte Belege erscheinen in der Belegkette **mit einem Marker** (z. B. durchgestrichen oder grau).
- Gelöschte Belege können **wiederhergestellt** werden — sie erscheinen dann wieder in der Liste.
- Die Belegnummer einer wiederhergestellten Rechnung wird **nicht** erneut vergeben (sie behält ihre ursprüngliche Nummer).

### 5.4 Lösch-Schutz <a id="54-loesch-schutz"></a>

Wenn Sie versuchen, einen Beleg zu löschen, der **lebende Nachfolger** hat, wird das Löschen **verhindert**. Das System zeigt eine Warnung mit der Liste der blockierenden Belege an.

| Belegtyp | Löschen blockiert durch |
|---|---|
| Angebot | Lebender Auftrag |
| Auftrag | Lebender Lieferschein oder lebende Rechnung |
| Lieferschein | Lebende Rechnung mit Verweis auf diesen Lieferschein |
| Rechnung | Lebende Mahnungen |
| Mahnung | Lebende höhere Mahnstufen |

> **Achtung:** Dies gilt nur für **lebende** (nicht gelöschte) Nachfolger. Wenn der Auftrag bereits gelöscht wurde, können Sie das Angebot löschen.

---

## 6. Belegnummern und Geschäftsjahre <a id="6-belegnummern-und-geschaeftsjahre"></a>

### Belegnummern

Jeder Belegtyp hat einen eigenen Zähler. Das Format lautet: `{Prefix}{JJJJ}-{NNNN}`

| Belegtyp | Beispiel |
|---|---|
| Angebot | `AN2026-0001` |
| Auftrag | `AU2026-0018` |
| Lieferschein | `LS2026-0009` |
| Rechnung | `RE2026-0008` |
| Mahnung | `MA2026-0003` |

**So funktioniert der Zähler:**

- Der Zähler speichert die **letzte vergebene Nummer** (nicht die nächste).
- Die **Vorschau** zeigt die Nummer, die Sie erhalten werden — **ohne** den Zähler zu erhöhen.
- Der Zähler erhöht sich erst beim **Speichern** des Belegs.
- Wenn Sie einen Beleg erstellen und dann nicht speichern, wird die Nummer **nicht** verbraucht.

> **Praxis-Tipp:** Wenn Sie die Vorschau ansehen (z. B. "RE2026-0015"), bedeutet das: "Wenn Sie jetzt speichern, erhalten Sie diese Nummer." Solange Sie nicht speichern, bleibt der Zähler unverändert.

### Geschäftsjahre

Sie können mehrere Geschäftsjahre verwalten. Jedes Jahr hat eigene Belegzähler und einen eigenen Buchungsmonat.

**Geschäftsjahr wechseln:**

- Wählen Sie im Reiter "Geschäftsjahre und Belegnummern" das gewünschte Jahr aus der Auswahlliste.
- Rechtsklick auf die Auswahlliste setzt das gewählte Jahr als **aktives Geschäftsjahr**.
- Buchungsmonat und Zähler werden pro Jahr gespeichert und mit dem Jahr gewechselt.

**Neues Geschäftsjahr anlegen:**

- Klicken Sie auf den Button "Neues Geschäftsjahr…" neben der Auswahlliste.
- Das System schlägt das nächste Jahr (aktuelles Jahr + 1) vor.
- Die Jahreszahl MUSS höher sein als das letzte angelegte Jahr — so bleibt die chronologische Reihenfolge garantiert.
- Das neue Jahr wird sofort als aktives Jahr gesetzt.

Das aktive Geschäftsjahr wird in der Sidebar angezeigt (unter dem Belegdatum, mit einem Kalendersymbol).

---

## 7. Mehrwertsteuer-System

Das MwSt-System arbeitet mit **Klassen** und **zeitabhängigen Sätzen**.

**Klassen:** Jede MwSt-Klasse (z. B. "Normalsatz", "Reduzierter Satz", "Steuerfrei") hat mehrere Sätze mit Startdatum. Beispiel:

| Klasse | Satz | ab Datum |
|---|---|---|
| Normalsatz | 15 % | 01.01.2024 |
| Normalsatz | 16 % | 01.07.2024 |
| Normalsatz | 18 % | 01.01.2025 |
| Reduzierter Satz | 7 % | 01.01.2024 |

**Einfrieren des MwSt-Satzes:** Wenn Sie eine Position auf einem Beleg erstellen, wird der **zum Belegdatum aktuelle Satz** in der Position gespeichert. Das bedeutet:

- Beleg vom 15.03.2025 mit Normalsatz → Position bekommt 18 %
- Steuererhöhung auf 20 % zum 01.06.2025
- Beleg vom 10.06.2025 mit Normalsatz → Position bekommt 20 %
- Der alte Beleg vom 15.03.2025 bleibt bei 18 %

> **Warum das wichtig ist:** Wenn Sie alte Belege nachdrucken, zeigen sie den korrekten MwSt-Satz für den Zeitpunkt der Erstellung. Sie müssen nichts manuell anpassen.

---

## 8. Belege bearbeiten

Die Bedienung folgt für alle Belegtypen (Angebot, Auftrag, Lieferschein, Rechnung, Mahnung) demselben Muster. Belegtyp-spezifische Besonderheiten sind in den folgenden Abschnitten beschrieben.

### 8.0 Allgemeiner Ablauf <a id="80-allgemeiner-ablauf"></a>

#### Liste eines Belegtyps

Jede Belegliste hat dieselbe Werkzeugleiste oben:

| Button | Wirkung | Kurztaste |
|---|---|---|
| **Neu** | Leeren Beleg-Dialog öffnen | **Strg + N** |
| **Bearbeiten** | Markierten Beleg im Dialog öffnen | Doppelklick auf die Zeile |
| **Löschen** | Markierten Beleg soft-löschen (mit Lösch-Schutz, siehe [Löschen und Wiederherstellen](#53-loeschen-und-wiederherstellen)) | **Entf** |
| **Drucken** | PDF erzeugen und im Viewer öffnen | **Strg + P** |
| **Testdruck** | Wie Drucken, aber mit Wasserzeichen und ohne Erstellungsdatum (siehe [Testdruck](#112-testdruck)) | |
| **→ _Nachfolger_** | Folgebeleg erzeugen (z. B. „→ Auftrag" in der Angebotsliste). Der Buttonname richtet sich nach dem nächsten Belegtyp. | |
| **Journal drucken** | Beleg-Journal eines Zeitraums als PDF (siehe [Journale](#113-journale-drucken)) | |
| **Aktualisieren** | Liste neu laden (nützlich im Mehrbenutzerbetrieb) | **F5** |

In der Rechnungsliste gibt es zusätzlich **→ Mahnung** und **Als bezahlt markieren**, in der Mahnungsliste **→ Nächste Stufe**.

> **Tipp:** Spaltenbreiten und Sortierung in jeder Liste werden pro Modul automatisch gespeichert.

#### Beleg-Dialog — Aufbau

Sobald Sie einen Beleg neu anlegen oder bearbeiten, öffnet sich der Beleg-Dialog mit vier Blöcken:

```
┌──────────────────────────────────────────────────────────────────┐
│ 1. Kopfdaten                                                     │
│    Nummer · Datum · ggf. Zusatzdatum (Gültig bis, Lieferdatum)   │
│    Kunde wählen · Zahlungskondition · Quelle (Vorgänger)         │
│    Betreff · Text oben (mit Marker-Buttons) · [Belegkette]       │
├──────────────────────────────────────────────────────────────────┤
│ 2. Positionen                                                    │
│    Toolbar: Hinzufügen · Bearbeiten · Löschen · ↑ · ↓            │
│    Spalten: Pos · Bezeichnung · Menge · Einheit · Preis ·        │
│             Steuerschlüssel · Rabatt% · Gesamt                   │
│    Live-Summen: Netto · MwSt pro Satz · Brutto                   │
├──────────────────────────────────────────────────────────────────┤
│ 3. Text unten (Freitext + Marker-Buttons)                        │
├──────────────────────────────────────────────────────────────────┤
│ 4. Button-Leiste:   [Original]   …   [Speichern]  [Abbrechen]    │
└──────────────────────────────────────────────────────────────────┘
```

#### Schritt für Schritt einen Beleg bearbeiten

1. **Beleg öffnen:** Beleg in der Liste markieren und **Bearbeiten** klicken, oder die Zeile doppelklicken.
2. **Kopfdaten prüfen/anpassen:**
   - **Datum** ändern (Klick auf das Datumsfeld öffnet einen Kalender)
   - **Kunde wählen** mit dem gleichnamigen Button (Suche nach Name, Firma, Kundennummer)
   - **Zahlungskondition** aus der Dropdown-Liste wählen — die Fälligkeit wird daraus automatisch berechnet
   - **Betreff** eingeben (Rechtschreibprüfung aktiv)
   - **Text oben** bei Bedarf anpassen; Marker (z. B. `{RENR}`) per Button-Klick einfügen
3. **Positionen bearbeiten:** siehe [Positionen-Editor](#80b-positionen-editor) unten.
4. **Text unten** anpassen (analog Text oben).
5. **Belegkette prüfen** über den Button **Belegkette** — zeigt alle Vorgänger und Nachfolger.
6. **Speichern** oder **Abbrechen**. Bei ungespeicherten Änderungen erscheint vor dem Schließen eine Rückfrage („Speichern / Verwerfen / Abbrechen").

> **Tasten im Beleg-Dialog:** **F1** öffnet die Doku. **Esc** schließt den Dialog, fragt aber bei ungespeicherten Änderungen vorher nach.

#### Was geht, was nicht

- **Neue Belegnummer:** Wird beim Speichern aus dem Zähler vergeben. Die Vorschau im Dialog zeigt nur, was Sie _würden_. Solange Sie nicht speichern, verbraucht der Beleg keine Nummer.
- **Bestehende Belegnummer:** Nicht änderbar. Sie bleibt über die gesamte Lebensdauer fest.
- **Bezahlte Rechnungen:** Sind gesperrt und können nicht mehr bearbeitet werden (Hinweis erscheint).
- **Belege mit Nachfolger:** Sind teils gesperrt — ein Angebot, aus dem ein Auftrag entstand, ist im Status „angenommen" und kann nicht mehr bearbeitet werden.
- **Mehrere Tabs gleichzeitig:** Eine Liste und ein Beleg-Dialog können parallel offen sein. Speichern Sie den Dialog, damit die Liste die neuen Werte sieht (oder **F5** in der Liste).

### 8.0b Positionen-Editor <a id="80b-positionen-editor"></a>

Die Positionen sind das Herzstück jedes Belegs. Der Positionen-Editor erscheint mittig im Beleg-Dialog mit eigener Werkzeugleiste.

| Aktion | Button | Wirkung |
|---|---|---|
| Neue Position | **Hinzufügen** | Öffnet die Artikel-Auswahl. Wählen Sie einen Artikel, dann wird die Position mit dessen Daten (Preis, MwSt-Klasse, Einheit) eingefügt. |
| Position ändern | **Bearbeiten** | Öffnet den Positions-Dialog mit allen Feldern. Alternativ: Doppelklick auf die Tabellenzeile. |
| Position entfernen | **Löschen** | Entfernt die markierte Position aus dem Beleg. |
| Reihenfolge | **↑** / **↓** | Verschiebt die markierte Position eine Stelle nach oben oder unten. |

#### Felder im Positions-Dialog

| Feld | Bedeutung |
|---|---|
| Bezeichnung | Kurzer Positionstext — erscheint in der PDF-Positionstabelle. Rechtschreibprüfung aktiv. |
| Beschreibung | Optionaler längerer Text unter der Bezeichnung. Rechtschreibprüfung aktiv. |
| Menge | Stückzahl, Stunden, kg, … (Dezimalkomma erlaubt). |
| Einheit | Mengeneinheit; freie Eingabe oder Vorschlagsliste (Stk., Std., kg, m, ml, …). |
| Einzelpreis (€) | Preis pro Mengeneinheit (netto). Aus dem Artikel vorbelegt, pro Beleg änderbar. |
| Rabatt (%) | Prozentualer Abschlag auf den Gesamtpreis dieser Position. |
| MwSt-Klasse | Steuerklasse. Aus dem Artikel vorbelegt. Der konkrete Satz wird beim Speichern aus dem Belegdatum eingefroren (siehe [Mehrwertsteuer-System](#7-mehrwertsteuer-system)). |

> **Live-Summenzeile:** Unter der Positionstabelle erscheint stets eine Zusammenfassung: `Netto · MwSt pro Satz · Brutto`. Sie aktualisiert sich nach jeder Änderung — ohne dass Sie speichern müssen.

> **Hinweis Lieferscheine:** Auf dem gedruckten Lieferschein werden die Preisspalten ausgeblendet. Im Bearbeitungsdialog sind die Preise jedoch sichtbar, weil der Lieferschein die Daten für eine spätere Rechnung mitträgt.

### 8.1 Angebote

**Angebot erstellen:**

1. Button **+** oder **Strg + N**
2. Kunde wählen aus dem Dropdown (Suche nach Name/Firma)
3. Datum setzen (Standard: heute oder Ersatzdatum)
4. Optional: Gültigkeit des Angebots angeben
5. Positionen hinzufügen: Artikel wählen, Menge eingeben, ggf. Preis anpassen
6. Betreff und evtl. Freitext eingeben
7. Speichern

**Angebot zu Auftrag machen:**

Wählen Sie das Angebot aus der Liste und klicken Sie **→ Auftrag**:

- Der Angebotsstatus wird auf **"angenommen"** gesetzt
- Alle Positionen werden übernommen
- Der Auftrag wird mit demselben Kunden erstellt
- Die Belegkette verbindet Angebot und Auftrag

Sie können den Auftrag danach bearbeiten (Positionen ändern, Datum anpassen).

**Angebot drucken:**

Wählen Sie das Angebot und klicken Sie **Drucken**. Es wird ein PDF erzeugt und im Viewer geöffnet.

### 8.2 Aufträge <a id="82-auftraege"></a>

**Auftrag erstellen:**

Aufträge können auf zwei Wegen erstellt werden:

1. **Aus einem Angebot:** Button **→ Auftrag** in der Angebotsliste
2. **Manuell:** Button **+** in der Auftragsliste

**Auftrag zu Lieferschein machen:**

Button **→ Lieferschein** — übernimmt Kunde, Datum und Positionen.

**Auftrag direkt zu Rechnung machen:**

Button **→ Rechnung** — überspringt den Lieferschein. Der Auftragsstatus wird auf **"abgeschlossen"** gesetzt.

> **Workflow-Hinweis:** Sie können aus einem Auftrag **sowohl** einen Lieferschein **als auch** eine Rechnung erstellen. Wenn Sie beides machen, verweist die Rechnung sowohl auf den Auftrag als auch auf den Lieferschein.

### 8.3 Lieferscheine

Lieferscheine werden aus Aufträgen erstellt. Sie dokumentieren die Auslieferung.

- Auf Lieferscheinen werden **keine Preise** angezeigt
- Die Mengen und Artikel werden vom Auftrag übernommen
- Sie können die Mengen auf dem Lieferschein anpassen (z. B. bei Teillieferungen)

**Lieferschein zu Rechnung machen:**

Button **→ Rechnung** — übernimmt alle Daten und setzt das Lieferdatum.

### 8.4 Rechnungen

**Rechnung erstellen:**

Rechnungen werden über den Button **→ Rechnung** in der **Lieferscheinliste** erstellt. Der Lieferschein muss zuvor aus einem Auftrag erstellt worden sein.

Wenn kein Lieferschein benötigt wird, kann der Auftrag direkt einen Lieferschein erzeugen, der sofort zur Rechnung gemacht wird. Es gibt keinen direkten „Auftrag → Rechnung"-Button.

**Zahlungskondition:**

Die Rechnung übernimmt die Zahlungskondition vom Kunden (wenn konfiguriert). Die Fälligkeit wird automatisch berechnet: **Rechnungsdatum + Konditionstage**.

**Als bezahlt markieren:**

Wählen Sie die Rechnung und klicken Sie **Als bezahlt markieren**:

- Das Bezahldatum wird auf heute gesetzt
- Bezahlte Rechnungen können danach **nicht mehr bearbeitet** werden
- Bezahlte Rechnungen werden mit einem entsprechenden Marker in der Liste angezeigt

> **Achtung:** Eine als bezahlt markierte Rechnung kann nicht mehr geändert werden. Stellen Sie sicher, dass alle Daten korrekt sind, bevor Sie dies tun.

**Erstellungsdatum:**

Jede Rechnung zeigt das Datum und die Uhrzeit, zu dem sie zum ersten Mal gedruckt wurde. Dieses Datum wird beim ersten Druck festgeschrieben und bleibt danach unveränderbar. Es ist im Beleg-Dialog und im PDF-Header (oben rechts) sichtbar.

**Rechnung festschreiben:**

Beim ersten echten Druck (kein Testdruck) wird eine Rechnung automatisch *festgeschrieben*:

- Das Erstellungsdatum und die Uhrzeit werden unveränderbar gespeichert.
- Festgeschriebene Rechnungen können **nicht mehr geändert** werden — nur noch storniert.
- Im Beleg-Dialog erscheint ein roter **„FESTGESCHRIEBEN"**-Hinweis.

**Rechnung stornieren:**

Eine festgeschriebene Rechnung kann über den Button **„Storno"** storniert werden:

1. Die Originalrechnung erhält den Status **„storniert"** und kann nicht mehr bearbeitet werden.
2. Automatisch wird eine neue **Stornorechnung** mit den gleichen Positionen, jedoch negativen Beträgen, erstellt.
3. Die Stornorechnung wird in der Liste mit dem Präfix „Storno:" angezeigt und kann ebenfalls gedruckt werden.
4. Optional kann aus der Stornorechnung sofort eine Korrekturrechnung erstellt werden.

> **Achtung:** Storno ist unwiderruflich. Stellen Sie sicher, dass Sie die richtige Rechnung ausgewählt haben.

**Rechnung zu Mahnung:**

Button **→ Mahnung** — erstellt die nächste Mahnung basierend auf der Mahnkondition (vom Kunden oder der Firma).

### 8.5 Mahnungen

**Wie Mahnungen funktionieren:**

Das Mahnverfahren arbeitet stufenweise. Jede Stufe hat:

- Eine **Bezeichnung** (z. B. "Zahlungserinnerung", "1. Mahnung", "2. Mahnung", "Letzte Mahnung")
- Eine **Fälligkeit in Tagen** (z. B. 7, 14, 30 Tage)
- Optional: **Mahnkosten** in Euro
- Optional: **Zinssatz** in Prozent

Die Stufen werden automatisch vergeben (1 bis 4). Stufe 1 entspricht der "Zahlungserinnerung", Stufe 4 der "Letzten Mahnung".

**Mahnung erstellen:**

1. Gehen Sie zum Modul **Mahnungen** oder verwenden Sie den Button **→ Mahnung** in der Rechnungsliste
2. Wählen Sie die ausstehende Rechnung aus
3. Die Mahnung wird mit der nächsten freien Stufe erstellt
4. Drucken → PDF wird erzeugt

**Nächste Mahnstufe:**

Button **→ Nächste Stufe** — erstellt die nächste Mahnung der Kondition:

- Die Mahnstufe erhöht sich um 1 (z. B. von 1. auf 2. Mahnung)
- Die Mahnkondition der nächsten Stufe wird angewendet
- Falls keine nächste Stufe definiert ist oder das Maximum (4) erreicht ist, erscheint eine Warnung

**Säumniszuschlag:**

Wenn ein Zinssatz für die Mahnstufe definiert ist, wird ein **Säumniszuschlag** berechnet:

- Berechnung: **Offener Betrag × Zinssatz / 100 × Tage / 365** (tagesgenau pro Mahnperiode)
- Der Zuschlag wird als **steuerfreie Position** ausgewiesen
- Er erscheint unter dem Gesamtbetrag
- Bei Zinssatz 0 % (z. B. bei der Zahlungserinnerung) werden **keine** Zinsen berechnet

> **Belegkette bei Mahnungen:** Wenn Sie eine Mahnung öffnen, sehen Sie die gesamte Kette: Angebot → Auftrag → Lieferschein → Rechnung → Zahlungserinnerung → 1. Mahnung → 2. Mahnung usw.

---

## 9. Konditionen

### 9.1 Zahlungskonditionen

Zahlungskonditionen bestimmen, wie lange ein Kunde nach Rechnungsstellung für die Zahlung Zeit hat.

**So funktioniert es:**

- Sie definieren Konditionen im Firmenstamm (z. B. "14 Tage netto", "30 Tage netto", "sofort")
- Jede Kondition hat eine **Anzahl Tage** und eine **Bezeichnung**
- Ein Kunde kann eine Standard-Kondition zugewiesen bekommen
- Bei Erzeugung einer Rechnung wird die Fälligkeit berechnet: **Rechnungsdatum + Konditionstage**

**Beispiele:**

| Kondition | Tage | Beispiel (Rechnung vom 01.03.) |
|---|---|---|
| Sofort | 0 | Fällig am 01.03. |
| 14 Tage netto | 14 | Fällig am 15.03. |
| 30 Tage netto | 30 | Fällig am 31.03. |

### 9.2 Mahnkonditionen

Mahnkonditionen bestimmen das Verhalten des Mahnverfahrens pro Stufe.

**So funktioniert es:**

- Sie definieren Mahnstufen im Firmenstamm
- Jede Stufe hat: Bezeichnung, Fälligkeitstage, Mahnkosten, Zinssatz
- Ein Kunde kann eine eigene Mahnkondition haben (überschreibt die Standard-Kondition)
- Wenn keine Kunden-Kondition definiert ist, wird die Standard-Kondition verwendet

**Beispiel-Konfiguration:**

| Stufe | Bezeichnung | Fälligkeit | Mahnkosten | Zinssatz |
|---|---|---|---|---|
| 1 | Zahlungserinnerung | 7 Tage | 0,00 € | 0 % |
| 2 | 1. Mahnung | 7 Tage | 5,00 € | 5 % |
| 3 | 2. Mahnung | 7 Tage | 15,00 € | 10 % |
| 4 | Letzte Mahnung | 14 Tage | 30,00 € | 15 % |

### 9.3 Basiszinssatz

Der Basiszinssatz der Bundesbank dient als Grundlage für die Berechnung von Säumniszinsen.

- Sie können historische Basiszinssätze mit Startdatum pflegen
- Das System ermittelt den zum Zeitpunkt der Mahnung gültigen Satz
- Der Basiszinssatz wird zur Festlegung des Säumniszinssatzes verwendet
- Wenn der Zinssatz in der Mahnkondition 0 % ist (z. B. bei einer Zahlungserinnerung), wird **kein** Basiszinssatz addiert

---

## 10. Standardtexte und Marker

### 10.1 Standardtexte

Im Firmenstamm (Reiter "Standardtexte") können Sie für jeden Belegtyp einen **oberen** und **unteren** Standardtext definieren. Diese Texte:

- Werden auf den Belegen (PDFs) angezeigt
- Werden beim Anlegen eines Belegs automatisch in "Text oben" / "Text unten" vorbelegt
- Können im Belegdialog frei geändert werden

Jeder Belegtyp (Angebot, Auftrag, Lieferschein, Rechnung, Zahlungserinnerung, 1. Mahnung, 2. Mahnung, Letzte Mahnung) hat eigene Standardtexte. Die Texte sind in aufklappbare Boxen eingebettet, die Sie per Klick auf den Pfeil oder den Titel auf- und zuklappen können.

### 10.2 Marker-System

Marker sind Platzhalter, die beim Drucken automatisch durch die entsprechenden Werte ersetzt werden. Das Format lautet: `{PräfixSuffix}` (z. B. `{ANNR}`, `{REFÄLLIG}`).

**Allgemeine Marker-Referenz (Präfix + Suffix):**

| Präfix | Suffix | Bedeutung | Beispiel |
|---|---|---|---|
| `AN` | `NR` | Angebotsnummer | `AN2026-0001` |
| `AN` | `DATUM` | Angebotsdatum | `15.03.2026` |
| `AN` | `GÜLTIG` | Gültigkeitsdatum (gültig bis) | `30.04.2026` |
| `AU` | `NR` | Auftragsnummer | `AU2026-0018` |
| `AU` | `DATUM` | Auftragsdatum | `15.03.2026` |
| `AU` | `GESAMT` | Auftragsbetrag brutto | `1.234,56 €` |
| `AU` | `FÄLLIG` | Auftrags-Fälligkeitsdatum | `14.04.2026` |
| `AU` | `FTAGE` | Zahlungstage des Auftrags | `30` |
| `LS` | `NR` | Lieferscheinnummer | `LS2026-0009` |
| `LS` | `DATUM` | Lieferschein-Datum | `01.04.2026` |
| `LS` | `GESAMT` | Lieferschein-Betrag brutto | `1.234,56 €` |
| `LS` | `FÄLLIG` | Lieferschein-Fälligkeitsdatum | |
| `LS` | `FTAGE` | Zahlungstage des Lieferscheins | |
| `RE` | `NR` | Rechnungsnummer | `RE2026-0008` |
| `RE` | `DATUM` | Rechnungsdatum | `01.04.2026` |
| `RE` | `GESAMT` | Rechnungsbetrag brutto | `1.459,13 €` |
| `RE` | `FÄLLIG` | Fälligkeitsdatum | `01.05.2026` |
| `RE` | `FTAGE` | Zahlungstage der Rechnung (aus Zahlungskondition) | `30` |
| `MA` | `NR` | Mahnungsnummer | `MA2026-0003` |
| `MA` | `DATUM` | Mahnungsdatum | `10.05.2026` |
| `MA` | `GESAMT` | Mahnungsbetrag brutto | `1.459,13 €` |
| `MA` | `FÄLLIG` | Fälligkeitsdatum der Mahnung | `17.05.2026` |
| `MA` | `FTAGE` | Zahlungstage der Mahnung | `7` |

**Mahnung-spezifische Marker (nur ab Mahnung verfügbar):**

| Marker | Bedeutung |
|---|---|
| `{MAZTAGE}` | Fälligkeitstage der aktuellen Mahnstufe (aus Mahnkondition) |
| `{MAZINS%}` | Gesamtzinssatz der aktuellen Mahnstufe (Basiszins + Mahnsatz) in % |
| `{MAZINS€}` | Summe aller Verzugszinsen der Mahnung in € |

**Firma-Marker (ohne Präfix, ab Rechnung verfügbar):**

| Marker | Bedeutung |
|---|---|
| `{IBAN}` | IBAN der Firma |
| `{BIC}` | BIC der Firma |
| `{BANK}` | Bankname der Firma |

**Marker pro Standardtext-Typ (im Firmenstamm verfügbar):**

Die verfügbaren Marker-Buttons sind **kumulativ** — jeder nächste Belegtyp erbt die Marker seiner Vorgänger:

| Belegtyp | Verfügbare Marker |
|---|---|
| **Angebot** | `{ANNR}`, `{ANDATUM}` |
| **Auftrag** | `{ANNR}`, `{ANDATUM}`, `{AUNR}`, `{AUDATUM}` |
| **Lieferschein** | `{ANNR}`, `{ANDATUM}`, `{AUNR}`, `{AUDATUM}`, `{LSNR}`, `{LSDATUM}` |
| **Rechnung** | `{ANNR}`, `{ANDATUM}`, `{AUNR}`, `{AUDATUM}`, `{LSNR}`, `{LSDATUM}`, `{RENR}`, `{REDATUM}`, `{REGESAMT}`, `{REFÄLLIG}`, `{REFTAGE}`, `{IBAN}`, `{BIC}`, `{BANK}` |
| **Zahlungserinnerung** | **Alle** bis RE + `{MANR}`, `{MADATUM}`, `{MAGESAMT}`, `{MAFÄLLIG}`, `{MAFTAGE}`, `{MAZTAGE}`, `{MAZINS%}`, `{MAZINS€}` |
| **1. Mahnung** | **Alle** bis RE + `{MANR}`, `{MADATUM}`, `{MAGESAMT}`, `{MAFÄLLIG}`, `{MAFTAGE}`, `{MAZTAGE}`, `{MAZINS%}`, `{MAZINS€}` |
| **2. Mahnung** | **Alle** bis RE + `{MANR}`, `{MADATUM}`, `{MAGESAMT}`, `{MAFÄLLIG}`, `{MAFTAGE}`, `{MAZTAGE}`, `{MAZINS%}`, `{MAZINS€}` |
| **Letzte Mahnung** | **Alle** bis RE + `{MANR}`, `{MADATUM}`, `{MAGESAMT}`, `{MAFÄLLIG}`, `{MAFTAGE}`, `{MAZTAGE}`, `{MAZINS%}`, `{MAZINS€}` |

**Marker-Buttons in Standardtexten:**

Im Firmenstamm (Reiter "Standardtexte") erscheinen unter jedem Textfeld klickbare Marker-Buttons. Ein Klick fügt den Marker an der Cursor-Position ein.

**Marker-Buttons in Belegdialogen:**

In Beleg-Dialogen (z. B. bei der Angebot- oder Rechnungserstellung) finden Sie unter den Textfeldern "Text oben" und "Text unten" dieselben klickbaren Marker-Buttons.

**Praktisches Beispiel:**

Ein Standardtext für eine Mahnung könnte so aussehen:

```
Sehr geehrte Damen und Herren,

bezugnehmend auf unsere Rechnung {RENR} vom {REDATUM}
in Höhe von {REGESAMT} EUR, die am {REFÄLLIG} fällig war,
möchten wir Sie freundlich an die offene Zahlungspflicht erinnern.

Bitte überweisen Sie den Betrag innerhalb von {REFTAGE} Tagen
auf unser Konto: {IBAN} ({BIC}).
```

> **Tipp:** Marker werden nur ersetzt, wenn der jeweilige Belegtyp in der Kette vorhanden ist. Wenn Sie z. B. `{ANNR}` in einer Rechnung verwenden, aber die Rechnung nicht aus einem Angebot stammt, wird der gesamte Satz entfernt. So bleibt der Text sauber, ohne dass leere Platzhalter erscheinen.

---

## 11. Drucken und Journale

### 11.1 Einzelbelege drucken

Wählen Sie einen Beleg in der Liste und klicken Sie **Drucken** (oder **Strg + P**).

- Das PDF wird automatisch im Verzeichnis `Ausdrucke/{JJJJ}/{MM}/{TT}` gespeichert
- Wenn kein Export-Pfad im Firmenstamm konfiguriert ist, wird das PDF im Anwendungsverzeichnis gespeichert
- Dateiname: `{Typ}_{Belegnummer}.pdf`
- Das PDF öffnet sich automatisch im Standard-PDF-Viewer
- Der Header des PDFs enthält Ihre Firmendaten
- Der Footer enthält Bankverbindung und konfigurierbare Drucktexte

**PDF-Inhalt:** Jedes PDF enthält:

- Firmenlogo (falls konfiguriert)
- Absenderadresse (aus Firmenstamm)
- Empfängeradresse (aus Kundenstamm, zum Zeitpunkt des Belegs gespeichert)
- Belegnummer und Datum
- Betreffzeile
- Positionstabelle mit Artikelnummer, Bezeichnung, Menge, Einheit, Einzelpreis, MwSt, Gesamt
- Zusammenfassung: Zwischensumme, MwSt-Positionen pro Satz, Gesamtsumme
- Zahlungsbedingungen (Fälligkeit, Bankverbindung)
- Optional: Standardtext aus den Firmeneinstellungen
- Belegkette (Vorgängernummern)
- Erstellungsdatum (oben rechts im Header)

**Folgeseite-Hinweis:** Wenn ein Beleg mehrere Seiten hat, erscheint auf jeder Seite bis zur vorletzten der Hinweis "Bitte Folgeseite N beachten!" direkt unter dem Gesamtpreis. Auf der letzten Seite erscheint dieser Hinweis nicht.

### 11.2 Testdruck

Der Testdruck erzeugt ein PDF, das identisch mit dem echten Druck aussieht, aber mit **TESTDRUCK**-Wasserzeichen auf jeder Seite. Das Wasserzeichen liegt garantiert über dem Beleg-Inhalt.

- Der Testdruck speichert **kein** Erstellungsdatum in der Datenbank
- Im Testdruck-PDF erscheint oben rechts "99.99.9999" als Platzhalter
- Der Dateiname beginnt mit `TEST_`

### 11.3 Journale drucken

Unter **Auswertungen → Journal drucken** können Sie Beleglisten als PDF erzeugen:

- **Belegtyp wählen:** Angebote, Aufträge, Lieferscheine, Rechnungen, Mahnungen (oder alle)
- **Jahr und Monat** wählen
- Das Journal zeigt alle Belege des gewählten Zeitraums mit Nummer, Datum, Kunde und Betrag
- **PDF drucken** — das gesamte Journal als PDF exportieren

> **Praxis-Tipp:** Journale sind hilfreich für die Buchhaltung. Sie können jeden Monat ein Journal aller Rechnungen erzeugen und dieses an Ihre Buchhaltung weiterleiten.

---

## 12. Sperren-System

Das Sperren-System schützt Stammdaten vor ungewollten Änderungen.

**So funktioniert es:**

- Im Firmenstamm (Reiter **Sperren**) können Sie einzelne Module sperren
- Ein gesperrtes Modul zeigt die Daten an, aber erlaubt **keine Änderungen**
- Die Sperre gilt für alle offenen Tabs des Moduls
- Die Sperre wird in Echtzeit überwacht — wenn jemand eine Sperre setzt, werden alle anderen Tabs sofort benachrichtigt

**Sperren-Übersicht:**

| Spalte | Beschreibung |
|---|---|
| Modul | Der Name des Moduls (Kunden, Artikel, etc.) |
| Gesperrt | Ob das Modul gesperrt ist |
| Sperre bis | Wann die Sperre automatisch aufgehoben wird |

> **Achtung:** Wenn Sie ein Modul sperren, können Sie auch selbst keine Änderungen mehr vornehmen. Die Sperre muss explizit aufgehoben werden.

---

### 12.1 E-Mail-Postausgang

Beim Originaldruck eines Belegs (Angebot, Auftrag, Rechnung, Mahnung) wird automatisch eine E-Mail im Postausgang abgelegt, sofern beim Kunden die entsprechende E-Mail-Versandart aktiviert ist. Der Postausgang liegt unter **Module → E-Mails** und zeigt alle ausstehenden, gesendeten und fehlerhaften E-Mails.

**E-Mail-Client wählen:**

Unter *Firmenstamm → Parameter* wählen Sie aus, über welchen Weg der Versand erfolgt. Pro Firma ist genau ein Client aktiv:

| Client | Versandart | Anhang | Voraussetzung |
|---|---|---|---|
| Brevo | HTTP-API (Cloud) | automatisch | Brevo-Konto, API-Key |
| Gmail | SMTP (smtp.gmail.com:587, STARTTLS) | automatisch | Gmail-Konto, 2-Faktor-Authentifizierung, App-Passwort |
| Outlook 365 Classic | Lokale Desktop-App (COM) | automatisch | Outlook 365 Classic installiert, `pywin32` |
| New Outlook | `mailto:`-Aufruf | manuell per Drag & Drop | New Outlook als Standard-Mailclient |

**Gmail einrichten:**

Gmail erlaubt keinen Versand über Ihr normales Konto-Passwort. Sie benötigen ein **App-Passwort**:

1. 2-Faktor-Authentifizierung im Google-Konto aktivieren.
2. Unter `https://myaccount.google.com/apppasswords` ein neues App-Passwort generieren.
3. Das 16-stellige Passwort in *Firmenstamm → Parameter → Gmail App-Passwort* eintragen, dazu die zugehörige Gmail-Adresse.

**Versandoptionen pro Beleg und Kunde:**

Am Kunden steuern Sie für jeden Belegtyp (Rechnung, Angebot, Auftrag, Mahnung) separat:

- `0` — kein E-Mail-Versand
- `1` — PDF-Datei als Anhang
- `2` — E-Rechnung-XML als Anhang
- `3` — PDF und E-Rechnung-XML gemeinsam

---

### 12.2 E-Rechnung-Spool

Wenn beim Kunden die Option **„E-Rechnung erstellen"** aktiviert ist, wird beim ersten echten Druck einer Rechnung automatisch eine maschinenlesbare XML-Datei nach **EN 16931** erzeugt und im Spool abgelegt.

**Module → E-Rechnung-Spool** listet alle vorliegenden Dateien. Doppelklick öffnet die XML im Standard-Editor; **„Im Explorer anzeigen"** öffnet das Spool-Verzeichnis direkt.

Wiederholungsdrucke erzeugen keine neue XML — sie bleibt vom Original-Druck unverändert.

---

## 13. Firmenverwaltung (Admin)

Die Funktionen in diesem Bereich sind **Admin-Funktionen** und müssen vorher im Menü "Admin Einstellungen" aktiviert werden.

### 13.1 Firma kopieren

Mit dieser Funktion können Sie eine existierende Firma (inklusive aller zugehörigen Daten) als Vorlage verwenden, um eine neue Firma anzulegen.

**Was kopiert wird:**

- Firmenadresse und Kontaktdaten
- Alle Kunden und Artikel
- Alle Belege und Positionen (Angebote, Aufträge, Lieferscheine, Rechnungen, Mahnungen)
- Geschäftsjahre und Belegzähler
- Basiszinssätze

**Wichtig zu wissen:**

- Die kopierte Firma bekommt eine **neue, eigene ID**
- Kundennummern und Artikelnummern bleiben identisch zur Quelle
- Belege bekommen **neue Nummern** basierend auf den Zählern der neuen Firma
- Globale Tabellen (MwSt-Klassen, Zahlungskonditionen, Mahnkonditionen) werden **nicht** kopiert — diese werden firmenübergreifend geteilt
- Die Kopie ist eine vollständige, unabhängige Firma

**So verwenden Sie die Funktion:**

1. Aktivieren Sie "Firma kopieren aktivieren" in den Admin-Einstellungen
2. Öffnen Sie den Firmenstamm und klicken Sie auf den Button "Firma kopieren"
3. Wählen Sie die Quell-Firma und geben Sie die Zieldaten ein
4. Bestätigen Sie die Kopie

### 13.2 Firma löschen <a id="132-firma-loeschen"></a>

Das Löschen einer Firma kann auf zwei Arten erfolgen:

**Soft-Delete (Standard):**

- Die Firma wird als "gelöscht" markiert, aber die Daten bleiben in der Datenbank
- Gelöschte Firmen können bei Bedarf wiederhergestellt werden
- Dies ist die Standardfunktion und erfordert keine Aktivierung

**Hard-Delete (Admin):**

- Die Firma wird zusammen mit allen zugehörigen Daten **völlig** aus der Datenbank entfernt
- Diese Aktion ist **unwiderruflich**
- Aktivieren Sie "Firma löschen aktivieren" in den Admin-Einstellungen, um diese Funktion zu nutzen
- Beim Hard-Delete können Sie wählen, welche Daten mitgelöscht werden sollen (Belege, Stammdaten oder alles)

> **Achtung:** Hard-Delete ist endgültig. Vor dem völligen Löschen sollten Sie ein Backup der Datenbank erstellen.

---

## 14. Import und Export

Die Anwendung unterstützt das Exportieren und Importieren aller Daten.

**Daten exportieren:**

Menü **Datei → Daten exportieren**:

- Alle Daten werden in eine JSON-Datei geschrieben
- Die Datei wird im Anwendungsverzeichnis gespeichert
- Verwenden Sie dies für **Backups** oder zum Übertragen auf ein anderes System

**Daten importieren:**

Menü **Datei → Daten importieren**:

- Wählen Sie eine vorher exportierte JSON-Datei aus
- Die Daten werden in die bestehende Datenbank übernommen

> **Achtung:** Importierte Daten werden **hinzugefügt** — bestehende Daten werden nicht automatisch gelöscht. Wenn Sie Daten in eine leere Datenbank importieren möchten, sollten Sie zuerst die Datenbankdatei sichern und dann löschen.

---

## 15. Rechtschreibprüfung <a id="15-rechtschreibpruefung"></a>

Die Anwendung prüft die Rechtschreibung in Freitextfeldern und Standardtexten.

**So funktioniert es:**

- Falsch geschriebene Wörter werden **rot wellig unterstrichen**
- Die Prüfung erfolgt automatisch nach einer kurzen Pause (wenn Sie aufhören zu tippen)
- Gilt für alle freien Textfelder und Textareas

**Abkürzungen und Fachbegriffe:**

Die Anwendung kennt bereits eine Reihe von Fachbegriffen und Abkürzungen (z. B. "USt-ID", "Mahnkondition", "SEPA", "IBAN", "BIC"). Diese werden nicht als Fehler markiert.

**Wenn die Rechtschreibprüfung nicht funktioniert:**

Die Prüfung benötigt Hunspell-Dictionaries für Deutsch. Wenn keine installiert sind, funktioniert die Anwendung trotzdem — nur ohne Unterstreichung von Fehlern.

> **Lösung:** Installieren Sie Hunspell mit deutschen Dictionaries (`de_DE.aff` / `de_DE.dic`). Alternativ funktioniert pyenchant mit einem systemweiten Hunspell. Das Installationsprogramm `Install_Rechtschreibpruefung.cmd` nimmt Ihnen diese Arbeit ab.

---

## 16. Einstellungen

**Sprache:**

Umschalten zwischen Deutsch und Englisch. Erreichbar über das Hauptmenü. Die gesamte Benutzeroberfläche wechselt sofort; die kontextbezogene F1-Hilfe öffnet dann `doku.de.html` (Deutsch) bzw. `doku.en.html` (Englisch).

**Dark Mode:**

Umschalten zwischen hellem und dunklem Design. Erreichbar über das Hauptmenü.

**Programmeinstellungen (Admin):**

- **Firma löschen aktivieren** — schaltet den Hard-Delete-Modus frei
- **Firma kopieren aktivieren** — schaltet die Firma-Kopier-Funktion frei
- **Satz-ID anzeigen** — zeigt oder blendet die interne Satz-ID in den Tabellen

Die Fenstergröße und -position werden automatisch gespeichert. Auch die Größe aller Dialogfenster und die Spaltenbreiten in Tabellen werden gemerkt.

---

## 17. Datenbank und Sicherung

Alle Daten werden in einer SQLite-Datenbank (`app/daten/auftragsabwicklung.db`) gespeichert.

**Automatische Schema-Updates:**

Beim Programmstart wird die Datenbankversion geprüft und automatisch auf den aktuellen Stand gebracht. Sie müssen nichts manuell tun.

**Backup erstellen:**

Ein Backup ist einfach — kopieren Sie die Datenbankdatei:

```
copy app\daten\auftragsabwicklung.db app\daten\auftragsabwicklung.db.bak
```

Oder verwenden Sie die Export-Funktion im Menü (Menü Datei → Daten exportieren).

> **Regelmäßig sichern!** Es empfiehlt sich, die Datenbank regelmäßig zu sichern — z. B. nach jeder Änderung an wichtigen Belegen. Eine einfache Methode: Kopieren Sie die Datenbankdatei in ein Backup-Verzeichnis mit Datum.

---

## 18. Test-Modus

Der Test-Modus dient dazu, die Anwendung mit veränderten Daten zu testen, ohne das echte Datum zu verändern.

**Aktivieren:**

1. Öffnen Sie den Firmenstamm
2. Aktivieren Sie die Checkbox "Test aktivieren" (neben "Gelöschte Firmen anzeigen")
3. Ein Button **+10** erscheint in der Sidebar unter dem Belegdatum

**Funktionsweise:**

- Jeder Klick auf **+10** erhöht das Belegdatum um 10 Tage
- So können Sie schnell in die "Zukunft" springen und z. B. Mahnungen oder Fälligkeiten testen
- Der Test-Modus wird in den Einstellungen gespeichert (persistent)
- Das Belegdatum selbst ist **nicht persistent** — bei Neustart zurück auf "heute"

---

## 19. Hinweise und FAQ

### Warum erscheint die Belegnummer erst beim Speichern?

Die Nummer wird erst beim Speichern vergeben, damit nicht gespeicherte Belege keine Nummer verbrauchen. Wenn Sie einen Beleg erstellen und dann schließen, bleibt der Zähler unverändert.

### Was passiert, wenn sich der MwSt-Satz ändert?

Jede Position speichert den MwSt-Satz zum Zeitpunkt ihrer Entstehung. Eine Änderung des Satzes betrifft nur neue Positionen. Alte Belege bleiben korrekt.

### Kann ich gelöschte Belege wiederherstellen?

Ja. Da alle Löschungen "Soft-Delete" sind, bleiben die Daten in der Datenbank. Sie können über die Funktion "Wiederherstellen" den Beleg zurückbringen.

### Warum kann ich einen Beleg nicht löschen?

Wenn der Beleg lebende Nachfolger hat (z. B. ein Angebot, aus dem ein Auftrag erstellt wurde), wird das Löschen verhindert. Sie müssen zuerst die Nachfolger löschen oder wiederherstellen.

### Warum erscheint die Rechtschreibprüfung nicht?

Die Prüfung benötigt Hunspell-Dictionaries. Wenn keine installiert sind, funktioniert die Anwendung trotzdem, aber ohne Unterstreichung von Fehlern. Siehe [Rechtschreibprüfung](#15-rechtschreibpruefung).

### Seitennummerierung in PDFs

Die Seitennummerierung erfolgt im Format `gesamt - aktuelle` (z. B. `2 - 1`, `2 - 2`).

### Kann ich mehrere Belege parallel bearbeiten?

Ja. Sie können mehrere Tabs gleichzeitig öffnen und zwischen ihnen wechseln. Jeder Tab arbeitet mit denselben Daten, aber jede Änderung wird erst beim Speichern wirksam.

### Was ist das Erstellungsdatum?

Das Erstellungsdatum wird beim ersten Druck eines Belegs festgeschrieben (Datum + Uhrzeit). Es bleibt danach unveränderbar und erscheint im Beleg-Dialog sowie im PDF-Header (oben rechts). Beim Testdruck wird kein Erstellungsdatum gespeichert.

---

*Stand: Mai 2026*
