"""One version number: manifest.json is the source, everything visible must agree."""
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMP = ROOT / "custom_components" / "adaptive_solar_controller"


def norm(v: str) -> str:
    return re.sub(r"\s+", "", v).lower()


class VersionTests(unittest.TestCase):
    def setUp(self):
        self.version = json.loads((COMP / "manifest.json").read_text(encoding="utf-8"))["version"]

    def test_const_reads_the_manifest(self):
        src = (COMP / "const.py").read_text(encoding="utf-8")
        self.assertIn("manifest.json", src)
        self.assertNotRegex(src, r'(?m)^VERSION\s*=\s*"\d')

    def test_no_hardcoded_version_in_panel(self):
        js = (COMP / "frontend" / "asc-panel.js").read_text(encoding="utf-8")
        self.assertNotRegex(js, r"v0\.\d+\.\d+")
        self.assertIn("sensor.adaptive_solar_controller_asc_version", js)

    def test_dashboard_example_has_no_version_titles(self):
        yaml = (ROOT / "examples" / "dashboard_solar_asc.yaml")
        if yaml.exists():
            self.assertNotRegex(yaml.read_text(encoding="utf-8"), r"v0\.4\.\d")

    def test_changelog_top_entry_matches_manifest(self):
        m = re.search(r"(?m)^## (\S+(?: \S+)?)", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
        self.assertIsNotNone(m)
        self.assertEqual(norm(m.group(1)), norm(self.version))

    def test_readme_status_matches_manifest_for_releases(self):
        if "dev" in self.version:
            self.skipTest("test build: README status belongs to the released version")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        status = next((l for l in readme.splitlines() if "Status" in l), "")
        self.assertIn(norm(self.version), norm(status))


if __name__ == "__main__":
    unittest.main()
