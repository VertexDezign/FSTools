"""Swapping single files into an existing mod zip (stdlib zipfile, no 7z).

The use case is a *foreign* mod — a ModHub download whose textures or xml you
want to tweak locally. Unpacking, editing and repacking it loses the upstream
zip's structure and is easy to get wrong, so instead this keeps a small overlay
folder that mirrors the mod's internal layout, and rewrites the base zip entry
by entry: every untouched entry is copied across verbatim.

The base zip is never modified — it stays the pristine copy the next patch run
starts from, so re-running after upstream updates the mod is always clean.
"""
from __future__ import annotations

import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from . import pack

MODDESC = "modDesc.xml"

# Byte-level splice of <version>…</version>. Deliberately not an XML round-trip:
# this rewrites someone else's modDesc, and re-serializing it would drop their
# comments and reorder attributes for no gain.
_VERSION_RE = re.compile(rb"<version\s*>(.*?)</version\s*>", re.DOTALL)


class PatchError(Exception):
    """Raised when the base zip or the patch overlay cannot be used."""


@dataclass
class Plan:
    """What a patch run will do, resolved against the base zip's entry names."""

    base: Path
    replaced: dict[str, Path] = field(default_factory=dict)  # zip entry -> file on disk
    added: dict[str, Path] = field(default_factory=dict)     # not in the base zip
    recased: dict[str, str] = field(default_factory=dict)    # overlay path -> zip entry

    @property
    def empty(self) -> bool:
        return not self.replaced and not self.added


@dataclass
class PatchResult:
    size: int
    replaced: int
    added: int


def resolve_base(source: str, patch_dir: Path, mods: Path | None) -> Path:
    """Locate the pristine base zip named by ``[patch].source``.

    A bare name is looked up in the FS25 mods folder (where a ModHub mod already
    sits); anything with a separator is a path, relative ones to the patch folder.
    """
    spec = source if source.lower().endswith(".zip") else f"{source}.zip"
    raw = Path(spec).expanduser()
    if len(raw.parts) > 1:
        base = raw if raw.is_absolute() else patch_dir / raw
        base = base.resolve()
    elif mods is None:
        raise PatchError(
            f"'source = \"{source}\"' is a bare zip name, but the FS25 mods folder "
            "was not found. Set FS25_MODS_DIR, or give a path instead.")
    else:
        base = mods / raw.name
    if not base.is_file():
        raise PatchError(f"Base zip not found: {base}")
    if not zipfile.is_zipfile(base):
        raise PatchError(f"Not a zip file: {base}")
    return base


def out_stem(base: Path, override: str | None) -> str:
    """The output zip stem: ``zip_name`` if configured, else the base zip's.

    Defaulting to the base's name is what makes the patched zip *replace* the
    original in the mods folder — FS keys mods by zip filename, so a different
    name would install a second, competing copy of the mod.
    """
    return pack.zip_stem(base.with_suffix(""), override)


def plan(base: Path, patch_dir: Path, entries: list[Path]) -> Plan:
    """Match the overlay's files against the base zip's entry names.

    Falls back to a case-insensitive match (recording it in ``recased``): the zip
    comes from a Windows toolchain, so 'textures/Foo.dds' vs 'textures/foo.dds'
    is a live risk — writing the overlay's spelling would leave a duplicate entry
    that FS never reads.
    """
    with zipfile.ZipFile(base) as zf:
        names = [i.filename for i in zf.infolist() if not i.is_dir()]
    exact = set(names)
    folded: dict[str, str] = {}
    for name in names:
        folded.setdefault(name.lower(), name)

    result = Plan(base=base)
    for rel in entries:
        posix = rel.as_posix()
        disk = patch_dir / rel
        if posix in exact:
            result.replaced[posix] = disk
        elif posix.lower() in folded:
            actual = folded[posix.lower()]
            result.replaced[actual] = disk
            result.recased[posix] = actual
        else:
            result.added[posix] = disk
    return result


def read_moddesc(plan: Plan) -> tuple[str, bytes]:
    """The modDesc.xml that will end up in the output zip (an overlay copy wins)."""
    for arc, disk in (*plan.replaced.items(), *plan.added.items()):
        if arc.lower() == MODDESC.lower():
            return arc, disk.read_bytes()
    with zipfile.ZipFile(plan.base) as zf:
        for item in zf.infolist():
            if item.filename.lower() == MODDESC.lower():
                return item.filename, zf.read(item)
    raise PatchError(f"{plan.base.name} has no {MODDESC}")


def bump_version(data: bytes, suffix: str) -> tuple[bytes, str, str]:
    """modDesc.xml bytes with ``suffix`` appended to <version>; (bytes, old, new).

    Marking the version is what makes a local patch visible in-game: FS shows the
    installed version next to ModHub's, so '1.2.0.0-bl' says at a glance that this
    copy is yours and the patch has to be re-applied after an update. Appending is
    idempotent, so patching an already-patched zip does not stack suffixes.
    """
    m = _VERSION_RE.search(data)
    if m is None:
        raise PatchError(f"{MODDESC} has no <version> element — cannot apply version_suffix")
    old = m.group(1).decode("utf-8", "replace").strip()
    if old.endswith(suffix):
        return data, old, old
    new = f"{old}{suffix}"
    return data[:m.start(1)] + new.encode("utf-8") + data[m.end(1):], old, new


def version_change(plan: Plan, suffix: str) -> tuple[str, str]:
    """(old, new) <version> the patch would write — for dry runs and log lines."""
    _, data = read_moddesc(plan)
    _, old, new = bump_version(data, suffix)
    return old, new


def _write_from_disk(dst: zipfile.ZipFile, disk: Path, arcname: str,
                     compress_type: int) -> None:
    """Stream a replacement file in, keeping the entry's original compression."""
    zi = zipfile.ZipInfo.from_file(disk, arcname)
    zi.compress_type = compress_type
    with disk.open("rb") as src, dst.open(zi, "w") as out:
        shutil.copyfileobj(src, out)


def apply(out_zip: Path, plan: Plan, *, version_suffix: str | None = None) -> PatchResult:
    """Write the patched zip. Entries not in the plan are copied over verbatim."""
    overrides: dict[str, bytes] = {}
    if version_suffix:
        arc, data = read_moddesc(plan)
        overrides[arc], _, _ = bump_version(data, version_suffix)

    out_zip.parent.mkdir(parents=True, exist_ok=True)
    # Build beside the target and move into place, so a failure halfway through
    # cannot leave a truncated zip where a working one used to be.
    tmp = out_zip.with_name(f"{out_zip.name}.part")
    replaced = added = 0
    try:
        with zipfile.ZipFile(plan.base) as src, \
                zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as dst:
            for item in src.infolist():
                if item.is_dir():
                    dst.writestr(item, b"")
                    continue
                override = overrides.pop(item.filename, None)
                disk = plan.replaced.get(item.filename)
                if disk is not None:
                    replaced += 1
                if override is not None:
                    dst.writestr(item, override)
                elif disk is not None:
                    _write_from_disk(dst, disk, item.filename, item.compress_type)
                else:
                    with src.open(item) as fsrc, dst.open(item, "w") as fdst:
                        shutil.copyfileobj(fsrc, fdst)
            for arc, disk in plan.added.items():
                override = overrides.pop(arc, None)
                if override is not None:
                    dst.writestr(arc, override)
                else:
                    dst.write(disk, arcname=arc)
                added += 1
        tmp.replace(out_zip)
    finally:
        tmp.unlink(missing_ok=True)
    return PatchResult(size=out_zip.stat().st_size, replaced=replaced, added=added)
