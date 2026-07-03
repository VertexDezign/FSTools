"""Tiny coloured-output helpers shared by all subcommands."""
from __future__ import annotations

import typer


def info(msg: str) -> None:
    typer.secho(":: ", fg=typer.colors.BLUE, nl=False)
    typer.echo(msg)


def ok(msg: str) -> None:
    typer.secho("✓ ", fg=typer.colors.GREEN, nl=False)
    typer.echo(msg)


def warn(msg: str) -> None:
    typer.secho(f"! {msg}", fg=typer.colors.YELLOW, err=True)


def die(msg: str) -> "typer.Exit":
    """Print an error and raise. Call as `raise die(...)`."""
    typer.secho(f"✗ {msg}", fg=typer.colors.RED, err=True)
    return typer.Exit(code=1)
