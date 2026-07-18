"""Shared configuration and Steam/Proton path detection for FS25."""
from __future__ import annotations

import os
import re
from pathlib import Path

APPID = os.environ.get("FS25_APPID", "2300320")

# Steam library roots to probe, in priority order.
_STEAM_ROOTS = (".local/share/Steam", ".steam/steam", ".steam/root")

# Path of the Proton prefix relative to a Steam root.
_PREFIX_REL = f"steamapps/compatdata/{APPID}/pfx"

# Path of the game-data dir relative to a Steam root (inside the Proton prefix).
_GAMEDATA_REL = (
    f"{_PREFIX_REL}/drive_c/users/steamuser/"
    "Documents/My Games/FarmingSimulator2025"
)


def game_data_dir() -> Path | None:
    """The 'FarmingSimulator2025' folder (holds mods/, log.txt, savegames…)."""
    home = Path.home()
    for root in _STEAM_ROOTS:
        candidate = home / root / _GAMEDATA_REL
        if candidate.is_dir():
            return candidate
    return None


def mods_dir() -> Path | None:
    override = os.environ.get("FS25_MODS_DIR")
    if override:
        p = Path(override)
        return p if p.is_dir() else None
    base = game_data_dir()
    if base is None:
        return None
    mods = base / "mods"
    return mods if mods.is_dir() else None


def prefix_dir() -> Path | None:
    """The FS25 Proton prefix ('.../pfx', holding drive_c)."""
    home = Path.home()
    for root in _STEAM_ROOTS:
        candidate = home / root / _PREFIX_REL
        if candidate.is_dir():
            return candidate
    return None


def _version_key(p: Path) -> tuple[int, ...]:
    """Version tuple parsed from an editor folder name, for picking the newest.

    'GIANTS_Editor_10.0.11' -> (10, 0, 11); () if no version found.
    """
    m = re.search(r"(\d+(?:[._]\d+)+)", p.parent.name)
    return tuple(int(x) for x in re.split(r"[._]", m.group(1))) if m else ()


def editor_exe() -> Path | None:
    """Locate the GIANTS Editor's editor.exe inside the FS25 Proton prefix.

    Checks FS25_EDITOR first, else the default install location under
    Program Files (e.g. 'GIANTS Software/GIANTS_Editor_10.0.11/editor.exe', or
    an older 'GIANTS Editor 64bit 10.x/editor.exe'), newest version wins.
    """
    override = os.environ.get("FS25_EDITOR")
    if override:
        p = Path(override)
        return p if p.is_file() else None
    prefix = prefix_dir()
    if prefix is None:
        return None
    drive_c = prefix / "drive_c"
    matches: list[Path] = []
    for pf in ("Program Files", "Program Files (x86)"):
        base = drive_c / pf
        # editor.exe sits either directly in an editor folder or one vendor
        # folder deeper ('GIANTS Software/GIANTS_Editor_.../editor.exe').
        for exe in (*base.glob("*/editor.exe"), *base.glob("*/*/editor.exe")):
            if "editor" in exe.parent.name.lower():
                matches.append(exe)
    return max(matches, default=None, key=_version_key)


def game_install_dir() -> Path | None:
    """The 'Farming Simulator 25' install folder (holds FarmingSimulator2025.exe)."""
    override = os.environ.get("FS25_GAME_DIR")
    if override:
        p = Path(override)
        return p if p.is_dir() else None
    home = Path.home()
    for root in _STEAM_ROOTS:
        candidate = home / root / "steamapps/common/Farming Simulator 25"
        if candidate.is_dir():
            return candidate
    return None


def to_wine_path(p: Path) -> str:
    r"""Map an absolute Linux path to its Proton-prefix drive path (Z:\...)."""
    return "Z:" + str(p).replace("/", "\\")


def log_path() -> Path | None:
    override = os.environ.get("FS25_LOG")
    if override:
        p = Path(override)
        return p if p.is_file() else None
    base = game_data_dir()
    if base is None:
        return None
    log = base / "log.txt"
    return log if log.is_file() else None
