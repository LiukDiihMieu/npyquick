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
# OUTPUT is resolved after the wheel is installed (below), so its default name
# can carry the package version — matching the Windows installer's naming.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo ">> creating clean venv"
"$PYTHON" -m venv "$WORK/venv" 2>/dev/null || "$PYTHON" -m venv --without-pip "$WORK/venv"
VPY="$WORK/venv/bin/python"
if ! "$VPY" -m pip --version >/dev/null 2>&1; then
    echo ">> bootstrapping pip (this venv lacks ensurepip)"
    curl -sSL https://bootstrap.pypa.io/get-pip.py | "$VPY"
fi
"$VPY" -m pip install --upgrade pip >/dev/null

WHEEL="${1:-}"
if [ -z "$WHEEL" ]; then
    # Build the wheel inside the venv so the host PYTHON doesn't need `build`
    # installed — it usually isn't, outside CI. The wheel is pure-Python, so
    # the result is identical regardless of which interpreter builds it.
    echo ">> building wheel"
    "$VPY" -m pip install build >/dev/null
    "$VPY" -m build --wheel --outdir "$WORK/wheel"
    WHEEL="$(ls "$WORK"/wheel/npyquick-*.whl | head -1)"
fi
echo ">> wheel: $WHEEL"

"$VPY" -m pip install "$WHEEL" pyinstaller

# Read the version from the installed distribution's metadata (the standard
# importlib.metadata API — reads .dist-info, never imports package code), so the
# default output name matches the wheel and the Windows installer.
VERSION="$("$VPY" -c 'from importlib.metadata import version; print(version("npyquick"))')"
OUTPUT="${OUTPUT:-$REPO_ROOT/dist/npyquick-${VERSION}-${ARCH}.AppImage}"

echo ">> running PyInstaller"
"$WORK/venv/bin/pyinstaller" --noconfirm \
    --distpath "$WORK/dist" --workpath "$WORK/build" \
    packaging/pyinstaller/npyquick.spec

echo ">> assembling AppDir"
APPDIR="$WORK/AppDir"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/lib" \
         "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/metainfo" \
         "$APPDIR/usr/share/mime/packages" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps" \
         "$APPDIR/usr/share/icons/hicolor/512x512/apps"
cp -a "$WORK/dist/npyquick/." "$APPDIR/usr/bin/"

install -m 755 packaging/appimage/AppRun "$APPDIR/AppRun"
cp packaging/appimage/io.github.liukdiihmieu.npyquick.desktop \
   "$APPDIR/io.github.liukdiihmieu.npyquick.desktop"
cp packaging/appimage/io.github.liukdiihmieu.npyquick.desktop \
   "$APPDIR/usr/share/applications/io.github.liukdiihmieu.npyquick.desktop"
cp packaging/appimage/io.github.liukdiihmieu.npyquick.appdata.xml \
   "$APPDIR/usr/share/metainfo/io.github.liukdiihmieu.npyquick.appdata.xml"
# Declare the .npy/.npz MIME types (same file --install-desktop installs). Inert
# until a tool installs it host-side; ships here to document intent.
cp src/npyquick/resources/io.github.liukdiihmieu.npyquick.mime.xml \
   "$APPDIR/usr/share/mime/packages/npyquick.xml"
# Install icons under the reverse-DNS name so they match the desktop Icon= key.
cp packaging/appimage/npyquick.png "$APPDIR/io.github.liukdiihmieu.npyquick.png"
cp packaging/appimage/npyquick.png "$APPDIR/.DirIcon"
cp packaging/appimage/npyquick.png \
   "$APPDIR/usr/share/icons/hicolor/256x256/apps/io.github.liukdiihmieu.npyquick.png"
[ -f packaging/appimage/npyquick-512.png ] && \
    cp packaging/appimage/npyquick-512.png \
       "$APPDIR/usr/share/icons/hicolor/512x512/apps/io.github.liukdiihmieu.npyquick.png"

# Bundle host libs PyInstaller doesn't ship: Qt >= 6.5 dlopens libxcb-cursor,
# which is absent on many systems. AppRun adds usr/lib to LD_LIBRARY_PATH.
LDCONFIG="$(command -v ldconfig || echo /sbin/ldconfig)"
for lib in libxcb-cursor.so.0; do
    # Read all of ldconfig's output (no awk `exit`): exiting at the first match
    # closes the pipe early, ldconfig gets SIGPIPE, and `set -o pipefail` would
    # abort the whole build — flaky, since the match is near the top of a long
    # list. Print only the first match instead.
    src="$("$LDCONFIG" -p 2>/dev/null | awk -v l="$lib" '$1==l && !f {print $NF; f=1}')"
    if [ -n "$src" ] && [ -f "$src" ]; then
        cp -L "$src" "$APPDIR/usr/lib/$lib"
        echo ">> bundled $lib ($src)"
    else
        echo ">> WARNING: $lib not found on build host; AppImage may fail where it is missing"
    fi
done

# Guard: the GLib family must NOT be bundled anywhere in the AppDir (the .spec
# filters it out of the PyInstaller bundle) so the host provides it and host GIO
# modules like dconf keep working — otherwise dark mode and other desktop
# settings break on hosts newer than the build machine (issue #19). Run this once
# the whole AppDir is assembled so it also covers the gap-fill libs above. Fail
# loudly if a GLib library ever leaks back in.
stray="$(find "$APPDIR" -regextype posix-extended \
    -regex '.*/lib(glib|gio|gobject|gmodule|gthread)-2\.0\.so.*' 2>/dev/null)"
if [ -n "$stray" ]; then
    echo ">> ERROR: GLib libraries leaked into the bundle (must come from host):" >&2
    echo "$stray" >&2
    exit 1
fi

# Pin a stable appimagetool release and verify it: `continuous` is a rolling
# tag, so the build would silently change over time and couldn't be audited.
APPIMAGETOOL_VERSION="1.9.1"
appimagetool_sha256() {
    case "$1" in
        x86_64) echo "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0" ;;
        *) echo "" ;;
    esac
}

echo ">> fetching appimagetool $APPIMAGETOOL_VERSION"
TOOL="${APPIMAGETOOL:-}"
if [ -z "$TOOL" ]; then
    TOOL="$WORK/appimagetool-${ARCH}.AppImage"
    curl -sSL -o "$TOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/${APPIMAGETOOL_VERSION}/appimagetool-${ARCH}.AppImage"
    want="$(appimagetool_sha256 "$ARCH")"
    if [ -n "$want" ]; then
        echo "$want  $TOOL" | sha256sum -c - \
            || { echo ">> ERROR: appimagetool checksum mismatch" >&2; exit 1; }
    else
        echo ">> WARNING: no pinned checksum for arch $ARCH; skipping verification" >&2
    fi
    chmod +x "$TOOL"
fi

echo ">> building AppImage"
mkdir -p "$(dirname "$OUTPUT")"
ARCH="$ARCH" APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" "$APPDIR" "$OUTPUT"
echo ">> done: $OUTPUT"
