# Panini-Sticker-Datenbank

Grundlage für das Sticker-Tauschportal: Alben, Sticker, Bilder und Sammlungen der Nutzer
in einer SQLite-Datenbank. Läuft ohne Installation mit Python 3.9+ (nur Standardbibliothek).
Der Ordner hängt nicht mit dem Spiele-Scanner zusammen und kann 1:1 ins Portal-Repo verschoben werden.

## Wichtigste Idee

Getauscht wird über **Album + Sticker-Code**. Name, Mannschaft und Bild sind Zusatzinfos.
Ein Album ist deshalb schon nutzbar, sobald bekannt ist, welche Codes es gibt –
notfalls als nummerierte Platzhalter (`fill`). Namen und Bilder kommen später dazu.

## Schnellstart

```bash
cd panini-db
python3 stickerdb.py fetch                                   # offizielle Panini-Checklisten laden (data/sources.csv)
python3 stickerdb.py import - data/checklists/panini-dfb-team-set-2024.json   # oder offline aus dem Repo
python3 stickerdb.py import-albums data/albums.csv          # Start-Katalog (10 aktuelle Alben, noch ohne Sticker)
python3 stickerdb.py import panini-3-liga-2026-2027 liste.txt --dry-run   # erst prüfen
python3 stickerdb.py import panini-3-liga-2026-2027 liste.txt             # dann speichern
python3 stickerdb.py fill panini-fifa-365-2027 --to 591      # oder nur Nummern 1..591
python3 stickerdb.py stats                                   # was ist wie vollständig?
python3 stickerdb.py export panini-3-liga-2026-2027 > 3liga.json
```

Die Datei heißt standardmäßig `stickers.db` (änderbar mit `--db` oder `STICKER_DB`).
Tests: `python3 -m unittest discover -s tests`

## Checklisten-Formate

| Format | Aufbau |
|---|---|
| `.txt` | Eine Zeile pro Sticker: `12 Max Mustermann - FC Beispiel` oder `12 Max Mustermann (FC Beispiel)`. Zeilen ohne Nummer gelten als Abschnitt (Mannschaft/Kapitel). Codes wie `00`, `FWC5`, `GER 12`, `12a` werden erkannt. Siehe `data/checklists/BEISPIEL-format.txt`. |
| `.csv` | Kopfzeile mit `code` (oder `Nr`), optional `name`/`Spieler`, `team`/`Verein`, `section`, `variant`, `special`/`Glitzer`. Trennzeichen `,` `;` oder Tab. Excel-Export geht direkt. |
| `.pdf` | Offizielle Panini-Checklisten (Text-PDFs, mehrspaltig). Braucht `pdftotext` (Paket `poppler-utils`). Vorher mit `--dry-run` prüfen. |
| `.json` | Das Format von `export` – enthält Album und Sticker, ideal zum Austausch zwischen Datenbanken. Mit Album-Slug `-` wird der Slug aus der Datei übernommen. |

Ein erneuter Import desselben Albums aktualisiert vorhandene Sticker und lässt die Sammlungen
der Nutzer unangetastet. `--replace` entfernt zusätzlich Sticker, die nicht mehr in der Liste
stehen (und damit auch deren Sammlungseinträge) – nur bewusst einsetzen.

## Bilder – ohne laufende Suche

Bilder werden nicht im Netz gesucht, sondern als Dateien zugeordnet:

```
bilder/
  panini-3-liga-2026-2027/
    1.jpg
    2.jpg
    FWC5.png
```

```bash
python3 stickerdb.py attach-images bilder/            # landet als "pending" zur Prüfung
python3 stickerdb.py attach-images bilder/ --approve  # direkt freigeben
```

Gespeichert werden nur Pfad und Prüfsumme (doppelte Bilder werden erkannt). Im Portal am
einfachsten: Nutzer fotografieren ihre eigenen Sticker beim Eintragen, das Foto kommt mit
`origin = 'user_upload'` und `status = 'pending'` in `sticker_images`, ein Admin gibt frei.
So wächst der Bildbestand mit der Community von allein.

**Rechtlich beachten:** Sticker-Motive und Fotos darauf sind urheberrechtlich geschützt
(Panini bzw. Lizenzgeber wie FIFA, Vereine, Disney …). Kleine Vorschaubilder zum
Identifizieren beim Tausch sind gängig, aber vor dem Livegang solltest du das prüfen lassen
oder bei Panini nachfragen. Auch fremde Tauschbörsen-Datenbanken (z. B. LastSticker) in großem
Stil zu übernehmen ist heikel (Datenbankherstellerrecht, §87b UrhG) – daher gibt es hier
bewusst keinen Scraper für solche Seiten.

## Woher die Checklisten kommen

### Automatisch von panini.de: `fetch`

