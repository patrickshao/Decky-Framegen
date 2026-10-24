from __future__ import annotations

import decky
import configparser
import sys
import tempfile
import os
import subprocess
import json
import shutil
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path

# One reviewed source manifest is used by the builder and the installed plugin.
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
if not (ASSETS_DIR / "runtime-assets.json").is_file():
    ASSETS_DIR = Path(__file__).resolve().parent / "defaults" / "assets"
RUNTIME_ASSETS = json.loads((ASSETS_DIR / "runtime-assets.json").read_text())
OPTISCALER_ARCHIVE_ASSET = RUNTIME_ASSETS["optiscaler"]
OPTIPATCHER_ASSET = RUNTIME_ASSETS["optipatcher"]
FSR4_UPSCALER_FILENAME = "OptiScaler/amd_fidelityfx_upscaler_dx12.dll"
INSTALL_MANIFEST_FILENAME = "install-manifest.json"
VERSION_FILENAME = "version.txt"
DEFAULT_FSR4_VARIANT = "fsr4-lite"
FSR4_VARIANTS = RUNTIME_ASSETS["variants"]

PROXY_DLL_BACKUPS = [
    "dxgi.dll",
    "winmm.dll",
    "dbghelp.dll",
    "version.dll",
    "wininet.dll",
    "winhttp.dll",
    "OptiScaler.asi",
]

VALID_DLL_NAMES = set(PROXY_DLL_BACKUPS)

RESTORABLE_BACKUP_FILES = list(PROXY_DLL_BACKUPS)
SUPPORT_FILES = [
    "OptiScaler/amd_fidelityfx_loader_dx12.dll",
    "OptiScaler/amd_fidelityfx_framegeneration_dx12.dll",
    "OptiScaler/amd_fidelityfx_vk.dll",
    "OptiScaler/libxess.dll",
    "OptiScaler/libxess_dx11.dll",
    "OptiScaler/libxess_fg.dll",
    "OptiScaler/libxell.dll",
    "OptiScaler/dlssg_to_fsr3_amd_is_better.dll",
    "OptiScaler/amdvkffx64.dll",
    "OptiScaler/amdxcffx64.dll",
]

MARKER_FILENAME = "FRAMEGEN_PATCH"

BAD_EXE_SUBSTRINGS = [
    "crashreport",
    "crashreportclient",
    "eac",
    "easyanticheat",
    "beclient",
    "eosbootstrap",
    "benchmark",
    "uninstall",
    "setup",
    "launcher",
    "updater",
    "bootstrap",
    "_redist",
    "prereq",
]

