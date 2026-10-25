"""Exercise the installed backend boundary, including Decky's frozen runtime."""
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent


class BackendRuntimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.target = self.home / "FINAL FANTASY XVI"
        self.target.mkdir()
        self.bundle = self.home / "fgmod"
        payload = {
            "OptiScaler.dll": b"test injector",
            "OptiScaler.ini": b"[FSR]\nFsr4Model=auto\n",
            "OptiScaler/plugins/OptiPatcher.asi": b"test patcher",
        }
        for name, data in payload.items():
            destination = self.bundle / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        assets = json.loads((ROOT / "defaults/assets/runtime-assets.json").read_text())
        (self.bundle / "install-manifest.json").write_text(json.dumps({
            "selected_default_variant": "fsr4-lite",
            "fsr4_variants": assets["variants"],
            "optiscaler": {"version": "test", "native_upscaler_sha256": "test"},
            "payload_files": {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()},
        }))
        decky = types.ModuleType("decky")
        decky.HOME = str(self.home)
        decky.logger = logging.getLogger("backend-test")
        spec = importlib.util.spec_from_file_location("framegen_backend", ROOT / "main.py")
        self.backend = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {"decky": decky}):
            spec.loader.exec_module(self.backend)
        self.plugin = self.backend.Plugin()

    def test_patch_unpatch_repatch_under_frozen_decky(self):
        """A frozen executable must never be launched as the helper interpreter."""
        launcher = self.home / "PluginLoader"
        sentinel = self.home / "loader-was-started"
        launcher.write_text(f"#!/bin/sh\ntouch '{sentinel}'\nexit 99\n")
        launcher.chmod(0o755)
        original = b"original game DLL"
        (self.target / "dxgi.dll").write_bytes(original)
        with mock.patch.object(sys, "executable", str(launcher)), \
             mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.dict(os.environ, {"PYTHONHOME": "/invalid/decky-python", "PYTHONPATH": "/invalid/decky-modules", "LD_LIBRARY_PATH": "/invalid/decky-libs"}):
            for _ in range(2):
                result = self.plugin._game_file_action("patch", self.target)
                self.assertEqual(result["status"], "success", result)
                self.assertEqual((self.target / "dxgi.dll").read_bytes(), b"test injector")
                result = self.plugin._game_file_action("unpatch", self.target)
                self.assertEqual(result["status"], "success", result)
                self.assertEqual((self.target / "dxgi.dll").read_bytes(), original)
                self.assertFalse((self.target / ".framegen-files.json").exists())
        self.assertFalse(sentinel.exists(), "The helper started Decky Loader")

    def test_system_library_path_restored_for_external_python(self):
        run = self.backend.subprocess.run
        with mock.patch.dict(os.environ, {"LD_LIBRARY_PATH": "/decky/bundled", "LD_LIBRARY_PATH_ORIG": "/system/original"}), \
             mock.patch.object(self.backend.subprocess, "run", wraps=run) as called:
            result = self.plugin._game_file_action("patch", self.target)
        self.assertEqual(result["status"], "success", result)
        self.assertEqual(called.call_args.kwargs["env"]["LD_LIBRARY_PATH"], "/system/original")

    def test_helper_error_is_returned_without_modifying_game(self):
        (self.bundle / "OptiScaler.dll").write_bytes(b"tampered")
        result = self.plugin._game_file_action("patch", self.target)
        self.assertEqual(result["status"], "error", result)
        self.assertIn("hash mismatch", result["message"])
        self.assertEqual(list(self.target.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
