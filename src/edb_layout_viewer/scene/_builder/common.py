"""Shared internal scene-builder values."""

from typing import TYPE_CHECKING

_UNSET = object()

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from layout_viewer_core.scene import Point

    Progress = Callable[[str, int, int], None]
    Placement = tuple[Callable[[Point], Point], Callable[[Point], Point], float]
    PinOwner = dict[str, Any]
