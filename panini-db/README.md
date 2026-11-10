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
python3 stickerdb.py import-albums data/albums.csv          # Start-Katalog (10 aktuelle Alben)
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
