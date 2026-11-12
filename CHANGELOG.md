# Changelog

Notable changes to npyquick, newest first. Versions before 0.1.5 are described
on the [GitHub Releases](https://github.com/LiukDiihMieu/npyquick/releases) page.

## 0.1.5 (2026-11-12)

### Added

- **File › Open Recent** lists the last eight files.
- The `vmin` / `vmax` markers in the Histogram view can be dragged, and the image follows live.
- Dragging a file over the window shows a drop target.
- The View menu shows a gradient swatch next to each colormap.
- The window now has its own icon in the title bar and on the taskbar. On Windows these used to show a generic icon.
- `npyquick --self-test` checks that an installed copy can load files and export plots, and prints a report to attach to a bug report.

### Changed

- New application icon: the mark sits on a plate, so its brackets no longer vanish on a dark dock or taskbar, and small sizes use a simplified version that stays readable at 16 px.
- The Windows installer ticks "Associate .npy and .npz files with npyquick" by default. It is still a checkbox, and upgrading keeps your earlier choice.
- Warning labels follow the light or dark theme, including when the system theme changes while npyquick is running.
- The README install instructions are reorganised by platform, and recommend `uv` or `pipx` for installing from PyPI.

### Fixed

- A `.npz` archive with an upper-case extension (`DATA.NPZ`) failed to open with "the magic string is not correct". The file type is now detected from the file's contents, so a missing or wrong extension works too.
- The documentation claimed that object arrays (`dtype=object`) open in the Table view. They never did and still do not: NumPy stores them with pickle, which npyquick refuses to load because reading a pickle can run code from the file.
