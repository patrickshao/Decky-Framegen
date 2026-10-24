#!/usr/bin/env python3
"""Package locally built UI and verified upstream binaries into a Decky ZIP."""

import hashlib
import json
from pathlib import Path
import zipfile

from fetch_assets import ROOT, verify


def package():
    assets = json.loads((ROOT / "defaults/assets/runtime-assets.json").read_text())
    names = [assets[key]["name"] for key in ("optiscaler", "optipatcher")]
    for key in ("optiscaler", "optipatcher"):
        verify(ROOT / "bin" / assets[key]["name"], assets[key]["sha256"])
    for name, entry in assets["amd_driver"]["files"].items():
        verify(ROOT / "bin" / name, entry["sha256"])
        names.append(name)
    if not (ROOT / "dist/index.js").is_file():
        raise RuntimeError("Run pnpm build first")
    version = json.loads((ROOT / "package.json").read_text())["version"]
    plugin_name = json.loads((ROOT / "plugin.json").read_text())["name"]
    destination = ROOT / "out" / f"Decky-Framegen-{version}.zip"
    destination.parent.mkdir(exist_ok=True)
    files = [(ROOT / name, name) for name in ("main.py", "plugin.json", "package.json", "LICENSE", "README.md")]
    files.extend((ROOT / "bin" / name, "bin/" + name) for name in names)
    for folder, target in (("dist", "dist"), ("defaults", "")):
        for path in sorted((ROOT / folder).rglob("*")):
            if path.is_file() and path.suffix not in (".map", ".pyc") and "__pycache__" not in path.parts:
                files.append((path, str(Path(target) / path.relative_to(ROOT / folder))))
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, name in sorted(files, key=lambda item: item[1]):
            info = zipfile.ZipInfo(plugin_name + "/" + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if path.suffix == ".sh" else 0o644) << 16
            archive.writestr(info, path.read_bytes())
    checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(".zip.sha256").write_text(f"{checksum}  {destination.name}\n")
    print(destination)
    print(f"SHA-256: {checksum}")
    return destination


if __name__ == "__main__":
    package()
