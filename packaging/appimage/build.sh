#!/usr/bin/env bash
# Build the npyquick AppImage: PyInstaller onedir -> AppDir -> appimagetool.
# Run from anywhere; paths resolve relative to the repository root.
#
#   packaging/appimage/build.sh [WHEEL]
#
# WHEEL  optional path to a prebuilt npyquick wheel. If omitted, one is built
#        with `python -m build`. CI passes the shared wheel artifact here so the
#        AppImage and the PyPI release come from the same wheel.
#
# Env overrides:
#   PYTHON         interpreter for the build venv (default: python3). Must NOT be
#                  a conda Python — conda's C-extensions link against conda libs
#                  and break in the bundle (e.g. pyexpat undefined symbols).
#   APPIMAGETOOL   path to an existing appimagetool; if unset, it is downloaded.
#   OUTPUT         output path (default: dist/npyquick-<arch>.AppImage).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${PYTHON:-python3}"
ARCH="${ARCH:-x86_64}"
OUTPUT="${OUTPUT:-$REPO_ROOT/dist/npyquick-${ARCH}.AppImage}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

WHEEL="${1:-}"
if [ -z "$WHEEL" ]; then
    echo ">> building wheel"
    "$PYTHON" -m build --wheel --outdir "$WORK/wheel"
    WHEEL="$(ls "$WORK"/wheel/npyquick-*.whl | head -1)"
fi
echo ">> wheel: $WHEEL"

echo ">> creating clean venv"
"$PYTHON" -m venv "$WORK/venv" 2>/dev/null || "$PYTHON" -m venv --without-pip "$WORK/venv"
if ! "$WORK/venv/bin/python" -m pip --version >/dev/null 2>&1; then
    echo ">> bootstrapping pip (this venv lacks ensurepip)"
    curl -sSL https://bootstrap.pypa.io/get-pip.py | "$WORK/venv/bin/python"
fi
"$WORK/venv/bin/python" -m pip install --upgrade pip >/dev/null
"$WORK/venv/bin/python" -m pip install "$WHEEL" pyinstaller

echo ">> running PyInstaller"
"$WORK/venv/bin/pyinstaller" --noconfirm \
    --distpath "$WORK/dist" --workpath "$WORK/build" \
    packaging/pyinstaller/npyquick.spec

echo ">> assembling AppDir"
APPDIR="$WORK/AppDir"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/lib" \
         "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps" \
         "$APPDIR/usr/share/icons/hicolor/512x512/apps"
cp -a "$WORK/dist/npyquick/." "$APPDIR/usr/bin/"
install -m 755 packaging/appimage/AppRun "$APPDIR/AppRun"
cp packaging/appimage/npyquick.desktop "$APPDIR/npyquick.desktop"
cp packaging/appimage/npyquick.desktop "$APPDIR/usr/share/applications/npyquick.desktop"
cp packaging/appimage/npyquick.png "$APPDIR/npyquick.png"
cp packaging/appimage/npyquick.png "$APPDIR/.DirIcon"
cp packaging/appimage/npyquick.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/npyquick.png"
[ -f packaging/appimage/npyquick-512.png ] && \
    cp packaging/appimage/npyquick-512.png "$APPDIR/usr/share/icons/hicolor/512x512/apps/npyquick.png"

# Bundle host libs PyInstaller doesn't ship: Qt >= 6.5 dlopens libxcb-cursor,
# which is absent on many systems. AppRun adds usr/lib to LD_LIBRARY_PATH.
LDCONFIG="$(command -v ldconfig || echo /sbin/ldconfig)"
for lib in libxcb-cursor.so.0; do
    src="$("$LDCONFIG" -p 2>/dev/null | awk -v l="$lib" '$1==l {print $NF; exit}')"
    if [ -n "$src" ] && [ -f "$src" ]; then
        cp -L "$src" "$APPDIR/usr/lib/$lib"
        echo ">> bundled $lib ($src)"
    else
        echo ">> WARNING: $lib not found on build host; AppImage may fail where it is missing"
    fi
done

echo ">> fetching appimagetool"
TOOL="${APPIMAGETOOL:-}"
if [ -z "$TOOL" ]; then
    TOOL="$WORK/appimagetool-${ARCH}.AppImage"
    curl -sSL -o "$TOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
    chmod +x "$TOOL"
fi

echo ">> building AppImage"
mkdir -p "$(dirname "$OUTPUT")"
ARCH="$ARCH" APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" "$APPDIR" "$OUTPUT"
echo ">> done: $OUTPUT"
