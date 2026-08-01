"""Optional per-mod fsTools config (``fstools.toml``).

Holds a ``[mod]`` section to drive the packed mod's metadata without editing
modDesc.xml or renaming the folder. Drop an ``fstools.toml`` next to modDesc.xml
to build a differently-named variant (e.g. a dev build that coexists with your
stable mod in the same savegame):

    [mod]
    zip_name = "FS25_MyMod_dev"   # packed .zip stem (FS25_ prefix added if missing)
    version  = "1.0.0.0-dev"      # overrides <version>
    author   = "Me"               # overrides <author>
    title    = "My Mod (dev)"     # overrides every <title> language entry

    # …or set titles per language instead of one string:
    # [mod.title]
    # en = "My Mod (dev)"
    # de = "Mein Mod (dev)"

Every key is optional; overrides are written into the packed zip's modDesc.xml
(the file on disk is untouched). The file is never packed into the zip.

A ``[patch]`` section drives ``fs patch`` instead — swapping single files into an
existing mod zip (someone else's ModHub download, typically) without unpacking it:

    [patch]
    source         = "~/Downloads/FS25_SomeMod.zip"  # pristine base zip, never modified
    zip_name       = "FS25_SomeMod"                  # output stem (default: the base's)
    version_suffix = "-bl"                           # appended to the base's <version>

The two sections are independent — a folder is either a mod source tree or a
patch overlay. Other tools may add their own top-level sections in the future.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_NAME = "fstools.toml"


class PackConfigError(Exception):
    """Raised when fstools.toml exists but cannot be parsed or is malformed."""


@dataclass
class PackConfig:
    zip_name: str | None = None            # override the packed zip stem (no .zip)
    title: str | dict[str, str] | None = None  # str: all langs; dict: per-language
    version: str | None = None             # override <version>
    author: str | None = None              # override <author>

    @property
    def overrides_moddesc(self) -> bool:
        """True if any field rewrites modDesc.xml (title/version/author)."""
        return any(v is not None for v in (self.title, self.version, self.author))

    def title_display(self) -> str:
        """Human-readable title for log lines (handles the per-language table)."""
        if isinstance(self.title, dict):
            return ", ".join(f"{lang}={text}" for lang, text in self.title.items())
        return self.title or ""


@dataclass
class PatchConfig:
    source: str | None = None              # base zip to patch (path, or bare name -> mods dir)
    zip_name: str | None = None            # override the output zip stem (no .zip)
    version_suffix: str | None = None      # appended to the base's <version>


def config_path(mod_dir: Path) -> Path:
    return mod_dir / CONFIG_NAME


def _clean_str(value: object, key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PackConfigError(f"'{key}' must be a string in {CONFIG_NAME}")
    value = value.strip()
    return value or None


def _load_title(value: object) -> str | dict[str, str] | None:
    if value is None or isinstance(value, str):
        return _clean_str(value, "title")
    if isinstance(value, dict):
        out: dict[str, str] = {}
        for lang, text in value.items():
            clean = _clean_str(text, f"title.{lang}")
            if clean:
                out[lang] = clean
        return out or None
    raise PackConfigError(f"'title' must be a string or a table in {CONFIG_NAME}")


def _load_zip_name(value: object) -> str | None:
    name = _clean_str(value, "zip_name")
    if name and name.lower().endswith(".zip"):  # tolerate a stray .zip
        name = name[:-4] or None
    if name and Path(name).name != name:
        raise PackConfigError(f"'zip_name' must not contain path separators in {CONFIG_NAME}")
    return name


def _section(mod_dir: Path, name: str) -> dict | None:
    """One top-level table of fstools.toml. None when the file does not exist."""
    path = config_path(mod_dir)
    if not path.is_file():
        return None
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise PackConfigError(f"{CONFIG_NAME} is not valid TOML: {exc}") from exc
    section = data.get(name, {})
    if not isinstance(section, dict):
        raise PackConfigError(f"'[{name}]' must be a table in {CONFIG_NAME}")
    return section


def load(mod_dir: Path) -> PackConfig:
    """Read the [mod] section of fstools.toml. Missing file -> empty config."""
    mod = _section(mod_dir, "mod")
    if mod is None:
        return PackConfig()
    return PackConfig(
        zip_name=_load_zip_name(mod.get("zip_name")),
        title=_load_title(mod.get("title")),
        version=_clean_str(mod.get("version"), "version"),
        author=_clean_str(mod.get("author"), "author"),
    )


def load_patch(patch_dir: Path) -> PatchConfig:
    """Read the [patch] section of fstools.toml. Missing file -> empty config."""
    patch = _section(patch_dir, "patch")
    if patch is None:
        return PatchConfig()
    return PatchConfig(
        source=_clean_str(patch.get("source"), "source"),
        zip_name=_load_zip_name(patch.get("zip_name")),
        version_suffix=_clean_str(patch.get("version_suffix"), "version_suffix"),
    )
