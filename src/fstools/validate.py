"""Lightweight modDesc.xml sanity checks before packing/shipping a mod."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


def validate(mod_dir: Path) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Non-empty errors mean the mod is broken."""
    errors: list[str] = []
    warnings: list[str] = []

    desc = mod_dir / "modDesc.xml"
    if not desc.is_file():
        return (["modDesc.xml is missing"], warnings)

    try:
        root = ET.parse(desc).getroot()
    except ET.ParseError as exc:
        return ([f"modDesc.xml is not valid XML: {exc}"], warnings)

    if root.tag != "modDesc":
        errors.append(f"root element is <{root.tag}>, expected <modDesc>")

    if root.get("descVersion") is None:
        errors.append("modDesc is missing the descVersion attribute")

    if root.findtext("version", "").strip() == "":
        errors.append("<version> is missing or empty")
    if root.findtext("author", "").strip() == "":
        warnings.append("<author> is missing or empty")

    title = root.find("title")
    if title is None or len(list(title)) == 0:
        errors.append("<title> is missing or has no language entries")
    elif title.find("en") is None:
        warnings.append("<title> has no <en> entry")

    icon = root.findtext("iconFilename", "").strip()
    if icon == "":
        errors.append("<iconFilename> is missing")
    else:
        # modDesc usually names the .dds, but FS also accepts a .png (or other
        # image) with the same stem and converts it at load — accept any of them.
        icon_path = mod_dir / icon
        same_stem = list(icon_path.parent.glob(f"{icon_path.stem}.*")) \
            if icon_path.parent.is_dir() else []
        if not icon_path.is_file() and not same_stem:
            errors.append(f"iconFilename '{icon}' not found (no file named "
                          f"'{icon_path.stem}.*' either)")

    # Referenced store-item XMLs should exist.
    for item in root.findall(".//storeItems/storeItem"):
        ref = item.get("xmlFilename")
        if ref and not (mod_dir / ref).is_file():
            warnings.append(f"storeItem xmlFilename '{ref}' not found")

    return (errors, warnings)
