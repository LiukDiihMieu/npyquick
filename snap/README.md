# npyquick (Snap)

Snap packaging for npyquick. Build locally with:

```sh
snapcraft pack --use-lxd
```

## Opening files

The Snap is strictly confined. **File ▸ Open** (Ctrl+O) opens any file you pick —
it goes through the desktop portal, so it reaches files anywhere, including other
drives. Drag-and-drop is limited by the sandbox to your home folder (and
removable media once that interface is connected).

### Double-clicking in the file manager

Out of the box, double-clicking a `.npy` / `.npz` won't launch npyquick: a Snap
can't register new file types with the host, so the desktop doesn't recognise
these extensions as npyquick's. It can be enabled with a one-time MIME
registration on the host — see "Linux desktop integration" in the top-level
README. (This is a Snap/desktop-integration gap, not the sandbox — classic snaps
have it too.)
