import importlib.util
import pathlib
import tempfile
import unittest

BASE = pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "adaptive_solar_controller"
spec = importlib.util.spec_from_file_location("recorder_files", BASE / "recorder_files.py")
rf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rf)


class NameTests(unittest.TestCase):
    def test_valid_names(self):
        for n in ("ASC_v0.4.6_FlightRecorder_2026-11-25.csv", "ASC_v0.4.8_FlightRecorder_2026-11-25_old.csv",
                  "ASC_v0.4.8_FlightRecorder_2026-11-25_old2.csv"):
            self.assertTrue(rf.valid_name(n), n)

    def test_path_traversal_and_other_files_rejected(self):
        for n in ("", "../secrets.yaml", "../../.storage/auth", "ASC_v0.4.6_FlightRecorder_2026-11-25.csv/../x",
                  "ASC_v0.4.6_FlightRecorder_2026-11-25.csv.exe", "other.csv", "/etc/passwd",
                  "ASC_v0.4.6_FlightRecorder_2026-11-25.csv\\..\\x"):
            self.assertFalse(rf.valid_name(n), n)


class FolderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        for n in ("ASC_v0.4.6_FlightRecorder_2026-11-24.csv", "ASC_v0.4.7_FlightRecorder_2026-11-25.csv", "notes.txt"):
            (self.dir / n).write_text("a,b\n1,2\n")

    def tearDown(self): self.tmp.cleanup()

    def test_list_is_newest_first_and_only_recorder_files(self):
        names = [f["name"] for f in rf.list_files(self.dir)]
        self.assertEqual(names, ["ASC_v0.4.7_FlightRecorder_2026-11-25.csv", "ASC_v0.4.6_FlightRecorder_2026-11-24.csv"])

    def test_resolve_existing_and_missing(self):
        self.assertIsNotNone(rf.resolve(self.dir, "ASC_v0.4.6_FlightRecorder_2026-11-24.csv"))
        self.assertIsNone(rf.resolve(self.dir, "ASC_v0.4.6_FlightRecorder_2026-01-01.csv"))
        self.assertIsNone(rf.resolve(self.dir, "../x"))

    def test_symlink_out_of_folder_is_rejected(self):
        outside = self.dir.parent / "outside_secret.csv"
        outside.write_text("x")
        link = self.dir / "ASC_v0.4.6_FlightRecorder_2026-11-20.csv"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("symlinks unavailable")
        self.assertIsNone(rf.resolve(self.dir, link.name))
        outside.unlink()

    def test_missing_folder_gives_empty_list(self):
        self.assertEqual(rf.list_files(self.dir / "nope"), [])


if __name__ == "__main__":
    unittest.main()


class PruneTests(unittest.TestCase):
    def _folder(self, names):
        import tempfile, pathlib
        d = pathlib.Path(tempfile.mkdtemp())
        for n in names:
            (d / n).write_text("x")
        return d

    def test_old_recorder_files_are_deleted_new_and_foreign_files_stay(self):
        import datetime as dt
        today = dt.date(2026, 11, 27)
        d = self._folder([
            "ASC_v0.4.6_FlightRecorder_2026-07-01.csv",        # alt
            "ASC_v0.4.6_FlightRecorder_2026-07-01_old2.csv",   # alt, Archiv
            "ASC_v0.4.6_FlightRecorder_2026-11-26.csv",        # neu
            "ASC_v0.4.6_FlightRecorder_2026-11-27.csv",        # heute
            "meine_notizen_2026-01-01.csv",                    # fremd
            "ASC_v0.4.6_FlightRecorder_2026-01-01.csv.bak",    # fremd (kein .csv am Ende)
        ])
        gone = rf.prune(d, today, 120)
        self.assertEqual(gone, ["ASC_v0.4.6_FlightRecorder_2026-07-01.csv", "ASC_v0.4.6_FlightRecorder_2026-07-01_old2.csv"])
        left = sorted(p.name for p in d.iterdir())
        self.assertIn("ASC_v0.4.6_FlightRecorder_2026-11-27.csv", left)
        self.assertIn("ASC_v0.4.6_FlightRecorder_2026-11-26.csv", left)
        self.assertIn("meine_notizen_2026-01-01.csv", left)
        self.assertIn("ASC_v0.4.6_FlightRecorder_2026-01-01.csv.bak", left)
        self.assertNotIn("ASC_v0.4.6_FlightRecorder_2026-07-01.csv", left)

    def test_zero_disables_rotation(self):
        import datetime as dt
        d = self._folder(["ASC_v0.4.6_FlightRecorder_2020-01-01.csv"])
        self.assertEqual(rf.prune(d, dt.date(2026, 11, 27), 0), [])
        self.assertEqual(len(list(d.iterdir())), 1)

    def test_missing_folder_is_not_an_error(self):
        import datetime as dt, pathlib
        self.assertEqual(rf.prune(pathlib.Path("/nonexistent/asc"), dt.date(2026, 11, 27)), [])
