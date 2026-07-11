"""`fs` — Farming Simulator 25 modding helpers.

Subcommands:
    fs pack MOD       pack a mod folder into a .zip (optionally deploy + launch)
    fs log            follow the game log.txt (errors in red, warnings yellow)
    fs validate MOD   sanity-check a mod's modDesc.xml
    fs edit FILE.i3d  open an .i3d scene in the GIANTS Editor
    fs register-editor  associate .i3d files with the GIANTS Editor
    fs paths          show the detected FS25 folders
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import typer

from . import (
    config, editor as editormod, logtail, pack as packmod, packconfig,
    testrunner, validate as validatemod,
)
from .console import die, info, ok, warn

app = typer.Typer(
    help="Farming Simulator 25 modding helpers.",
    no_args_is_help=True,
)


@app.command()
def pack(
    mod_folder: Path = typer.Argument(
        Path("."), help="mod folder to pack (default: current folder)"),
    output: Optional[Path] = typer.Option(
        None, "-o", "--output", help="write the .zip here (default: mod folder's parent)"),
    deploy: bool = typer.Option(
        False, "-d", "--deploy", help="also copy the .zip into the FS25 mods folder"),
    play: bool = typer.Option(
        False, "-p", "--play", help="deploy, then launch FS25 via Steam (implies --deploy)"),
    dry_run: bool = typer.Option(
        False, "-n", "--dry-run", help="show what would happen without writing anything"),
) -> None:
    """Pack a mod folder into a distributable .zip."""
    mod_dir = mod_folder.expanduser().resolve()
    if not mod_dir.is_dir():
        raise die(f"Mod folder not found: {mod_folder}")
    if not (mod_dir / "modDesc.xml").is_file():
        raise die(f"'{mod_dir.name}' has no modDesc.xml — packing canceled!")

    try:
        cfg = packconfig.load(mod_dir)
    except packconfig.PackConfigError as exc:
        raise die(str(exc))

    out_dir = output.expanduser().resolve() if output else mod_dir
    zip_path = out_dir / f"{packmod.zip_stem(mod_dir, cfg.zip_name)}.zip"

    info(f"Packing mod {typer.style(mod_dir.name, bold=True)}")
    info(f"  source : {mod_dir}")
    info(f"  output : {zip_path}")
    src = f"(from {packconfig.CONFIG_NAME})"
    if cfg.zip_name:
        info(f"  zip    : {zip_path.stem} {src}")
    if cfg.title:
        info(f"  title  : {cfg.title_display()} {src}")
    if cfg.version:
        info(f"  version: {cfg.version} {src}")
    if cfg.author:
        info(f"  author : {cfg.author} {src}")

    entries = packmod.collect_files(mod_dir, zip_path.name)

    if dry_run:
        warn(f"dry-run: would pack {len(entries)} files:")
        for rel in entries:
            typer.echo(f"    {rel}")
    else:
        if zip_path.exists():
            warn(f"Old {zip_path.name} will be replaced")
        size = packmod.write_zip(mod_dir, zip_path, entries,
                                 title=cfg.title, version=cfg.version, author=cfg.author)
        ok(f"Mod '{mod_dir.name}' packed successfully! "
           f"({len(entries)} files, {size / 1_048_576:.1f} MiB)")

    if deploy or play:
        mods = config.mods_dir()
        if mods is None:
            raise die("Could not find FS25 mods folder. Set FS25_MODS_DIR.")
        info(f"Deploying to {mods}")
        if dry_run:
            warn(f"dry-run: would copy {zip_path.name} -> {mods}/")
        else:
            shutil.copy2(zip_path, mods / zip_path.name)
            ok(f"Copied {zip_path.name} into mods folder")

    if play:
        if dry_run:
            warn(f"dry-run: would run: steam -applaunch {config.APPID}")
        elif shutil.which("steam") is None:
            raise die("steam not found on PATH.")
        else:
            info(f"Launching FS25 via Steam (app {config.APPID})…")
            subprocess.Popen(
                ["steam", "-applaunch", config.APPID],
                start_new_session=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            ok("Launch requested — check Steam.")


@app.command()
def log(
    errors_only: bool = typer.Option(
        False, "-e", "--errors-only", help="only show Error/Warning lines"),
    lines: int = typer.Option(
        20, "-n", "--lines", help="lines of history to show before following"),
    no_follow: bool = typer.Option(
        False, "--no-follow", help="print existing content and exit (do not tail)"),
) -> None:
    """Follow the FS25 log.txt (errors red, warnings yellow)."""
    log_file = config.log_path()
    if log_file is None:
        raise die("FS25 log.txt not found. Set FS25_LOG.")
    info(f"tailing {log_file}")
    logtail.tail(log_file, errors_only=errors_only, lines=lines, follow=not no_follow)


@app.command()
def validate(
    mod_folder: Path = typer.Argument(
        Path("."), help="mod folder to check (default: current folder)"),
) -> None:
    """Sanity-check a mod's modDesc.xml (fields, icon, store items)."""
    mod_dir = mod_folder.expanduser().resolve()
    if not mod_dir.is_dir():
        raise die(f"Mod folder not found: {mod_folder}")

    errors, warnings = validatemod.validate(mod_dir)
    for w in warnings:
        warn(w)
    if errors:
        for e in errors:
            typer.secho(f"✗ {e}", fg=typer.colors.RED, err=True)
        raise die(f"{mod_dir.name}: {len(errors)} error(s), {len(warnings)} warning(s)")
    ok(f"{mod_dir.name}: modDesc.xml looks good "
       f"({len(warnings)} warning(s))")


