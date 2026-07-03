# Prüfung nach der EU-KI-Verordnung (AI Act)

**Programm:** Auftragsabwicklung (Order Management System)
**Rechtsgrundlage:** Verordnung (EU) 2024/1689 („KI-Verordnung" / „AI Act")
**Prüfdatum:** 2026-07-03
**Ergebnis:** **Kein Verstoß.** Die KI-Nutzung fällt in die Kategorie *minimales Risiko*. Eine Lücke bei der Kennzeichnungs-Robustheit wurde im Zuge der Prüfung geschlossen (siehe Abschnitt 5).

> **Keine Rechtsberatung:** Dieser Bericht dokumentiert die technische Selbsteinschätzung des Programms. Er ersetzt keine individuelle rechtliche Beratung. Verantwortlich für den rechtskonformen Einsatz bleibt der Betreiber.

---

## 1. KI-Inventar (was das Programm mit KI macht)

Sämtliche LLM-Kommunikation läuft über einen einzigen Client (`app/ki_client.py`, OpenAI-kompatibel bzw. Anthropic-Messages-API). Konfigurierbare Anbieter: **OpenRouter** (Cloud), **Anthropic** (Cloud), **lokaler Server** (LM Studio/vLLM, on-premises). Funktionen:

| Funktion | Modul | Inhalt |
|---|---|---|
| Belegübersetzung beim Druck (Kundenkopie) | `app/uebersetzung.py`, `app/druck_beleg.py` | Positions-Bezeichnung/-Beschreibung, Sicherheitshinweise, Herstellerinfo, Betreff, Freitexte, Steuerhinweis |
| Rückübersetzung + Qualitätsbewertung | `app/uebersetzung.py` (`uebersetze_rueck`, `bewerte_und_korrigiere`) | Gegenprobe/Bewertung gepflegter Übersetzungen (Drucktexte, Einheiten, App-Sprachen) |
| Rechtschreib-/Grammatikkorrektur | `app/modul/mod_artikel.py` | Artikeltexte, auf Knopfdruck, mit Anzeige vor Übernahme |
| App-Sprachdatei-Generator | `app/modul/mod_sprachdatei.py`, `sprachdatei_lauf.py` | UI-Strings; Rückübersetzungs-Kontrolle + manuelle Bestätigung |
| Sprach-Selbsteinschätzung des Modells | `app/mod_firma_tabs/mod_firma_laender.py` | Ja/Nein + Fähigkeitsnote je Sprache |

**Nicht an das LLM übertragen werden:** Kundenname/Adressblock (Kopf/Fuß des Belegs wird nicht übersetzt), Zahlen/Beträge, E-Mail-Texte (`email_gen.py` nutzt keine KI), E-Rechnungs-XML (wird nie übersetzt).

## 2. Einstufung nach Risikoklassen

- **Verbotene Praktiken (Art. 5):** nicht einschlägig. Keine Manipulation, kein Social Scoring, keine biometrische Erkennung.
- **Hochrisiko (Art. 6 / Anhang III):** nicht einschlägig. Es gibt **keine automatisierten Entscheidungen über natürliche Personen** — Mahnwesen, Preisfindung, MwSt und Fristen sind vollständig regelbasiert (Stammdaten/Konditionen). Kein Scoring, keine Bonitätsbewertung, keine Beschäftigten-/Bildungs-/Justiz-Kontexte.
- **Transparenzpflichtige Systeme (Art. 50):** teilweise einschlägig, siehe Abschnitt 3. Kein Chatbot / keine direkte KI-Interaktion mit natürlichen Personen (Art. 50 Abs. 1), keine Deepfakes, keine Texte zur Information der Öffentlichkeit (Art. 50 Abs. 4).
- **GPAI-Modelle (Kap. V):** Die Pflichten treffen die **Modellanbieter** (OpenRouter/Anthropic bzw. den Betreiber des lokalen Modells), nicht dieses Programm als API-Nutzer.

**Ergebnis: minimales Risiko.** Verbleibende relevante Pflichten: Transparenz/Kennzeichnung (Art. 50, anwendbar ab 02.08.2026) und KI-Kompetenz der Betreiber (Art. 4, anwendbar seit 02.02.2025).

## 3. Transparenz & Kennzeichnung (Art. 50)

