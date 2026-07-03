"""Packing a mod folder into a distributable .zip (stdlib zipfile, no 7z)."""
from __future__ import annotations

import fnmatch
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

MOD_PREFIX = "FS25_"

# File globs matched against each file's name (case-insensitive).
EXCLUDE_FILES = [
    "*.cmd", "*.sh", "*.py", "*.zip", "*.yml", "*.yaml",
    "*.blend", "*.obj", "*.fbx",
    "*.mel", "*.mb", "*.ma",
    "*.txt", "*.md",
    ".gitattributes", ".gitignore", ".editorconfig",
    ".DS_Store", "Thumbs.db",
]

# Image sources — excluded by default, kept with keep_images=True.
EXCLUDE_IMAGES = ["*.png", "*.psd", "*.tga", "*.pdn", "*.gim"]

# Whole directories to skip (matched against any path component).
EXCLUDE_DIRS = {
    ".git", ".svn", ".idea", ".vscode", ".mayaSwatches",
    "substance", "$data",
}


def zip_stem(mod_dir: Path) -> str:
    """Mod folder name, ensuring the required FS25_ prefix (e.g. 'FS25_MyMod')."""
    name = mod_dir.name
    return name if name.startswith(MOD_PREFIX) else f"{MOD_PREFIX}{name}"


def icon_stems(mod_dir: Path) -> set[str]:
    """Lowercased stem(s) of iconFilename in modDesc.xml, so we never strip the
    mod's store icon even when it ships as a .png (FS converts png->dds)."""
    desc = mod_dir / "modDesc.xml"
    try:
        root = ET.parse(desc).getroot()
    except (ET.ParseError, OSError):
        return set()
    icon = (root.findtext("iconFilename") or "").strip()
    return {Path(icon).stem.lower()} if icon else set()


def is_excluded(rel: Path, keep_images: bool, keep_stems: set[str]) -> bool:
    if any(part in EXCLUDE_DIRS for part in rel.parts):
        return True
    name = rel.name.lower()
    if any(fnmatch.fnmatch(name, p.lower()) for p in EXCLUDE_FILES):
        return True
    if not keep_images and any(fnmatch.fnmatch(name, p.lower()) for p in EXCLUDE_IMAGES):
        # keep it anyway if it's the mod's icon
        return rel.stem.lower() not in keep_stems
    return False


def collect_files(mod_dir: Path, zip_name: str, keep_images: bool) -> list[Path]:
    """Return the mod-relative paths that would be packed, in stable order."""
    keep_stems = icon_stems(mod_dir)
    entries: list[Path] = []
    for path in sorted(mod_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(mod_dir)
        if is_excluded(rel, keep_images, keep_stems):
            continue
        if rel.name == zip_name:  # a previous build sitting in the folder
            continue
        entries.append(rel)
    return entries


def write_zip(mod_dir: Path, zip_path: Path, entries: list[Path]) -> int:
    """Write the zip (contents at root so modDesc.xml is top-level). Returns byte size."""
    if zip_path.exists():
        zip_path.unlink()
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for rel in entries:
            zf.write(mod_dir / rel, arcname=str(rel))
    return zip_path.stat().st_size
