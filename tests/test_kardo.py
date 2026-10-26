"""Kardo test suite. Standard library only:

    python -m unittest discover -s tests -v

Each run uses a throwaway data directory, so it never touches a real collection.
"""
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = tempfile.mkdtemp(prefix="kardo-test-")
os.environ["KARDO_DATA"] = DATA  # must be set before server is imported: it opens the database on import
os.environ["KARDO_LOG"] = "0"
sys.path.insert(0, ROOT)

import lab  # noqa: E402
import server  # noqa: E402

SAMPLES = os.path.join(ROOT, "samples")
DAY = 86400
NOW = 1_800_000_000  # a fixed clock keeps the scheduler tests deterministic


def wipe():
    for t in ("cards", "decks", "notetypes", "revlog", "settings"):
        server.db.execute(f"delete from {t}")


def card(**kw):
    c = {"state": "new", "due": 0, "ivl": 0, "ease": 2.5, "reps": 0, "lapses": 0, "step": 0}
    c.update(kw)
    return c


class Scheduler(unittest.TestCase):
    S = dict(server.DEFAULTS)

    def ds(self):
        return server.day_start(NOW, 0, self.S["rollover_hour"])

    def run_(self, c, rating, fuzz=False):
        return server.schedule(c, rating, NOW, self.ds(), self.S, fuzz=fuzz)

    def test_new_card_good_walks_learning_steps(self):
        c = self.run_(card(), 3)
        self.assertEqual(c["state"], "learning")
        self.assertEqual(c["step"], 1)
        self.assertEqual(c["due"], NOW + 10 * 60)  # second step of "1 10"
        c = self.run_(c, 3)
        self.assertEqual(c["state"], "review")
        self.assertEqual(c["ivl"], self.S["graduating_ivl"])

    def test_new_card_again_restarts_first_step(self):
        c = self.run_(card(), 1)
        self.assertEqual((c["state"], c["step"], c["due"]), ("learning", 0, NOW + 60))

    def test_new_card_easy_graduates_immediately(self):
        c = self.run_(card(), 4)
        self.assertEqual((c["state"], c["ivl"]), ("review", self.S["easy_ivl"]))

    def test_hard_on_first_step_averages_steps(self):
        c = self.run_(card(), 2)
        self.assertEqual(c["due"], NOW + int(5.5 * 60))

    def test_review_intervals_are_ordered(self):
        base = card(state="review", ivl=10, ease=2.5, due=self.ds())
        ivls = [self.run_(base, r)["ivl"] for r in (2, 3, 4)]
        self.assertLess(ivls[0], ivls[1])
        self.assertLess(ivls[1], ivls[2])
        self.assertEqual(ivls[1], 25)  # 10 days * 2.5 ease

    def test_lapse_moves_to_relearning_and_drops_ease(self):
        c = self.run_(card(state="review", ivl=30, ease=2.5, due=self.ds()), 1)
        self.assertEqual(c["state"], "relearning")
        self.assertEqual(c["lapses"], 1)
        self.assertAlmostEqual(c["ease"], 2.3)
        self.assertEqual(c["ivl"], 1)  # lapse_mult 0 keeps the minimum of one day

    def test_ease_never_drops_below_floor(self):
        c = card(state="review", ivl=5, ease=1.3, due=self.ds())
        self.assertEqual(self.run_(c, 1)["ease"], 1.3)
        self.assertEqual(self.run_(c, 2)["ease"], 1.3)

    def test_max_interval_is_respected(self):
        S = dict(self.S, max_ivl=7)
        c = server.schedule(card(state="review", ivl=6, ease=2.5, due=self.ds()), 4, NOW, self.ds(), S)
        self.assertLessEqual(c["ivl"], 7)

    def test_fuzz_stays_within_five_percent(self):
        base = card(state="review", ivl=40, ease=2.5, due=self.ds())
        for _ in range(200):
            self.assertTrue(95 <= self.run_(base, 3, fuzz=True)["ivl"] <= 105)

    def test_day_start_honours_rollover_and_time_zone(self):
        # 2027-01-15 03:00 UTC is still the previous study day with a 4 am rollover
        t = 1_799_982_000
        ds = server.day_start(t, 0, 4)
        self.assertEqual(ds % DAY, 4 * 3600)
        self.assertLessEqual(ds, t)
        self.assertLess(t - ds, DAY)
        # a viewer at UTC+10 gets a day boundary 10 hours earlier
        self.assertEqual((server.day_start(t, 600, 4) - (4 - 10) * 3600) % DAY, 0)

    def test_fmt_span(self):
        self.assertEqual(server.fmt_span(30), "<1m")
        self.assertEqual(server.fmt_span(600), "10m")
        self.assertEqual(server.fmt_span(4 * DAY), "4d")
        self.assertEqual(server.fmt_span(45 * DAY), "1.5mo")
        self.assertEqual(server.fmt_span(730 * DAY), "2y")


