<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/LiukDiihMieu/npyquick/main/docs/assets/logo-horizontal-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/LiukDiihMieu/npyquick/main/docs/assets/logo-horizontal-light.svg">
    <img alt="npyquick logo" src="https://raw.githubusercontent.com/LiukDiihMieu/npyquick/main/docs/assets/logo-horizontal-light.svg" width="400">
  </picture>
</p>

## Why npyquick?

Researchers often need to quickly inspect .npy and .npz files without writing a notebook, launching an IDE, or remembering the array shape in advance.

npyquick is designed as a small, practical viewer for this job:

* open NumPy array files directly from the terminal or file manager
* inspect common scientific data layouts immediately
* stay lightweight and easy to understand
* avoid turning a simple array viewer into a full image-processing application

<video src="https://github.com/user-attachments/assets/678de9e3-45c3-4b20-ba3a-f8350ad4d89d" autoplay loop muted playsinline width="800"></video>

## Installation

**Linux (AppImage):**

On x86-64 Linux, AppImage is available for one-click installation. Download `npyquick-x86_64.AppImage` from the [latest release](https://github.com/LiukDiihMieu/npyquick/releases/latest), then:

```bash
chmod +x npyquick-x86_64.AppImage
./npyquick-x86_64.AppImage path/to/file.npy
```

**With pip:**
```bash
pip install npyquick
```

**With conda:**
```bash
conda env create -f environment.yml
conda activate npyquick
```

The pip and conda installs need Python ≥ 3.10, NumPy, SciPy, Matplotlib, and PySide6.

## Usage

```bash
npyquick                        # open GUI
npyquick path/to/file.npy       # open with a file
npyquick path/to/file.npz       # open a multi-array archive
```

Files can be opened via **File › Open** (`Ctrl+O`) or by **dragging and dropping** onto the window.

## Features

### Image view

Preview 2D grayscale arrays and RGB arrays with interactive zoom, pan, colormap control, brightness adjustment, and a draggable cross-section profile.

![Image view of an RGB array](https://raw.githubusercontent.com/LiukDiihMieu/npyquick/main/docs/assets/screenshot-rgb.png)

### Histogram view

Inspect value distributions with linear or log-scaled counts, robust range selection, summary statistics, and NaN / Inf reporting.

![Histogram view](https://raw.githubusercontent.com/LiukDiihMieu/npyquick/main/docs/assets/screenshot-hist.png)

### Line Plot view

Display 1D signals and paired `(x, y)` arrays with interactive zoom, pan, reset, and optional log-scaled axes.

![Line plot view](https://raw.githubusercontent.com/LiukDiihMieu/npyquick/main/docs/assets/screenshot-line.png)

### Table view

Fallback preview for arrays that are not naturally displayed as images or line plots, including higher-dimensional, complex, object, scalar, or empty arrays.

![Table view](https://raw.githubusercontent.com/LiukDiihMieu/npyquick/main/docs/assets/screenshot-table.png)

### `.npz` archives

When a `.npz` archive contains multiple arrays, npyquick shows a key selector with each array's name, shape, and dtype. Switching the selected key reloads the active view.

![Open an .npz archive](https://raw.githubusercontent.com/LiukDiihMieu/npyquick/main/docs/assets/screenshot-npz.png)

For detailed display rules, normalization behavior, downsampling, and performance limits, see [Display behavior](docs/behavior.md).

## Keyboard shortcuts

| Shortcut         | Action                         |
| ---------------- | ------------------------------ |
| `Ctrl+O`         | Open file                      |
| `Ctrl+S`         | Export current figure          |
| `Ctrl+C`         | Copy current figure            |
| `Ctrl+Q`         | Quit                           |
| `F5` / `Ctrl+R`  | Reload current file            |
| `Ctrl+Tab`       | Switch to next enabled tab     |
| `Ctrl+Shift+Tab` | Switch to previous enabled tab |

## Linux desktop integration

Register npyquick as the handler for `.npy` / `.npz` files so you can double-click them in your file manager, or right-click → Open With:

```bash
npyquick --install-desktop
```

This installs a `.desktop` entry, the `.npy` / `.npz` MIME types, and the app icon under `~/.local/share` (user-level, no root). Then double-click a file, or test from the terminal:

```bash
xdg-open path/to/file.npy
```

To remove it:

```bash
npyquick --uninstall-desktop
```

Works on desktops that follow the freedesktop.org desktop-entry and MIME standards (GNOME, KDE Plasma, XFCE, Cinnamon, MATE). Some environments only show the new association after the file manager restarts or you log out and back in.

<details>
<summary>Manual setup (without the CLI command)</summary>

Create `~/.local/share/applications/npyquick.desktop`, replacing the `Exec=` path with the output of `which npyquick`:

```ini
[Desktop Entry]
Type=Application
Name=npyquick
Comment=Open NumPy array files
Exec=/path/to/npyquick %f
Icon=npyquick
Terminal=false
Categories=Science;Utility;
MimeType=application/x-npy;application/x-npz;
StartupNotify=true
```

Register the MIME types by creating `~/.local/share/mime/packages/npyquick.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-npy">
    <comment>NumPy array file</comment>
    <glob pattern="*.npy" weight="100"/>
  </mime-type>
  <mime-type type="application/x-npz">
    <comment>NumPy compressed archive</comment>
    <sub-class-of type="application/zip"/>
    <glob pattern="*.npz" weight="100"/>
  </mime-type>
</mime-info>
```

The `sub-class-of` and high glob weight matter for `.npz`: it is a ZIP container internally, so without them some desktops classify it as `application/zip` before the extension rule applies.

Then update the databases and set the default handler:

```bash
update-mime-database ~/.local/share/mime
update-desktop-database ~/.local/share/applications
xdg-mime default npyquick.desktop application/x-npy
xdg-mime default npyquick.desktop application/x-npz
```
</details>


## Roadmap

- [ ] `>2D` array slicer
- [ ] Complex array support: real / imaginary / magnitude / phase

## Contributing

Bug reports, feature requests, and suggestions are welcome — please open an [issue](https://github.com/LiukDiihMieu/npyquick/issues).

> The code in this repository is primarily written by an AI coding agent and reviewed by a human maintainer.

## License

Copyright 2026 LiukDiihMieu

This project is licensed under the **GNU General Public License v3.0 or later**. Project logo and visual assets are included for use with this project.
See the [LICENSE](LICENSE) file for details.