KI-generierte Inhalte erreichen Dritte ausschließlich über die **übersetzte Kundenkopie** eines Belegs. Diese ist doppelt gekennzeichnet:

1. Kopfzeile „Kundenkopie in {Sprache}".
2. **KI-Disclaimer** im Fuß der letzten Seite (rot), Standardtext: *„Die Übersetzung erfolgte mit Hilfe einer KI {LLM}. Der Ausdruck erfolgt nur informatorisch. Rechtswirksam ist ausschließlich das Original in {firmensprache}."* — nennt das verwendete Modell und stellt die Rechtsverbindlichkeit des Originals klar.

Das Original wird immer zuerst vollständig in der Firmensprache gedruckt; die KI-Kopie ist rein informatorisch. Reine Übersetzung ohne wesentliche inhaltliche Veränderung fällt zudem unter die Unterstützungs-Ausnahme des Art. 50 Abs. 2 — die Kennzeichnung geht damit über das Pflichtmaß hinaus (Good Practice).

## 4. KI-Kompetenz (Art. 4) und Datenschutz-Randpunkte

- Die Anwenderdoku (`app/doku.de.html`, Abschnitt „EU-KI-Verordnung (AI Act)", Anker `#ki-eu-ai-act`) erläutert Einstufung, Kennzeichnung, Grenzen der maschinellen Übersetzung und den Rückübersetzungs-/Bewertungs-Workflow als Kontrollinstrument — Grundlage für die Betreiber-Pflicht aus Art. 4.
- **DSGVO-Randpunkt:** Frei eingegebene Betreff-/Freitexte werden bei Cloud-Anbietern mit übertragen. Die Doku warnt jetzt ausdrücklich davor, dort personenbezogene Daten einzutragen, und verweist auf den lokalen KI-Server als datensparsame Alternative. Der Adressblock wird systembedingt nie übertragen.
- Klartext-Protokoll `app/daten/uebersetzung.log` entsteht **nur** im Admin-Übersetzungstest-Modus; der Produktivbetrieb protokolliert ausschließlich Token-Metriken (`app/token_log.py`, `TOKENS.DB`).

## 5. Gefundene Lücke und Behebung (2026-07-03)

**Lücke:** Der KI-Disclaimer war frei editierbar und durfte leer gespeichert werden (`mod_firma_steuerung.py`); `druck_beleg.py` druckte dann die Kundenkopie **ohne** KI-Kennzeichnung — die Transparenz war faktisch abschaltbar.

**Behebung (Fallback beim Druck):**
- `app/ki_client.py`: neue Konstante `KI_DISCLAIMER_DEFAULT` (Standardtext, identisch zum DB-Default).
- `app/druck_beleg.py`: Ist das Firmenfeld leer, wird beim Druck der Kundenkopie automatisch der Standardtext verwendet — die Kennzeichnung kann nicht mehr entfallen. Originaldrucke bleiben unverändert ohne Disclaimer.
- `app/language.json` (`firma.steuerung.ki_disclaimer_hint`): Hinweis im Firmenstamm → Steuerung ergänzt.
- `app/doku.de.html`: neuer Abschnitt `#ki-eu-ai-act` + Fallback-Hinweis beim Steuerung-Feld.

## 6. Restpunkte / Empfehlungen (kein AI-Act-Verstoß)

| Punkt | Einordnung |
|---|---|
| API-Keys unverschlüsselt in der DB (nur Admins sehen sie; dokumentiert in `doku.de.html`) | IT-Sicherheit, nicht AI Act. Empfehlung: mittelfristig Verschlüsselung oder OS-Credential-Store erwägen. |
| ~~`doku.en.html` veraltet~~ | **Erledigt 2026-07-03:** EN-Doku vollständig nachgezogen, inkl. Abschnitt `#ki-eu-ai-act` („EU AI Act"). |
| Kein erzwungener Freigabe-Klick vor Druck der übersetzten Kundenkopie | Nach Einstufung (minimales Risiko) nicht erforderlich; Disclaimer + rechtsverbindliches Original genügen. Rückübersetzungs-Workflow für gepflegte Texte vorhanden. |
| Anwenderschulung (Art. 4) | Doku-Abschnitt vorhanden; Betreiber sollte neue Anwender aktiv darauf hinweisen. |
