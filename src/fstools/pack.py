"""Packing a mod folder into a distributable .zip (stdlib zipfile, no 7z)."""
from __future__ import annotations

import fnmatch
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from .packconfig import CONFIG_NAME

MOD_PREFIX = "FS25_"

# File globs matched against each file's name (case-insensitive).
EXCLUDE_FILES = [
    "*.cmd", "*.sh", "*.py", "*.zip", "*.yml", "*.yaml",
    "*.blend", "*.obj", "*.fbx",
    "*.mel", "*.mb", "*.ma",
    "*.txt", "*.md",
    ".gitattributes", ".gitignore", ".editorconfig",
    ".DS_Store", "Thumbs.db",
    CONFIG_NAME,  # our own fspack.toml — never ship it
]

# Image sources — excluded by default, kept with keep_images=True.
EXCLUDE_IMAGES = ["*.png", "*.psd", "*.tga", "*.pdn", "*.gim"]

# Whole directories to skip (matched against any path component).
EXCLUDE_DIRS = {
    ".git", ".svn", ".idea", ".vscode", ".mayaSwatches",
    "substance", "$data",
}


def zip_stem(mod_dir: Path, override: str | None = None) -> str:
    """The zip name (without .zip), normalized to the required 'FS25_' prefix.

    Uses ``override`` (from fspack.toml) when given, else the mod folder name.
    The 'FS25_' prefix is added if missing (any existing prefix, any case, is
    normalized to 'FS25_'); the rest of the name is left as-is.
    """
    name = override if override else mod_dir.name
    if name[: len(MOD_PREFIX)].upper() == MOD_PREFIX:  # strip existing prefix, any case
        name = name[len(MOD_PREFIX):]
    return f"{MOD_PREFIX}{name}"


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


def _set_child_text(root: ET.Element, tag: str, text: str) -> None:
    """Set <tag>text</tag> under root, creating the element if it's missing."""
    el = root.find(tag)
    if el is None:
        el = ET.SubElement(root, tag)
    el.text = text


def _apply_title(root: ET.Element, title: str | dict[str, str]) -> None:
    el = root.find("title")
    if el is None:
        el = ET.SubElement(root, "title")
    if isinstance(title, str):  # one string -> every existing language entry
        langs = list(el)
        if langs:
            for lang in langs:  # <en>…</en>, <de>…</de>, …
                lang.text = title
        else:
            el.text = title
    else:  # per-language table -> set/create each listed language
        for lang, text in title.items():
            child = el.find(lang)
            if child is None:
                child = ET.SubElement(el, lang)
            child.text = text


def rewrite_moddesc(mod_dir: Path, *, title: str | dict[str, str] | None = None,
                    version: str | None = None, author: str | None = None) -> bytes:
    """modDesc.xml bytes with the given fields overridden.

    Lets fstools.toml drive the mod's metadata without editing the file on disk.
    """
    root = ET.parse(mod_dir / "modDesc.xml").getroot()
    if version is not None:
        _set_child_text(root, "version", version)
    if author is not None:
        _set_child_text(root, "author", author)
    if title is not None:
        _apply_title(root, title)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def write_zip(mod_dir: Path, zip_path: Path, entries: list[Path], *,
              title: str | dict[str, str] | None = None,
              version: str | None = None, author: str | None = None) -> int:
    """Write the zip (contents at root so modDesc.xml is top-level). Returns byte size.

    When any of title/version/author is given, modDesc.xml is rewritten in the
    zip with those values (the file on disk is untouched)."""
    if zip_path.exists():
        zip_path.unlink()
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    moddesc_bytes = None
    if title is not None or version is not None or author is not None:
        moddesc_bytes = rewrite_moddesc(mod_dir, title=title, version=version, author=author)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for rel in entries:
            if moddesc_bytes is not None and rel.as_posix() == "modDesc.xml":
                zf.writestr("modDesc.xml", moddesc_bytes)
            else:
                zf.write(mod_dir / rel, arcname=str(rel))
    return zip_path.stat().st_size
