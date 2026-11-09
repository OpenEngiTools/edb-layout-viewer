# Copyright (C) 2023 - 2026 Contributors.
# SPDX-License-Identifier: Apache-2.0

"""Optional frontend dependency checks."""

_INSTALL_HINT = "The layout viewer requires optional dependencies: pip install layout-viewer."


def require_layout_viewer() -> None:
    """Raise an actionable error when the optional frontend is not installed."""
    try:
        import layout_viewer  # noqa: F401
    except ImportError as exc:
        raise ImportError(_INSTALL_HINT) from exc
