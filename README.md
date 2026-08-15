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

### Shell completion

`fs` can complete subcommands, options, and file arguments. Install it once for
your shell, then restart the shell (or `source` your rc file):

```sh
fs --install-completion          # detects your shell (bash/zsh/fish/PowerShell)
```

This appends a small snippet to your shell config (e.g. `~/.bashrc`,
`~/.zshrc`, `~/.config/fish/completions/`). Prefer to wire it up yourself?
`fs --show-completion` prints the script to stdout instead of installing it.

## Commands

```sh
cd MyMod && fs pack        # pack the current folder -> ./FS25_MyMod.zip
fs pack -o build           # -> build/FS25_MyMod.zip
fs pack -d                 # also copy into the FS25 mods folder
fs pack -p                 # deploy, then launch FS25 via Steam
fs pack -n                 # dry run — list files, write nothing
fs pack ../OtherMod        # a path still works if you'd rather not cd

fs patch                   # swap files into an existing mod zip (needs fstools.toml)
fs patch -d                # …and copy the patched zip into the mods folder
fs patch -n                # dry run — show what would be replaced

fs validate                # check the current folder's modDesc.xml

fs test                    # run the GIANTS ModHub TestRunner (opens the HTML report)
fs test ../SomeMod.zip     # test an existing zip instead of packing
fs testrunner              # show installed TestRunner + whether a newer one exists
fs testrunner --update     # install the newest TestRunner*.zip found
fs testrunner -s FILE.zip  # install a specific TestRunner archive/exe

fs edit scene.i3d          # open an .i3d in the GIANTS Editor
fs register-editor         # make .i3d files open with the editor from any file manager
fs register-editor --remove  # undo that association

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
(`LiquidManureTransfer` → `FS25_LiquidManureTransfer.zip`), and is written inside
the mod folder by default (the `.zip` is excluded from its own packing). It packs
the folder's *contents* so `modDesc.xml`
lands at the zip root (what FS requires), using the stdlib `zipfile` — no
`7z`/`zip` binary needed. It refuses to pack a folder without a `modDesc.xml`.

Excluded by default: source/DCC files (`*.blend *.obj *.fbx *.mel *.mb *.ma`),
image-editor sources (`*.psd *.pdn *.ora *.xcf *.kra`), scripts
(`*.cmd *.sh *.py`), docs (`*.txt *.md`), VCS/IDE dirs
(`.git .svn .idea .vscode …`), and `$data` / `substance` folders.

> Rendered images (`.png`, `.dds`, `.tga`, …) are **kept** — a mod's textures and
> icon ship as-is; only the layered editor sources above are dropped. If your
> repo holds image (or other) files that aren't part of the mod, list them in a
> `.fsignore` (see below). Run `fs test` before publishing: the GIANTS TestRunner
> flags a `.png` used where a `.dds` is expected, so you don't need the packer to
> guess.

### Ignoring files (`.fsignore`)

Drop a `.fsignore` in the mod folder to keep repo-only files out of the zip. It's
gitignore-flavoured — one glob per line, `#` comments and blank lines ignored:

```gitignore
# working files that live in the repo but aren't part of the mod
*.blend1
*.afphoto
textures/_wip/          # a whole subfolder
docs/preview.png        # a specific file
```

A pattern **without** a `/` matches that name at any depth (`*.blend1`, `_wip/`); a
pattern **with** a `/` is anchored to the mod-relative path (`textures/_wip/`).
`*` spans path separators. The `.fsignore` itself is never packed.

### Per-mod config (`fstools.toml`)

Drop an optional `fstools.toml` next to `modDesc.xml` to drive the packed mod's
name and metadata **without editing `modDesc.xml` or renaming the folder**:

```toml
[mod]
zip_name = "FS25_MyMod_dev"   # packed .zip stem (FS25_ prefix added if missing)
version  = "1.0.0.0-dev"      # overrides <version>
author   = "Me"               # overrides <author>
title    = "My Mod (dev)"     # overrides every <title> language entry

# …or set titles per language instead of one string:
# [mod.title]
# en = "My Mod (dev)"
# de = "Mein Mod (dev)"
```

Every key is optional. `zip_name` changes only the output filename; `version`,
`author`, and `title` are rewritten **inside the packed zip's `modDesc.xml`** —
the file on disk is untouched, and `fstools.toml` itself is never packed. A
string `title` sets every existing `<title>` language entry; a `[mod.title]`
table sets (or creates) each language you list.

This lets a **dev build coexist with your stable mod in the same savegame**: give
it a different `zip_name` (FS keys mods by zip filename) and a `title` so you can
tell them apart in the mod list. Delete or `.gitignore` the file to go back to a
normal build. `fs test` honours the same config.

The same file also carries the `[patch]` section that drives `fs patch` (below);
the two sections are independent — a folder is either a mod source tree or a
patch overlay.

### Patching someone else's mod (`fs patch`)

`fs pack` builds *your* mod from source. `fs patch` is for the other case: a mod
you downloaded — usually from ModHub — where you want to swap out a texture, an
xml or two, without unpacking and repacking the whole thing.

