"""Initialize, build and verify a self-contained offline animated picture book."""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

from PIL import Image


def require(condition, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_local(root: Path, relative: str) -> Path:
    require(isinstance(relative, str) and bool(relative), "Resource path must be a nonempty string.")
    path = (root / relative).resolve()
    require(not Path(relative).is_absolute() and path.is_relative_to(root),
            f"Copy resources into the project before building: {relative}")
    require(path.is_file(), f"Missing resource: {path}")
    return path


def inspect_webp(path: Path) -> dict:
    total, hashes = 0, set()
    with Image.open(path) as animation:
        require(animation.format == "WEBP" and animation.n_frames >= 2,
                f"Expected an animated WebP: {path}")
        width, height = animation.size
        require(width == height, f"Expected a square animation: {path}")
        require(animation.info.get("loop") == 1, f"WebP must play once (loop=1): {path}")
        count = animation.n_frames
        for index in range(count):
            animation.seek(index)
            animation.load()
            duration = animation.info.get("duration", 0)
            require(duration > 0, f"Missing frame duration: {path}, frame {index}")
            total += duration
            frame = animation.convert("RGBA")
            hashes.add(digest(frame.tobytes()))
            alpha = frame.getchannel("A")
            require(alpha.getextrema()[1] > 0, f"Empty frame: {path}, frame {index}")
            require(all(alpha.getpixel(p) == 0 for p in
                        ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1))),
                    f"Expected transparent animation corners: {path}, frame {index}")
    require(len(hashes) >= 2, f"No frame changes: {path}")
    return {"size": [width, height], "frames": count, "durationMs": total, "loop": 1,
            "distinctFrames": len(hashes), "sha256": digest(path.read_bytes())}


def checked_ids(entries: list, key: str, label: str) -> list[str]:
    require(isinstance(entries, list) and len(entries) > 0, f"{label} must be a nonempty list.")
    ids = [entry[key] for entry in entries]
    require(all(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]+", value) for value in ids),
            f"Invalid {label} ID.")
    require(len(set(ids)) == len(ids), f"Duplicate {label} IDs.")
    return ids


def prepare(root: Path) -> tuple[dict, dict[str, bytes], dict]:
    spec = json.loads((root / "book.json").read_text(encoding="utf-8"))
    require(isinstance(spec["title"], str) and spec["title"].strip(), "A title is required.")
    char_ids = checked_ids(spec["characters"], "id", "characters")
    scene_ids = checked_ids(spec["scenes"], "id", "scenes")
    checked_ids(spec["pages"], "key", "pages")
    assets, checks = {}, {}

    def media(relative: str, destination: str, animated=False) -> str:
        path = read_local(root, relative)
        require(path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}, f"Unsupported image: {path}")
        if animated:
            checks[relative] = inspect_webp(path)
        else:
            with Image.open(path) as image:
                image.verify()
        key = "assets/" + destination + path.suffix.lower()
        require(key not in assets, f"Duplicate output resource: {key}")
        assets[key] = path.read_bytes()
        return key

    manifest = {"mode": "folder", "title": spec["title"],
                "coverLines": spec.get("coverLines", [spec["title"]]),
                "footerText": spec.get("footerText", "小螺号听觉言语语言康复平台："),
                "footerAddress": spec.get("footerAddress", "TC-SLP.top"),
                "autoPlay": spec.get("autoPlay", True),
                "defaultCharacter": spec.get("defaultCharacter", char_ids[0]),
                "defaultScene": spec.get("defaultScene", scene_ids[0]),
                "coverHoldMs": spec.get("coverHoldMs", 2600), "pageHoldMs": spec.get("pageHoldMs", 800)}
    require(manifest["defaultCharacter"] in char_ids and manifest["defaultScene"] in scene_ids,
            "Default character or scene does not exist.")
    require(isinstance(manifest["autoPlay"], bool), "autoPlay must be a boolean.")
    for key in ("coverHoldMs", "pageHoldMs"):
        require(type(manifest[key]) is int and manifest[key] >= 0, f"Invalid {key}.")
    require(isinstance(manifest["coverLines"], list) and manifest["coverLines"] and
            all(isinstance(line, str) for line in manifest["coverLines"]), "coverLines must be a list of text.")
    manifest["logo"] = media(spec["logo"], "brand/logo") if spec.get("logo") else None
    manifest["characters"] = [dict(id=char["id"], name=char["name"],
        subject=char.get("subject", char["name"]), dot=char.get("dot", "#7ea75b"),
        cover=media(char["cover"], "covers/" + char["id"])) for char in spec["characters"]]
    manifest["scenes"] = [dict(id=scene["id"], name=scene["name"], location=scene["location"],
        water=scene.get("water", False), bg=media(scene["image"], "scenes/" + scene["id"])
        if scene.get("image") else None) for scene in spec["scenes"]]
    pages = []
    for page in spec["pages"]:
        require(set(page["animations"]) == set(char_ids),
                f"Animation matrix must contain exactly all characters for {page['key']}.")
        sprites, durations = {}, {}
        for char_id in char_ids:
            relative = page["animations"][char_id]
            sprites[char_id] = media(relative, f"animations/{char_id}/{page['key']}", animated=True)
            durations[char_id] = checks[relative]["durationMs"]
        pages.append(dict(key=page["key"], word=page["word"], note=page.get("note", ""),
                          pool=page.get("pool", False), sprite=sprites, durationMsByCharacter=durations))
    manifest["pages"] = pages
    return manifest, assets, checks


