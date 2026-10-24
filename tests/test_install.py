import configparser
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("patch_game", ROOT / "defaults/assets/patch-game.py")
game = importlib.util.module_from_spec(spec)
spec.loader.exec_module(game)
ASSETS = json.loads((ROOT / "defaults/assets/runtime-assets.json").read_text())


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.bundle = self.home / "fgmod"
        self.target = self.home / "Game with spaces"
        self.target.mkdir()
        self.bundle.mkdir()
        self.payload = {
            "OptiScaler.dll": b"official injector",
            "OptiScaler.ini": b"[Upscalers]\nDx12Upscaler=auto\n[FSR]\nFsr4Model=auto\n[FrameGen]\nEnabled=false\n",
            "OptiScaler/amdvkffx64.dll": b"AMD Vulkan provider",
            "OptiScaler/amdxcffx64.dll": b"AMD DX12 provider",
            "OptiScaler/plugins/OptiPatcher.asi": b"official patcher",
        }
        for name, data in self.payload.items():
            path = self.bundle / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.manifest = {
            "schema_version": 2, "fsr4_variants": ASSETS["variants"],
            "selected_default_variant": "fsr4-lite",
            "optiscaler": {"version": "10-test", "native_upscaler_sha256": "fixture"},
            "payload_files": {name: hashlib.sha256(data).hexdigest() for name, data in self.payload.items()},
        }
        (self.bundle / "install-manifest.json").write_text(json.dumps(self.manifest))

    def patch(self, dll="dxgi.dll", variant="fsr4-lite"):
        return game.patch(self.target, self.bundle, dll, variant)

    def ini(self):
        config = configparser.ConfigParser()
        config.read(self.target / "OptiScaler.ini")
        return config

    def test_lite_configuration_and_v10_layout(self):
        self.patch()
        self.assertEqual(self.ini()["FSR"]["Fsr4GpuSupport"], "4")
        self.assertEqual(self.ini()["FSR"]["Fsr4Model"], "3")
        self.assertEqual(self.ini()["Upscalers"]["Dx12Upscaler"], "ffx")
        self.assertEqual(self.ini()["FrameGen"]["Enabled"], "false")
        self.assertTrue((self.target / "OptiScaler/amdvkffx64.dll").is_file())
        self.assertFalse((self.target / "amdvkffx64.dll").exists())

    def test_switch_and_uninstall_restore_originals_and_keep_other_plugins(self):
        (self.target / "dxgi.dll").write_bytes(b"original game proxy")
        (self.target / "OptiScaler.ini").write_bytes(b"; original settings\n[FSR]\nFsr4Model=auto\n")
        (self.target / "OptiScaler/plugins").mkdir(parents=True)
        (self.target / "OptiScaler/plugins/unrelated.asi").write_bytes(b"other plugin")
        (self.target / "OptiScaler/amdvkffx64.dll").write_bytes(b"original provider")
        self.patch()
        self.patch("winmm.dll", "fsr4-auto")
        self.assertEqual(self.ini()["FSR"]["Fsr4Model"], "auto")
        self.assertEqual((self.target / "dxgi.dll").read_bytes(), b"original game proxy")
        game.unpatch(self.target)
        self.assertFalse((self.target / "winmm.dll").exists())
        self.assertEqual((self.target / "OptiScaler/amdvkffx64.dll").read_bytes(), b"original provider")
        self.assertEqual((self.target / "OptiScaler/plugins/unrelated.asi").read_bytes(), b"other plugin")
        self.assertTrue((self.target / "OptiScaler.ini").read_bytes().startswith(b"; original settings"))

    def test_tampered_payload_is_rejected_before_mutation(self):
        (self.bundle / "OptiScaler/amdvkffx64.dll").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.patch()
        self.assertEqual(list(self.target.iterdir()), [])

    def test_changed_game_dll_is_preserved(self):
        self.patch()
        (self.target / "dxgi.dll").write_bytes(b"user replacement")
        with self.assertRaisesRegex(ValueError, "Managed file changed"):
            game.unpatch(self.target)
        with self.assertRaisesRegex(ValueError, "Managed file changed"):
            self.patch()
        self.assertEqual((self.target / "dxgi.dll").read_bytes(), b"user replacement")

    def test_preserved_ini_comments_and_user_settings(self):
        self.patch()
        with (self.target / "OptiScaler.ini").open("a") as handle:
            handle.write("\n; custom value\n[Menu]\nScale=1.25\n")
        self.patch()
        self.assertEqual(self.ini()["Menu"]["Scale"], "1.25")
        self.assertIn("; custom value", (self.target / "OptiScaler.ini").read_text())

    def test_symlink_destination_is_rejected(self):
        outside = self.home / "outside"
        outside.mkdir()
        (self.target / "OptiScaler").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.patch()
        self.assertEqual(list(outside.iterdir()), [])

    def test_path_traversal_in_state_is_rejected(self):
        outside = self.home / "important"
        outside.write_bytes(b"keep")
        (self.target / game.STATE).write_text(json.dumps({"files": {"OptiScaler/../../important": "hash"}, "backups": []}))
        with self.assertRaises(ValueError):
            game.unpatch(self.target)
        self.assertEqual(outside.read_bytes(), b"keep")

    def test_failed_write_rolls_back(self):
        (self.target / "dxgi.dll").write_bytes(b"original")
        original_write = game.atomic_write
        failed = False

        def fail_once(path, data):
            nonlocal failed
            if path.name == "amdxcffx64.dll" and not failed:
                failed = True
                raise OSError("disk full")
            original_write(path, data)

        with mock.patch.object(game, "atomic_write", side_effect=fail_once):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.patch()
        self.assertEqual((self.target / "dxgi.dll").read_bytes(), b"original")
        self.assertFalse((self.target / game.STATE).exists())
        self.assertFalse((self.target / "OptiScaler/amdvkffx64.dll").exists())

    def test_backups_precede_overwrites_and_survive_until_restore(self):
        original = b"original game proxy"
        (self.target / "dxgi.dll").write_bytes(original)
        write = game.atomic_write

        def observe_patch(path, data):
            if path == self.target / "dxgi.dll":
                self.assertEqual((self.target / game.BACKUPS / "dxgi.dll").read_bytes(), original)
            write(path, data)

        with mock.patch.object(game, "atomic_write", side_effect=observe_patch):
            self.patch()

        def observe_restore(path, data):
            if path == self.target / "dxgi.dll":
                self.assertEqual((self.target / game.BACKUPS / "dxgi.dll").read_bytes(), original)
                self.assertTrue((self.target / game.STATE).is_file())
            write(path, data)

        with mock.patch.object(game, "atomic_write", side_effect=observe_restore):
            game.unpatch(self.target)

    def test_legacy_install_is_not_destructively_migrated(self):
        (self.target / game.MARKER).write_text("{}")
        (self.target / "dxgi.dll.b").write_bytes(b"game original")
        with self.assertRaisesRegex(ValueError, "older Framegen"):
            self.patch()
        self.assertEqual((self.target / "dxgi.dll.b").read_bytes(), b"game original")

    def test_launch_wrapper_uses_same_installer(self):
        (self.bundle / "patch-game.py").write_bytes((ROOT / "defaults/assets/patch-game.py").read_bytes())
        wrapper = ROOT / "defaults/assets/fgmod.sh"
        result = subprocess.run(["bash", str(wrapper), str(self.target)],
                                env={**os.environ, "HOME": str(self.home), "DLL": "winmm.dll"},
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.target / "winmm.dll").is_file())
        self.assertEqual(self.ini()["FSR"]["Fsr4Model"], "3")

    def test_uninstaller_does_not_need_source_bundle(self):
        self.patch()
        result = subprocess.run([sys.executable, str(ROOT / "defaults/assets/patch-game.py"),
                                 "unpatch", str(self.target), "--bundle", str(self.home / "missing")],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.target / "dxgi.dll").exists())


if __name__ == "__main__":
    unittest.main()
