"""Packing a mod folder into a distributable .zip (stdlib zipfile, no 7z)."""
from __future__ import annotations

import fnmatch
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import defusedxml.ElementTree as DefusedET

from .packconfig import CONFIG_NAME

MOD_PREFIX = "FS25_"

# gitignore-style file listing extra paths to leave out of the zip (per mod).
IGNORE_NAME = ".fsignore"

# File globs matched against each file's name (case-insensitive).
EXCLUDE_FILES = [
    "*.cmd", "*.sh", "*.py", "*.zip", "*.yml", "*.yaml",
    "*.blend", "*.obj", "*.fbx",
    "*.mel", "*.mb", "*.ma",
    "*.psd", "*.pdn", "*.ora", "*.xcf", "*.kra",  # image editor sources — never part of a mod zip
    "*.txt", "*.md",
    ".gitattributes", ".gitignore", ".editorconfig",
    ".DS_Store", "Thumbs.db",
    CONFIG_NAME,   # our own fstools.toml — never ship it
    IGNORE_NAME,   # nor the .fsignore
]

# Whole directories to skip (matched against any path component).
EXCLUDE_DIRS = {
    ".git", ".svn", ".idea", ".vscode", ".mayaSwatches",
    "substance", "$data",
}


def zip_stem(mod_dir: Path, override: str | None = None) -> str:
    """The zip name (without .zip), normalized to the required 'FS25_' prefix.

    Uses ``override`` (from fstools.toml) when given, else the mod folder name.
    The 'FS25_' prefix is added if missing (any existing prefix, any case, is
    normalized to 'FS25_'); the rest of the name is left as-is.
    """
    name = override if override else mod_dir.name
    if name[: len(MOD_PREFIX)].upper() == MOD_PREFIX:  # strip existing prefix, any case
        name = name[len(MOD_PREFIX):]
    return f"{MOD_PREFIX}{name}"


def is_excluded(rel: Path) -> bool:
    if any(part in EXCLUDE_DIRS for part in rel.parts):
        return True
    name = rel.name.lower()
    return any(fnmatch.fnmatch(name, p.lower()) for p in EXCLUDE_FILES)


def load_ignore(mod_dir: Path) -> list[str]:
    """Read .fsignore patterns from the mod folder (blank lines and # comments
    skipped). Absent file -> no extra patterns."""
    path = mod_dir / IGNORE_NAME
    if not path.is_file():
        return []
    patterns: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def is_ignored(rel: Path, patterns: list[str]) -> bool:
    """gitignore-flavoured match against a mod-relative path. A pattern with a
    '/' is matched against the whole path (so it can target a subfolder); one
    without is matched against every path component (so 'wip/' or '*.psd' hits
    at any depth). '*' spans path separators."""
    if not patterns:
        return False
    posix = rel.as_posix()
    for pat in patterns:
        anchored = pat.startswith("/")
        p = pat.strip("/")
        if not p:
            continue
        if anchored or "/" in p:
            if fnmatch.fnmatch(posix, p) or fnmatch.fnmatch(posix, f"{p}/*"):
                return True
        elif any(fnmatch.fnmatch(part, p) for part in rel.parts):
            return True
    return False


def collect_files(mod_dir: Path, zip_name: str) -> list[Path]:
    """Return the mod-relative paths that would be packed, in stable order."""
    ignore = load_ignore(mod_dir)
    entries: list[Path] = []
    for path in sorted(mod_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(mod_dir)
        if is_excluded(rel) or is_ignored(rel, ignore):
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


# Expat reports a CDATA section as plain character data, so an ElementTree
# round-trip would silently turn <![CDATA[…]]> into escaped text. The GIANTS
# TestRunner insists on real CDATA sections in modDesc.xml (<description>), so
# the section boundaries are fenced with sentinels while parsing and rebuilt
# after serializing. NUL cannot occur in XML text, hence it cannot collide with
# anything the modDesc actually contains.
_CDATA_OPEN = "\x00[CDATA\x00"
_CDATA_CLOSE = "\x00CDATA]\x00"
_CDATA_SPAN = re.compile(
    re.escape(_CDATA_OPEN.encode()) + b"(.*?)" + re.escape(_CDATA_CLOSE.encode()),
    re.DOTALL,
)


class _CDataParser(DefusedET.DefusedXMLParser):
    """Defused parser that fences CDATA sections in the text it hands to the tree."""

    def __init__(self) -> None:
        super().__init__(target=ET.TreeBuilder())
        # Expat calls these around the section's character data, so the markers
        # land in the same .text/.tail string as the content they wrap.
        self.parser.StartCdataSectionHandler = lambda: self.target.data(_CDATA_OPEN)
        self.parser.EndCdataSectionHandler = lambda: self.target.data(_CDATA_CLOSE)


def _restore_cdata(data: bytes) -> bytes:
    """Turn every fenced span back into a literal CDATA section.

    ET escaped the fenced content on the way out ('<' -> '&lt;', …); inside a
    CDATA section it has to be raw again, so undo exactly those three.
    """
    def unfence(match: re.Match[bytes]) -> bytes:
        text = (match.group(1)
                .replace(b"&lt;", b"<")
                .replace(b"&gt;", b">")
                .replace(b"&amp;", b"&"))
        return b"<![CDATA[" + text + b"]]>"

    return _CDATA_SPAN.sub(unfence, data)


def rewrite_moddesc(mod_dir: Path, *, title: str | dict[str, str] | None = None,
                    version: str | None = None, author: str | None = None) -> bytes:
    """modDesc.xml bytes with the given fields overridden.

    Lets fstools.toml drive the mod's metadata without editing the file on disk.
    """
    root = DefusedET.parse(mod_dir / "modDesc.xml", parser=_CDataParser()).getroot()
    if version is not None:
        _set_child_text(root, "version", version)
    if author is not None:
        _set_child_text(root, "author", author)
    if title is not None:
        _apply_title(root, title)
    return _restore_cdata(ET.tostring(root, encoding="utf-8", xml_declaration=True))


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
