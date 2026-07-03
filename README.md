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

## Configuration

Paths auto-detect for Steam app `2300320`. Override via env vars:

| Variable        | Meaning                                |
|-----------------|----------------------------------------|
| `FS25_MODS_DIR` | mods folder (else auto-detected)       |
| `FS25_APPID`    | Steam app id (default `2300320`)       |
| `FS25_LOG`      | path to `log.txt` (else auto-detected) |

## Project layout

```
pyproject.toml            # deps + `fs` entry point (fstools.cli:app)
src/fstools/
  cli.py                  # Typer app — subcommand wiring
  config.py               # shared Steam/Proton path detection
  pack.py                 # zip packing + exclusion rules
  logtail.py              # log.txt follower
  validate.py             # modDesc.xml checks
  console.py              # coloured output helpers
```
