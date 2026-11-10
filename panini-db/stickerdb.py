#!/usr/bin/env python3
"""Panini-Sticker-Datenbank: Anlegen, Importieren, Bilder zuordnen, Exportieren.

Nur Python-Standardbibliothek (sqlite3, csv, json) – keine Installation nötig.

Beispiele:
    python3 stickerdb.py init
    python3 stickerdb.py import-albums data/albums.csv
    python3 stickerdb.py import panini-3-liga-2026-2027 checkliste.txt
    python3 stickerdb.py fill panini-3-liga-2026-2027          # Platzhalter 1..N
    python3 stickerdb.py attach-images bilder/ --approve
    python3 stickerdb.py export panini-3-liga-2026-2027 > album.json
    python3 stickerdb.py stats
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_DB = Path(os.environ.get("STICKER_DB", HERE / "stickers.db"))
SCHEMA = HERE / "schema.sql"
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}


# --------------------------------------------------------------------------- DB

def connect(db_path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.commit()


def slugify(text: str) -> str:
    text = text.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def publisher_id(con: sqlite3.Connection, name: str) -> int:
    slug = slugify(name)
    row = con.execute("SELECT id FROM publishers WHERE slug = ?", (slug,)).fetchone()
    if row:
        return row["id"]
    return con.execute("INSERT INTO publishers(slug, name) VALUES (?, ?)", (slug, name)).lastrowid


def album_by_slug(con: sqlite3.Connection, slug: str) -> sqlite3.Row:
    row = con.execute("SELECT * FROM albums WHERE slug = ?", (slug,)).fetchone()
    if not row:
        raise SystemExit(f"Album '{slug}' nicht gefunden. Erst mit 'import-albums' anlegen.")
    return row


ALBUM_FIELDS = ("title", "year", "season", "category", "region", "kind",
                "total_stickers", "cover_url", "source", "notes")


def upsert_album(con: sqlite3.Connection, data: dict) -> int:
    """Legt ein Album an oder aktualisiert es (Schlüssel: slug)."""
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("Album ohne Titel")
    pub = (data.get("publisher") or "Panini").strip()
    slug = (data.get("slug") or "").strip() or slugify(f"{pub} {title}")
    values = {k: (data.get(k) or None) for k in ALBUM_FIELDS}
    values["title"] = title
    values["kind"] = values["kind"] or "sticker"
    for k in ("year", "total_stickers"):
        if values[k] is not None:
            values[k] = int(values[k])
    pid = publisher_id(con, pub)
    cols = ", ".join(ALBUM_FIELDS)
    marks = ", ".join("?" for _ in ALBUM_FIELDS)
    updates = ", ".join(f"{k} = excluded.{k}" for k in ALBUM_FIELDS)
    con.execute(
        f"INSERT INTO albums(slug, publisher_id, {cols}) VALUES (?, ?, {marks}) "
        f"ON CONFLICT(slug) DO UPDATE SET publisher_id = excluded.publisher_id, {updates}, "
        f"updated_at = datetime('now')",
        (slug, pid, *(values[k] for k in ALBUM_FIELDS)),
    )
    return con.execute("SELECT id FROM albums WHERE slug = ?", (slug,)).fetchone()["id"]


# ------------------------------------------------------------------- Checklisten

@dataclass
class StickerRow:
    code: str
    name: str | None = None
    team: str | None = None
    section: str | None = None
    variant: str = "normal"
    is_special: bool = False
    extra: dict = field(default_factory=dict)


# "12 Max Muster - FC Beispiel", "12. Max Muster (FC Beispiel)", "GER 12 Max Muster", "FWC5 Logo"
_LINE = re.compile(r"^\s*(?P<code>(?:[A-Za-z]{1,4}\s?)?\d{1,4}[a-zA-Z]?)\s*[.:)\-–]?\s+(?P<rest>.*)$")
_CODE_ONLY = re.compile(r"^\s*(?P<code>(?:[A-Za-z]{1,4}\s?)?\d{1,4}[a-zA-Z]?)\s*$")
_SPECIAL_HINT = re.compile(r"\b(glitzer|glitter|foil|holo|gold|silber|silver|extra|special|legend|badge|wappen|logo)\b", re.I)


def normalize_code(code: str) -> str:
    return re.sub(r"\s+", "", code.strip()).upper()


def _true(v) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "ja", "yes", "x", "y"}


def parse_text(text: str) -> list[StickerRow]:
    """Liest eine Checkliste als Fließtext, wie sie Verlage/Foren veröffentlichen.

    - Eine Zeile pro Sticker: "<Code> <Name> [- Mannschaft | (Mannschaft)]"
    - Abschnittsüberschriften: Zeilen ohne Code, z. B. "FC Beispiel" oder "## Wappen:"
    """
    rows: list[StickerRow] = []
    section = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _CODE_ONLY.match(line)
        if m:
            rows.append(StickerRow(code=normalize_code(m["code"]), section=section))
            continue
        m = _LINE.match(line)
        if not m:
            section = line.lstrip("#").strip().rstrip(":").strip() or section
            continue
        rest = m["rest"].strip()
        name, team = rest, None
        paren = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", rest)
        if paren:
            name, team = paren[1], paren[2]
        elif " - " in rest or " – " in rest:
            name, team = re.split(r"\s+[-–]\s+", rest, maxsplit=1)
        rows.append(StickerRow(
            code=normalize_code(m["code"]),
            name=name.strip() or None,
            team=(team or "").strip() or None,
            section=section,
            is_special=bool(_SPECIAL_HINT.search(rest)),
        ))
    return rows


def parse_csv(text: str) -> list[StickerRow]:
    """CSV mit Kopfzeile. Pflicht: code. Optional: name, team, section, variant, special."""
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(text.splitlines(), dialect=dialect)
    if not reader.fieldnames:
        return []
    reader.fieldnames = [f.strip().lower() for f in reader.fieldnames]
    aliases = {"nr": "code", "nummer": "code", "number": "code", "no": "code", "no.": "code",
               "spieler": "name", "title": "name", "titel": "name",
               "mannschaft": "team", "verein": "team", "club": "team",
               "abschnitt": "section", "kapitel": "section", "glitzer": "special"}
    rows = []
    for rec in reader:
        rec = {aliases.get(k, k): (v or "").strip() for k, v in rec.items() if k}
        if not rec.get("code"):
            continue
        rows.append(StickerRow(
            code=normalize_code(rec["code"]),
            name=rec.get("name") or None,
            team=rec.get("team") or None,
            section=rec.get("section") or None,
            variant=rec.get("variant") or "normal",
            is_special=_true(rec.get("special")),
        ))
    return rows


def parse_json(text: str) -> tuple[dict | None, list[StickerRow]]:
    """Format von 'export': {"album": {...}, "stickers": [{code, name, team, section, ...}]}."""
    data = json.loads(text)
    album = None
    items = data
    if isinstance(data, dict):
        album = data.get("album")
        items = data.get("stickers", [])
    rows = [StickerRow(
        code=normalize_code(str(it["code"])),
        name=it.get("name"), team=it.get("team"), section=it.get("section"),
        variant=it.get("variant") or "normal", is_special=bool(it.get("is_special")),
    ) for it in items]
    return album, rows


# Spalten-Layout aus PDF-Checklisten (pdftotext -layout): mehrere Spalten pro Zeile,
# jede Spalte beginnt mit einem Code: "1 Cover      51 Manuel Neuer   Deutschland"
_PDF_CODE = r"(?:[A-Z]{1,5}-?\d{1,4}|\d{1,4}[a-z]?)"
_PDF_SEG = re.compile(rf"(?:(?<=^)|(?<=\s{{2}}))\s*(?P<code>{_PDF_CODE})(?:\s+(?=[^\s\d])|\s*$)")


def _natural_key(code: str) -> tuple:
    m = re.match(r"^([A-Z]*)-?(\d+)([A-Z]?)$", code)
    return (m[1], int(m[2]), m[3]) if m else (code, 0, "")


def parse_pdf_text(text: str) -> list[StickerRow]:
    """Liest den Text einer PDF-Checkliste (Ausgabe von `pdftotext -layout`).

    Zeilen werden in Spalten zerlegt; jede Spalte = Code, Name und optional Team
    (durch mind. zwei Leerzeichen getrennt). Zeilen ohne Code (Überschriften, Hinweise)
    werden ignoriert. Ergebnis ist nach Code sortiert, weil die Spalten im PDF
    nebeneinander stehen (1, 51, 2, 52 …).
    """
    rows: dict[str, StickerRow] = {}
    prefix_order: dict[str, int] = {}
    for line in text.splitlines():
        line = line.rstrip()
        starts = [m for m in _PDF_SEG.finditer(line)]
        for i, m in enumerate(starts):
            end = starts[i + 1].start() if i + 1 < len(starts) else len(line)
            parts = [p.strip() for p in re.split(r"\s{2,}", line[m.end():end].strip()) if p.strip()]
            code = normalize_code(m["code"])
            name = parts[0] if parts else None
            team = parts[1] if len(parts) > 1 else None
            if (name and re.fullmatch(r"(Seite|Page)\b.*", name, re.I)) or code in rows:
                continue
            rows[code] = StickerRow(code=code, name=name, team=team,
                                    is_special=bool(name and _SPECIAL_HINT.search(name)))
            prefix_order.setdefault(_natural_key(code)[0], len(prefix_order))
    # Überschriften wie "2 PARALLELS PRO BOX" oder "2026 PDC …" sehen aus wie Sticker – aussortieren:
    numeric = [c for c in rows if c.isdigit()]
    if len(numeric) < 0.2 * len(rows):          # Album nutzt Präfix-Codes (BA-01 …)
        for c in numeric:
            del rows[c]
    else:                                        # Album nutzt Nummern: Jahreszahlen raus
        small = [int(c) for c in numeric if int(c) < 1900]
        top = max(small, default=0)
        for c in numeric:
            if 1900 <= int(c) <= 2100 and top < 1000:
                del rows[c]
    return sorted(rows.values(), key=lambda r: (prefix_order[_natural_key(r.code)[0]], _natural_key(r.code)))


def pdf_to_text(path: Path) -> str:
    import shutil
    import subprocess
    if not shutil.which("pdftotext"):
        raise SystemExit("Für PDF-Import wird 'pdftotext' benötigt (Paket poppler-utils).")
    return subprocess.run(["pdftotext", "-layout", str(path), "-"], check=True,
                          capture_output=True, text=True).stdout


def parse_file(path: Path) -> tuple[dict | None, list[StickerRow]]:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return None, parse_pdf_text(pdf_to_text(path))
    text = path.read_text(encoding="utf-8-sig")
    if ext == ".json":
        return parse_json(text)
    if ext in {".csv", ".tsv"}:
        return None, parse_csv(text)
    return None, parse_text(text)


def section_id(con: sqlite3.Connection, album_id: int, name: str | None, cache: dict) -> int | None:
    if not name:
        return None
    if name in cache:
        return cache[name]
    row = con.execute("SELECT id FROM sections WHERE album_id = ? AND name = ?", (album_id, name)).fetchone()
    if row:
        sid = row["id"]
    else:
        pos = con.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM sections WHERE album_id = ?",
                          (album_id,)).fetchone()[0]
        sid = con.execute("INSERT INTO sections(album_id, name, position) VALUES (?, ?, ?)",
                          (album_id, name, pos)).lastrowid
    cache[name] = sid
    return sid


def import_stickers(con: sqlite3.Connection, album_id: int, rows: list[StickerRow],
                    replace: bool = False) -> dict:
    """Fügt Sticker ein bzw. aktualisiert sie. Reihenfolge der Eingabe = Reihenfolge im Album.

    replace=True löscht Sticker, die nicht (mehr) in der Liste stehen – inklusive
    der Sammlungseinträge der Nutzer für diese Sticker.
    """
    seen, dupes = set(), []
    for r in rows:
        if r.code in seen:
            dupes.append(r.code)
        seen.add(r.code)
    if dupes:
        raise ValueError(f"Doppelte Codes in der Checkliste: {', '.join(sorted(set(dupes))[:20])}")

    cache: dict = {}
    before = con.execute("SELECT COUNT(*) FROM stickers WHERE album_id = ?", (album_id,)).fetchone()[0]
    for pos, r in enumerate(rows, start=1):
        con.execute(
            "INSERT INTO stickers(album_id, code, sort_key, name, team, section_id, variant, is_special) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(album_id, code) DO UPDATE SET sort_key = excluded.sort_key, "
            "name = COALESCE(excluded.name, stickers.name), team = COALESCE(excluded.team, stickers.team), "
            "section_id = COALESCE(excluded.section_id, stickers.section_id), "
            "variant = excluded.variant, is_special = excluded.is_special",
            (album_id, r.code, pos, r.name, r.team, section_id(con, album_id, r.section, cache),
             r.variant, int(r.is_special)),
        )
    removed = 0
    if replace and rows:
        marks = ",".join("?" for _ in seen)
        removed = con.execute(f"DELETE FROM stickers WHERE album_id = ? AND code NOT IN ({marks})",
                              (album_id, *seen)).rowcount
    after = con.execute("SELECT COUNT(*) FROM stickers WHERE album_id = ?", (album_id,)).fetchone()[0]
    return {"rows": len(rows), "added": after - before + removed, "removed": removed, "total": after}


def fill_placeholders(con: sqlite3.Connection, album: sqlite3.Row, start: int | None,
                      end: int | None, prefix: str = "") -> dict:
    """Legt nummerierte Sticker ohne Namen an – reicht zum Tauschen aus."""
    start = 1 if start is None else start
    end = end if end is not None else album["total_stickers"]
    if not end:
        raise SystemExit("Keine Anzahl bekannt: --to angeben oder total_stickers am Album setzen.")
    existing = {r["code"] for r in con.execute("SELECT code FROM stickers WHERE album_id = ?", (album["id"],))}
    max_sort = con.execute("SELECT COALESCE(MAX(sort_key), 0) FROM stickers WHERE album_id = ?",
                           (album["id"],)).fetchone()[0]
    added = 0
    for n in range(start, end + 1):
        code = normalize_code(f"{prefix}{n}")
        if code in existing:
            continue
        con.execute("INSERT INTO stickers(album_id, code, sort_key) VALUES (?, ?, ?)",
                    (album["id"], code, max_sort + n))
        added += 1
    return {"added": added}


# --------------------------------------------------------------------- Bilder

def attach_images(con: sqlite3.Connection, root: Path, approve: bool = False,
                  origin: str = "import") -> dict:
    """Ordnet Bilddateien nach dem Schema <root>/<album-slug>/<code>.<ext> zu.

    Es werden nur Pfade (relativ zu root) und Prüfsummen gespeichert, keine Kopien.
    """
    stats = {"linked": 0, "skipped_known": 0, "unmatched": []}
    status = "approved" if approve else "pending"
    for album_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        album = con.execute("SELECT id FROM albums WHERE slug = ?", (album_dir.name,)).fetchone()
        for img in sorted(album_dir.iterdir()):
            if img.suffix.lower() not in IMAGE_EXT:
                continue
            sticker = None
            if album:
                sticker = con.execute("SELECT id FROM stickers WHERE album_id = ? AND code = ?",
                                      (album["id"], normalize_code(img.stem))).fetchone()
            if not sticker:
                stats["unmatched"].append(str(img.relative_to(root)))
                continue
            digest = hashlib.sha256(img.read_bytes()).hexdigest()
            cur = con.execute(
                "INSERT OR IGNORE INTO sticker_images(sticker_id, path, origin, status, sha256) "
                "VALUES (?, ?, ?, ?, ?)",
                (sticker["id"], img.relative_to(root).as_posix(), origin, status, digest),
            )
            stats["linked" if cur.rowcount else "skipped_known"] += 1
    return stats


# --------------------------------------------------------------------- Export

def export_album(con: sqlite3.Connection, slug: str) -> dict:
    a = album_by_slug(con, slug)
    pub = con.execute("SELECT name FROM publishers WHERE id = ?", (a["publisher_id"],)).fetchone()["name"]
    album = {"slug": a["slug"], "publisher": pub, **{k: a[k] for k in ALBUM_FIELDS}}
    stickers = []
    for s in con.execute(
        "SELECT s.*, sec.name AS section_name, "
        "(SELECT path FROM sticker_images i WHERE i.sticker_id = s.id AND i.status = 'approved' "
        " ORDER BY i.id LIMIT 1) AS image "
        "FROM stickers s LEFT JOIN sections sec ON sec.id = s.section_id "
        "WHERE s.album_id = ? ORDER BY s.sort_key", (a["id"],)):
        item = {"code": s["code"], "name": s["name"], "team": s["team"], "section": s["section_name"],
                "variant": s["variant"], "is_special": bool(s["is_special"]), "image": s["image"]}
        stickers.append({k: v for k, v in item.items() if v not in (None, False, "normal")})
    return {"album": album, "stickers": stickers}


def stats(con: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in con.execute(
        "SELECT a.slug, a.title, a.year, a.total_stickers AS offiziell, COUNT(s.id) AS erfasst, "
        "SUM(CASE WHEN s.name IS NOT NULL THEN 1 ELSE 0 END) AS mit_name, "
        "(SELECT COUNT(DISTINCT i.sticker_id) FROM sticker_images i JOIN stickers s2 ON s2.id = i.sticker_id "
        " WHERE s2.album_id = a.id AND i.status = 'approved') AS mit_bild "
        "FROM albums a LEFT JOIN stickers s ON s.album_id = a.id "
        "GROUP BY a.id ORDER BY a.year DESC, a.title")]


# ---------------------------------------------------------------- Quellen-Liste

def download(url: str, cache: Path) -> Path:
    """Lädt eine Datei einmalig in den Cache (erneuter Aufruf nutzt die Kopie)."""
    import urllib.request
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / (hashlib.sha1(url.encode()).hexdigest()[:12] + "-" + Path(url.split("?")[0]).name)
    if not target.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (StickerDB-Import)"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            target.write_bytes(resp.read())
    return target


def import_sources(con: sqlite3.Connection, sources_csv: Path, cache: Path,
                   only: str | None = None) -> list[dict]:
    """Lädt alle Checklisten aus sources.csv herunter und importiert sie."""
    results = []
    with open(sources_csv, encoding="utf-8-sig", newline="") as fh:
        for rec in csv.DictReader(fh):
            if only and rec["slug"] != only:
                continue
            try:
                album_id = upsert_album(con, {**rec, "source": rec["url"]})
                _, rows = parse_file(download(rec["url"], cache))
                if not rows:
                    raise ValueError("keine Sticker erkannt (PDF evtl. nur als Bild?)")
                res = import_stickers(con, album_id, rows)
                con.commit()
                results.append({"slug": rec["slug"], **res})
            except Exception as e:  # eine kaputte Quelle soll den Rest nicht stoppen
                con.rollback()
                results.append({"slug": rec["slug"], "error": str(e)})
    return results


# ------------------------------------------------------------------------ CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(DEFAULT_DB), help="Pfad zur SQLite-Datei (Standard: stickers.db)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Datenbank anlegen/aktualisieren")

    p = sub.add_parser("import-albums", help="Album-Katalog aus CSV einlesen")
    p.add_argument("file")

    p = sub.add_parser("import", help="Checkliste (.txt/.csv/.json/.pdf) in ein Album einlesen")
    p.add_argument("album", help="Album-Slug (bei .json mit Albumdaten: '-' für automatisch)")
    p.add_argument("file")
    p.add_argument("--replace", action="store_true",
                   help="Sticker löschen, die nicht in der Datei stehen (löscht auch Sammlungseinträge!)")
    p.add_argument("--dry-run", action="store_true", help="Nur prüfen und anzeigen, nichts speichern")

    p = sub.add_parser("fill", help="Nummerierte Platzhalter-Sticker anlegen")
    p.add_argument("album")
    p.add_argument("--from", dest="start", type=int)
    p.add_argument("--to", dest="end", type=int)
    p.add_argument("--prefix", default="", help="z. B. 'FWC' für FWC1..FWC19")

    p = sub.add_parser("attach-images", help="Bilder aus <ordner>/<album-slug>/<code>.jpg zuordnen")
    p.add_argument("folder")
    p.add_argument("--approve", action="store_true", help="Direkt freigeben statt 'pending'")

    p = sub.add_parser("export", help="Album als JSON ausgeben")
    p.add_argument("album")

    p = sub.add_parser("search", help="Sticker nach Name/Mannschaft suchen")
    p.add_argument("text")

    p = sub.add_parser("fetch", help="Checklisten aus data/sources.csv herunterladen und importieren")
    p.add_argument("--sources", default=str(HERE / "data" / "sources.csv"))
    p.add_argument("--only", help="nur dieses Album (Slug)")
    p.add_argument("--cache", default=str(HERE / ".cache"))

    sub.add_parser("stats", help="Übersicht: wie vollständig sind die Alben erfasst")

    args = ap.parse_args(argv)
    con = connect(args.db)
    init_db(con)  # idempotent – Schema ist immer aktuell

    if args.cmd == "init":
        print(f"Datenbank bereit: {args.db}")

    elif args.cmd == "import-albums":
        with open(args.file, encoding="utf-8-sig", newline="") as fh:
            n = sum(1 for rec in csv.DictReader(fh) if upsert_album(con, rec))
        con.commit()
        print(f"{n} Alben eingelesen/aktualisiert.")

    elif args.cmd == "import":
        album_meta, rows = parse_file(Path(args.file))
        if not rows:
            raise SystemExit("Keine Sticker in der Datei erkannt.")
        slug = args.album
        if album_meta:
            if slug != "-":
                album_meta = {**album_meta, "slug": slug}
            album_id = upsert_album(con, album_meta)
        else:
            album_id = album_by_slug(con, slug)["id"]
        try:
            result = import_stickers(con, album_id, rows, replace=args.replace)
        except ValueError as e:
            con.rollback()
            raise SystemExit(str(e))
        if args.dry_run:
            con.rollback()
            print("Probelauf (nichts gespeichert):", json.dumps(result, ensure_ascii=False))
            for r in rows[:10]:
                print(f"  {r.code:>6}  {r.name or '':30}  {r.team or '':20}  {r.section or ''}")
        else:
            con.commit()
            print(json.dumps(result, ensure_ascii=False))

    elif args.cmd == "fill":
        res = fill_placeholders(con, album_by_slug(con, args.album), args.start, args.end, args.prefix)
        con.commit()
        print(json.dumps(res))

    elif args.cmd == "attach-images":
        res = attach_images(con, Path(args.folder), approve=args.approve)
        con.commit()
        print(f"{res['linked']} Bilder zugeordnet, {res['skipped_known']} schon bekannt.")
        if res["unmatched"]:
            print(f"{len(res['unmatched'])} Dateien ohne passenden Sticker, z. B.:")
            for u in res["unmatched"][:10]:
                print("  ", u)

    elif args.cmd == "export":
        json.dump(export_album(con, args.album), sys.stdout, ensure_ascii=False, indent=2)
        print()

    elif args.cmd == "search":
        q = f"%{args.text}%"
        for r in con.execute(
            "SELECT a.slug, s.code, s.name, s.team FROM stickers s JOIN albums a ON a.id = s.album_id "
            "WHERE s.name LIKE ? OR s.team LIKE ? ORDER BY a.year DESC, s.sort_key LIMIT 100", (q, q)):
            print(f"{r['slug']:45} {r['code']:>6}  {r['name'] or ''}  {('(' + r['team'] + ')') if r['team'] else ''}")

    elif args.cmd == "fetch":
        for r in import_sources(con, Path(args.sources), Path(args.cache), args.only):
            if "error" in r:
                print(f"FEHLER  {r['slug']}: {r['error']}")
            else:
                print(f"OK      {r['slug']}: {r['total']} Sticker ({r['added']} neu)")

    elif args.cmd == "stats":
        rows = stats(con)
        print(f"{'Album':45} {'Jahr':>4} {'offiz.':>6} {'erfasst':>7} {'Name':>5} {'Bild':>5}")
        for r in rows:
            print(f"{r['slug'][:45]:45} {r['year'] or '':>4} {r['offiziell'] or '?':>6} "
                  f"{r['erfasst']:>7} {r['mit_name'] or 0:>5} {r['mit_bild'] or 0:>5}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
