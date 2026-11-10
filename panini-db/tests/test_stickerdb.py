import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stickerdb as sdb  # noqa: E402

HERE = Path(__file__).resolve().parents[1]


class StickerDbTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "t.db"
        self.con = sdb.connect(self.db)
        sdb.init_db(self.con)
        self.album_id = sdb.upsert_album(self.con, {"slug": "test-album", "title": "Test", "total_stickers": "5"})
        self.con.commit()

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_parse_text_example(self):
        rows = sdb.parse_text((HERE / "data/checklists/BEISPIEL-format.txt").read_text(encoding="utf-8"))
        codes = [r.code for r in rows]
        self.assertEqual(codes, ["00", "1", "2", "3", "4", "5", "X1"])
        by = {r.code: r for r in rows}
        self.assertEqual((by["3"].name, by["3"].team), ("Max Mustermann", "FC Beispielstadt"))
        self.assertEqual((by["4"].name, by["4"].team), ("Erika Musterfrau", "FC Beispielstadt"))
        self.assertEqual(by["3"].section, "FC Beispielstadt")
        self.assertEqual(by["X1"].section, "Extra-Sticker")
        self.assertTrue(by["2"].is_special)
        self.assertIsNone(by["5"].name)

    def test_codes_with_prefix(self):
        rows = sdb.parse_text("GER 12 Spieler A\nFWC5 Pokal\n12a Variante")
        self.assertEqual([r.code for r in rows], ["GER12", "FWC5", "12A"])

    def test_csv_with_german_headers(self):
        rows = sdb.parse_csv("Nr;Spieler;Verein;Glitzer\n1;A;X;ja\n2;B;Y;\n")
        self.assertEqual([(r.code, r.name, r.team, r.is_special) for r in rows],
                         [("1", "A", "X", True), ("2", "B", "Y", False)])

    def test_import_is_idempotent_and_keeps_inventory(self):
        rows = sdb.parse_text("1 A\n2 B\n3 C")
        sdb.import_stickers(self.con, self.album_id, rows)
        sid = self.con.execute("SELECT id FROM stickers WHERE code='2'").fetchone()[0]
        self.con.execute("INSERT INTO inventory VALUES ('u1', ?, 3)", (sid,))
        res = sdb.import_stickers(self.con, self.album_id, sdb.parse_text("1 A\n2 B neu\n3 C"))
        self.assertEqual(res["added"], 0)
        self.assertEqual(self.con.execute("SELECT name FROM stickers WHERE id=?", (sid,)).fetchone()[0], "B neu")
        self.assertEqual(self.con.execute("SELECT quantity FROM inventory").fetchone()[0], 3)

    def test_duplicate_codes_rejected(self):
        with self.assertRaises(ValueError):
            sdb.import_stickers(self.con, self.album_id, sdb.parse_text("1 A\n1 B"))

    def test_fill_and_swap_views(self):
        album = sdb.album_by_slug(self.con, "test-album")
        self.assertEqual(sdb.fill_placeholders(self.con, album, None, None)["added"], 5)
        ids = {r["code"]: r["id"] for r in self.con.execute("SELECT id, code FROM stickers")}
        self.con.executemany("INSERT INTO user_albums VALUES (?, ?)", [("anna", self.album_id), ("ben", self.album_id)])
        self.con.executemany("INSERT INTO inventory VALUES (?, ?, ?)",
                             [("anna", ids["1"], 2), ("anna", ids["2"], 1), ("ben", ids["3"], 3)])
        swaps = {(r["giver"], r["taker"], r["code"]) for r in self.con.execute("SELECT * FROM v_swap_candidates")}
        self.assertEqual(swaps, {("anna", "ben", "1"), ("ben", "anna", "3")})
        prog = {r["user_id"]: (r["total"], r["owned"], r["duplicates"])
                for r in self.con.execute("SELECT * FROM v_album_progress")}
        self.assertEqual(prog, {"anna": (5, 2, 1), "ben": (5, 1, 2)})

    def test_attach_images_and_export_roundtrip(self):
        sdb.import_stickers(self.con, self.album_id, sdb.parse_text("Team\n1 A - X\n2 B"))
        img_root = Path(self.tmp.name) / "bilder"
        (img_root / "test-album").mkdir(parents=True)
        (img_root / "test-album" / "1.jpg").write_bytes(b"fake")
        (img_root / "test-album" / "99.jpg").write_bytes(b"x")
        res = sdb.attach_images(self.con, img_root, approve=True)
        self.assertEqual(res["linked"], 1)
        self.assertEqual(res["unmatched"], ["test-album/99.jpg"])
        self.assertEqual(sdb.attach_images(self.con, img_root, approve=True)["skipped_known"], 1)

        data = sdb.export_album(self.con, "test-album")
        self.assertEqual(data["stickers"][0], {"code": "1", "name": "A", "team": "X",
                                               "section": "Team", "image": "test-album/1.jpg"})
        # JSON-Export lässt sich in eine frische DB zurückspielen
        other = sdb.connect(Path(self.tmp.name) / "o.db")
        sdb.init_db(other)
        album, rows = sdb.parse_json(json.dumps(data))
        aid = sdb.upsert_album(other, album)
        sdb.import_stickers(other, aid, rows)
        self.assertEqual(sdb.export_album(other, "test-album")["stickers"][1], {"code": "2", "name": "B", "section": "Team"})
        other.close()

    def test_cli_end_to_end(self):
        db = str(self.db)
        self.assertEqual(sdb.main(["--db", db, "import-albums", str(HERE / "data/albums.csv")]), 0)
        self.assertEqual(sdb.main(["--db", db, "import", "panini-3-liga-2026-2027",
                                   str(HERE / "data/checklists/BEISPIEL-format.txt")]), 0)
        n = sqlite3.connect(db).execute("SELECT COUNT(*) FROM albums").fetchone()[0]
        self.assertEqual(n, 11)


if __name__ == "__main__":
    unittest.main()
