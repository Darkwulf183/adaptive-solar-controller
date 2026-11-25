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