class Templates(unittest.TestCase):
    def test_cloze_front_and_back(self):
        t = "The {{c1::mitochondrion}} makes {{c2::ATP::energy}}."
        self.assertIn("[...]", server.render_cloze(t, 1, "q"))
        self.assertIn("ATP", server.render_cloze(t, 1, "q"))
        self.assertIn("[energy]", server.render_cloze(t, 2, "q"))
        self.assertIn('<span class="cloze">ATP</span>', server.render_cloze(t, 2, "a"))

    def test_conditional_sections(self):
        tmpl = "{{Front}}{{#Extra}}<i>{{Extra}}</i>{{/Extra}}{{^Extra}}none{{/Extra}}"
        self.assertEqual(server.render_template(tmpl, {"Front": "Q", "Extra": ""}, "q", 1), "Qnone")
        self.assertEqual(server.render_template(tmpl, {"Front": "Q", "Extra": "x"}, "q", 1), "Q<i>x</i>")

    def test_special_fields_and_filters(self):
        tmpl = "{{Deck}}|{{Subdeck}}|{{text:Front}}|{{type:Back}}"
        out = server.render_template(tmpl, {"Front": "<b>hi</b>", "Back": "x"}, "q", 1, deck="A::B")
        self.assertEqual(out, "A::B|B|hi|")

    def test_media_paths_are_rewritten(self):
        out = server.fix_media('<img src="cat.png"> [sound:meow.mp3] <img src="https://x.org/a.png">')
        self.assertIn('src="/media/cat.png"', out)
        self.assertIn('<audio controls preload="none" src="/media/meow.mp3">', out)
        self.assertIn('src="https://x.org/a.png"', out)

    def test_media_names_cannot_escape_the_folder(self):
        self.assertEqual(server.safe_media_name("../../etc/passwd"), "passwd")
        self.assertEqual(server.safe_media_name("..\\..\\win.ini"), "win.ini")
        self.assertIsNone(server.safe_media_name(".."))


