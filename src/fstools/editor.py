"""Open .i3d scenes in the GIANTS Editor and register that as the Linux
file-association for .i3d.

The GIANTS Editor is a Windows program living inside the FS25 Proton prefix, so
we launch it via `protontricks-launch` (same mechanism as the TestRunner) with
the i3d file mapped to its `Z:\\` prefix path. The registration side drops a
freedesktop `.desktop` handler plus a `application/x-i3d` MIME type so any file
manager (or `xdg-open`) opens `*.i3d` with `fs edit`.
"""
from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterator

try:
    import termios
except ImportError:  # non-POSIX; the tool is Linux-only, but stay defensive.
    termios = None  # type: ignore[assignment]

from . import config

MIME_TYPE = "application/x-i3d"
DESKTOP_ID = "fs-i3d-editor.desktop"

_MIME_HOME = Path.home() / ".local/share/mime"
_APPS_DIR = Path.home() / ".local/share/applications"
MIME_PKG_FILE = _MIME_HOME / "packages" / "fs-i3d.xml"
DESKTOP_FILE = _APPS_DIR / DESKTOP_ID

_MIME_XML = """<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-i3d">
    <comment>GIANTS i3d scene</comment>
    <glob pattern="*.i3d"/>
  </mime-type>
</mime-info>
"""


def launch(i3d: Path, quiet: bool = True) -> subprocess.Popen:
    """Open an .i3d in the GIANTS Editor. Raises FileNotFoundError if the editor
    or protontricks-launch is missing.

    quiet=True detaches and discards the editor's console output (normal use).
    quiet=False inherits the terminal's stdio so the editor's warnings — e.g.
    'Could not load file ...' for a missing/mis-cased reference — are visible;
    the caller should then wait() for it.
    """
    exe = config.editor_exe()
    if exe is None:
        raise FileNotFoundError(
            "GIANTS Editor not found in the FS25 prefix. Install it in the prefix, "
            "or set FS25_EDITOR to editor.exe.")
    if shutil.which("protontricks-launch") is None:
        raise FileNotFoundError("protontricks-launch not found (install protontricks)")

    env = {**os.environ, "PROTONTRICKS_NO_TERM": "1"}
    cmd = ["protontricks-launch", "--appid", config.APPID, str(exe),
           config.to_wine_path(i3d)]
    if not quiet:
        # Inherit stdio so the editor's console (missing-file warnings) is shown.
        return subprocess.Popen(cmd, env=env)
    # Redirect stdin too: otherwise the editor inherits our terminal on fd 0 and
    # Wine flips it into raw mode (broken arrow keys / no echo) while it runs in
    # the background — and, being detached, there is no exit we can wait for to
    # restore it. Detaching stdin prevents the corruption entirely.
    return subprocess.Popen(
        cmd, start_new_session=True, env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


@contextlib.contextmanager
def preserve_terminal() -> Iterator[None]:
    """Snapshot the controlling terminal's mode and restore it on exit.

    The GIANTS Editor runs under Wine, which switches the tty into raw mode and
    does not reset it when it quits. Without this, running `fs edit -v` (which
    inherits our stdio and waits) leaves the shell unusable afterwards — arrow
    keys emit raw escape codes, input is not echoed. We save termios before the
    editor starts and restore it once it is gone.
    """
    saved = None
    fd = -1
    if termios is not None and sys.stdin.isatty():
        try:
            fd = sys.stdin.fileno()
            saved = termios.tcgetattr(fd)
        except (termios.error, OSError, ValueError):
            saved = None
    try:
        yield
    finally:
        if saved is not None:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, saved)
            except (termios.error, OSError, ValueError):
                pass


def _fs_bin() -> str:
    """Absolute path to the installed `fs` executable (for the .desktop Exec)."""
    return shutil.which("fs") or str(Path(sys.argv[0]).resolve())


def _desktop_entry() -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=GIANTS Editor (fsTools)\n"
        "Comment=Open i3d scenes in the GIANTS Editor via the FS25 Proton prefix\n"
        f"Exec={_fs_bin()} edit %f\n"
        "Terminal=false\n"
        "NoDisplay=true\n"
        f"MimeType={MIME_TYPE};\n"
        "Categories=Graphics;3DGraphics;\n"
    )


def _refresh_databases() -> None:
    if shutil.which("update-mime-database"):
        subprocess.run(["update-mime-database", str(_MIME_HOME)], check=False)
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(_APPS_DIR)], check=False)


def register() -> None:
    """Install the .i3d MIME type + desktop handler and make it the default."""
    MIME_PKG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _APPS_DIR.mkdir(parents=True, exist_ok=True)
    MIME_PKG_FILE.write_text(_MIME_XML)
    DESKTOP_FILE.write_text(_desktop_entry())
    _refresh_databases()
    if shutil.which("xdg-mime"):
        subprocess.run(["xdg-mime", "default", DESKTOP_ID, MIME_TYPE], check=False)


def unregister() -> None:
    """Remove the desktop handler and MIME type installed by register()."""
    MIME_PKG_FILE.unlink(missing_ok=True)
    DESKTOP_FILE.unlink(missing_ok=True)
    _refresh_databases()