class Plugin:
    async def _main(self):
        decky.logger.info("Framegen plugin loaded")

    async def _unload(self):
        decky.logger.info("Framegen plugin unloaded.")
        
    def _create_renamed_copies(self, source_file, renames_dir):
        """Create renamed copies of the OptiScaler.dll file"""
        try:
            renames_dir.mkdir(exist_ok=True)
            
            rename_files = [
                "dxgi.dll",
                "winmm.dll",
                "dbghelp.dll",
                "version.dll",
                "wininet.dll",
                "winhttp.dll",
                "OptiScaler.asi"
            ]
            
            if source_file.exists():
                for rename_file in rename_files:
                    dest_file = renames_dir / rename_file
                    shutil.copy2(source_file, dest_file)
                    decky.logger.info(f"Created renamed copy: {dest_file}")
                return True
            else:
                decky.logger.error(f"Source file {source_file} does not exist")
                return False
                
        except Exception as e:
            decky.logger.error(f"Failed to create renamed copies: {e}")
            return False
    
    def _copy_launcher_scripts(self, assets_dir, extract_path):
        """Copy launcher scripts from assets directory"""
        try:
            # Copy fgmod script
            fgmod_script_src = assets_dir / "fgmod.sh"
            fgmod_script_dest = extract_path / "fgmod"
            if fgmod_script_src.exists():
                shutil.copy2(fgmod_script_src, fgmod_script_dest)
                fgmod_script_dest.chmod(0o755)
                decky.logger.info(f"Copied fgmod script to {fgmod_script_dest}")
            
            # Copy uninstaller script
            uninstaller_src = assets_dir / "fgmod-uninstaller.sh"
            uninstaller_dest = extract_path / "fgmod-uninstaller.sh"
            if uninstaller_src.exists():
                shutil.copy2(uninstaller_src, uninstaller_dest)
                uninstaller_dest.chmod(0o755)
                decky.logger.info(f"Copied uninstaller script to {uninstaller_dest}")

            # Copy optiscaler config updater script
            optiscaler_config_updater_src = assets_dir / "update-optiscaler-config.py"
            optiscaler_config_updater_dest = extract_path / "update-optiscaler-config.py"
            if optiscaler_config_updater_src.exists():
                shutil.copy2(optiscaler_config_updater_src, optiscaler_config_updater_dest)
                optiscaler_config_updater_dest.chmod(0o755)
                decky.logger.info(f"Copied update-optiscaler-config.py script to {optiscaler_config_updater_dest}")
                
            return True
        except Exception as e:
            decky.logger.error(f"Failed to copy launcher scripts: {e}")
            return False
    
    def _file_sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _read_json_file(self, path: Path) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write_json_file(self, path: Path, payload: dict) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def _extract_archive(self, archive_path: Path, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        extractor = next((shutil.which(name) for name in ("7z", "7zz", "bsdtar") if shutil.which(name)), None)
        if not extractor:
            raise RuntimeError("A 7z, 7zz or bsdtar extractor is required (included with SteamOS).")
        if Path(extractor).name == "bsdtar":
            command = [extractor, "-xf", str(archive_path), "-C", str(output_dir)]
        else:
            command = [extractor, "x", "-y", "-o" + str(output_dir), str(archive_path)]
        clean_env = os.environ.copy()
        clean_env["LD_LIBRARY_PATH"] = ""
        subprocess.run(command, capture_output=True, text=True, check=True, env=clean_env, timeout=600)

    def _verify_bundled_asset(self, path: Path, expected_sha256: str, description: str) -> str:
        actual_sha256 = self._file_sha256(path)
        if actual_sha256.lower() != expected_sha256.lower():
            raise RuntimeError(
                f"{description} hash mismatch: expected {expected_sha256}, got {actual_sha256}"
            )
        return actual_sha256

    def _install_manifest_path(self, fgmod_path: Path) -> Path:
        return fgmod_path / INSTALL_MANIFEST_FILENAME

    def _load_install_manifest(self, fgmod_path: Path) -> dict:
        return self._read_json_file(self._install_manifest_path(fgmod_path))

    def _normalize_fsr4_variant(self, fsr4_variant: str | None) -> str:
        variant = str(fsr4_variant or "").strip()
        if variant in FSR4_VARIANTS:
            return variant
        return DEFAULT_FSR4_VARIANT

    def _selected_fsr4_variant(self, fgmod_path: Path, requested_variant: str | None = None) -> str:
        normalized_requested = str(requested_variant or "").strip()
        if normalized_requested in FSR4_VARIANTS:
            return normalized_requested
        manifest = self._load_install_manifest(fgmod_path)
        manifest_variant = str(manifest.get("selected_default_variant") or "").strip()
        if manifest_variant in FSR4_VARIANTS:
            return manifest_variant
        return DEFAULT_FSR4_VARIANT

    def _activate_default_fsr4_variant(self, fgmod_path: Path, fsr4_variant: str | None) -> str:
        variant = self._normalize_fsr4_variant(fsr4_variant)
        if not (fgmod_path / FSR4_UPSCALER_FILENAME).is_file():
            raise FileNotFoundError("v10 runtime missing. Run Setup again.")
        return variant

    def _detect_fsr4_variant(self, directory: Path, upscaler_sha256: str | None) -> str | None:
        if upscaler_sha256 != OPTISCALER_ARCHIVE_ASSET["upscaler_sha256"]:
            return None
        config = configparser.ConfigParser(strict=False, interpolation=None)
        try:
            config.read(directory / "OptiScaler.ini")
            return "fsr4-lite" if config.get("FSR", "Fsr4Model", fallback="auto") == "3" else "fsr4-auto"
        except configparser.Error:
            return None

    def _fgmod_version(self, fgmod_path: Path) -> str | None:
        manifest = self._load_install_manifest(fgmod_path)
        optiscaler = manifest.get("optiscaler") if isinstance(manifest, dict) else None
        if isinstance(optiscaler, dict) and optiscaler.get("version"):
            return str(optiscaler.get("version"))
        version_file = fgmod_path / VERSION_FILENAME
        try:
            if version_file.exists():
                return version_file.read_text(encoding="utf-8").strip() or None
        except Exception:
            return None
        return None

    async def extract_static_optiscaler(self, selected_default_variant: str = DEFAULT_FSR4_VARIANT) -> dict:
        """Stage and verify official binaries before replacing the shared bundle."""
        try:
            bin_path = Path(decky.DECKY_PLUGIN_DIR) / "bin"
            extract_path = Path(decky.HOME) / "fgmod"
            selected_default_variant = self._normalize_fsr4_variant(selected_default_variant)
            required_assets = [OPTISCALER_ARCHIVE_ASSET, OPTIPATCHER_ASSET]
            required_assets += [{"name": name, **info} for name, info in RUNTIME_ASSETS["amd_driver"]["files"].items()]
            for asset in required_assets:
                self._verify_bundled_asset(bin_path / asset["name"], asset["sha256"], asset["name"])

            with tempfile.TemporaryDirectory(prefix=".fgmod-stage-", dir=decky.HOME) as temporary:
                stage = Path(temporary) / "fgmod"
                self._extract_archive(bin_path / OPTISCALER_ARCHIVE_ASSET["name"], stage)
                native_hash = self._verify_bundled_asset(stage / FSR4_UPSCALER_FILENAME,
                    OPTISCALER_ARCHIVE_ASSET["upscaler_sha256"], "SDK upscaler")
                for name in RUNTIME_ASSETS["amd_driver"]["files"]:
                    shutil.copy2(bin_path / name, stage / "OptiScaler" / name)
                plugins = stage / "OptiScaler" / "plugins"
                plugins.mkdir(parents=True, exist_ok=True)
                shutil.copy2(bin_path / OPTIPATCHER_ASSET["name"], plugins / "OptiPatcher.asi")
                # Keep upstream frame generation defaults; Lite selects upscaling only.
                ini = stage / "OptiScaler.ini"
                content = ini.read_text()
                content = re.sub(r"(?m)^LoadAsiPlugins\s*=.*$", "LoadAsiPlugins=true", content)
                content = re.sub(r"(?m)^UseHQFont\s*=.*$", "UseHQFont=false", content)
                ini.write_text(content)
                if not self._create_renamed_copies(stage / "OptiScaler.dll", stage / "renames"):
                    raise RuntimeError("Failed to prepare proxy DLLs")
                if not self._copy_launcher_scripts(ASSETS_DIR, stage):
                    raise RuntimeError("Failed to copy launcher scripts")
                shutil.copy2(ASSETS_DIR / "patch-game.py", stage / "patch-game.py")
                payload_files = {
                    str(path.relative_to(stage)): self._file_sha256(path)
                    for path in (stage / "OptiScaler").rglob("*") if path.is_file()
                }
                for name in ("OptiScaler.dll", "OptiScaler.ini"):
                    payload_files[name] = self._file_sha256(stage / name)
                manifest = {
                    "schema_version": 2,
                    "installed_at": datetime.now(timezone.utc).isoformat(),
                    "optiscaler": {**OPTISCALER_ARCHIVE_ASSET, "native_upscaler_sha256": native_hash},
                    "amd_driver": RUNTIME_ASSETS["amd_driver"],
                    "optipatcher": OPTIPATCHER_ASSET,
                    "fsr4_variants": FSR4_VARIANTS,
                    "selected_default_variant": selected_default_variant,
                    "payload_files": payload_files,
                }
                self._write_json_file(stage / INSTALL_MANIFEST_FILENAME, manifest)
                (stage / VERSION_FILENAME).write_text(OPTISCALER_ARCHIVE_ASSET["version"])
                previous = Path(temporary) / "previous"
                if extract_path.exists():
                    extract_path.rename(previous)
                try:
                    stage.rename(extract_path)
                except Exception:
                    if previous.exists():
                        previous.rename(extract_path)
                    raise
            return {"status": "success", "version": OPTISCALER_ARCHIVE_ASSET["version"],
                    "selected_default_variant": selected_default_variant,
                    "selected_default_variant_label": FSR4_VARIANTS[selected_default_variant]["label"]}
        except Exception as exc:
            decky.logger.exception("OptiScaler setup failed")
            return {"status": "error", "message": str(exc)}

    async def run_uninstall_fgmod(self) -> dict:
        try:
            # Remove fgmod directory
            fgmod_path = Path(decky.HOME) / "fgmod"
            
            if fgmod_path.exists():
                shutil.rmtree(fgmod_path)
                decky.logger.info(f"Removed directory: {fgmod_path}")
                return {
                    "status": "success", 
                    "output": "Successfully removed fgmod directory"
                }
            else:
                return {
                    "status": "success", 
                    "output": "No fgmod directory found to remove"
                }
            
        except Exception as e:
            decky.logger.error(f"Uninstall error: {str(e)}")
            return {
                "status": "error", 
                "message": f"Uninstall failed: {str(e)}", 
                "output": str(e)
            }

    async def set_default_fsr4_variant(self, selected_default_variant: str = DEFAULT_FSR4_VARIANT) -> dict:
        try:
            fgmod_path = Path(decky.HOME) / "fgmod"
            if not fgmod_path.exists():
                return {"status": "error", "message": "OptiScaler bundle not installed. Run Install first."}

            selected_default_variant = self._normalize_fsr4_variant(selected_default_variant)
            manifest = self._load_install_manifest(fgmod_path)
            if not manifest:
                return {"status": "error", "message": "Install manifest missing. Reinstall OptiScaler."}

            selected_default_variant = self._activate_default_fsr4_variant(fgmod_path, selected_default_variant)
            active_upscaler_sha256 = self._file_sha256(fgmod_path / FSR4_UPSCALER_FILENAME)
            manifest["selected_default_variant"] = selected_default_variant
            manifest["active_root_upscaler"] = {
                "path": FSR4_UPSCALER_FILENAME,
                "sha256": active_upscaler_sha256,
                "variant": selected_default_variant,
            }
            manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._write_json_file(self._install_manifest_path(fgmod_path), manifest)
            return {
                "status": "success",
                "output": f"Default FSR4 runtime switched to {FSR4_VARIANTS[selected_default_variant]['label']}.",
                "version": self._fgmod_version(fgmod_path),
                "selected_default_variant": selected_default_variant,
                "selected_default_variant_label": FSR4_VARIANTS[selected_default_variant]["label"],
            }
        except Exception as e:
            decky.logger.error(f"Failed to switch default FSR4 runtime: {e}")
            return {"status": "error", "message": f"Failed to switch default FSR4 runtime: {e}"}

    async def run_install_fgmod(self, selected_default_variant: str = DEFAULT_FSR4_VARIANT) -> dict:
        try:
            decky.logger.info("Starting OptiScaler installation from static bundle")
            selected_default_variant = self._normalize_fsr4_variant(selected_default_variant)

            extract_result = await self.extract_static_optiscaler(selected_default_variant)
            if extract_result["status"] != "success":
                return {
                    "status": "error",
                    "message": f"OptiScaler extraction failed: {extract_result.get('message', 'Unknown error')}"
                }

            return {
                "status": "success",
                "output": (
                    "Successfully installed OptiScaler "
                    f"{extract_result.get('version', OPTISCALER_ARCHIVE_ASSET['version'])} "
                    f"with {extract_result.get('selected_default_variant_label', FSR4_VARIANTS[selected_default_variant]['label'])}."
                ),
                "version": extract_result.get("version", OPTISCALER_ARCHIVE_ASSET["version"]),
                "selected_default_variant": extract_result.get("selected_default_variant", selected_default_variant),
                "selected_default_variant_label": extract_result.get(
                    "selected_default_variant_label",
                    FSR4_VARIANTS[selected_default_variant]["label"],
                ),
            }

        except Exception as e:
            decky.logger.error(f"Unexpected error during installation: {str(e)}")
            return {
                "status": "error",
                "message": f"Installation failed: {str(e)}"
            }

    async def check_fgmod_path(self) -> dict:
        path = Path(decky.HOME) / "fgmod"
        required_files = ["OptiScaler.dll", "OptiScaler.ini", FSR4_UPSCALER_FILENAME,
                          *SUPPORT_FILES, "OptiScaler/plugins/OptiPatcher.asi",
                          "fgmod", "fgmod-uninstaller.sh", "patch-game.py", INSTALL_MANIFEST_FILENAME]
        if not all((path / name).is_file() for name in required_files):
            return {"exists": False}

        manifest = self._load_install_manifest(path)
        selected_variant = self._selected_fsr4_variant(path)
        return {
            "exists": True,
            "version": self._fgmod_version(path),
            "selected_fsr4_variant": selected_variant,
            "selected_fsr4_variant_label": FSR4_VARIANTS[selected_variant]["label"],
            "install_manifest_present": bool(manifest),
        }

    def _resolve_target_directory(self, directory: str) -> Path:
        decky.logger.info(f"Resolving target directory: {directory}")
        target = Path(directory).expanduser()
        if not target.exists():
            raise FileNotFoundError(f"Target directory does not exist: {directory}")
        if not target.is_dir():
            raise NotADirectoryError(f"Target path is not a directory: {directory}")
        if not os.access(target, os.W_OK | os.X_OK):
            raise PermissionError(f"Insufficient permissions for {directory}")
        decky.logger.info(f"Resolved directory {directory} to absolute path {target}")
        return target

    def _game_file_action(self, action: str, directory: Path, *arguments: str) -> dict:
        result = subprocess.run(
            [sys.executable, str(ASSETS_DIR / "patch-game.py"), action, str(directory),
             "--bundle", str(Path(decky.HOME) / "fgmod"), *arguments],
            capture_output=True, text=True, timeout=600, check=False,
        )
        try:
            return json.loads(result.stdout)
        except (ValueError, TypeError):
            return {"status": "error", "message": result.stderr or "Game file operation failed"}

    def _manual_patch_directory_impl(self, directory: Path, dll_name: str = "dxgi.dll",
                                     fsr4_variant: str | None = None,
                                     allow_managed_support_cleanup: bool = False) -> dict:
        variant = self._selected_fsr4_variant(Path(decky.HOME) / "fgmod", fsr4_variant)
        return self._game_file_action("patch", directory, "--dll", dll_name, "--variant", variant)

    def _manual_unpatch_directory_impl(self, directory: Path) -> dict:
        return self._game_file_action("unpatch", directory)

    # ── Steam library discovery ───────────────────────────────────────────────

    def _home_path(self) -> Path:
        try:
            return Path(decky.HOME)
        except TypeError:
            return Path(str(decky.HOME))

    def _steam_root_candidates(self) -> list[Path]:
        home = self._home_path()
        candidates = [
            home / ".local" / "share" / "Steam",
            home / ".steam" / "steam",
            home / ".steam" / "root",
            home / ".var" / "app" / "com.valvesoftware.Steam" / "home" / ".local" / "share" / "Steam",
            home / ".var" / "app" / "com.valvesoftware.Steam" / "home" / ".steam" / "steam",
        ]
        unique: list[Path] = []
        seen: set[str] = set()
        for c in candidates:
            key = str(c)
            if key not in seen:
                unique.append(c)
                seen.add(key)
        return unique

    def _steam_library_paths(self) -> list[Path]:
        library_paths: list[Path] = []
        seen: set[str] = set()
        for steam_root in self._steam_root_candidates():
            if steam_root.exists():
                key = str(steam_root)
                if key not in seen:
                    library_paths.append(steam_root)
                    seen.add(key)
            library_file = steam_root / "steamapps" / "libraryfolders.vdf"
            if not library_file.exists():
                continue
            try:
                with open(library_file, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if '"path"' not in line:
                            continue
                        path = line.split('"path"', 1)[1].strip().strip('"').replace("\\\\", "/")
                        candidate = Path(path)
                        key = str(candidate)
                        if key not in seen:
                            library_paths.append(candidate)
                            seen.add(key)
            except Exception as exc:
                decky.logger.error(f"[Framegen] failed to parse libraryfolders: {library_file}: {exc}")
        return library_paths

    def _find_installed_games(self, appid: str | None = None) -> list[dict]:
        games: list[dict] = []
        for library_path in self._steam_library_paths():
            steamapps_path = library_path / "steamapps"
            if not steamapps_path.exists():
                continue
            for appmanifest in steamapps_path.glob("appmanifest_*.acf"):
                game_info: dict = {"appid": "", "name": "", "library_path": str(library_path), "install_path": ""}
                install_dir = ""
                try:
                    with open(appmanifest, "r", encoding="utf-8", errors="replace") as f:
                        for line in f:
                            if '"appid"' in line:
                                game_info["appid"] = line.split('"appid"', 1)[1].strip().strip('"')
                            elif '"name"' in line:
                                game_info["name"] = line.split('"name"', 1)[1].strip().strip('"')
                            elif '"installdir"' in line:
                                install_dir = line.split('"installdir"', 1)[1].strip().strip('"')
                except Exception as exc:
                    decky.logger.error(f"[Framegen] skipping manifest {appmanifest}: {exc}")
                    continue
                if not game_info["appid"] or not game_info["name"]:
                    continue
                if "Proton" in game_info["name"] or "Steam Linux Runtime" in game_info["name"]:
                    continue
                install_path = steamapps_path / "common" / install_dir if install_dir else Path()
                game_info["install_path"] = str(install_path)
                if appid is None or str(game_info["appid"]) == str(appid):
                    games.append(game_info)
        deduped: dict[str, dict] = {}
        for game in games:
            deduped[str(game["appid"])] = game
        return sorted(deduped.values(), key=lambda g: g["name"].lower())

    def _game_record(self, appid: str) -> dict | None:
        matches = self._find_installed_games(appid)
        return matches[0] if matches else None

    # ── Patch target auto-detection ───────────────────────────────────────────

    def _normalized_path_string(self, value: str) -> str:
        normalized = value.lower().replace("\\", "/")
        normalized = normalized.replace("z:/", "/")
        normalized = normalized.replace("//", "/")
        return normalized

    def _candidate_executables(self, install_root: Path) -> list[Path]:
        if not install_root.exists():
            return []
        candidates: list[Path] = []
        try:
            for exe in install_root.rglob("*.exe"):
                if exe.is_file():
                    candidates.append(exe)
        except Exception as exc:
            decky.logger.error(f"[Framegen] exe scan failed for {install_root}: {exc}")
        return candidates

    def _exe_score(self, exe: Path, install_root: Path, game_name: str) -> int:
        normalized = self._normalized_path_string(str(exe))
        name = exe.name.lower()
        score = 0
        if normalized.endswith("-win64-shipping.exe"):
            score += 300
        if "shipping.exe" in name:
            score += 220
        if "/binaries/win64/" in normalized:
            score += 200
        if "/win64/" in normalized:
            score += 80
        if exe.parent == install_root:
            score += 20
        sanitized_game = re.sub(r"[^a-z0-9]", "", game_name.lower())
        sanitized_name = re.sub(r"[^a-z0-9]", "", exe.stem.lower())
        sanitized_root = re.sub(r"[^a-z0-9]", "", install_root.name.lower())
        if sanitized_game and sanitized_game in sanitized_name:
            score += 120
        if sanitized_root and sanitized_root in sanitized_name:
            score += 90
        for bad in BAD_EXE_SUBSTRINGS:
            if bad in normalized:
                score -= 200
        score -= len(exe.parts)
        return score

    def _best_running_executable(self, candidates: list[Path]) -> Path | None:
        if not candidates:
            return None
        try:
            result = subprocess.run(["ps", "-eo", "args="], capture_output=True, text=True, check=False)
            process_lines = result.stdout.splitlines()
        except Exception as exc:
            decky.logger.error(f"[Framegen] running exe scan failed: {exc}")
            return None
        normalized_candidates = [(exe, self._normalized_path_string(str(exe))) for exe in candidates]
        matches: list[tuple[int, Path]] = []
        for line in process_lines:
            normalized_line = self._normalized_path_string(line)
            for exe, normalized_exe in normalized_candidates:
                if normalized_exe in normalized_line:
                    matches.append((len(normalized_exe), exe))
        if not matches:
            return None
        matches.sort(key=lambda item: item[0], reverse=True)
        return matches[0][1]

    def _guess_patch_target(self, game_info: dict) -> tuple[Path, Path | None]:
        install_root = Path(game_info["install_path"])
        candidates = self._candidate_executables(install_root)
        if not candidates:
            return install_root, None
        running_exe = self._best_running_executable(candidates)
        if running_exe:
            return running_exe.parent, running_exe
        best = max(candidates, key=lambda exe: self._exe_score(exe, install_root, game_info["name"]))
        return best.parent, best

    def _is_game_running(self, game_info: dict) -> bool:
        install_root = Path(game_info["install_path"])
        candidates = self._candidate_executables(install_root)
        return self._best_running_executable(candidates) is not None

    # ── Marker file tracking ──────────────────────────────────────────────────

    def _find_marker(self, install_root: Path) -> Path | None:
        if not install_root.exists():
            return None
        try:
            for marker in install_root.rglob(MARKER_FILENAME):
                if marker.is_file():
                    return marker
        except Exception:
            pass
        return None

    def _read_marker(self, marker_path: Path) -> dict:
        try:
            with open(marker_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write_marker(
        self,
        marker_path: Path,
        *,
        appid: str,
        game_name: str,
        dll_name: str,
        target_dir: Path,
        original_launch_options: str,
        backed_up_files: list[str],
        optiscaler_version: str | None = None,
        fsr4_variant: str | None = None,
        fsr4_upscaler_sha256: str | None = None,
    ) -> None:
        normalized_variant = self._normalize_fsr4_variant(fsr4_variant)
        variant_info = FSR4_VARIANTS[normalized_variant]
        payload = {
            "appid": str(appid),
            "game_name": game_name,
            "dll_name": dll_name,
            "target_dir": str(target_dir),
            "original_launch_options": original_launch_options,
            "backed_up_files": backed_up_files,
            "optiscaler_version": optiscaler_version,
            "fsr4_variant": normalized_variant,
            "fsr4_variant_label": variant_info["label"],
            "fsr4_upscaler_sha256": fsr4_upscaler_sha256,
            "managed_files": [
                {
                    "path": str(target_dir / FSR4_UPSCALER_FILENAME),
                    "sha256": fsr4_upscaler_sha256,
                    "kind": "fsr4-upscaler",
                    "variant": normalized_variant,
                }
            ],
            "patched_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_json_file(marker_path, payload)

    # ── Launch options helpers ────────────────────────────────────────────────

    def _build_managed_launch_options(self, dll_name: str) -> str:
        if dll_name == "OptiScaler.asi":
            return "SteamDeck=0 %command%"
        base = dll_name.replace(".dll", "")
        return f"WINEDLLOVERRIDES={base}=n,b SteamDeck=0 %command%"

    def _is_managed_launch_options(self, opts: str) -> bool:
        if not opts or not opts.strip():
            return False
        normalized = " ".join(opts.strip().split())
        for dll_name in VALID_DLL_NAMES:
            if dll_name == "OptiScaler.asi":
                continue
            base = dll_name.replace(".dll", "")
            if f"WINEDLLOVERRIDES={base}=n,b" in normalized:
                return True
        if "fgmod/fgmod" in normalized:
            return True
        return False

    async def list_installed_games(self) -> dict:
        try:
            games = []
            for game in self._find_installed_games():
                install_root = Path(game["install_path"])
                games.append({
                    "appid": str(game["appid"]),
                    "name": game["name"],
                    "install_found": install_root.exists(),
                })
            return {"status": "success", "games": games}
        except Exception as e:
            decky.logger.error(str(e))
            return {"status": "error", "message": str(e)}

    async def get_path_defaults(self) -> dict:
        try:
            home_path = Path(decky.HOME)
        except TypeError:
            home_path = Path(str(decky.HOME))

        steam_common = home_path / ".local" / "share" / "Steam" / "steamapps" / "common"

        return {
            "home": str(home_path),
            "steam_common": str(steam_common),
        }

    async def log_error(self, error: str) -> None:
        decky.logger.error(f"FRONTEND: {error}")

    async def manual_patch_directory(
        self,
        directory: str,
        dll_name: str = "dxgi.dll",
        fsr4_variant: str = DEFAULT_FSR4_VARIANT,
    ) -> dict:
        if dll_name not in VALID_DLL_NAMES:
            return {"status": "error", "message": f"Invalid proxy DLL name: {dll_name}"}
        try:
            target_dir = self._resolve_target_directory(directory)
        except (FileNotFoundError, NotADirectoryError, PermissionError) as exc:
            decky.logger.error(f"Manual patch validation failed: {exc}")
            return {"status": "error", "message": str(exc)}

        allow_managed_support_cleanup = (target_dir / MARKER_FILENAME).exists()
        return self._manual_patch_directory_impl(
            target_dir,
            dll_name,
            fsr4_variant,
            allow_managed_support_cleanup=allow_managed_support_cleanup,
        )

    async def manual_unpatch_directory(self, directory: str) -> dict:
        try:
            target_dir = self._resolve_target_directory(directory)
        except (FileNotFoundError, NotADirectoryError, PermissionError) as exc:
            decky.logger.error(f"Manual unpatch validation failed: {exc}")
            return {"status": "error", "message": str(exc)}

        return self._manual_unpatch_directory_impl(target_dir)

    # ── AppID-based patch / unpatch / status ───────────────────────────────────────

    async def get_game_status(self, appid: str) -> dict:
        try:
            game_info = self._game_record(str(appid))
            if not game_info:
                return {
                    "status": "success",
                    "appid": str(appid),
                    "install_found": False,
                    "patched": False,
                    "dll_name": None,
                    "target_dir": None,
                    "fsr4_variant": None,
                    "fsr4_variant_label": None,
                    "message": "Game not found in Steam library.",
                }
            install_root = Path(game_info["install_path"])
            if not install_root.exists():
                return {
                    "status": "success",
                    "appid": str(appid),
                    "name": game_info["name"],
                    "install_found": False,
                    "patched": False,
                    "dll_name": None,
                    "target_dir": None,
                    "fsr4_variant": None,
                    "fsr4_variant_label": None,
                    "message": "Game install directory not found.",
                }
            marker = self._find_marker(install_root)
            if not marker:
                return {
                    "status": "success",
                    "appid": str(appid),
                    "name": game_info["name"],
                    "install_found": True,
                    "patched": False,
                    "dll_name": None,
                    "target_dir": None,
                    "fsr4_variant": None,
                    "fsr4_variant_label": None,
                    "message": "Not patched.",
                }
            metadata = self._read_marker(marker)
            dll_name = metadata.get("dll_name", "dxgi.dll")
            target_dir = marker.parent
            dll_present = (target_dir / dll_name).exists()
            upscaler_path = target_dir / FSR4_UPSCALER_FILENAME
            upscaler_sha256 = self._file_sha256(upscaler_path) if upscaler_path.exists() else None
            detected_variant = self._detect_fsr4_variant(target_dir, upscaler_sha256)
            stored_variant = str(metadata.get("fsr4_variant") or "").strip() or None
            effective_variant = detected_variant or (stored_variant if stored_variant in FSR4_VARIANTS else None)
            effective_label = FSR4_VARIANTS[effective_variant]["label"] if effective_variant else None
            return {
                "status": "success",
                "appid": str(appid),
                "name": game_info["name"],
                "install_found": True,
                "patched": dll_present,
                "dll_name": dll_name,
                "target_dir": str(target_dir),
                "patched_at": metadata.get("patched_at"),
                "optiscaler_version": metadata.get("optiscaler_version"),
                "fsr4_variant": effective_variant,
                "fsr4_variant_label": effective_label,
                "fsr4_upscaler_sha256": upscaler_sha256,
                "message": (
                    f"Patched using {dll_name}" + (f" with {effective_label}." if effective_label else ".")
                    if dll_present
                    else f"Marker found but {dll_name} is missing. Reinstall recommended."
                ),
            }
        except Exception as exc:
            decky.logger.error(f"[Framegen] get_game_status failed for {appid}: {exc}")
            return {"status": "error", "message": str(exc)}

    async def patch_game(
        self,
        appid: str,
        dll_name: str = "dxgi.dll",
        current_launch_options: str = "",
        fsr4_variant: str = DEFAULT_FSR4_VARIANT,
    ) -> dict:
        try:
            if dll_name not in VALID_DLL_NAMES:
                return {"status": "error", "message": f"Invalid proxy DLL name: {dll_name}"}
            game_info = self._game_record(str(appid))
            if not game_info:
                return {"status": "error", "message": "Game not found in Steam library."}
            install_root = Path(game_info["install_path"])
            if not install_root.exists():
                return {"status": "error", "message": "Game install directory does not exist."}
            if self._is_game_running(game_info):
                return {"status": "error", "message": "Close the game before patching."}
            fgmod_path = Path(decky.HOME) / "fgmod"
            if not fgmod_path.exists():
                return {"status": "error", "message": "OptiScaler bundle not installed. Run Install first."}

            # Preserve true original launch options across re-patches
            original_launch_options = current_launch_options or ""
            existing_marker = self._find_marker(install_root)
            existing_marker_metadata = self._read_marker(existing_marker) if existing_marker else {}
            existing_marker_target_dir = Path(
                existing_marker_metadata.get("target_dir", str(existing_marker.parent))
            ) if existing_marker else None
            if existing_marker:
                stored_opts = str(existing_marker_metadata.get("original_launch_options") or "")
                if stored_opts and not self._is_managed_launch_options(stored_opts):
                    original_launch_options = stored_opts
            if self._is_managed_launch_options(original_launch_options):
                original_launch_options = ""

            # Auto-detect the right directory to patch
            target_dir, target_exe = self._guess_patch_target(game_info)
            decky.logger.info(f"[Framegen] patch_game: appid={appid} dll={dll_name} target={target_dir} exe={target_exe}")

            allow_managed_support_cleanup = bool(
                existing_marker and existing_marker_target_dir == target_dir
            ) or (target_dir / MARKER_FILENAME).exists()
            result = self._manual_patch_directory_impl(
                target_dir,
                dll_name,
                fsr4_variant,
                allow_managed_support_cleanup=allow_managed_support_cleanup,
            )
            if result["status"] != "success":
                return result

            backed_up = [dll for dll in dict.fromkeys(RESTORABLE_BACKUP_FILES) if (target_dir / f"{dll}.b").exists()]
            marker_path = target_dir / MARKER_FILENAME
            self._write_marker(
                marker_path,
                appid=str(appid),
                game_name=game_info["name"],
                dll_name=dll_name,
                target_dir=target_dir,
                original_launch_options=original_launch_options,
                backed_up_files=backed_up,
                optiscaler_version=result.get("optiscaler_version"),
                fsr4_variant=result.get("fsr4_variant"),
                fsr4_upscaler_sha256=result.get("fsr4_upscaler_sha256"),
            )

            if existing_marker and existing_marker != marker_path:
                try:
                    existing_marker.unlink()
                except Exception:
                    pass

            managed_launch_options = self._build_managed_launch_options(dll_name)
            decky.logger.info(f"[Framegen] patch_game success: appid={appid} launch_options={managed_launch_options}")
            return {
                "status": "success",
                "appid": str(appid),
                "name": game_info["name"],
                "dll_name": dll_name,
                "target_dir": str(target_dir),
                "launch_options": managed_launch_options,
                "original_launch_options": original_launch_options,
                "optiscaler_version": result.get("optiscaler_version"),
                "fsr4_variant": result.get("fsr4_variant"),
                "fsr4_variant_label": result.get("fsr4_variant_label"),
                "fsr4_upscaler_sha256": result.get("fsr4_upscaler_sha256"),
                "message": (
                    f"Patched {game_info['name']} using {dll_name} "
                    f"with {result.get('fsr4_variant_label', FSR4_VARIANTS[self._normalize_fsr4_variant(fsr4_variant)]['label'])}."
                ),
            }
        except Exception as exc:
            decky.logger.error(f"[Framegen] patch_game failed for {appid}: {exc}")
            return {"status": "error", "message": str(exc)}

    async def unpatch_game(self, appid: str) -> dict:
        try:
            game_info = self._game_record(str(appid))
            if not game_info:
                return {"status": "error", "message": "Game not found in Steam library."}
            install_root = Path(game_info["install_path"])
            if not install_root.exists():
                return {
                    "status": "success",
                    "appid": str(appid),
                    "name": game_info["name"],
                    "launch_options": "",
                    "message": "Game install directory does not exist.",
                }
            if self._is_game_running(game_info):
                return {"status": "error", "message": "Close the game before unpatching."}
            marker = self._find_marker(install_root)
            if not marker:
                return {
                    "status": "success",
                    "appid": str(appid),
                    "name": game_info["name"],
                    "launch_options": "",
                    "message": "No Framegen patch found for this game.",
                }
            metadata = self._read_marker(marker)
            target_dir = marker.parent
            original_launch_options = str(metadata.get("original_launch_options") or "")
            result = self._manual_unpatch_directory_impl(target_dir)
            if result["status"] != "success":
                return result
            try:
                marker.unlink()
            except FileNotFoundError:
                pass
            decky.logger.info(f"[Framegen] unpatch_game success: appid={appid} target={target_dir}")
            return {
                "status": "success",
                "appid": str(appid),
                "name": game_info["name"],
                "launch_options": original_launch_options,
                "message": f"Unpatched {game_info['name']}.",
            }
        except Exception as exc:
            decky.logger.error(f"[Framegen] unpatch_game failed for {appid}: {exc}")
            return {"status": "error", "message": str(exc)}
