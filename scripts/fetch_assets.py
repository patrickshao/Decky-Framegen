#!/usr/bin/env python3
"""Fetch pinned upstream assets over verified HTTPS. Never run the AMD EXE."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "defaults/assets/runtime-assets.json"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(path, expected):
    if sha256(path) != expected:
        raise ValueError(f"SHA-256 mismatch: {path.name}")


def download(asset, destination):
    request = urllib.request.Request(asset["url"], headers={"User-Agent": "Decky-Framegen-builder/0.18", "Referer": "https://www.amd.com/"})
    if not asset["url"].startswith("https://"):
        raise ValueError("Only HTTPS sources are allowed")
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            with urllib.request.urlopen(request, timeout=300, context=ssl.create_default_context()) as response:
                if not response.url.startswith("https://"):
                    raise ValueError("Insecure download redirect")
                shutil.copyfileobj(response, handle)
            handle.close()
            verify(temporary, asset["sha256"])
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)


def fetch(amd_package=None):
    manifest = json.loads(MANIFEST.read_text())
    binary_dir = ROOT / "bin"
    binary_dir.mkdir(exist_ok=True)
    for key in ("optiscaler", "optipatcher"):
        asset = manifest[key]
        destination = binary_dir / asset["name"]
        if not destination.is_file() or sha256(destination) != asset["sha256"]:
            print(f"Downloading {asset['name']}", flush=True)
            download(asset, destination)
        verify(destination, asset["sha256"])

    driver = manifest["amd_driver"]
    if all((binary_dir / name).is_file() and sha256(binary_dir / name) == entry["sha256"]
           for name, entry in driver["files"].items()):
        print("All pinned runtime assets verified.")
        return
    if not shutil.which("bsdtar"):
        raise RuntimeError("bsdtar (libarchive) is required to extract the AMD package")
    with tempfile.TemporaryDirectory(prefix="framegen-amd-") as temporary:
        work = Path(temporary)
        package = Path(amd_package) if amd_package else work / driver["name"]
        if not amd_package:
            print("Downloading AMD driver package for DLL extraction only", flush=True)
            download(driver, package)
        verify(package, driver["sha256"])
        archive = work / "driver.7z"
        with package.open("rb") as source, archive.open("wb") as output:
            source.seek(driver["archive_offset"])
            if source.read(6) != b"7z\xbc\xaf\x27\x1c":
                raise ValueError("AMD package archive signature mismatch")
            source.seek(driver["archive_offset"])
            shutil.copyfileobj(source, output)
        # Extract named members into temporary files, never arbitrary archive paths.
        for name, entry in driver["files"].items():
            destination = work / name
            with destination.open("wb") as output:
                subprocess.run(["bsdtar", "-xOf", str(archive), entry["member"]],
                               stdout=output, check=True, timeout=600)
            verify(destination, entry["sha256"])
            shutil.copy2(destination, binary_dir / name)
    print("All pinned runtime assets verified.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--amd-package", type=Path, help="Reuse the exact pinned AMD installer downloaded from AMD")
    fetch(parser.parse_args().amd_package)
