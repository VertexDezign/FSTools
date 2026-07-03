"""Following the FS25 log.txt with error/warning highlighting."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import typer


def _is_interesting(line: str) -> bool:
    low = line.lower()
    return "error" in low or "warning" in low


def _emit(line: str, errors_only: bool) -> None:
    if errors_only and not _is_interesting(line):
        return
    low = line.lower()
    text = line.rstrip("\n")
    if "error" in low:
        typer.secho(text, fg=typer.colors.RED)
    elif "warning" in low:
        typer.secho(text, fg=typer.colors.YELLOW)
    else:
        typer.echo(text)


def tail(log: Path, errors_only: bool, lines: int, follow: bool) -> None:
    with log.open("r", errors="replace") as fh:
        existing = fh.readlines()
        head = existing if not follow else existing[-lines:]
        for line in head:
            _emit(line, errors_only)

        if not follow:
            return

        try:
            while True:
                where = fh.tell()
                line = fh.readline()
                if line:
                    _emit(line, errors_only)
                    continue
                if log.stat().st_size < where:  # truncated on relaunch
                    fh.seek(0)
                else:
                    time.sleep(0.4)
        except KeyboardInterrupt:
            typer.echo("", err=True)