@app.command()
def test(
    mod: Path = typer.Argument(
        Path("."), help="mod folder or .zip to test (default: current folder)"),
    verbose: bool = typer.Option(
        False, "--verbose", help="pass --verbose to the TestRunner"),
) -> None:
    """Run the GIANTS ModHub TestRunner against a mod (via the FS25 Proton prefix).

    Requires protontricks and a downloaded TestRunner (set FS25_TESTRUNNER or drop
    the TestRunner*.zip in the project / ~/Downloads — it is installed on first use).
    """
    mod = mod.expanduser().resolve()

    # Ensure the TestRunner exe is installed.
    if testrunner.installed_exe() is None:
        source = testrunner.find_source()
        if source is None:
            raise die("TestRunner not found. Download it from the GIANTS Developer "
                      "Network and set FS25_TESTRUNNER, or drop TestRunner*.zip in "
                      "~/Downloads.")
        info(f"Installing TestRunner from {source.name}")
        testrunner.install(source)
        ok(f"Installed to {testrunner.INSTALL_DIR}")

    # Resolve the mod to a clean .zip (pack a folder; use a .zip as-is).
    tmp: tempfile.TemporaryDirectory | None = None
    if mod.is_dir():
        if not (mod / "modDesc.xml").is_file():
            raise die(f"'{mod.name}' has no modDesc.xml")
        try:
            cfg = packconfig.load(mod)
        except packconfig.PackConfigError as exc:
            raise die(str(exc))
        tmp = tempfile.TemporaryDirectory(prefix="fstest-")
        zip_path = Path(tmp.name) / f"{packmod.zip_stem(mod, cfg.zip_name)}.zip"
        entries = packmod.collect_files(mod, zip_path.name)
        packmod.write_zip(mod, zip_path, entries,
                          title=cfg.title, version=cfg.version, author=cfg.author)
        info(f"Packed {mod.name} -> {zip_path.name} ({len(entries)} files)")
        output_dir = mod.parent
    elif mod.suffix.lower() == ".zip" and mod.is_file():
        zip_path = mod
        output_dir = mod.parent
    else:
        raise die(f"Not a mod folder or .zip: {mod}")

    info("Running TestRunner in the FS25 Proton prefix (the GIANTS Editor may "
         "open briefly — this can take a few minutes)…")
    try:
        result = testrunner.run(zip_path, output_dir, verbose=verbose)
    except testrunner.TestRunnerBusy as exc:
        raise die(str(exc))
    except FileNotFoundError as exc:
        raise die(str(exc))
    finally:
        if tmp is not None:
            tmp.cleanup()

    verdict = result["verdict"]
    style = {"PASS": typer.colors.GREEN, "FAIL": typer.colors.YELLOW,
             "CRASH": typer.colors.RED}.get(verdict, typer.colors.WHITE)
    typer.secho(f"TestRunner verdict: {verdict}", fg=style, bold=True)

    for r in result["results"]:
        info(f"  report : {r}")
    if result["log"]:
        info(f"  log    : {result['log']}")

    if verdict == "CRASH":
        warn("The TestRunner aborted without writing a report — see the log above. "
             "This is usually an internal TestRunner bug, not necessarily your mod.")
        raise typer.Exit(code=2)

    raise typer.Exit(code=0 if verdict == "PASS" else 1)


