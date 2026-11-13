# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 LiukDiihMieu

from __future__ import annotations

import argparse
import sys

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="npyquick serve",
        description=(
            "Serve a web viewer for a .npy / .npz array. Intended to run on a "
            "remote machine and be reached from a laptop browser via an SSH "
            "port-forward, e.g.:\n"
            "  ssh -L 8765:localhost:8765 remote-host\n"
            "  npyquick serve /path/on/remote/array.npy"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "file", nargs="?", help="Path to a .npy or .npz file to open on launch"
    )
    parser.add_argument(
        "--host", default=DEFAULT_HOST,
        help=f"Bind address (default: {DEFAULT_HOST} — localhost only, use with an SSH tunnel)",
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help=f"Bind port (default: {DEFAULT_PORT})"
    )
    args = parser.parse_args(argv)

    try:
        import nicegui  # noqa: F401
        import plotly  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "npyquick serve requires the 'serve' extra: pip install npyquick[serve]"
        ) from exc

    from npyquick.serve.app import run_server

    run_server(args.file, host=args.host, port=args.port)


if __name__ == "__main__":
    main(sys.argv[1:])