class Importers(unittest.TestCase):
    def setUp(self):
        wipe()

    def load(self, name):
        with open(os.path.join(SAMPLES, name), "rb") as f:
            return server.import_file(f.read(), name)

    def test_sample_decks_import(self):
        expected = {  # cards, media files
            "geography-flags-capitals.apkg": (62, 31),   # 31 notes x 2 templates, one flag image each
            "spanish-a1-vocabulary.apkg": (72, 0),       # 36 notes x 2 templates
            "japanese-hiragana.apkg": (46, 0),
            "cell-biology-cloze.apkg": (37, 0),          # one card per cloze number
            "git-essentials.apkg": (20, 0),
        }
        for name, (cards, media) in expected.items():
            with self.subTest(deck=name):
                st = self.load(name)
                self.assertEqual(st["added"], cards)
                self.assertEqual(st["media"], media)
                self.assertEqual(st["skipped"], 0)

    def test_subdecks_are_created(self):
        self.load("spanish-a1-vocabulary.apkg")
        names = {r[0] for r in server.db.execute("select name from decks")}
        self.assertTrue({"Languages", "Languages::Spanish", "Languages::Spanish::A1 Vocabulary"} <= names)

    def test_reimport_updates_text_and_keeps_progress(self):
        self.load("git-essentials.apkg")
        cid = server.db.execute("select id from cards limit 1").fetchone()[0]
        server.db.execute("update cards set state='review', ivl=12, reps=5 where id=?", (cid,))
        st = self.load("git-essentials.apkg")
        self.assertEqual((st["added"], st["updated"]), (0, 20))
        row = server.db.execute("select state, ivl, reps from cards where id=?", (cid,)).fetchone()
        self.assertEqual(tuple(row), ("review", 12, 5))

    def test_cloze_cards_render_one_gap_each(self):
        self.load("cell-biology-cloze.apkg")
        fronts = [r[0] for r in server.db.execute("select front from cards")]
        self.assertTrue(all(f.count("[...]") == 1 for f in fronts))

    def test_csv_with_anki_headers(self):
        data = ("#separator:tab\n#html:false\n#columns:Front\tBack\tTags\n#deck:Capitals\n"
                "France\tParis\tgeo europe\nJapan\tTokyo <city>\tgeo asia\n\n").encode()
        st = server.import_file(data, "x.txt")
        self.assertEqual(st["added"], 2)
        row = server.db.execute("select back, tags from cards where sort_text='Japan'").fetchone()
        self.assertIn("Tokyo &lt;city&gt;", row["back"])
        self.assertEqual(row["tags"], " geo asia ")
        self.assertEqual(server.db.execute("select count(*) from decks where name='Capitals'").fetchone()[0], 1)

    def test_csv_sniffs_separator_and_names_deck_after_file(self):
        st = server.import_file("Q1;A1\nQ2;A2\n".encode(), "my_deck.csv")
        self.assertEqual(st["added"], 2)
        self.assertIsNotNone(server.db.execute("select 1 from decks where name='my deck'").fetchone())

    def test_rejects_bad_packages(self):
        with self.assertRaises(server.ApiError):
            server.import_file(b"PK\x03\x04 not really a zip", "x.apkg")
        with self.assertRaises(server.ApiError):
            server.import_file(b"whatever", "backup.colpkg")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("collection.anki21b", b"zstd")
            z.writestr("collection.anki2", b"stub")
        with self.assertRaises(server.ApiError) as e:
            server.import_file(buf.getvalue(), "new.apkg")
        self.assertIn("older", str(e.exception))


class StudyQueue(unittest.TestCase):
    def setUp(self):
        wipe()
        with open(os.path.join(SAMPLES, "japanese-hiragana.apkg"), "rb") as f:
            server.import_file(f.read(), "japanese-hiragana.apkg")

    def test_daily_new_limit(self):
        server.save_settings({"new_per_day": 5})
        t = NOW
        seen = 0
        while True:
            res = server.next_card(None, None, t, 0)
            if not res["card"] or res["card"]["state"] != "new":
                break
            server.answer_card(res["card"]["id"], 4, 1000, t, 0)
            seen += 1
            t += 5
        self.assertEqual(seen, 5)
        self.assertEqual(server.next_card(None, None, t, 0)["counts"]["new"], 0)

    def test_undo_restores_card(self):
        res = server.next_card(None, None, NOW, 0)
        cid = res["card"]["id"]
        server.answer_card(cid, 3, 1000, NOW, 0)
        self.assertEqual(server.db.execute("select state from cards where id=?", (cid,)).fetchone()[0], "learning")
        server.undo_last(NOW, 0)
        self.assertEqual(server.db.execute("select state, reps from cards where id=?", (cid,)).fetchone()[:], ("new", 0))
        self.assertEqual(server.db.execute("select count(*) from revlog").fetchone()[0], 0)

    def test_settings_validation(self):
        with self.assertRaises(server.ApiError):
            server.save_settings({"new_per_day": -1})
        with self.assertRaises(server.ApiError):
            server.save_settings({"learn_steps": "one ten"})
        server.save_settings({"learn_steps": "1, 10, 60", "unknown_key": 3})
        self.assertEqual(server.get_settings()["learn_steps"], "1 10 60")


