# Display behavior

This document describes how npyquick decides which view to use, how arrays are displayed, and what simplifications are applied for performance.

The goal is to keep the GUI responsive while preserving the original array data for inspection whenever possible.

## File loading

npyquick supports:

* `.npy` files containing a single NumPy array
* `.npz` files containing one or more arrays

For `.npz` files, the GUI shows a key selector listing each array's name, shape, and dtype. Selecting a different key reloads the current view using that array.

## View selection

npyquick provides four main views:

* Image view
* Histogram view
* Line Plot view
* Table view

Some views are only enabled when the selected array has a compatible shape and dtype. When an array does not naturally fit an image, histogram, or line plot representation, the Table view is used as a fallback preview.

## Image view

### Supported arrays

The Image view supports:

* 2D numeric arrays as grayscale images
* `(H, W, 3)` numeric arrays as RGB images
* 2D complex arrays, shown as two panels (real / imaginary or absolute value / argument)

Other shapes are not shown in the Image view by default.

### Grayscale arrays

2D numeric arrays are displayed as grayscale images.

The visible brightness range can be adjusted with `vmin` and `vmax` controls. The selected range is also reflected in the Histogram view when applicable.

Available colormaps include:

* gray
* viridis
* plasma
* inferno
* magma
* cividis
* twilight (cyclic, suited to phase/angle data)
* hot
* coolwarm
* RdBu
* turbo

Any colormap can be flipped with the **Reverse** option.

### RGB arrays

RGB arrays must have shape `(H, W, 3)`.

The display normalization depends on dtype and value range:

* `uint8` arrays are displayed directly in `[0, 255]`.
* Other integer arrays are scaled by their dtype maximum, for example `uint16 / 65535`.
* Floating-point arrays already inside `[0, 1]` are displayed directly.
* Floating-point arrays outside `[0, 1]` are min-max stretched globally for display.

The selected RGB normalization strategy is shown in the control bar.

### Complex arrays

A 2D complex array is shown as two side-by-side image panels. By default the panels show the real and imaginary parts (`Real`, `Imag`); a **Component** selector in the top bar switches them to absolute value (magnitude) and argument (phase), labelled `Abs` and `Angle`.

The two panels share a single zoom/pan and a single cross-section line, so they always show the same region. Clicking a panel makes it the active one: the cross-section profile and the `vmin` / `vmax` controls then follow that panel, and the controls are labelled with its component. The `Angle` panel shows phase in radians and defaults to a fixed `(-π, π]` range. `Reset` restores both panels.

### Image interactions

The Image view supports:

* scroll to zoom
* left-drag to pan
* double-click to reset zoom
* draggable cross-section endpoints
* live intensity profile along the selected cross-section line

The cross-section is intended as a quick inspection tool, not as a replacement for full quantitative analysis scripts.

## Histogram view

The Histogram view shows the value distribution of real numeric arrays. Complex arrays are also supported: a **Component** selector in the top bar chooses which real-valued component (`Real`, `Imag`, `Abs`, or `Angle`, default `Abs`) is histogrammed, and switching it re-bins that component.

Supported inputs include:

* 1D arrays
* 2D arrays
* RGB arrays
* higher-dimensional real numeric arrays
* complex arrays (via the component selector)

NaN and Inf values are excluded from the histogram and reported separately. For a complex array, a value counts as an anomaly when either its real or imaginary part is NaN or Inf.

### Histogram controls

The Histogram view supports:

* bin count selection: auto, 64, 128, 256, 512
* linear or log-scaled count axis
* full-range display
* robust-range display using the p2–p98 percentile range
* x-axis zooming by scroll
* summary statistics: min, max, mean, std, p1, p50, p99

When a 2D image is loaded, the current Image view `vmin` and `vmax` are shown as labelled dashed markers in the Histogram view.

## Line Plot view

The Line Plot view is intended for 1D signals and simple paired `(x, y)` datasets.

### Supported arrays

The Line Plot view supports:

* `(N,)` real numeric arrays
  The x-axis is the element index.
* `(2, N)` real numeric arrays with `N > 2`
  Row 0 is interpreted as x values, and row 1 as y values.
* `(N, 2)` real numeric arrays with `N > 2`
  Column 0 is interpreted as x values, and column 1 as y values.

Other shapes are not shown in the Line Plot view by default.

### Line plot interactions

The Line Plot view supports:

* scroll to zoom the x-axis
* `Shift + scroll` to zoom the y-axis
* left-drag to pan
* double-click to reset zoom
* optional log scaling for x and y axes

Log scaling is disabled automatically when the corresponding data has no positive values.

### Downsampling

Large arrays may be downsampled for display to keep the GUI responsive.

The current display budget is 1,000,000 points. When a line plot exceeds this budget, npyquick draws a reduced representation for display.

The original array is still kept internally and is used for readout where possible. Downsampling is only a display optimization.

## Table view

The Table view is the fallback preview for arrays that are not naturally displayed by the Image or Line Plot views.

Examples include:

* higher-dimensional arrays
* complex arrays that are not 2D
* object arrays
* scalar arrays
* empty arrays
* unsupported image-like shapes

To keep very large arrays usable, displayed rows and columns are capped.

The current display cap is 2,000 rows and 2,000 columns. This cap only affects the table preview, not the original loaded array.

## Performance notes

npyquick is designed for quick inspection, not as a full analysis environment.

For very large arrays, the GUI may simplify the displayed representation by:

* downsampling line plots
* capping table rows and columns
* excluding NaN / Inf values from histograms
* using display normalization for RGB images
* computing complex components only for the displayed (downsampled) data

These choices are intended to keep preview interactions responsive while making the applied behavior visible to the user.
