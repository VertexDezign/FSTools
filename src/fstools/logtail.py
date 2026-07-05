"""Following the FS25 log.txt with error/warning highlighting."""
from __future__ import annotations

import os
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
    fh = log.open("r", errors="replace")
    try:
        existing = fh.readlines()
        head = existing if not follow else existing[-lines:]
        for line in head:
            _emit(line, errors_only)

        if not follow:
            return

        inode = os.fstat(fh.fileno()).st_ino
        while True:
            line = fh.readline()
            if line:
                _emit(line, errors_only)
                continue

            # EOF — check whether the game rotated (relaunch: new file) or
            # truncated (in-place) log.txt, and if so start reading it afresh.
            try:
                st = log.stat()
            except FileNotFoundError:
                time.sleep(0.4)  # brief gap while the game recreates it
                continue
            if st.st_ino != inode or st.st_size < fh.tell():
                fh.close()
                fh = log.open("r", errors="replace")
                inode = os.fstat(fh.fileno()).st_ino
                continue  # re-emit the fresh log from its start
            time.sleep(0.4)
    except KeyboardInterrupt:
        typer.echo("", err=True)
    finally:
        fh.close()