def embedded(manifest: dict, assets: dict[str, bytes]) -> dict:
    def uri(path):
        if path is None:
            return None
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}[Path(path).suffix]
        return f"data:{mime};base64," + base64.b64encode(assets[path]).decode("ascii")
    result = deepcopy(manifest)
    result["mode"] = "single"
    result["logo"] = uri(result["logo"])
    for char in result["characters"]:
        char["cover"] = uri(char["cover"])
    for scene in result["scenes"]:
        scene["bg"] = uri(scene["bg"])
    for page in result["pages"]:
        page["sprite"] = {key: uri(path) for key, path in page["sprite"].items()}
    return result


def render(root: Path, manifest: dict) -> bytes:
    template = (root / "source" / "book-template.html").read_text(encoding="utf-8")
    require(template.count("__BOOK_DATA__") == 1 and template.count("__BOOK_TITLE__") == 1,
            "Template must contain one book-data and one title placeholder.")
    payload = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return template.replace("__BOOK_TITLE__", html.escape(manifest["title"], quote=True)).replace(
        "__BOOK_DATA__", payload).encode("utf-8")


def output_paths(root: Path, title: str) -> tuple[Path, Path, Path]:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")
    require(bool(name), "Title cannot form an output filename.")
    if re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", name):
        name = "_" + name
    output = root / "output"
    paths = output / (name + "_绘本"), output / (name + ".html"), output / (name + "_绘本.zip")
    require(all(path.resolve().is_relative_to(root) for path in paths), "Output paths must remain inside the project.")
    return paths


def folder_files(root: Path, manifest: dict, assets: dict[str, bytes]) -> dict[str, bytes]:
    guide = (f"《{manifest['title']}》动态绘本\n\n"
             "请完整解压后，用 Chrome 或 Edge 打开 index.html；assets 文件夹须一起保留。\n"
             "单文件 HTML 可单独复制。所有资源已包含，无须联网。\n"
             f"本书包含 {len(manifest['characters'])} 个角色、{len(manifest['pages'])} 个动作和 "
             f"{len(manifest['scenes'])} 个场景。\n"
             "点动作或手动翻页会暂停；自动播放按钮可暂停/继续。角色和场景切换保留播放状态。\n"
             "再看一次从头重播；方向键翻页，Home 回封面，空格切换自动播放。\n"
             "文字由当前角色、位置与动作组成；末页自动回封面循环。\n"
             "本书采用虚构插画，设备播放与课堂使用效果以实际检查为准。\n")
    return {**assets, "index.html": render(root, manifest), "使用说明.txt": guide.encode("utf-8-sig")}


