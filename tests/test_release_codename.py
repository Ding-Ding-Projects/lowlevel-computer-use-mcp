import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseCodenameTests(unittest.TestCase):
    def test_selects_first_image_backed_dish_not_already_used(self):
        catalog = {
            "dishes": [
                {"id": "one", "name": {"en": "First", "zhHant": "一"}, "image": {"path": "images/one.png", "alt": {"en": "First dish"}}},
                {"id": "two", "name": {"en": "Second", "zhHant": "二"}, "image": {"path": "images/two.png", "alt": {"en": "Second dish"}}},
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog_path = directory / "catalog.json"
            used_path = directory / "used.txt"
            output_path = directory / "selected.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            used_path.write_text("Code name: First · 一\n", encoding="utf-8")
            result = subprocess.run([
                sys.executable,
                str(ROOT / "scripts" / "resolve_release_codename.py"),
                "--catalog", str(catalog_path),
                "--used-notes", str(used_path),
                "--output", str(output_path),
            ], cwd=ROOT, capture_output=True, text=True, check=True)
            selected = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(selected["codeName"], "Second · 二")
            self.assertIn("catalog-v1", selected["imageUrl"])
            self.assertEqual(json.loads(result.stdout)["codeName"], "Second · 二")


if __name__ == "__main__":
    unittest.main()
