"""`fs` — Farming Simulator 25 modding helpers.

Subcommands:
    fs pack MOD       pack a mod folder into a .zip (optionally deploy + launch)
    fs log            follow the game log.txt (errors in red, warnings yellow)
    fs validate MOD   sanity-check a mod's modDesc.xml
    fs paths          show the detected FS25 folders
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

import typer

from . import config, logtail, pack as packmod, validate as validatemod
from .console import die, info, ok, warn

app = typer.Typer(
    help="Farming Simulator 25 modding helpers.",
    no_args_is_help=True,
    add_completion=False,
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
    keep_images: bool = typer.Option(
        False, "--keep-images", help="do NOT strip png/psd/tga/pdn/gim"),
    dry_run: bool = typer.Option(
        False, "-n", "--dry-run", help="show what would happen without writing anything"),
) -> None:
    """Pack a mod folder into a distributable .zip."""
    mod_dir = mod_folder.expanduser().resolve()
    if not mod_dir.is_dir():
        raise die(f"Mod folder not found: {mod_folder}")
    if not (mod_dir / "modDesc.xml").is_file():
        raise die(f"'{mod_dir.name}' has no modDesc.xml — packing canceled!")

    out_dir = output.expanduser().resolve() if output else mod_dir.parent
    zip_path = out_dir / f"{packmod.zip_stem(mod_dir)}.zip"

    info(f"Packing mod {typer.style(mod_dir.name, bold=True)}")
    info(f"  source : {mod_dir}")
    info(f"  output : {zip_path}")
    if keep_images:
        info("  images : included (--keep-images)")

    entries = packmod.collect_files(mod_dir, zip_path.name, keep_images)

    if dry_run:
        warn(f"dry-run: would pack {len(entries)} files:")
        for rel in entries:
            typer.echo(f"    {rel}")
    else:
        if zip_path.exists():
            warn(f"Old {zip_path.name} will be replaced")
        size = packmod.write_zip(mod_dir, zip_path, entries)
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
def paths() -> None:
    """Show the detected FS25 folders (useful for debugging config)."""
    gamedata = config.game_data_dir()
    info(f"app id     : {config.APPID}")
    info(f"game data  : {gamedata or '(not found)'}")
    info(f"mods dir   : {config.mods_dir() or '(not found)'}")
    info(f"log.txt    : {config.log_path() or '(not found)'}")


if __name__ == "__main__":
    app()