def verify(root: Path, prepared=None) -> dict:
    manifest, assets, checks = prepared or prepare(root)
    folder, single, archive_path = output_paths(root, manifest["title"])
    expected = folder_files(root, manifest, assets)
    actual_names = {path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file()}
    require(actual_names == set(expected), "Folder contains missing or unexpected files.")
    for name, data in expected.items():
        require((folder / name).read_bytes() == data, f"Folder bytes differ from current source: {name}")
    require(single.read_bytes() == render(root, embedded(manifest, assets)), "Single-file content differs from current source.")
    with zipfile.ZipFile(archive_path) as archive:
        require(archive.testzip() is None, "ZIP CRC failed.")
        require(len(archive.namelist()) == len(expected) and set(archive.namelist()) == set(expected),
                "ZIP member list differs from the folder.")
        for name, data in expected.items():
            require(archive.read(name) == data, f"ZIP bytes differ: {name}")
    result = {"checkedAtUTC": datetime.now(timezone.utc).isoformat(), "fileChecks": "passed",
              "browserAndVisualChecks": "not_run_by_script", "characters": len(manifest["characters"]),
              "actions": len(manifest["pages"]), "scenes": len(manifest["scenes"]),
              "animationChecks": checks, "embeddedAssetCount": len(assets), "zipMembers": len(expected),
              "artifacts": [{"path": str(p), "bytes": p.stat().st_size, "sha256": digest(p.read_bytes())}
                            for p in (folder / "index.html", single, archive_path)]}
    (root / "review").mkdir(exist_ok=True)
    (root / "review" / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def build(root: Path) -> dict:
    prepared = prepare(root)
    manifest, assets, checks = prepared
    folder, single, archive_path = output_paths(root, manifest["title"])
    expected = folder_files(root, manifest, assets)
    existing = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    require(not existing.difference(expected),
            "Unexpected existing output files; review obsolete generated files or use a separate version directory.")
    folder.mkdir(parents=True, exist_ok=True)
    for name, data in expected.items():
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    single.write_bytes(render(root, embedded(manifest, assets)))
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in sorted(expected):
            archive.writestr(name, expected[name])
    result = verify(root, prepared)
    report = {"title": manifest["title"], "configSha256": digest((root / "book.json").read_bytes()),
              "templateSha256": digest((root / "source" / "book-template.html").read_bytes()),
              "sourceAnimationChecks": checks, "outputFolder": str(folder),
              "files": {name: digest(data) for name, data in expected.items()},
              "artifacts": result["artifacts"], "browserAndVisualChecks": "pending_actual_review"}
    (root / "review" / "build-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def initialize(destination: Path, title: str) -> None:
    skill = Path(__file__).resolve().parents[1]
    require((skill / "assets" / "book.example.json").is_file(), "Run init from the installed skill's scripts/book.py.")
    require(not destination.exists() or destination.is_dir() and not any(destination.iterdir()),
            "Initialize into an empty directory; existing work will not be overwritten.")
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("source/brand", "source/atlases", "source/animations", "source/covers", "source/scenes", "review", "output"):
        (destination / name).mkdir(parents=True, exist_ok=True)
    for name in ("book.py", "atlas_to_webp.py", "pptx.py", "pptx.mjs"):
        shutil.copyfile(skill / "scripts" / name, destination / "source" / name)
    shutil.copyfile(skill / "assets" / "book-template.html", destination / "source" / "book-template.html")
    shutil.copyfile(skill / "assets" / "xiaoluohao-logo.png", destination / "source" / "brand" / "xiaoluohao-logo.png")
    spec = json.loads((skill / "assets" / "book.example.json").read_text(encoding="utf-8"))
    if title != spec["title"]:
        spec["coverLines"] = [title]
    spec["title"] = title
    (destination / "book.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"project": str(destination), "next": "Fill book.json and add the referenced source assets before build."}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Create a fresh project with local editable sources")
    init.add_argument("--out", type=Path, required=True)
    init.add_argument("--title", required=True)
    for name in ("build", "verify"):
        sub.add_parser(name).add_argument("project", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "init":
            initialize(args.out.resolve(), args.title)
        else:
            result = (build if args.command == "build" else verify)(args.project.resolve())
            print(json.dumps({key: result[key] for key in ("fileChecks", "characters", "actions", "scenes", "embeddedAssetCount", "zipMembers", "artifacts")}, ensure_ascii=False))
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
