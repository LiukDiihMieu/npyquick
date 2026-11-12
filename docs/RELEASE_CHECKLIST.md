# Release Checklist

Building is now automated: pushing a `v*` tag runs `.github/workflows/release.yml`,
which builds the wheel, AppImage and Windows installer from one shared wheel,
publishes to PyPI, and opens a **draft** GitHub Release with the binaries attached.
The build steps below are done by CI; this checklist is the prep and the
verification of what CI produced (and the recipe if you ever build locally).

## Before tagging

- [ ] `main` is clean and up to date.
- [ ] Version is bumped in `src/npyquick/__init__.py` (`__version__`; the single source — `pyproject.toml` reads it via `[tool.hatch.version]`).
- [ ] The AppStream metainfo (`packaging/appimage/*.appdata.xml`) has a `<release>` entry for this version. The Snap takes its version from it. The release workflow refuses a tag that disagrees with either.
- [ ] `CHANGELOG.md` has a section for this version.
- [ ] Tests pass.
- [ ] README install/download instructions match the release.
- [ ] Optional: try the packages CI built from the release commit. The `tests` workflow run for that commit keeps the AppImage and the Windows installer as artifacts for 7 days; download them from the run's page.

## Every package

CI runs `npyquick --self-test` inside the AppImage, the Snap and the installed
Windows program. It builds the window, loads a `.npy` and a `.npz`, and exports
plots as PNG, SVG and PDF, so a resource, Qt plugin or matplotlib backend
missing from a bundle fails the build. It cannot judge anything visual; the
items below still need a person.

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

## Linux Snap

Pushing the tag runs `.github/workflows/snap.yml`: it builds the snap, self-tests it, and then waits for approval of the `snap-store` environment before uploading to the **edge** channel. Promotion to stable stays manual. The same workflow can be started by hand from the Actions tab to try a build before tagging; nothing is uploaded unless the approval is given.

To build locally instead: `snapcraft pack --use-lxd`, then `sudo snap install --dangerous <file>`.

- [ ] The workflow's build job passed, including `--self-test`.
- [ ] The upload to edge was approved, and `sudo snap refresh npyquick --edge` installs this version.
- [ ] `.npy` and `.npz` sample files open across the image / table / cross-section / histogram views.
- [ ] Launches from the application menu with the correct icon.
- [ ] Works on both X11 and Wayland sessions (the Qt xcb path needs the staged xcb/xkb libs).
- [ ] A file outside the sandbox (e.g. on another drive) shows the sandbox hint, not a raw error.
- [ ] After edge verification, promoted to stable: `snapcraft release npyquick <rev> stable`. Installed snaps update themselves from stable within days, so this reaches every existing user.
- [ ] Store listing updated. Uploading a revision does not change it: push text and icon with `snapcraft upload-metadata <snap> --force`, and set screenshots, links and categories in the web dashboard.

## Windows installer

- [ ] PyInstaller onedir build succeeds on Windows.
- [ ] `npyquick.exe sample.npy` and `sample.npz` open.
- [ ] GUI opens by double-click.
- [ ] File → Open works.
- [ ] Drag-and-drop works.
- [ ] Installer runs without admin.
- [ ] Start Menu shortcut works.
- [ ] The npyquick icon shows in the title bar, on the taskbar button and on the Start Menu shortcut (CI cannot see this).
- [ ] In Explorer's list view, an associated `.npy` file shows the small bracket icon rather than a blur.
- [ ] `.npy/.npz` association is ticked by default on a fresh install and works; unticking it leaves the file types alone.
- [ ] Upgrading an install that had the association off keeps it off.
- [ ] Silent install and uninstall work.
- [ ] Uninstall removes Start Menu shortcut and app directory.
- [ ] Windows unsigned-build note is present in README/release notes.

## After a release

- [ ] Refresh the pinned dependencies for the next cycle, so the new versions get some use before they ship. `packaging/requirements.in` has the command and the reasons for any deliberate limit. Review the diff of `packaging/constraints.txt`, open a pull request, and let the packaging CI build and self-test all three packages.

## Release

Pushing the tag builds everything and opens a draft GitHub Release, then stops: the PyPI upload and the Snap upload each wait for approval of their environment (`pypi`, `snap-store`). Nothing is public until those are approved, so this is the point to check the packages. If something is wrong, delete the tag and the draft, fix it, and tag again.

- [ ] Tag is created from the final release commit.
- [ ] The draft GitHub Release has the AppImage and Windows setup.exe attached (GitHub shows a SHA-256 digest per asset).
- [ ] Those two packages have been installed and checked by hand (the per-package sections above) **before approving anything**. A PyPI upload cannot be undone.
- [ ] `pypi` environment approved; the upload succeeds.
- [ ] The PyPI project page shows the new README correctly; it only changes with a release.
- [ ] Release notes mention major changes and known Windows SmartScreen warning. Start from the version's section in `CHANGELOG.md`.
