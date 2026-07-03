"""Shared configuration and Steam/Proton path detection for FS25."""
from __future__ import annotations

import os
from pathlib import Path

APPID = os.environ.get("FS25_APPID", "2300320")

# Steam library roots to probe, in priority order.
_STEAM_ROOTS = (".local/share/Steam", ".steam/steam", ".steam/root")

# Path of the game-data dir relative to a Steam root (inside the Proton prefix).
_GAMEDATA_REL = (
    f"steamapps/compatdata/{APPID}/pfx/drive_c/users/steamuser/"
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
