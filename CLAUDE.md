# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single `fs` CLI (Python 3.11+, [Typer](https://typer.tiangolo.com/), packaged with
[uv](https://docs.astral.sh/uv/)) for packing, deploying, launching and debugging **Farming
Simulator 25** mods **on Linux**. FS25 and its modding tools are Windows programs that run under
Steam Proton — that single fact drives most of the design below. Runtime deps are only `typer` and
`defusedxml`; packing uses the stdlib `zipfile` on purpose (no `7z`/`zip` binary).

## Commands

```sh
uv tool install --editable .   # install `fs` on PATH; editable, so source edits apply immediately
uv tool uninstall fstools
```

The checked-in `.venv/` belongs to the maintainer's host machine (absolute host paths in its
shebangs) and will not execute in a container — but its `site-packages` is importable. To exercise
the CLI without uv, put `src/` and those packages on `PYTHONPATH` (glob the interpreter version
rather than hard-coding it; the project supports Python 3.11+):

```sh
export PYTHONPATH="src:$(echo .venv/lib/python3*/site-packages)"
python3 -m fstools.cli --help
```

There is **no test suite, linter config, or CI**. Verify changes by running the CLI against a
throwaway mod folder (any directory containing a `modDesc.xml`):

```sh
python3 -m fstools.cli pack /tmp/FS25_Demo -n
python3 -m fstools.cli validate /tmp/FS25_Demo
```

`pack`/`validate`/`patch` work anywhere (`patch` only needs the mods folder when its `source` is a
bare zip name — pack a throwaway mod to a zip and point `source` at it). `test`, `edit`, `paths` and
`log` need a real Steam + Proton FS25 install (and `protontricks`), so they can only be verified on
the user's machine.

## Architecture

Thin Typer command layer (`cli.py`) over one module per feature (`pack`, `patch`, `validate`,
`testrunner`, `editor`, `logtail`), plus two shared modules: `config.py` (paths) and `console.py`
(output).

### Path detection lives only in config.py

Every FS25 location is derived there: three candidate Steam roots are probed, and everything else
hangs off the Proton prefix `steamapps/compatdata/$FS25_APPID/pfx` (game data, `mods/`, `log.txt`,
the GIANTS Editor under `drive_c/Program Files/…`). Detectors **return `Path | None`, never raise**;
`cli.py` turns a `None` into `die("… Set FS25_XXX.")`. Each has an env override (`FS25_MODS_DIR`,
`FS25_GAME_DIR`, `FS25_LOG`, `FS25_EDITOR`, `FS25_TESTRUNNER`, `FS25_APPID`). Add new locations
here rather than inline in a command.

### Windows tooling is invoked through the Proton prefix

`fs test` and `fs edit` drive Windows executables that live inside the FS25 prefix (GIANTS
TestRunner, GIANTS Editor). The shared pattern (`testrunner.run`, `editor.launch`) is:
`protontricks-launch --appid <APPID> <exe> …` with **every path argument converted by
`config.to_wine_path()`** (`/home/x` → `Z:\home\x`) and `PROTONTRICKS_NO_TERM=1` in the environment.

Terminal gotcha, learned the hard way: Wine leaves the tty in raw mode. Detached launches must pass
`stdin=subprocess.DEVNULL` (plus `start_new_session=True`); foreground launches must be wrapped in
`editor.preserve_terminal()`, which snapshots and restores termios. Keep both when touching
subprocess code, or the user's shell breaks after running `fs edit`.

### Pack pipeline (shared by `pack` and `test`)

`packconfig.load()` → `pack.zip_stem()` → `pack.collect_files()` → `pack.write_zip()`.

- Three exclusion layers: `EXCLUDE_DIRS` (any path component), `EXCLUDE_FILES` (case-insensitive
  name globs), and the per-mod `.fsignore` (gitignore-flavoured; a pattern with `/` is anchored to
  the mod-relative path, one without matches any path component).
- The zip stores **mod-relative** paths, so `modDesc.xml` ends up at the zip root — FS requires this.
- `fstools.toml` overrides (`title`/`version`/`author`) are applied by `rewrite_moddesc()` **in
  memory** and injected with `writestr`. The `modDesc.xml` on disk is never modified — that
  invariant is the entire point of the config file. `zip_name` only changes the output filename.