class Http(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def req(self, path, data=None, method=None):
        r = urllib.request.Request(self.base + path, data=data, method=method)
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_end_to_end_study_session(self):
        wipe()
        with open(os.path.join(SAMPLES, "geography-flags-capitals.apkg"), "rb") as f:
            code, body = self.req("/api/import?filename=geo.apkg", f.read())
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["added"], 62)
        code, body = self.req("/api/next")
        card = json.loads(body)["card"]
        self.assertEqual(set(card["intervals"]), {"1", "2", "3", "4"})
        code, body = self.req("/api/answer", json.dumps({"card_id": card["id"], "rating": 3}).encode())
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(self.req("/api/stats")[1])["today"]["reviews"], 1)

    def test_static_app_and_media(self):
        code, body = self.req("/")
        self.assertEqual(code, 200)
        self.assertIn(b"<title>Kardo</title>", body)
        self.assertEqual(self.req("/manifest.webmanifest")[0], 200)
        self.assertEqual(self.req("/some/client/route")[0], 200)  # falls back to the app shell

    def test_path_traversal_is_blocked(self):
        code, body = self.req("/../server.py")
        self.assertNotIn(b"import sqlite3", body)
        self.assertEqual(self.req("/media/..%2f..%2fkardo.db")[0], 404)

    def test_backup_is_a_sqlite_file(self):
        code, body = self.req("/api/backup")
        self.assertEqual(code, 200)
        self.assertTrue(body.startswith(b"SQLite format 3"))

    def test_errors_are_json(self):
        code, body = self.req("/api/nope")
        self.assertEqual(code, 404)
        self.assertIn("error", json.loads(body))
        code, body = self.req("/api/answer", json.dumps({"card_id": 1, "rating": 9}).encode())
        self.assertEqual(code, 400)


class PortConflict(unittest.TestCase):
    def setUp(self):
        self.busy = server.KardoServer(("0.0.0.0", 0), server.Handler)
        self.port = self.busy.server_address[1]

    def tearDown(self):
        self.busy.server_close()

    def test_explicit_port_in_use_exits_with_a_clear_message(self):
        with self.assertRaises(SystemExit) as e:
            server.bind_server(self.port, explicit=True)
        self.assertIn(f"port {self.port} is already in use", str(e.exception.code))

    def test_default_port_in_use_falls_back_to_the_next_free_one(self):
        srv, port = server.bind_server(self.port, explicit=False)
        try:
            self.assertNotEqual(port, self.port)
            self.assertGreater(port, self.port)
        finally:
            srv.server_close()


class SqlLab(unittest.TestCase):
    def test_every_reference_solution_passes_its_own_check(self):
        for ex in lab.exercises():
            with self.subTest(exercise=ex["id"]):
                verdict = lab.check_answer(ex, ex["solution"])
                self.assertTrue(verdict["ok"], verdict["message"])

    def test_wrong_answer_is_explained(self):
        ex = lab.get_exercise("f02")[1]
        verdict = lab.check_answer(ex, "SELECT first_name FROM customers")
        self.assertFalse(verdict["ok"])
        self.assertIn("column", verdict["message"])

    def test_queries_cannot_reach_the_filesystem(self):
        out = None
        try:
            out = lab.run_for_display("ATTACH DATABASE '/tmp/x.db' AS x")
        except lab.LabError:
            return
        self.assertTrue(out.get("error") or out.get("notes"), out)


if __name__ == "__main__":
    unittest.main()
