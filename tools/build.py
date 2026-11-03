#!/usr/bin/env python
"""Build LiveCaptionsRU as a onedir bundle (faster start than onefile).

Usage:
    python tools/build.py            # build into dist/LiveCaptionsRU
    python tools/build.py --onefile  # single-file build (slower start)

The model must be in models/t-one (see tools/fetch_model.py).
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
MODEL = ROOT / "models" / "t-one"
FONTS = APP / "fonts"
ICON = ROOT / "assets" / "icon.ico"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
PATHS_PY = APP / "paths.py"
INSTALLER = ROOT / "installer" / "LiveCaptionsRU.iss"


def _version_from(source: str, pattern: str, label: str) -> str | None:
    import re

    match = re.search(pattern, source)
    if match is None:
        print(f"version not found in {label}", file=sys.stderr)
        return None
    return match.group(1)


def check_version() -> int:
    """Fail the build when the app and the installer disagree about the version.

    Both are written by hand, and since 1.0.6 the log reset also depends on the version
    inside the running app: a mismatch ships a package that claims one version and
    behaves like another.
    """
    app_version = _version_from(
        PATHS_PY.read_text(encoding="utf-8"), r'APP_VERSION\s*=\s*"([^"]+)"', str(PATHS_PY)
    )
    if app_version is None:
        return 5
    if not INSTALLER.exists():
        print(f"installer script not found: {INSTALLER}", file=sys.stderr)
        return 5
    setup_version = _version_from(
        INSTALLER.read_text(encoding="utf-8"), r'#define\s+AppVersion\s+"([^"]+)"', str(INSTALLER)
    )
    if setup_version is None:
        return 5
    if app_version != setup_version:
        print(
            f"version mismatch: app/paths.py APP_VERSION={app_version} "
            f"installer AppVersion={setup_version}",
            file=sys.stderr,
        )
        return 5
    print(f"version {app_version} (app and installer agree)")
    return 0


def write_version_resource(app_version: str) -> Path:
    """Version resource for the exe, so Properties shows a real version.

    Without --version-file the built exe has an empty FileVersion, ProductVersion
    and CompanyName, and Windows shows a blank Details tab.
    """
    parts = [int(part) for part in app_version.split(".")[:4] if part.isdigit()]
    while len(parts) < 4:
        parts.append(0)
    numbers = "(" + ", ".join(str(part) for part in parts) + ")"
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numbers},
    prodvers={numbers},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', '600D R3450N'),
         StringStruct('FileDescription', 'Live Captions RU'),
         StringStruct('FileVersion', '{app_version}'),
         StringStruct('InternalName', 'LiveCaptionsRU'),
         StringStruct('LegalCopyright', 'Copyright (c) 2026 600D R3450N. Apache License 2.0'),
         StringStruct('OriginalFilename', 'LiveCaptionsRU.exe'),
         StringStruct('ProductName', 'Live Captions RU'),
         StringStruct('ProductVersion', '{app_version}')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    BUILD.mkdir(parents=True, exist_ok=True)
    path = BUILD / "version_info.txt"
    path.write_text(text, encoding="utf-8")
    print(f"version resource: {path}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build LiveCaptionsRU")
    parser.add_argument("--onefile", action="store_true", help="single-file build (slower start)")
    parser.add_argument("--clean", action="store_true", help="remove previous build artefacts")
    parser.add_argument("--no-collect-ort", action="store_true", help="do not bundle all of onnxruntime")
    args = parser.parse_args()

    if not (MODEL / "model.onnx").exists():
        print(f"model not found: {MODEL / 'model.onnx'}", file=sys.stderr)
        print("run: python tools/fetch_model.py", file=sys.stderr)
        return 2
    if not ICON.exists():
        print(f"icon not found: {ICON}", file=sys.stderr)
        return 2
    rc = check_version()
    if rc != 0:
        return rc
    if args.clean:
        shutil.rmtree(DIST, ignore_errors=True)
        shutil.rmtree(BUILD, ignore_errors=True)

    # Licence texts must travel with the binaries: Qt is LGPL-3.0, T-one and Roboto
    # are Apache-2.0, and all three require the notices to be redistributed.
    # The tray icon is loaded from icon.ico / icon_off.ico at runtime, not only baked
    # into the exe: without these two entries the tray shows an empty slot.
    icon_data: list[str] = []
    for name in ("icon.ico", "icon_off.ico"):
        candidate = APP / name
        if candidate.exists():
            icon_data += ["--add-data", f"{candidate};."]
        else:
            print(f"icon missing: {candidate}", file=sys.stderr)
            return 3

    licence_data: list[str] = []
    for name in ("LICENSE", "NOTICE", "THIRD-PARTY-NOTICES.md"):
        candidate = ROOT / name
        if candidate.exists():
            licence_data += ["--add-data", f"{candidate};."]
    licences_dir = ROOT / "licenses"
    if licences_dir.is_dir():
        licence_data += ["--add-data", f"{licences_dir};licenses"]

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--name",
        "LiveCaptionsRU",
        "--noconsole",
        "--icon",
        str(ICON),
        "--paths",
        str(APP),
        "--add-data",
        f"{MODEL};models/t-one",
        "--add-data",
        f"{FONTS};fonts",
        *icon_data,
        *licence_data,
        "--distpath",
        str(DIST),
        "--workpath",
        str(BUILD / "work"),
        "--specpath",
        str(BUILD),
        "--onefile" if args.onefile else "--onedir",
    ]
    app_version = _version_from(
        PATHS_PY.read_text(encoding="utf-8"), r'APP_VERSION\s*=\s*"([^"]+)"', str(PATHS_PY)
    )
    if app_version is None:
        return 5
    version_resource = write_version_resource(app_version)
    command[command.index("--distpath"):command.index("--distpath")] = [
        "--version-file",
        str(version_resource),
    ]
    if not args.no_collect_ort:
        command += ["--collect-all", "onnxruntime"]
    command.append(str(APP / "main.py"))

    print(" ".join(command))
    rc = subprocess.call(command)
    if rc == 0 and not args.onefile:
        target = DIST / "LiveCaptionsRU"
        for name in ("LICENSE", "NOTICE", "THIRD-PARTY-NOTICES.md"):
            candidate = ROOT / name
            if candidate.exists() and target.is_dir():
                shutil.copy2(candidate, target / name)
        if licences_dir.is_dir() and target.is_dir():
            shutil.copytree(licences_dir, target / "licenses", dirs_exist_ok=True)
        rc = _strip_user_state(target)
    return rc


def _strip_user_state(target: Path) -> int:
    """Keep the log and settings of the build machine out of the release package.

    A fresh install has neither file, so anything found here came from a test run on
    this machine. The user opens the log through "Открыть журнал событий", and it
    must not start with entries from someone else's session.
    """
    if not target.is_dir():
        return 0
    removed: list[str] = []
    for pattern in ("*.log", "settings.json", "*.log.[0-9]*"):
        for path in target.rglob(pattern):
            try:
                path.unlink()
                removed.append(str(path.relative_to(target)))
            except OSError as exc:
                print(f"cannot remove {path}: {exc}", file=sys.stderr)
                return 4
    if removed:
        print("removed user state from the package: " + ", ".join(removed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