Make a folder that mirrors the mod's **internal** layout and drop an
`fstools.toml` in it:

```
MyMod-patch/
  fstools.toml
  textures/mainTexture.dds     # replaces textures/mainTexture.dds in the zip
  xml/vehicle.xml              # replaces xml/vehicle.xml in the zip
```

```toml
[patch]
source         = "~/Downloads/FS25_SomeMod.zip"  # the zip to patch (required)
zip_name       = "FS25_SomeMod"                  # output stem (default: the base's name)
version_suffix = "-bl"                           # appended to the base's <version>
```

Then `fs patch` writes a patched `FS25_SomeMod.zip` into the patch folder, and
`fs patch -d` copies it into the mods folder (`-p` also launches the game, `-n`
is a dry run, `-o DIR` writes elsewhere) — the same flags `fs pack` uses.

- **The base zip is never modified.** Every entry it holds is copied across
  verbatim except the ones you replace, so re-running after the mod updates
  upstream starts from a clean copy every time.
- `source` may be a path (relative ones resolve against the patch folder), or a
  bare zip name — then it's looked up in the FS25 mods folder. `.zip` is optional.
- A file that isn't in the base zip is **added**, with a warning — usually that
  means a typo in your layout, occasionally it's what you wanted.
- Case is matched leniently: `textures/foo.dds` still patches the zip's
  `textures/Foo.dds` (it keeps the zip's spelling, so FS keeps finding it) and
  says so.
- The same exclusions as `fs pack` apply, so a `.psd` sitting next to your `.dds`
  or a `README.md` in the patch folder won't end up in the zip. `.fsignore` works
  here too.

`version_suffix` is the point of the exercise for ModHub mods: it appends to
whatever `<version>` the base zip declares (`1.2.0.0` → `1.2.0.0-bl`), so in the
in-game mod list and the ModHub update prompt you can see at a glance that the
installed copy is *yours* — and needs re-patching once the update lands. It's
applied by splicing the version into `modDesc.xml`, leaving the rest of the
upstream file byte-for-byte intact, and appending twice is a no-op, so patching
an already-patched zip won't give you `1.2.0.0-bl-bl`.

> Keep `source` pointing at a pristine copy **outside** the mods folder (your
> Downloads folder is fine). `fs patch` refuses to deploy on top of its own base
> zip, since that would destroy the copy the next run needs.

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

### Opening i3d files (`fs edit` / `fs register-editor`)

`fs edit scene.i3d` opens an `.i3d` scene in the GIANTS Editor. Like `fs test`,
the editor is a Windows program living inside the FS25 Proton prefix, so it's
launched via `protontricks-launch` with the file mapped to its `Z:\` prefix
path — no manual "add non-Steam game" dance. The editor is auto-detected under
`.../drive_c/Program Files/` (e.g. `GIANTS Software/GIANTS_Editor_10.0.11/editor.exe`,
newest version wins); set `FS25_EDITOR` if yours lives elsewhere. Pass `-v` to
run it in the foreground and see the editor's console (its "could not load
file …" warnings are handy for spotting missing or mis-cased references).

`fs register-editor` wires `.i3d` into your desktop so you can **double-click an
`.i3d` in any file manager** (or run `xdg-open scene.i3d`) and it opens in the
editor. It installs a freedesktop desktop entry (`~/.local/share/applications/`)
and a `application/x-i3d` MIME type for `*.i3d` (`~/.local/share/mime/`), then
makes it the default handler. `fs register-editor --remove` undoes both. Run it
once; it points at the `fs` on your PATH, so editable source changes keep working.

Requirements: `protontricks` (`protontricks-launch` on PATH) and the GIANTS
Editor installed in the FS25 prefix — the same setup `fs test` needs.

## Configuration

Paths auto-detect for Steam app `2300320`. Override via env vars:

| Variable         | Meaning                                      |
|------------------|----------------------------------------------|
| `FS25_MODS_DIR`  | mods folder (else auto-detected)             |
| `FS25_GAME_DIR`  | game install dir (else auto-detected)        |
| `FS25_APPID`     | Steam app id (default `2300320`)             |
| `FS25_LOG`       | path to `log.txt` (else auto-detected)       |
| `FS25_TESTRUNNER`| path to `TestRunner_public.exe`              |
| `FS25_EDITOR`    | path to the GIANTS Editor `editor.exe`       |

## Project layout

```
pyproject.toml            # deps + `fs` entry point (fstools.cli:app)
src/fstools/
  cli.py                  # Typer app — subcommand wiring
  config.py               # shared Steam/Proton path detection
  pack.py                 # zip packing + exclusion rules
  packconfig.py           # per-mod fstools.toml ([mod] and [patch] sections)
  patch.py                # swap single files into an existing mod zip
  validate.py             # modDesc.xml checks
  testrunner.py           # GIANTS ModHub TestRunner runner (via Proton)
  editor.py               # open .i3d in the GIANTS Editor + .i3d file association
  logtail.py              # log.txt follower
  console.py              # coloured output helpers
```