- That rewrite must preserve **CDATA sections** — the TestRunner requires them in `<description>`,
  and a plain ElementTree round-trip silently escapes them away. `_CDataParser` fences each section
  with NUL sentinels while parsing and `_restore_cdata()` rebuilds `<![CDATA[…]]>` from the
  serialized bytes; keep both when touching `rewrite_moddesc()`.
- `fs pack --mod-version` feeds the same `version` override from the command line and **wins over
  `[mod] version`** — it is the CI path (version from the git tag), so the checked-in dev version
  must not override it. Used verbatim; `ET.tostring` escapes it, so no XML-safety check is needed
  here (unlike `patch`'s byte-level splice).
- `fs test` reuses the identical pipeline into a `TemporaryDirectory`, so packing changes apply to
  testing automatically; the two call sites in `cli.py` must stay in sync.

### Patch pipeline (`fs patch`)

`packconfig.load_patch()` → `patch.resolve_base()` → `patch.out_stem()` → `pack.collect_files()` →
`patch.plan()` → `patch.apply()`. Same overlay folder, `[patch]` section instead of `[mod]`; the
exclusion layers are reused wholesale, so `.fsignore` and `EXCLUDE_*` behave exactly as in `pack`.

- **The base zip is read-only.** It is the pristine copy every re-run starts from (mods get updated
  upstream), so `cli.py` refuses both an output path and a deploy target equal to it. `apply()`
  builds a `.part` file and `replace()`s it into place so a mid-write failure cannot truncate a
  good zip.
- Untouched entries are streamed across with their original `compress_type`; replacements keep the
  entry's compression too. Overlay paths are matched against zip entry names case-insensitively and
  the **zip's** spelling wins — a Windows-built zip may hold `textures/Foo.dds`, and writing the
  overlay's casing would silently add a second entry FS never reads.
- `version_suffix` is spliced into `modDesc.xml` at the **byte level** (`patch._VERSION_RE`), not
  via an XML round-trip: this is someone else's modDesc, and re-serializing would drop their
  comments. Appending is idempotent, so re-patching never stacks suffixes.
- `_deploy_and_play()` in `cli.py` is shared with `pack` — the `-d`/`-p` semantics must stay
  identical for both.

### Error and output conventions

Feature modules raise domain exceptions carrying a user-facing message (`PackConfigError`,
`PatchError`, `TestRunnerBusy`, `FileNotFoundError`); `cli.py` catches and re-emits them. `console.die()` prints
in red and **returns** a `typer.Exit`, so it is always used as `raise die(...)`. Decorated output
goes through `console.py` (`info`/`ok`/`warn`) — never bare `print`. Raw, unprefixed lines (the
`pack --dry-run` file listing, the `fs log` stream) use `typer.echo`/`typer.secho` directly, since
a `::` prefix would corrupt them. `fs test` exit codes are contractual:
`0` PASS, `1` FAIL, `2` CRASH (TestRunner aborted without a report).

### Other invariants

- `fs test` holds an `flock` on `~/.local/share/fstools/.lock` for the whole run: the TestRunner
  writes its results next to its own exe, so concurrent runs would corrupt each other. Stale results
  are cleared and new ones moved to the output dir while the lock is held.
- `logtail.tail` detects log rotation by **inode** and truncation by size, because FS recreates
  `log.txt` on every launch and the tail must survive a game restart.
- `pack.py` parses `modDesc.xml` with `defusedxml` (stdlib `ElementTree` is used only for building
  and serializing); `validate.py` still parses with stdlib ET. Prefer defusedxml for new parsing.

## Style

- `from __future__ import annotations` and `X | None` unions everywhere; annotate public functions.
- Module and function docstrings explain **why** (Proton, Wine, FS quirks), not what. Preserve that
  reasoning when editing — several comments encode bugs that were already fixed once.
- Commit subjects use an emoji prefix: ✨ feature, 🚑 fix, 🔨 refactor/rework, 📖 docs.
- `README.md` is the user-facing manual and is kept in sync with behaviour changes (flags, exclusion
  rules, `fstools.toml` keys, env vars).
