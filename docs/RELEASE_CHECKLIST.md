# Release Checklist

Building is now automated: pushing a `v*` tag runs `.github/workflows/release.yml`,
which builds the wheel, AppImage and Windows installer from one shared wheel,
publishes to PyPI, and opens a **draft** GitHub Release with the binaries attached.
The build steps below are done by CI; this checklist is the prep and the
verification of what CI produced (and the recipe if you ever build locally).

## Before tagging

- [ ] `main` is clean and up to date.
- [ ] Version is bumped in `src/npyquick/__init__.py` (`__version__`; the single source — `pyproject.toml` reads it via `[tool.hatch.version]`).
- [ ] No stale version strings in packaging scripts (e.g. the AppStream `<release>` in `packaging/appimage/*.appdata.xml`).
- [ ] Tests pass.
- [ ] README install/download instructions match the release.

## Python package

- [ ] `python -m build` succeeds.
- [ ] `twine check dist/*` succeeds.
- [ ] Wheel installs in a fresh venv.
- [ ] `npyquick --version` prints the release version.
- [ ] `.npy` and `.npz` sample files open.

## Linux AppImage

- [ ] AppImage builds from the release wheel.
- [ ] `--version` works.
- [ ] `.npy` and `.npz` sample files open.
- [ ] `--install-desktop` writes a correct desktop entry.
- [ ] AppImageLauncher integration still works.

## Windows installer

- [ ] PyInstaller onedir build succeeds on Windows.
- [ ] `npyquick.exe sample.npy` and `sample.npz` open.
- [ ] GUI opens by double-click.
- [ ] File → Open works.
- [ ] Drag-and-drop works.
- [ ] Installer runs without admin.
- [ ] Start Menu shortcut works.
- [ ] Optional `.npy/.npz` association works if selected.
- [ ] Silent install and uninstall work.
- [ ] Uninstall removes Start Menu shortcut and app directory.
- [ ] Windows unsigned-build note is present in README/release notes.

## Release

- [ ] Tag is created from the final release commit.
- [ ] GitHub Release has the AppImage and Windows setup.exe attached (GitHub shows a SHA-256 digest per asset).
- [ ] PyPI upload succeeds.
- [ ] Release notes mention major changes and known Windows SmartScreen warning.
