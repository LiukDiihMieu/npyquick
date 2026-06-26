# npyquick (Snap)

Snap packaging for npyquick. Build locally with:

```sh
snapcraft pack --use-lxd
```

## Opening files

The Snap is strictly confined, so it reads files in your home directory (and
removable media once that interface is connected). To open an array:

- **Drag and drop** a `.npy` or `.npz` file onto the window — the quickest way.
- Or use **File ▸ Open**.

### Why double-click doesn't open npyquick

Double-clicking a `.npy` / `.npz` in the file manager will not launch npyquick.
A Snap cannot register new file types with the host system, so the desktop
doesn't recognise these extensions as belonging to npyquick. This is a
limitation of how Snaps integrate with the system, not a setting we can flip
in the package (it is unrelated to the sandbox — the same gap exists without
strict confinement).

Open npyquick from the application menu, then drag a file in or use File ▸ Open.
