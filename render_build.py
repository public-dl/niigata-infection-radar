#!/usr/bin/env python3
from pathlib import Path
import shutil
import urllib.parse

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "render-dist"

NETLIFY_ORIGIN = "https://niigata-infection-radar.netlify.app"
RENDER_ORIGIN = "https://niigata-infection-radar.onrender.com"

IGNORE_NAMES = {
    ".git",
    ".github",
    "render-dist",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".idea",
    ".vscode",
    "scripts",
    "tests",
    "docs",
}

IGNORE_SUFFIXES = {".pyc", ".pyo"}
TEXT_SUFFIXES = {".html", ".htm", ".xml", ".txt", ".json", ".js", ".mjs", ".webmanifest"}

def ignore_item(path: Path) -> bool:
    if path.name in IGNORE_NAMES:
        return True
    if path.suffix.lower() in IGNORE_SUFFIXES:
        return True
    if path.name.startswith(".env"):
        return True
    return False

def copy_public_tree(src: Path, dst: Path) -> None:
    for item in src.iterdir():
        if ignore_item(item):
            continue
        target = dst / item.name
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            copy_public_tree(item, target)
        else:
            shutil.copy2(item, target)

def replace_origin_in_text_files(root: Path) -> int:
    replacements = 0
    pairs = [
        (NETLIFY_ORIGIN + "/", RENDER_ORIGIN + "/"),
        (NETLIFY_ORIGIN, RENDER_ORIGIN),
        (urllib.parse.quote(NETLIFY_ORIGIN + "/", safe=""), urllib.parse.quote(RENDER_ORIGIN + "/", safe="")),
        (urllib.parse.quote(NETLIFY_ORIGIN, safe=""), urllib.parse.quote(RENDER_ORIGIN, safe="")),
    ]
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new_text = text
        for old, new in pairs:
            if old in new_text:
                count = new_text.count(old)
                new_text = new_text.replace(old, new)
                replacements += count
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
    return replacements

def ensure_render_robots(root: Path) -> None:
    robots = root / "robots.txt"
    if robots.exists():
        return
    sitemap = root / "sitemap.xml"
    lines = ["User-agent: *", "Allow: /"]
    if sitemap.exists():
        lines.append(f"Sitemap: {RENDER_ORIGIN}/sitemap.xml")
    robots.write_text("\n".join(lines) + "\n", encoding="utf-8")

def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    copy_public_tree(ROOT, OUT)
    replacements = replace_origin_in_text_files(OUT)
    ensure_render_robots(OUT)
    index = OUT / "index.html"
    if not index.exists():
        raise SystemExit("ERROR: render-dist/index.html が見つかりません。")
    print(f"Render publish directory: {OUT}")
    print(f"URL replacements: {replacements}")
    print("Render build complete.")

if __name__ == "__main__":
    main()
