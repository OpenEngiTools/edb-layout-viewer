"""Top-level EDB-to-scene orchestration."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

from layout_viewer.scene import LayoutScene, SceneJoin, SceneLayer, ScenePad, ScenePolygon, SceneTrace

from viewer_adapter.diagnostics import _Diagnostics
from viewer_adapter.scene._builder.components import _components
from viewer_adapter.scene._builder.layers import _layer_names_by_id
from viewer_adapter.scene._builder.padstacks import _padstacks
from viewer_adapter.scene._builder.primitives import _primitives, _scene_filters

if TYPE_CHECKING:
    from pyedb.grpc.edb import Edb

    Progress = Callable[[str, int, int], None]


def scene_from_edb(
    edb: Edb,
    layers: str | Iterable[str] | None = None,
    nets: str | Iterable[str] | None = None,
    arc_segments: int | None = None,
    *,
    progress: Progress | None = None,
    analytic_traces: bool = True,
    exact_component_bounds: bool = False,
    chord_error: float | None = 0.002,
    preview: Callable[[LayoutScene], None] | None = None,
    debug: bool = False,
) -> LayoutScene:
    """Capture analytic traces, per-layer pads and zone contours in millimeters.

    When ``debug`` is True, any exception caught internally while inspecting
    layout objects is logged with a full traceback and re-raised immediately
    instead of being recorded as a diagnostic note and skipped.
    """
    if not edb.grpc:
        raise ValueError("The interactive layout viewer currently supports only the gRPC backend.")
    if arc_segments is not None and (
        isinstance(arc_segments, bool) or not isinstance(arc_segments, int) or arc_segments < 3
    ):
        raise ValueError("arc_segments must be an integer of at least three.")
    if arc_segments is None:
        if (
            isinstance(chord_error, bool)
            or not isinstance(chord_error, (int, float))
            or not math.isfinite(chord_error)
            or chord_error <= 0
        ):
            raise ValueError("chord_error must be a positive finite number in millimeters.")
        arc_segments = 8  # Only a fallback count; adaptive chords determine the actual tessellation.
    else:
        chord_error = None
    if progress is not None:
        progress("Reading polygons", 0, 0)
    # Fetch once: edb.stackup.layers wraps every stackup layer from the EDB
    # server, so every helper below reuses this instead of refetching it.
    layout_layers = edb.stackup.layers
    selected_layers, selected_nets = _scene_filters(edb, layers, nets, layout_layers)
    scene_layers = []
    for name, layer in layout_layers.items():
        if name in selected_layers:
            color = tuple(float(v) / 255.0 for v in layer.color[:3])
            scene_layers.append(SceneLayer(name, (*color, 1.0)))
    diagnostics = _Diagnostics(debug=debug)
    object_info = {}
    net_names = tuple(edb.nets.nets)
    title = edb.active_cell.name

    def publish(
        polygons: list[ScenePolygon], traces: list[SceneTrace], joins: list[SceneJoin], pads: list[ScenePad]
    ) -> None:
        if preview is not None and (polygons or traces or pads):
            preview(
                LayoutScene(
                    tuple(scene_layers),
                    tuple(polygons),
                    title,
                    traces=tuple(traces),
                    pads=tuple(pads),
                    joins=tuple(joins),
                    net_names=net_names,
                    object_info=tuple(object_info.values()),
                )
            )

    priority_layer = scene_layers[0].name if preview is not None and scene_layers else None
    polygons, traces, joins, pads = _primitives(
        edb,
        selected_layers,
        selected_nets,
        arc_segments,
        diagnostics,
        progress,
        analytic_traces,
        chord_error,
        publish if priority_layer is not None else None,
        priority_layer,
        object_info,
        _layer_names_by_id(layout_layers),
    )
    publish(polygons, traces, joins, pads)
    component_geometry = None if exact_component_bounds else {}
    via_pads, via_polygons = _padstacks(
        edb,
        selected_layers,
        selected_nets,
        arc_segments,
        diagnostics,
        progress,
        component_geometry,
        chord_error,
        object_info,
        layout_layers,
    )
    pads.extend(via_pads)
    polygons.extend(via_polygons)
    components = _components(
        edb, selected_layers, selected_nets, diagnostics, progress, component_geometry, layout_layers
    )
    diagnostics.append(
        "GPU copper and component envelopes/references; arbitrary text, 3D bodies and bondwires are not displayed."
    )
    return LayoutScene(
        tuple(scene_layers),
        tuple(polygons),
        title,
        tuple(diagnostics),
        traces=tuple(traces),
        pads=tuple(pads),
        joins=tuple(joins),
        net_names=net_names,
        components=components,
        object_info=tuple(object_info.values()),
    )
