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

**Normalization (RGB only):** integer types are scaled by their dtype maximum (e.g. uint16 ÷ 65535); float arrays outside [0, 1] are globally min-max stretched. The applied strategy is shown in the control bar.

**Interactions:**
- Scroll to zoom, left-drag to pan, double-click to reset zoom
- Two draggable endpoints define a cross-section line; the live intensity profile is shown in a side panel
- Colormap selector (**View › Colormap**) for grayscale images: gray, viridis, plasma, inferno, magma, cividis, hot, coolwarm, RdBu, turbo
- Manual brightness range via vmin / vmax inputs

### Table view
Fallback for any array shape or dtype that the image view cannot display (1D, >2D, non-numeric, empty, scalar). Rows and columns are capped at 10 000 to keep large arrays usable.

### .npz support
When a `.npz` archive contains multiple arrays, a dropdown appears above the tabs listing each key with its shape and dtype. Switching the selection immediately reloads the active view.

## TODO

- [ ] Histogram panel
- [ ] `>2D` array slicer
- [ ] 1D / time-series view
- [ ] Complex array support (real / imaginary / magnitude / phase)