@app.command("testrunner")
def testrunner_cmd(
    update: bool = typer.Option(
        False, "-u", "--update", help="install/replace the exe from SOURCE (or the "
        "newest TestRunner*.zip found in the project / ~/Downloads)"),
    source: Optional[Path] = typer.Option(
        None, "-s", "--source", help="path to a TestRunner*.zip or .exe to install"),
) -> None:
    """Show or update the installed GIANTS TestRunner executable."""
    current = testrunner.installed_exe()
    recorded = testrunner.installed_source()
    info(f"installed  : {current or '(not installed)'}")
    if recorded:
        info(f"from       : {recorded}")

    available = source.expanduser().resolve() if source else testrunner.find_source()
    if available:
        newer = (testrunner.parse_version(available.name)
                 > testrunner.parse_version(recorded or ""))
        tag = "  (newer)" if newer and recorded else ""
        info(f"available  : {available.name}{tag}")

    if not update and source is None:
        if available and recorded and \
                testrunner.parse_version(available.name) > testrunner.parse_version(recorded):
            warn(f"A newer TestRunner is available. Update with:  fs testrunner --update")
        return

    if available is None:
        raise die("No TestRunner*.zip or .exe found. Download it from the GIANTS "
                  "Developer Network, then pass --source PATH.")
    info(f"Installing {available.name} …")
    testrunner.install(available)
    ok(f"TestRunner updated -> {testrunner.INSTALL_DIR / testrunner.EXE_NAME}")


@app.command()
def edit(
    scene: Path = typer.Argument(
        ..., help="the .i3d scene to open in the GIANTS Editor"),
    debug: bool = typer.Option(
        False, "-v", "--debug", help="run in the foreground and print the editor's "
        "console (shows 'could not load file' warnings for missing/mis-cased refs)"),
) -> None:
    """Open an .i3d scene in the GIANTS Editor (via the FS25 Proton prefix)."""
    path = scene.expanduser().resolve()
    if not path.is_file():
        raise die(f"File not found: {scene}")
    if path.suffix.lower() != ".i3d":
        warn(f"{path.name} is not an .i3d file — opening it anyway")
    try:
        proc = editormod.launch(path, quiet=not debug)
    except FileNotFoundError as exc:
        raise die(str(exc))
    ok(f"Opening {path.name} in the GIANTS Editor…")
    if debug:
        info("Editor console follows (close the editor to return):")
        proc.wait()


@app.command("register-editor")
def register_editor(
    remove: bool = typer.Option(
        False, "--remove", help="undo the association instead of installing it"),
) -> None:
    """Associate .i3d files with the GIANTS Editor so you can open them from any
    file manager (double-click) or with `xdg-open FILE.i3d`."""
    if remove:
        editormod.unregister()
        ok("Removed the .i3d → GIANTS Editor file association.")
        return
    if config.editor_exe() is None:
        warn("GIANTS Editor not detected in the FS25 prefix — installing the "
             "association anyway. Set FS25_EDITOR or install the editor in the "
             "prefix so `fs edit` can find editor.exe.")
    editormod.register()
    ok("Registered .i3d files to open with the GIANTS Editor (via `fs edit`).")
    info("Double-click any .i3d in your file manager, or run:  xdg-open FILE.i3d")


@app.command()
def paths() -> None:
    """Show the detected FS25 folders (useful for debugging config)."""
    info(f"app id     : {config.APPID}")
    info(f"game data  : {config.game_data_dir() or '(not found)'}")
    info(f"game install: {config.game_install_dir() or '(not found)'}")
    info(f"editor     : {config.editor_exe() or '(not found)'}")
    info(f"mods dir   : {config.mods_dir() or '(not found)'}")
    info(f"log.txt    : {config.log_path() or '(not found)'}")
    info(f"testrunner : {testrunner.installed_exe() or '(not installed)'}")


if __name__ == "__main__":
    app()
