# Copyright (C) 2023 - 2026 Contributors.
# SPDX-License-Identifier: Apache-2.0

"""Entry point for the windowed PyInstaller build.

The frozen executable has no console, so output goes to a log file next to the
executable and errors are shown in a message box instead of being lost.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

LOG_PATH = Path(sys.executable).with_name("edb-layout-viewer.log")


def _redirect_streams() -> None:
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        log = open(LOG_PATH, "w", encoding="utf-8", buffering=1)  # noqa: SIM115
    except OSError:
        import io

        log = io.StringIO()
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log


def _show_error(message: str) -> None:
    title = "EDB Layout Viewer"
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        _app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, title, message)
    except Exception:  # noqa: BLE001 - fall back to a native dialog if Qt is unusable
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)


def run() -> int:
    _redirect_streams()
    try:
        from edb_layout_viewer.cli import main

        return main()
    except SystemExit as exc:
        if exc.code not in (0, None):
            _show_error(f"Invalid arguments (exit code {exc.code}). See {LOG_PATH} for details.")
        raise
    except Exception:  # noqa: BLE001 - top-level handler for the windowed app
        text = traceback.format_exc()
        print(text, file=sys.stderr, flush=True)
        _show_error(f"{text[-3000:]}\n\nFull log: {LOG_PATH}")
        return 1


if __name__ == "__main__":
    sys.exit(run())
