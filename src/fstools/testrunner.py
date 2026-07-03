"""Run the GIANTS ModHub TestRunner (a Windows exe) against a mod, on Linux.

The TestRunner is a console Windows program that also drives the GIANTS Editor.
We run it *inside the FS25 Proton prefix* via `protontricks-launch`, so it finds
the editor (from giantsPackageRegistry) and the game. Results (an html + xml
named `testResult_<mod>_..._<PASS|FAIL>.*`) and `TestRunner.log` are written
next to the exe; we move them to an output directory afterwards.

The exe is not shipped with fsTools — the user downloads it from the GIANTS
Developer Network. We keep an installed copy under ~/.local/share/fstools/.
"""
from __future__ import annotations

import contextlib
import fcntl
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

from . import config

INSTALL_DIR = Path.home() / ".local/share/fstools"
EXE_NAME = "TestRunner_public.exe"
SOURCE_FILE = INSTALL_DIR / ".source"   # records the archive the exe came from
LOCK_FILE = INSTALL_DIR / ".lock"       # guards the shared result/exe dir
RESULT_GLOBS = ("testResult_*.html", "testResult_*.xml", "TestRunner.log")


class TestRunnerBusy(RuntimeError):
    """Raised when another `fs test` run already holds the lock."""

# Places to look for a downloaded TestRunner zip/exe when it isn't installed yet.
_SEARCH_DIRS = (
    Path.cwd(),
    Path.home() / "Downloads",
)


def installed_exe() -> Path | None:
    import os
    override = os.environ.get("FS25_TESTRUNNER")
    if override and Path(override).is_file():
        return Path(override)
    exe = INSTALL_DIR / EXE_NAME
    return exe if exe.is_file() else None


def parse_version(name: str) -> tuple[int, ...]:
    """Extract a version tuple from a TestRunner archive/exe name.

    'TestRunner_public_0_9_18.zip' -> (0, 9, 18); returns () if none found.
    """
    m = re.search(r"(\d+(?:[._]\d+)+)", name)
    return tuple(int(x) for x in re.split(r"[._]", m.group(1))) if m else ()


def find_source() -> Path | None:
    """Find the newest TestRunner *.zip (or bare exe) across all search dirs."""
    candidates: list[Path] = []
    for d in _SEARCH_DIRS:
        if not d.is_dir():
            continue
        candidates.extend(d.glob("TestRunner*.zip"))
        exe = d / EXE_NAME
        if exe.is_file():
            candidates.append(exe)
    if not candidates:
        return None
    # Highest version wins; a bare exe (version ()) only wins if nothing else.
    return max(candidates, key=lambda p: parse_version(p.name))


def installed_source() -> str | None:
    """Name of the archive the installed exe came from, if recorded."""
    try:
        return SOURCE_FILE.read_text().strip() or None
    except OSError:
        return None


def install(source: Path) -> Path:
    """Install the TestRunner exe from a .exe or .zip into INSTALL_DIR."""
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    target = INSTALL_DIR / EXE_NAME
    if source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as zf:
            member = next((n for n in zf.namelist()
                           if n.lower().endswith(EXE_NAME.lower())), None)
            if member is None:
                raise FileNotFoundError(f"{EXE_NAME} not found inside {source.name}")
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    else:
        shutil.copy2(source, target)
    SOURCE_FILE.write_text(source.name)
    return target


@contextlib.contextmanager
def _exclusive_lock():
    """Advisory lock on the shared dir; released automatically on exit/crash."""
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    fd = open(LOCK_FILE, "w")
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise TestRunnerBusy(
                "another `fs test` run is already in progress "
                f"(lock held on {LOCK_FILE}). Wait for it to finish.")
        yield
    finally:
        fd.close()


def run(mod_zip: Path, output_dir: Path, verbose: bool = False) -> dict:
    """Run the TestRunner against a mod zip. Returns a result dict with keys:
    verdict ('PASS'|'FAIL'|'CRASH'|'UNKNOWN'), results (list[Path]), log (Path|None).
    """
    exe = installed_exe()
    if exe is None:
        raise FileNotFoundError("TestRunner not installed")
    game = config.game_install_dir()
    if game is None:
        raise FileNotFoundError("FS25 game install not found (set FS25_GAME_DIR)")
    if shutil.which("protontricks-launch") is None:
        raise FileNotFoundError("protontricks-launch not found (install protontricks)")

    exe_dir = exe.parent

    # The exe writes results into its own dir, so only one run may use it at a
    # time. The lock refuses (rather than corrupts) if another run is active.
    with _exclusive_lock():
        # Clear any stale results from a previous run in the exe dir.
        for pattern in RESULT_GLOBS:
            for stale in exe_dir.glob(pattern):
                stale.unlink()

        cmd = [
            "protontricks-launch", "--appid", config.APPID, str(exe),
            config.to_wine_path(mod_zip), "-g", config.to_wine_path(game),
        ]
        if verbose:
            cmd.append("--verbose")

        env = {"PROTONTRICKS_NO_TERM": "1"}
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              env={**_environ(), **env})

        # Collect and relocate result files (still under the lock).
        output_dir.mkdir(parents=True, exist_ok=True)
        results: list[Path] = []
        log: Path | None = None
        for pattern in RESULT_GLOBS:
            for f in exe_dir.glob(pattern):
                dest = output_dir / f.name
                shutil.move(str(f), dest)
                if dest.suffix == ".log":
                    log = dest
                else:
                    results.append(dest)

    verdict = _verdict(results, proc.stdout + proc.stderr, log)
    return {"verdict": verdict, "results": sorted(results), "log": log,
            "stdout": proc.stdout, "stderr": proc.stderr}


def _verdict(results: list[Path], output: str, log: Path | None) -> str:
    if not results:
        # No result files -> the tool aborted (e.g. internal crash/traceback).
        if "Traceback" in output or (log and "Traceback" in log.read_text(errors="replace")):
            return "CRASH"
        return "UNKNOWN"
    names = " ".join(p.name for p in results)
    if "_FAIL." in names:
        return "FAIL"
    if "_PASS." in names:
        return "PASS"
    return "UNKNOWN"


def _environ() -> dict:
    import os
    return dict(os.environ)
