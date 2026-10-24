#!/usr/bin/env python3
"""Install the verified v10 payload; shared by Decky and the launch wrapper."""

import argparse
import configparser
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile

STATE = ".framegen-files.json"
BACKUPS = ".framegen-backups"
MARKER = "FRAMEGEN_PATCH"
PROXIES = {"dxgi.dll", "winmm.dll", "version.dll", "dbghelp.dll", "winhttp.dll", "wininet.dll", "OptiScaler.asi"}


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def safe_path(root, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or not relative.parts or any(p in ("..", ".") for p in relative.parts) or "\\" in name:
        raise ValueError("Invalid managed path")
    path = root.joinpath(*relative.parts)
    for parent in [path, *path.parents]:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError(f"Refusing symlink: {parent}")
    return path


def managed_name(name):
    return name in PROXIES or name in {"OptiScaler.ini", MARKER} or name.startswith("OptiScaler/")


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(data)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def ini_settings(data, overrides):
    """Update section-qualified keys without dropping comments or user settings."""
    lines = data.decode("utf-8-sig").splitlines()
    for qualified, value in overrides.items():
        section, key = qualified.split(".", 1)
        start = next((i for i, line in enumerate(lines) if line.strip().lower() == f"[{section}]".lower()), None)
        if start is None:
            lines.extend(["", f"[{section}]", f"{key}={value}"])
            continue
        end = next((i for i in range(start + 1, len(lines)) if lines[i].strip().startswith("[")), len(lines))
        found = False
        for i in range(start + 1, end):
            if lines[i].split("=", 1)[0].strip().lower() == key.lower():
                lines[i] = f"{key}={value}"
                found = True
        if not found:
            lines.insert(end, f"{key}={value}")
    return ("\n".join(lines) + "\n").encode()


def read_state(target):
    path = safe_path(target, STATE)
    if not path.exists():
        return {"files": {}, "backups": []}
    state = json.loads(path.read_text())
    if not isinstance(state.get("files"), dict) or not isinstance(state.get("backups"), list):
        raise ValueError("Invalid Framegen file manifest")
    for name in [*state["files"], *state["backups"]]:
        if not managed_name(name):
            raise ValueError("Unrecognised managed filename")
        safe_path(target, name)
        safe_path(target, f"{BACKUPS}/{name}")
    return state


def transact(target, writes, removals):
    """Rollback all affected files if a write fails; never follow game symlinks."""
    names = set(writes) | set(removals)
    paths = {name: safe_path(target, name) for name in names}
    for path in paths.values():
        if path.exists() and not path.is_file():
            raise ValueError(f"Expected a file: {path}")
    with tempfile.TemporaryDirectory(prefix="framegen-transaction-") as temporary:
        undo = {}
        for i, (name, path) in enumerate(paths.items()):
            if path.exists():
                snapshot = Path(temporary) / str(i)
                shutil.copy2(path, snapshot)
                undo[name] = snapshot
        try:
            for name in removals:
                paths[name].unlink(missing_ok=True)
            for name, data in writes.items():
                atomic_write(paths[name], data)
        except Exception:
            for name, path in paths.items():
                if name in undo:
                    atomic_write(path, undo[name].read_bytes())
                else:
                    path.unlink(missing_ok=True)
            raise


def patch(target, bundle, dll_name, variant, preserve_ini=True):
    if dll_name not in PROXIES:
        raise ValueError("Invalid proxy DLL name")
    manifest = json.loads((bundle / "install-manifest.json").read_text())
    variants = manifest["fsr4_variants"]
    if variant not in variants:
        raise ValueError("Unknown FSR preset; reinstall the v10 bundle")
    state = read_state(target)
    marker_path = safe_path(target, MARKER)
    if marker_path.exists() and not (target / STATE).exists():
        raise ValueError("Unpatch the older Framegen install with its original plugin before installing v10.")
    for name, expected in state["files"].items():
        existing = safe_path(target, name)
        if name not in ("OptiScaler.ini", MARKER) and existing.exists() and digest(existing) != expected:
            raise ValueError(f"Managed file changed; preserve it before reinstalling: {name}")

    # Validate the whole source before changing any game files.
    payload = {}
    for name, expected in manifest["payload_files"].items():
        if name != "OptiScaler.dll" and name != "OptiScaler.ini" and not name.startswith("OptiScaler/"):
            raise ValueError("Unexpected payload filename")
        source = safe_path(bundle, name)
        if digest(source) != expected:
            raise ValueError(f"Payload hash mismatch: {name}. Run Setup again.")
        payload[dll_name if name == "OptiScaler.dll" else name] = source.read_bytes()

    ini_path = safe_path(target, "OptiScaler.ini")
    if preserve_ini and ini_path.is_file():
        payload["OptiScaler.ini"] = ini_path.read_bytes()
    payload["OptiScaler.ini"] = ini_settings(payload["OptiScaler.ini"], variants[variant]["config_overrides"])
    # Migrate backend names; all other per-game settings survive.
    data = payload["OptiScaler.ini"].decode()
    config = configparser.ConfigParser(strict=False, interpolation=None)
    config.read_string(data)
    migration = {}
    for key in ("Dx11Upscaler", "Dx12Upscaler", "VulkanUpscaler"):
        old = config.get("Upscalers", key, fallback="auto")
        if old in ("fsr31", "fsr31_12"):
            migration[f"Upscalers.{key}"] = "ffx" if old == "fsr31" else "ffx_12"
    payload["OptiScaler.ini"] = ini_settings(payload["OptiScaler.ini"], migration)
    marker = json.loads(marker_path.read_text()) if marker_path.exists() else {}
    marker.update({"target_dir": str(target), "dll_name": dll_name, "fsr4_variant": variant,
                   "optiscaler_version": manifest["optiscaler"]["version"]})
    payload[MARKER] = json.dumps(marker, indent=2).encode()

    writes = dict(payload)
    backups = set(state["backups"])
    removals = []
    for name in state["files"]:
        if name in payload:
            continue
        existing = safe_path(target, name)
        if existing.exists() and digest(existing) != state["files"][name]:
            raise ValueError(f"Managed file changed; preserve it before switching: {name}")
        if name in backups:
            writes[name] = safe_path(target, f"{BACKUPS}/{name}").read_bytes()
            removals.append(f"{BACKUPS}/{name}")
            backups.remove(name)
        else:
            removals.append(name)
    for name in payload:
        existing = safe_path(target, name)
        if name not in state["files"] and existing.is_file() and name not in backups:
            backup_name = f"{BACKUPS}/{name}"
            if safe_path(target, backup_name).exists():
                raise ValueError(f"Untracked backup exists: {backup_name}")
            writes[backup_name] = existing.read_bytes()
            backups.add(name)
    state = {"files": {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()},
             "backups": sorted(backups)}
    writes[STATE] = json.dumps(state, indent=2).encode()
    transact(target, writes, removals)
    return {"status": "success", "message": f"Installed {variants[variant]['label']} in {target}",
            "fsr4_variant": variant, "fsr4_variant_label": variants[variant]["label"],
            "optiscaler_version": manifest["optiscaler"]["version"],
            "fsr4_upscaler_sha256": manifest["optiscaler"]["native_upscaler_sha256"]}


def unpatch(target):
    state = read_state(target)
    if not (target / STATE).exists():
        raise ValueError("No v10 file manifest. Use the original plugin to unpatch older installs.")
    writes, removals = {}, [STATE]
    for name, expected in state["files"].items():
        path = safe_path(target, name)
        if name not in ("OptiScaler.ini", MARKER) and path.exists() and digest(path) != expected:
            raise ValueError(f"Managed file changed; preserve it before uninstalling: {name}")
        if name in state["backups"]:
            backup = f"{BACKUPS}/{name}"
            writes[name] = safe_path(target, backup).read_bytes()
            removals.append(backup)
        else:
            removals.append(name)
    transact(target, writes, removals)
    # Only empty directories are removed; unrelated game plugins are retained.
    for folder in (target / "OptiScaler", target / BACKUPS):
        if folder.is_dir():
            for path in sorted(folder.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                if path.is_dir() and not path.is_symlink():
                    try:
                        path.rmdir()
                    except OSError:
                        pass
            try:
                folder.rmdir()
            except OSError:
                pass
    return {"status": "success", "message": f"Removed Framegen from {target}"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("patch", "unpatch"))
    parser.add_argument("target", type=Path)
    parser.add_argument("--bundle", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--dll", default="dxgi.dll")
    parser.add_argument("--variant", default=None)
    parser.add_argument("--reset-ini", action="store_true")
    args = parser.parse_args()
    try:
        target = args.target.resolve(strict=True)
        if not target.is_dir() or target in (args.bundle.resolve(), Path.home(), Path(target.anchor)):
            raise ValueError("Invalid game directory")
        if args.action == "patch":
            variant = args.variant or json.loads((args.bundle / "install-manifest.json").read_text())["selected_default_variant"]
            result = patch(target, args.bundle, args.dll, variant, not args.reset_ini)
        else:
            result = unpatch(target)
        print(json.dumps(result))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
