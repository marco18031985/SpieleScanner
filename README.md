# Spiele-Scanner (Android)

Barcode einer Spielepackung scannen → Titel, Spielerzahl, Alter, Spieldauer, Verlag, Beschreibung.
Datenquellen: UPCitemdb (kostenlos, ca. 100 Abfragen/Tag), Wikidata, Wikipedia.

## APK von GitHub bauen lassen

1. Auf github.com einloggen → oben rechts **+** → **New repository** → Name z. B. `spiele-scanner` → **Create repository**.
2. Auf der leeren Repo-Seite **uploading an existing file** anklicken und den **Inhalt** dieses Ordners hineinziehen
   (alle Dateien und Ordner, auch den Ordner `.github`) → **Commit changes**.
   - Auf dem Mac ist `.github` im Finder versteckt: im Finder **Cmd + Shift + .** drücken, dann ist er sichtbar.
3. Reiter **Actions** öffnen. Der Lauf „APK bauen“ startet automatisch und braucht ca. 3–5 Minuten.
4. Danach rechts auf der Repo-Startseite unter **Releases** die neueste Version öffnen und `SpieleScanner.apk` herunterladen –
   am besten direkt auf dem Handy.
5. APK auf dem Handy öffnen. Android fragt einmalig, ob der Browser/Dateimanager Apps installieren darf → erlauben.

Jede Änderung, die du ins Repo hochlädst, erzeugt automatisch eine neue Version, die sich über die alte installiert.

## Hinweise
- Der Scanner kommt aus den Google-Play-Diensten (keine Kamera-Berechtigung nötig). Beim allerersten Start kann er ein paar Sekunden nachladen.
- Findet die App ein Spiel nicht oder falsch: unten den Titel eingeben und das richtige Spiel antippen. Die App merkt sich die Zuordnung für diesen Barcode.
- Der Signaturschlüssel `app/release.keystore` liegt bewusst im Projekt, damit Updates funktionieren. Für eine Veröffentlichung im Play Store bräuchtest du einen eigenen, geheimen Schlüssel.
