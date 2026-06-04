# npyquick

A fast, clean NumPy array viewer built with PySide6 and Matplotlib.

## Features

### File handling
- Open `.npy` and `.npz` files via menu (Ctrl+O) or drag and drop
- `.npz` files with multiple arrays show an array picker dropdown
- Remembers last-used directory, colormap, and window size across sessions

### Image view (2D grayscale and RGB)
- Supports `(H, W)` numeric arrays and `(H, W, 3)` RGB arrays
- Scroll to zoom, left-click drag to pan, double-click to reset zoom
- Colormap switching via **View › Colormap** menu (grayscale only): gray, viridis, plasma, inferno, magma, cividis, hot, coolwarm, RdBu, turbo
- Manual vmin/vmax control with Apply and Reset buttons

### Cross-section profile
- Adjustable line with two draggable endpoints overlaid on the image
- Live profile plot beside the image
- Grayscale: single intensity line; RGB: three colored lines (R/G/B)

### Status bar
- Hover pixel coordinates and value (`val` for grayscale, `R G B` for RGB)
- Endpoint positions always visible alongside hover info
- Switches to array shape/dtype info when Table tab is active

### Table view
- Fallback for any array shape or dtype
- Lazy loading via `QAbstractTableModel` — safe for very large arrays (capped at 10,000 rows × 10,000 columns)
- `(H, W, 3)` RGB arrays shown as three side-by-side channel tables (R, G, B)

### Architecture
- Clean MVC separation: `NpyDataModel`, `BaseView` subclasses, thin `MainWindow`
- Tab enable/disable driven by `compatible_views()` — invalid views are greyed out, never shown with errors
- Easy to extend: add a new `views/foo.py` and register it in `app.py`

## TODO

- [ ] 1D array / time series view
- [ ] 3D point cloud view (`(N, 3)` arrays)
- [ ] Handle `>2D` arrays gracefully (slice selector)

## Requirements

See `requirements.txt`. Built on PySide6, Matplotlib, NumPy, SciPy.

## Usage

```bash
python -m npyquick              # open GUI
python -m npyquick path/to.npy  # open with file
```
