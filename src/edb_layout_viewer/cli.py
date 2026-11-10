# Copyright (C) 2023 - 2026 Contributors.
# SPDX-License-Identifier: Apache-2.0

"""Command-line entry point: open an EDB design in the layout viewer."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Sequence

from edb_layout_viewer.viewer.launch import launch_viewer


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"expected a boolean (true/false), got {value!r}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="edb-layout-viewer",
        description="Open an EDB design (.aedb directory) in the interactive layout viewer.",
    )
    parser.add_argument(
        "design",
        type=Path,
        nargs="?",
        help="Path to the .aedb design directory. If omitted, select edb.def in a file dialog.",
    )
    parser.add_argument("--edbversion", help='EDB version, for example "2025.1". Defaults to PyEDB detection.')
    parser.add_argument(
        "--layers",
        nargs="+",
        metavar="LAYER",
        help="Layer names to include. Repeat the option or list several names.",
        action="extend",
    )
    parser.add_argument(
        "--nets",
        nargs="+",
        metavar="NET",
        help="Net names to include. Repeat the option or list several names.",
        action="extend",
    )
    parser.add_argument(
        "--backend",
        choices=["auto", "vulkan", "d3d11", "metal"],
        help="Rendering API. Defaults to PYEDB_VIEWER_BACKEND or auto.",
    )
    parser.add_argument(
        "--live",
        nargs="?",
        const=True,
        default=False,
        type=_parse_bool,
        metavar="{true,false}",
        help="Automatically refresh the viewer after supported PyEDB gRPC geometry edits. Default is false.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Log and re-raise capture exceptions with a full traceback.",
    )
    return parser


def _open_edb(design: Path, edbversion: str | None) -> Any:
    from pyedb import Edb

    if edbversion is None:
        return Edb(str(design))
    return Edb(str(design), edbversion=edbversion)


def _select_edb_file() -> Path | None:
    from layout_viewer_core.qt.app import _get_application
    from PySide6.QtWidgets import QFileDialog

    _get_application()
    filename, _ = QFileDialog.getOpenFileName(
        None,
        "Select EDB design",
        "",
        "EDB definition (edb.def)",
    )
    return Path(filename) if filename else None


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.design is None:
        selected = _select_edb_file()
        if selected is None:
            return 0
        if selected.name.lower() != "edb.def" or not selected.is_file():
            parser.error(f"select an existing edb.def file: {selected}")
        args.design = selected.parent
    if not args.design.is_dir():
        parser.error(f"design directory not found: {args.design}")

    edb = _open_edb(args.design, args.edbversion)
    launch_viewer(
        edb,
        layers=args.layers,
        nets=args.nets,
        backend=args.backend,
        live=args.live,
        debug=args.debug,
        block=True,
    )
    return 0
