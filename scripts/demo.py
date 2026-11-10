"""Build the two-action dinosaur sample in a new project, without AI/network calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

from book import build, initialize


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.out.resolve()
    package = Path(__file__).resolve().parents[1]
    initialize(root, "恐龙在公园里")
    shutil.copy2(package / "examples/book.json", root / "book.json")
    media = package / "examples/media"
    shutil.copy2(media / "cover-green.png", root / "source/covers/green.png")
    shutil.copy2(media / "park.jpg", root / "source/scenes/park.jpg")
    shutil.copytree(media / "green", root / "source/animations/green")
    result = build(root)
    print(json.dumps({"fileChecks": result["fileChecks"], "artifacts": result["artifacts"],
                      "browserChecks": "not_run_by_script"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
