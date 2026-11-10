-- Panini-Sticker-Datenbank (SQLite; mit kleinen Anpassungen auch PostgreSQL/MySQL)
--
-- Grundidee: Getauscht wird über Album + Sticker-Code. Name, Mannschaft und Bild
-- sind optionale Zusatzinfos – ein Album ist schon nutzbar, sobald bekannt ist,
-- welche Sticker-Codes es gibt.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS publishers (
    id    INTEGER PRIMARY KEY,
    slug  TEXT NOT NULL UNIQUE,          -- z. B. "panini"
    name  TEXT NOT NULL                  -- z. B. "Panini"
);

-- Ein Album bzw. eine Kollektion (z. B. "FIFA World Cup 2026", deutsche Ausgabe)
CREATE TABLE IF NOT EXISTS albums (
    id             INTEGER PRIMARY KEY,
    slug           TEXT NOT NULL UNIQUE,  -- stabiler Schlüssel, z. B. "panini-3-liga-2026-2027"
    publisher_id   INTEGER NOT NULL REFERENCES publishers(id),
    title          TEXT NOT NULL,
    year           INTEGER,               -- Erscheinungsjahr
    season         TEXT,                  -- z. B. "2026/27"
    category       TEXT,                  -- z. B. "Fußball", "Film & TV", "Tiere"
    region         TEXT,                  -- Ausgabe/Land, z. B. "DE", "INT", "US"
    kind           TEXT NOT NULL DEFAULT 'sticker' CHECK (kind IN ('sticker','card','mixed')),
    total_stickers INTEGER,               -- offizielle Anzahl laut Verlag/Album
    cover_url      TEXT,
    source         TEXT,                  -- woher die Album-Daten stammen
    notes          TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_albums_year ON albums(year);
CREATE INDEX IF NOT EXISTS idx_albums_category ON albums(category);

-- Abschnitte im Album (Mannschaft, Kapitel, Sonderseiten …)
CREATE TABLE IF NOT EXISTS sections (
    id        INTEGER PRIMARY KEY,
    album_id  INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    name      TEXT NOT NULL,
    position  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (album_id, name)
);

-- Einzelne Sticker. "code" ist das, was auf dem Sticker steht ("1", "00", "GER12", "FWC5", "M3").
CREATE TABLE IF NOT EXISTS stickers (
    id          INTEGER PRIMARY KEY,
    album_id    INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    code        TEXT NOT NULL,
    sort_key    INTEGER NOT NULL,          -- Reihenfolge im Album (aus code abgeleitet oder Zeilennummer)
    name        TEXT,                      -- Spieler, Figur, Motiv
    team        TEXT,                      -- Mannschaft/Gruppe (optional, Freitext)
    section_id  INTEGER REFERENCES sections(id) ON DELETE SET NULL,
    variant     TEXT NOT NULL DEFAULT 'normal', -- normal, glitzer, extra, gold, ...
    is_special  INTEGER NOT NULL DEFAULT 0 CHECK (is_special IN (0,1)),
    UNIQUE (album_id, code)
);
CREATE INDEX IF NOT EXISTS idx_stickers_album_sort ON stickers(album_id, sort_key);
CREATE INDEX IF NOT EXISTS idx_stickers_name ON stickers(name);

-- Bilder kommen NICHT aus einer Websuche, sondern aus Dateien/Uploads (siehe README).
CREATE TABLE IF NOT EXISTS sticker_images (
    id           INTEGER PRIMARY KEY,
    sticker_id   INTEGER NOT NULL REFERENCES stickers(id) ON DELETE CASCADE,
    path         TEXT NOT NULL,            -- relativer Pfad oder URL im eigenen Speicher
    origin       TEXT NOT NULL DEFAULT 'import' CHECK (origin IN ('import','user_upload','publisher')),
    uploaded_by  TEXT,                     -- Nutzer-ID aus dem Portal (bei Uploads)
    status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
    sha256       TEXT,                     -- verhindert doppelte Bilder
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (sticker_id, sha256)
);

-- Sammlungen der Portal-Nutzer: quantity = wie oft vorhanden (0 = fehlt, >=2 = doppelt).
-- user_id ist bewusst TEXT ohne Fremdschlüssel, damit die Tabelle an jedes Nutzer-System passt.
CREATE TABLE IF NOT EXISTS user_albums (
    user_id   TEXT NOT NULL,
    album_id  INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, album_id)
);

CREATE TABLE IF NOT EXISTS inventory (
    user_id    TEXT NOT NULL,
    sticker_id INTEGER NOT NULL REFERENCES stickers(id) ON DELETE CASCADE,
    quantity   INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    PRIMARY KEY (user_id, sticker_id)
);

-- Was jemand in einem Album sammelt, aber noch nicht hat.
CREATE VIEW IF NOT EXISTS v_needs AS
SELECT ua.user_id, s.album_id, s.id AS sticker_id, s.code
FROM user_albums ua
JOIN stickers s ON s.album_id = ua.album_id
LEFT JOIN inventory i ON i.user_id = ua.user_id AND i.sticker_id = s.id
WHERE COALESCE(i.quantity, 0) = 0;

-- Doppelte, die jemand abgeben kann.
CREATE VIEW IF NOT EXISTS v_offers AS
SELECT i.user_id, s.album_id, s.id AS sticker_id, s.code, i.quantity - 1 AS spare
FROM inventory i
JOIN stickers s ON s.id = i.sticker_id
WHERE i.quantity >= 2;

-- Tauschmöglichkeiten: wer (giver) kann wem (taker) welchen Sticker geben.
CREATE VIEW IF NOT EXISTS v_swap_candidates AS
SELECT o.user_id AS giver, n.user_id AS taker, o.album_id, o.sticker_id, o.code
FROM v_offers o
JOIN v_needs n ON n.sticker_id = o.sticker_id AND n.user_id <> o.user_id;

-- Fortschritt je Nutzer und Album
CREATE VIEW IF NOT EXISTS v_album_progress AS
SELECT ua.user_id, a.id AS album_id, a.title,
       COUNT(s.id) AS total,
       SUM(CASE WHEN COALESCE(i.quantity,0) > 0 THEN 1 ELSE 0 END) AS owned,
       SUM(CASE WHEN COALESCE(i.quantity,0) > 1 THEN i.quantity - 1 ELSE 0 END) AS duplicates
FROM user_albums ua
JOIN albums a ON a.id = ua.album_id
LEFT JOIN stickers s ON s.album_id = a.id
LEFT JOIN inventory i ON i.user_id = ua.user_id AND i.sticker_id = s.id
GROUP BY ua.user_id, a.id;
