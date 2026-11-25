"""Build the standalone Windows app and its installer.

    build.bat            (or: .venv\\Scripts\\python tools\\build.py)

Output in dist\\:
    PadDock-Setup-<version>.exe     installer (per user, no admin rights needed)
    PadDock-<version>-portable.zip  the same app as a folder; run PadDock.exe from anywhere

Needs PyInstaller in the venv (build.bat installs it).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from server import __version__  # noqa: E402

BUILD = ROOT / "build"
DIST = ROOT / "dist"
ICON = ROOT / "web" / "icons" / "paddock.ico"

# Modules PyInstaller can't see because they're imported dynamically.
COLLECT_SUBMODULES = ["uvicorn", "pynput", "pystray", "zeroconf", "comtypes", "pycaw"]
COLLECT_ALL = ["winrt"]  # namespace packages with native .pyd files per WinRT namespace
EXCLUDE = ["numpy", "pytest", "IPython", "matplotlib", "PyInstaller"]

VERSION_INFO = """# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(filevers=({v}, 0), prodvers=({v}, 0), mask=0x3f, flags=0x0, OS=0x40004,
    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'PadDock'),
      StringStruct('FileDescription', '{desc}'),
      StringStruct('FileVersion', '{ver}'),
      StringStruct('InternalName', '{name}'),
      StringStruct('OriginalFilename', '{name}.exe'),
      StringStruct('ProductName', 'PadDock'),
      StringStruct('ProductVersion', '{ver}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def version_file(name: str, desc: str) -> Path:
    parts = [int(x) for x in __version__.split(".")][:3]
    parts += [0] * (3 - len(parts))
    path = BUILD / f"{name}-version.txt"
    path.write_text(VERSION_INFO.format(v=", ".join(map(str, parts)), ver=__version__, name=name, desc=desc), "utf-8")
    return path


def pyinstaller(*args: str) -> None:
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
           "--workpath", str(BUILD / "work"), "--specpath", str(BUILD), *args]
    print(">", " ".join(cmd[3:]), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT)


def main() -> None:
    shutil.rmtree(BUILD, ignore_errors=True)
    BUILD.mkdir(parents=True)
    DIST.mkdir(exist_ok=True)
    sep = ";"  # PyInstaller --add-data separator on Windows

    # 1) The app: a folder with PadDock.exe (no console window; lives in the tray).
    app_args = [
        "--name", "PadDock", "--windowed", "--icon", str(ICON),
        "--version-file", str(version_file("PadDock", "PadDock touch dock")),
        "--distpath", str(BUILD / "app"),
        "--add-data", f"{ROOT / 'web'}{sep}web",
        "--add-data", f"{ROOT / 'config.example.json'}{sep}.",
        "--paths", str(ROOT),
    ]
    for m in COLLECT_SUBMODULES:
        app_args += ["--collect-submodules", m]
    for m in COLLECT_ALL:
        app_args += ["--collect-all", m]
    for m in EXCLUDE:
        app_args += ["--exclude-module", m]
    pyinstaller(*app_args, str(ROOT / "run.py"))
    app_dir = BUILD / "app" / "PadDock"
    # Leave out caches and stray files from the web folder.
    for junk in app_dir.rglob("__pycache__"):
        shutil.rmtree(junk, ignore_errors=True)

    # 2) Zip it: the portable download and the installer's payload.
    payload = BUILD / "PadDock.zip"
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in sorted(app_dir.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(app_dir))
    portable = DIST / f"PadDock-{__version__}-portable.zip"
    with zipfile.ZipFile(portable, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in sorted(app_dir.rglob("*")):
            if f.is_file():
                z.write(f, Path("PadDock") / f.relative_to(app_dir))

    # 3) The installer: one exe with the app zip inside.
    setup_name = f"PadDock-Setup-{__version__}"
    pyinstaller(
        "--onefile", "--windowed", "--name", setup_name, "--icon", str(ICON),
        "--version-file", str(version_file(setup_name, "PadDock installer")),
        "--distpath", str(DIST),
        "--add-data", f"{payload}{sep}.",
        "--add-data", f"{ICON}{sep}.",
        "--paths", str(ROOT),
        *sum((["--exclude-module", m] for m in EXCLUDE + ["uvicorn", "fastapi", "pydantic", "winrt", "psutil", "cryptography", "zeroconf", "PIL"]), []),
        str(ROOT / "installer" / "setup.py"),
    )

    for f in (DIST / f"{setup_name}.exe", portable):
        print(f"built {f}  ({f.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
