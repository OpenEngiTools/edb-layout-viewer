"""Component envelope collection for scene construction."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from layout_viewer.progress import progress_items
from layout_viewer.scene import SceneComponent, union_bounds

from viewer_adapter.diagnostics import _record_exception
from viewer_adapter.layer_metadata import _component_sides

if TYPE_CHECKING:
    from pyedb.grpc.edb import Edb

    Progress = Callable[[str, int, int], None]


def _components(
    edb: Edb,
    selected_layers: set[str],
    selected_nets: set[str] | None,
    diagnostics: list[str],
    progress: Progress | None = None,
    component_geometry: dict[Any, Any] | None = None,
    layout_layers: dict[str, Any] | None = None,
) -> tuple[SceneComponent, ...]:
    """Reuse captured pad envelopes, falling back to source bounds when needed."""
    manager = getattr(edb, "components", None)
    if manager is None:
        return ()
    sides = _component_sides(edb, diagnostics, layout_layers)
    if not sides:
        return ()
    net_filter = set(edb.nets.nets) if selected_nets is None else selected_nets
    result = []
    approximate_count = 0
    for reference, component in progress_items(manager.instances.items, progress, "Reading components"):
        try:
            if not component.is_enabled:
                continue
            layer = component.placement_layer
            if layer not in selected_layers or layer not in sides:
                continue
            captured = (component_geometry or {}).get(component.id) if selected_nets is None else None
            if captured is None and selected_nets is None and component_geometry:
                # Some component pads are not marked as layout pins and their
                # instance.component getter is null. Membership still identifies
                # them, without constructing a full-board layout instance.
                by_id = component_geometry.get("instances", {})
                members = getattr(getattr(component, "core", None), "members", ())
                records = [by_id[member.edb_uid] for member in members if member.edb_uid in by_id]
                if records:
                    captured = {
                        "bounds": union_bounds([record["bounds"] for record in records]),
                        "nets": set().union(*(record["nets"] for record in records)),
                        "approximate": any(record["approximate"] for record in records),
                    }
            nets = tuple(sorted(captured["nets"])) if captured is not None else tuple(component.nets)
            if (selected_nets is not None or net_filter) and not net_filter.intersection(nets):
                continue
            bounds = (
                captured["bounds"] if captured is not None else tuple(float(v) * 1000 for v in component.bounding_box)
            )
            if captured is not None and captured.get("approximate", False):
                # Copper-free SMT pins still locate the footprint. A modest
                # display margin avoids a full-board layout-instance build.
                x0, y0, x1, y1 = bounds
                margin = max(max(x1 - x0, y1 - y0) * 0.1, 0.05)
                bounds = x0 - margin, y0 - margin, x1 + margin, y1 + margin
                approximate_count += 1
            result.append(SceneComponent(component.id, component.name, layer, nets, bounds, sides[layer]))
        except Exception as exc:  # noqa: BLE001
            _record_exception(diagnostics, f"Component {reference}: {exc}", exc)
    if approximate_count:
        diagnostics.append(f"{approximate_count} component envelopes estimated from pin positions for fast display.")
    return tuple(result)
