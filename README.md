# fsTools — Farming Simulator 25 modding helpers (Linux)

A single `fs` command (Python + [Typer](https://typer.tiangolo.com/), packaged
with [uv](https://docs.astral.sh/uv/)) for packing, deploying, launching, and
debugging FS25 mods on Linux.

## Install

```sh
uv tool install --editable .
```

This puts an `fs` executable on your PATH (`~/.local/bin`). `--editable` links
it to the source, so edits under `src/fstools/` take effect immediately with no
reinstall. If `fs` isn't found afterwards, run `uv tool update-shell` once and
restart your shell.

Upgrade after pulling changes: nothing to do (editable). To uninstall:
`uv tool uninstall fstools`.

## Commands

```sh
cd MyMod && fs pack        # pack the current folder -> ../FS25_MyMod.zip
fs pack -o build           # -> build/FS25_MyMod.zip
fs pack -d                 # also copy into the FS25 mods folder
fs pack -p                 # deploy, then launch FS25 via Steam
fs pack --keep-images      # keep ALL png/psd/tga (icon is kept regardless)
fs pack -n                 # dry run — list files, write nothing
fs pack ../OtherMod        # a path still works if you'd rather not cd

fs validate                # check the current folder's modDesc.xml

fs test                    # run the GIANTS ModHub TestRunner (opens the HTML report)
fs test ../SomeMod.zip     # test an existing zip instead of packing
fs testrunner              # show installed TestRunner + whether a newer one exists
fs testrunner --update     # install the newest TestRunner*.zip found
fs testrunner -s FILE.zip  # install a specific TestRunner archive/exe

fs log                     # follow log.txt live (errors red, warnings yellow)
fs log -e                  # only Error/Warning lines
fs log -n 50               # last 50 lines, then follow
fs log --no-follow -e      # dump errors so far and exit

fs paths                   # show the detected FS25 folders
fs --help                  # full help (works on any subcommand too)
```

### Packing details

`fs pack` defaults to the **current folder** as the mod. The zip is named after
that folder, adding the required `FS25_` prefix if missing
(`LiquidManureTransfer` → `FS25_LiquidManureTransfer.zip`), and is written to the
folder's parent by default. It packs the folder's *contents* so `modDesc.xml`
lands at the zip root (what FS requires), using the stdlib `zipfile` — no
`7z`/`zip` binary needed. It refuses to pack a folder without a `modDesc.xml`.

Excluded by default: source/DCC files (`*.blend *.obj *.fbx *.mel *.mb *.ma`),
scripts (`*.cmd *.sh *.py`), docs (`*.txt *.md`), VCS/IDE dirs
(`.git .svn .idea .vscode …`), `$data` / `substance` folders, and image sources
(`*.png *.psd *.tga *.pdn *.gim`).

> Images are stripped by default (matching the original packer) — **except the
> mod's icon**: the file named in `<iconFilename>` is always kept, even when it
> ships as a `.png` that `modDesc` references as `.dds` (FS converts it at load).
> Use `--keep-images` if a mod ships *other* textures as `.png` rather than `.dds`.

### ModHub TestRunner (`fs test`)

Runs GIANTS' official [TestRunner](https://gdn.giants-software.com/) — the same
checks ModHub QA uses — against your mod on Linux. It packs the folder to a clean
zip (or takes a `.zip`), then runs the Windows TestRunner **inside the FS25 Proton
prefix** via `protontricks-launch`, so it finds the game and the GIANTS Editor
automatically. The HTML/XML report and `TestRunner.log` are written next to your
mod. Exit code: `0` PASS, `1` FAIL (report written), `2` the TestRunner crashed.

Requirements:
- `protontricks` installed (`protontricks-launch` on PATH).
- GIANTS Editor ≥10.0.3 installed **in the FS25 prefix** (install it once through
  the prefix so it registers in `giantsPackageRegistry`).
- The TestRunner itself (not redistributed here): download it from the GIANTS
  Developer Network. On first `fs test` it is installed automatically from a
  `TestRunner*.zip` found in the current directory or `~/Downloads`; or set
  `FS25_TESTRUNNER` to the exe. Installed copy lives in `~/.local/share/fstools/`.

**Updating the TestRunner:** drop the new `TestRunner_public_X.zip` in the current
directory or `~/Downloads` and run `fs testrunner --update` (picks the highest version found),
or `fs testrunner -s /path/to.zip` for a specific file. `fs testrunner` with no
args shows the installed version and warns if a newer archive is available.

> The TestRunner drives the GIANTS Editor GUI mid-run and can take several minutes
> (longer for maps). A window may flash open — that's expected. Because it writes
> results into one shared dir, only one `fs test` may run at a time — a second run
> refuses to start (lock) rather than corrupt results.

## Configuration

Paths auto-detect for Steam app `2300320`. Override via env vars:

| Variable         | Meaning                                      |
|------------------|----------------------------------------------|
| `FS25_MODS_DIR`  | mods folder (else auto-detected)             |
| `FS25_GAME_DIR`  | game install dir (else auto-detected)        |
| `FS25_APPID`     | Steam app id (default `2300320`)             |
| `FS25_LOG`       | path to `log.txt` (else auto-detected)       |
| `FS25_TESTRUNNER`| path to `TestRunner_public.exe`              |

## Project layout

```
pyproject.toml            # deps + `fs` entry point (fstools.cli:app)
src/fstools/
  cli.py                  # Typer app — subcommand wiring
  config.py               # shared Steam/Proton path detection
  pack.py                 # zip packing + exclusion rules
  validate.py             # modDesc.xml checks
  testrunner.py           # GIANTS ModHub TestRunner runner (via Proton)
  logtail.py              # log.txt follower
  console.py              # coloured output helpers
```
