# npyquick

A fast, lightweight GUI viewer for NumPy arrays (`.npy` / `.npz`), built with PySide6 and Matplotlib.

## Installation

**With conda (recommended):**
```bash
conda env create -f environment.yml
conda activate npyquick
```

**With pip only:**
```bash
pip install -e .
```

Dependencies: Python ≥ 3.10, NumPy, SciPy, Matplotlib, PySide6.

## Usage

```bash
npyquick                        # open GUI
npyquick path/to/file.npy       # open with a file
npyquick path/to/file.npz       # open a multi-array archive
```

Files can also be opened via **File › Open** (Ctrl+O) or by dragging and dropping onto the window.

## Features

### Image view
Displays 2D and RGB arrays as an interactive image.

**Supported formats:**
- 2D numeric arrays — any dtype (float32/64, uint8/16, int16/32, …)
- `(H, W, 3)` RGB arrays — uint8, uint16, and float32/64

**Normalization (RGB only):** uint8 is displayed directly in [0, 255] with no scaling; other integer types are scaled by their dtype maximum (e.g. uint16 ÷ 65535); float arrays outside [0, 1] are globally min-max stretched. The applied strategy is shown in the control bar.

**Interactions:**
- Scroll to zoom, left-drag to pan, double-click to reset zoom
- Two draggable endpoints define a cross-section line; the live intensity profile is shown in a side panel
- Colormap selector (**View › Colormap**) for grayscale images: gray, viridis, plasma, inferno, magma, cividis, hot, coolwarm, RdBu, turbo
- Manual brightness range via vmin / vmax inputs

### Histogram view
Shows the value distribution of any real numeric array (1D, 2D, RGB, or higher-dimensional). NaN/Inf values are excluded and reported separately.

**Controls:**
- Bin count selector: auto, 64, 128, 256, 512
- Log-scale toggle for the count axis
- X-range buttons: **Full** (entire data extent) and **Robust** (p2–p98), plus scroll-to-zoom on the x-axis
- Summary line with min, max, mean, std and the p1 / p50 / p99 percentiles
- Anomaly count (NaN / Inf) highlighted in red when present

**Interactions:**
- Hover over a bar to read its `[lo, hi)` range and count in the status bar
- When a 2D image is loaded, the image's current vmin / vmax appear as labelled dashed markers, kept in sync with the Image view's brightness range

### Line Plot view
Displays 1D signals and paired (x, y) datasets as an interactive line plot.

**Supported formats:**
- `(N,)` real numeric arrays — x axis is the element index
- `(2, N)` real numeric arrays with N > 2 — row 0 as x values, row 1 as y values
- `(N, 2)` real numeric arrays with N > 2 — column 0 as x values, column 1 as y values

For `(2, N)` and `(N, 2)` arrays the x axis uses the raw values stored in the data; physical units and spacing are the user's responsibility.

**Interactions:**
- Scroll to zoom x axis, **Shift + scroll** to zoom y axis, both centred on the cursor
- Left-drag to pan both axes freely
- Double-click to reset zoom (restores matplotlib's default 5 % margin on both axes)

**Controls:**
- **Log X / Log Y** checkboxes — switches each axis to logarithmic scale; automatically disabled when the data has no positive values
- **Reset** button — resets zoom to show all data

Large arrays are downsampled for display (budget: 1 M points); the original data is always used for hover readout (status bar shows index or x value, and y value).

### Table view
Fallback for any array shape or dtype that the image view cannot display (1D, >2D, non-numeric, empty, scalar, complex). Rows and columns are capped at 10 000 to keep large arrays usable.

### .npz support
When a `.npz` archive contains multiple arrays, a dropdown appears above the tabs listing each key with its shape and dtype. Switching the selection immediately reloads the active view.

## Linux desktop integration

You can register npyquick as an "Open With" application for `.npy` and `.npz`
files on Linux desktops that follow the freedesktop.org desktop entry and MIME
standards. This includes common desktop environments such as GNOME, KDE Plasma,
XFCE, Cinnamon, and MATE. It is not Ubuntu-specific, but exact file-manager
menus may vary by distribution and desktop environment.

This setup assumes npyquick is already installed in a working environment and
can open files from the command line:

```bash
npyquick path/to/file.npy
npyquick path/to/file.npz
```

First, find the absolute path to the executable:

```bash
which npyquick
```

For a conda environment, this may look like:

```bash
/opt/miniconda3/envs/npyquick/bin/npyquick
```

Create `~/.local/share/applications/npyquick.desktop` and replace the `Exec=`
path with the path reported by `which npyquick`:

```ini
[Desktop Entry]
Type=Application
Name=npyquick
Comment=Open NumPy array files
Exec=/opt/miniconda3/envs/npyquick/bin/npyquick %f
Icon=utilities-terminal
Terminal=false
Categories=Science;Utility;
MimeType=application/x-npy;application/x-npz;
StartupNotify=true
```

Register MIME types for `.npy` and `.npz` by creating
`~/.local/share/mime/packages/npyquick.xml`:

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

The high glob weight is important for `.npz`: because an `.npz` file is a ZIP
container internally, some desktops otherwise classify it as `application/zip`
before the extension-specific rule is applied.

Update the desktop and MIME databases, then set npyquick as the default handler:

```bash
update-mime-database ~/.local/share/mime
update-desktop-database ~/.local/share/applications
xdg-mime default npyquick.desktop application/x-npy
xdg-mime default npyquick.desktop application/x-npz
```

Test the association:

```bash
xdg-open path/to/file.npy
xdg-open path/to/file.npz
```

After this, most Linux file managers should show npyquick in the "Open With"
menu for `.npy` and `.npz` files. Some desktop environments may require
restarting the file manager or logging out and back in before the menu updates.

## TODO

- [ ] `>2D` array slicer
- [ ] Complex array support (real / imaginary / magnitude / phase)
