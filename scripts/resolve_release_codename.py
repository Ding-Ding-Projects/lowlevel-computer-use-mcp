"""Resolve the next unused public dim-sum release code name.

The consumer repository stores only the factual name and public catalog URL;
it never copies or downloads the catalog photo.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--used-notes", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    used_text = args.used_notes.read_text(encoding="utf-8", errors="replace")
    used = {match.strip() for match in re.findall(r"^Code name:\s*(.+?)\s*$", used_text, re.MULTILINE)}
    tag = "catalog-v1"
    base = "https://github.com/Ding-Ding-Projects/dim-sum-photos/releases/download/" + tag + "/"

    selected = None
    for dish in catalog.get("dishes", []):
        name = dish.get("name") or {}
        image = dish.get("image") or {}
        english = str(name.get("en") or "").strip()
        chinese = str(name.get("zhHant") or "").strip()
        image_path = str(image.get("path") or "").strip()
        if not english or not chinese or not image_path:
            continue
        code_name = f"{english} · {chinese}"
        if code_name in used:
            continue
        selected = {
            "catalogTag": tag,
            "dishId": dish.get("id"),
            "codeName": code_name,
            "english": english,
            "traditionalChinese": chinese,
            "imageFile": Path(image_path).name,
            "imageUrl": base + Path(image_path).name,
            "altText": (image.get("alt") or {}).get("en") or english,
        }
        break

    if selected is None:
        selected = {
            "catalogTag": None,
            "dishId": None,
            "codeName": "Unassigned build",
            "english": None,
            "traditionalChinese": None,
            "imageFile": None,
            "imageUrl": None,
            "altText": "No unused public catalog dish was available.",
        }
    args.output.write_text(json.dumps(selected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Keep command output ASCII-safe for Windows PowerShell and subprocess text
    # decoding; the JSON artifact itself remains UTF-8 with real dish names.
    print(json.dumps(selected, ensure_ascii=True))


if __name__ == "__main__":
    main()
