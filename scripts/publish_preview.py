#!/usr/bin/env python3
"""Point the reusable preview download at the newest published versioned ZIP."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

REPO = "patrickshao/Decky-Framegen"
CHANNEL = "latest-preview"
ALIAS = "Decky-Framegen-latest.zip"
UPDATE_URL = f"https://github.com/{REPO}/releases/download/{CHANNEL}/{ALIAS}"


def gh(*arguments):
    return subprocess.run(["gh", *arguments], check=True, capture_output=True, text=True).stdout.strip()


def newest_release(releases):
    versions = []
    for release in releases:
        match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", release["tagName"])
        if match and not release["isDraft"]:
            versions.append((tuple(map(int, match.groups())), release["tagName"]))
    if not versions:
        raise ValueError("No published versioned release found")
    return max(versions)[1]


def prepare_alias(archive, tag):
    """Verify the downloaded release before making any channel changes."""
    checksum = archive.with_suffix(".zip.sha256").read_text().split()
    if len(checksum) != 2 or checksum[1] != archive.name:
        raise ValueError("Invalid release checksum file")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if checksum[0] != digest:
        raise ValueError("Release ZIP hash mismatch")
    with zipfile.ZipFile(archive) as package:
        plugin = json.loads(package.read("Decky-Framegen/plugin.json"))
        manifest = json.loads(package.read("Decky-Framegen/package.json"))
        if plugin.get("name") != "Decky-Framegen" or manifest.get("version") != tag.removeprefix("v"):
            raise ValueError("Release ZIP identity/version mismatch")
    alias = archive.with_name(ALIAS)
    shutil.copyfile(archive, alias)
    alias_checksum = alias.with_suffix(".zip.sha256")
    alias_checksum.write_text(f"{digest}  {ALIAS}\n")
    return alias, alias_checksum


def main():
    releases = json.loads(gh("release", "list", "--repo", REPO, "--limit", "100", "--json", "tagName,isDraft"))
    tag = newest_release(releases)
    filename = f"Decky-Framegen-{tag.removeprefix('v')}.zip"
    commit = gh("api", f"repos/{REPO}/commits/{tag}", "--jq", ".sha")
    print(f"Publishing preview download from {tag} ({commit})", flush=True)
    with tempfile.TemporaryDirectory(prefix="framegen-preview-") as temporary:
        stage = Path(temporary)
        gh("release", "download", tag, "--repo", REPO, "--dir", temporary,
           "--pattern", filename, "--pattern", filename + ".sha256")
        alias, checksum = prepare_alias(stage / filename, tag)
        notes = stage / "notes.md"
        notes.write_text(
            f"Reusable download for the newest published Decky Framegen preview.\n\n"
            f"Current version: [{tag}](https://github.com/{REPO}/releases/tag/{tag})\n\n"
            f"Paste this URL into Decky's **Install Plugin from URL**:\n\n```text\n{UPDATE_URL}\n```\n\n"
            "Versioned releases retain their original files. This preview link updates when a new version is published.\n"
        )
        if any(release["tagName"] == CHANNEL for release in releases):
            gh("release", "upload", CHANNEL, str(alias), str(checksum), "--repo", REPO, "--clobber")
            gh("api", "--method", "PATCH", f"repos/{REPO}/git/refs/tags/{CHANNEL}", "-f", f"sha={commit}", "-F", "force=true")
            gh("release", "edit", CHANNEL, "--repo", REPO, "--title", "Latest FSR 4 Lite preview",
               "--prerelease", "--draft=false", "--notes-file", str(notes))
        else:
            gh("release", "create", CHANNEL, str(alias), str(checksum), "--repo", REPO, "--target", commit,
               "--title", "Latest FSR 4 Lite preview", "--prerelease", "--notes-file", str(notes))
    print(UPDATE_URL)


if __name__ == "__main__":
    main()
