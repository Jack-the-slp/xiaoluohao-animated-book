"""Install the local skill without replacing existing work; no network access."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import tempfile

NAME = "xiaoluohao-animated-book"
FILES = ("SKILL.md", "README.md", "LICENSE", "requirements.txt", "aizidonganzhuangskill.md")
DIRECTORIES = ("agents", "assets", "scripts", "references", "docs", "examples")


def install(source: Path, parent: Path) -> Path:
    source, parent = source.resolve(), parent.expanduser().resolve()
    target = parent / NAME
    if target.exists() or target.is_symlink():
        raise ValueError(f"Existing skill preserved: {target}. Compare versions before updating.")
    if parent == source or parent.is_relative_to(source):
        raise ValueError("Install outside the downloaded repository.")
    for name in FILES + DIRECTORIES:
        item = source / name
        if not item.exists() or item.is_symlink():
            raise ValueError(f"Missing or linked package entry: {name}")
        if item.is_dir() and any(p.is_symlink() for p in item.rglob("*")):
            raise ValueError(f"Linked package resource: {name}")
    parent.mkdir(parents=True, exist_ok=True)
    # Stage beside the target, then rename; a failed copy cannot expose a partial skill.
    with tempfile.TemporaryDirectory(prefix=".animated-book-install-", dir=parent) as temporary:
        staged = Path(temporary) / NAME
        staged.mkdir()
        for name in FILES:
            shutil.copy2(source / name, staged / name)
        for name in DIRECTORIES:
            shutil.copytree(source / name, staged / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
        staged.rename(target)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, help="Parent skills directory; default: ~/.agents/skills")
    args = parser.parse_args()
    default = Path.home() / ".agents" / "skills"
    legacy = Path.home() / ".codex" / "skills" / NAME
    if args.dest is None and legacy.exists():
        raise ValueError(f"Existing legacy skill preserved: {legacy}. Check your skill search paths first.")
    target = install(Path(__file__).resolve().parents[1], args.dest or default)
    print(f"Installed: {target}")
    print(f"Files: {sum(p.is_file() for p in target.rglob('*'))}")
    print("Next: check Pillow, run scripts/demo.py, then invoke the skill on the next turn.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
