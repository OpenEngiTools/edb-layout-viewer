# Copyright (C) 2023 - 2026 Contributors.
# SPDX-License-Identifier: Apache-2.0

"""EDB integration for the layout viewer. Importing this module does not load Qt."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from viewer_adapter.viewer.launch import launch_viewer

if TYPE_CHECKING:
    from viewer_adapter.scene.builder import scene_from_edb

__all__ = ["launch_viewer", "scene_from_edb"]


def __getattr__(name: str) -> Any:
    if name == "scene_from_edb":
        from viewer_adapter.scene.builder import scene_from_edb

        return scene_from_edb
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