`data/sources.csv` listet offizielle Checklisten-PDFs von panini.de. `fetch` lädt sie herunter
(einmalig, Cache in `.cache/`) und importiert sie – ohne Claude, z. B. per Cronjob.
Neue Kollektion = eine Zeile mit der PDF-Adresse ergänzen. PDFs findest du auf den
Produktseiten von panini.de („Zur Checkliste“) oder per Suche `site:panini.de/media/paniniFiles checkliste`.

Bereits enthalten (alle lückenlos geprüft, auch als JSON in `data/checklists/`):

| Kollektion | Art | Anzahl |
|---|---|---|
| Deutschland 2024 & die Besten aus Europa | Sticker | 290 |
| Score FIFA 2023-24 | Cards | 399 |
| DFB Team-Set 2024 | Cards | 119 |
| DFB-Frauen Team-Set 2025 | Cards | 126 (RIS-04 fehlt auch im Panini-PDF) |
| Google Pixel Frauen-Bundesliga 2024-25 | Cards | 208 (RISE-13/14 ohne Namen im PDF) |
| PDC World Championship 2025 | Cards | 221 |
| PDC World Championship 2026 | Cards | 321 |
| PDC Premier League Darts | Cards | 150 |

Zusätzlich aus offiziellen Panini-Quellen, nur als JSON in `data/checklists/` (nicht über `fetch`):

| Kollektion | Art | Anzahl | Stand |
|---|---|---|---|
| FIFA World Cup 2026 | Sticker | 980 | Alle Codes, Logo/Teamfoto/Intro benannt; Spielernamen erst für MEX, RSA, KOR und CZE 2–11 (Panini-Nachbestellshop zeigt nur die ersten 80) |
| FIFA World Cup 2026 – Update Set | Sticker | 118 | Vollständig (Panini-PDF), Code = ersetzter Platz im Hauptalbum |
| FIFA World Cup 2026 – Extra Stickers | Sticker | 80 | Vollständig (paninigroup.com): 20 Motive × regular/bronze/silver/gold, Codes `EXTRA-<Team>[-Farbe]` sind eigene Schlüssel |
| Google Pixel Frauen-Bundesliga 2024/25 | Sticker | 340 | Vollständig (Panini-PDF), PDF-Kodierfehler bei 132/196/212 korrigiert |

Für die fehlenden WM-Namen gilt: nur aus offiziellen Quellen oder von Nutzern ergänzen
(`import panini-fifa-world-cup-2026 liste.txt` aktualisiert vorhandene Codes, ohne Sammlungen zu verändern).

Grenzen: Viele Panini-PDFs sind eingescannte Bilder ohne Text (Disney, One Piece, Harry Potter,
Adrenalyn-Ordner …) – die liefern beim `fetch` die Meldung „keine Sticker erkannt“. Die
Checklisten der großen Sticker-Alben (WM 2026, Bundesliga, 3. Liga …) stehen bei Panini
meist nicht als PDF, sondern nur im Shop unter „fehlende Bilder“ (dort per JavaScript und hinter
einer Warteschlange) – dafür bleibt der Weg über `import` mit abgetippter/kopierter Liste.

### Weitere Wege

- **Panini selbst:** Checklisten auf paninigroup.com / paniniamerica.net und meist auf der
  letzten Albumseite – abtippen oder als Text kopieren und mit `import` einlesen.
- **Die eigene Community:** Ein Formular im Portal „Album fehlt / Liste korrigieren“, das eine
  `.txt`/`.csv` annimmt und nach Prüfung importiert. So wird die Datenbank mit der Zeit vollständig.
- **Ohne Liste:** `fill` mit der Gesamtzahl aus dem Album – Tauschen funktioniert sofort.

`data/albums.csv` enthält einen Start-Katalog aktueller Alben. Die offizielle Gesamtzahl
(`total_stickers`) ist dort bewusst leer gelassen, weil öffentliche Angaben je nach Ausgabe
abweichen – bitte aus dem Album übernehmen.

## Tabellen

| Tabelle/Sicht | Inhalt |
|---|---|
| `publishers`, `albums`, `sections`, `stickers` | Katalog |
| `sticker_images` | Bilder mit Herkunft und Freigabe-Status |
| `user_albums`, `inventory` | Was ein Nutzer sammelt und wie oft er jeden Sticker hat (0 = fehlt, ≥2 = doppelt) |
| `v_needs`, `v_offers` | Fehlende bzw. doppelte Sticker je Nutzer |
| `v_swap_candidates` | Wer kann wem welchen Sticker geben – Grundlage für Tauschvorschläge |
| `v_album_progress` | Fortschritt je Nutzer und Album |

`user_id` ist Text ohne Fremdschlüssel, damit es zu jedem Login-System passt. Das Schema ist
SQLite; für PostgreSQL `INTEGER PRIMARY KEY` → `SERIAL`/`IDENTITY` und `datetime('now')` → `now()` ersetzen.
