# Copyright (C) 2023 - 2026 Contributors.
# SPDX-License-Identifier: Apache-2.0

"""EDB integration for the layout viewer. Importing this module does not load Qt."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from viewer_adapter.viewer._dependencies import require_layout_viewer
from viewer_adapter.viewer.launch import launch_viewer

if TYPE_CHECKING:
    from layout_viewer.scene import LayoutScene

__all__ = ["launch_viewer", "scene_from_edb"]


def scene_from_edb(
    edb: Any,
    layers: str | list[str] | None = None,
    nets: str | list[str] | None = None,
    arc_segments: int | None = None,
    *,
    progress: Callable[[str, int, int], None] | None = None,
    analytic_traces: bool = True,
    exact_component_bounds: bool = False,
    chord_error: float = 0.002,
    preview: Callable[..., Any] | None = None,
    debug: bool = False,
) -> LayoutScene:
    """Capture detached millimeter-based geometry.

    ``progress(stage, completed, total)`` optionally reports completed items in
    the current stage. A zero total means the amount of work is not yet known.
    When ``debug`` is True, exceptions caught during capture are logged with a
    full traceback and re-raised immediately instead of being recorded as a
    diagnostic note and skipped.
    """
    require_layout_viewer()
    from viewer_adapter.scene.builder import scene_from_edb as extract

    return extract(
        edb,
        layers=layers,
        nets=nets,
        arc_segments=arc_segments,
        progress=progress,
        analytic_traces=analytic_traces,
        exact_component_bounds=exact_component_bounds,
        chord_error=chord_error,
        preview=preview,
        debug=debug,
    )
