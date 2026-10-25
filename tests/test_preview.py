import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("publish_preview", ROOT / "scripts/publish_preview.py")
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)


class PreviewTests(unittest.TestCase):
    def test_selects_newest_numeric_version_including_prerelease_channel(self):
        # Version tags use x.y.z even when GitHub marks the release as a preview.
        releases = [{"tagName": tag, "isDraft": draft} for tag, draft in (
            ("v0.18.9", False), ("latest-preview", False), ("v0.18.10", False),
            ("v0.19.0", True), ("nightly", False))]
        self.assertEqual(preview.newest_release(releases), "v0.18.10")
        with self.assertRaisesRegex(ValueError, "No published"):
            preview.newest_release([{"tagName": "latest-preview", "isDraft": False}])

    def make_archive(self, folder, version="0.18.2"):
        archive = folder / "Decky-Framegen-0.18.2.zip"
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr("Decky-Framegen/plugin.json", json.dumps({"name": "Decky-Framegen"}))
            package.writestr("Decky-Framegen/package.json", json.dumps({"version": version}))
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        archive.with_suffix(".zip.sha256").write_text(f"{checksum}  {archive.name}\n")
        return archive

    def test_alias_is_byte_identical_and_has_matching_checksum(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = self.make_archive(Path(temporary))
            alias, checksum = preview.prepare_alias(archive, "v0.18.2")
            self.assertEqual(alias.read_bytes(), archive.read_bytes())
            self.assertEqual(checksum.read_text(), f"{hashlib.sha256(alias.read_bytes()).hexdigest()}  {preview.ALIAS}\n")

    def test_tampered_or_wrong_version_zip_is_not_promoted(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            archive = self.make_archive(folder)
            archive.write_bytes(archive.read_bytes() + b"tampered")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                preview.prepare_alias(archive, "v0.18.2")
            self.assertFalse((folder / preview.ALIAS).exists())
            archive = self.make_archive(folder, version="0.18.1")
            with self.assertRaisesRegex(ValueError, "version mismatch"):
                preview.prepare_alias(archive, "v0.18.2")
            self.assertFalse((folder / preview.ALIAS).exists())


if __name__ == "__main__":
    unittest.main()
