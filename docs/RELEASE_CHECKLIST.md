# Release Checklist

## Before tagging

- [ ] `main` is clean and up to date.
- [ ] Version is bumped in `pyproject.toml`.
- [ ] No stale version strings in packaging scripts.
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
- [ ] GitHub Release has AppImage, Windows setup.exe, and SHA256 checksums.
- [ ] PyPI upload succeeds.
- [ ] Release notes mention major changes and known Windows SmartScreen warning.
