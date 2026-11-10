# Copyright (C) 2023 - 2026 Contributors.
# SPDX-License-Identifier: Apache-2.0

"""Build incremental scene updates from EDB layout-change notifications."""

from __future__ import annotations

from types import SimpleNamespace

from layout_viewer_core.scene import LayoutScene

from edb_layout_viewer.diagnostics import _Diagnostics
from edb_layout_viewer.scene.builder import _padstacks, _primitives
from edb_layout_viewer.scene.filters import normalize_names


def scene_patch_from_edb(
    edb, delta, previous, *, nets=None, arc_segments=None, analytic_traces=False, chord_error=0.002, progress=None
):
    """Read only notified copper handles; never enumerate the layout or its nets.

    Layer metadata comes from the accepted snapshot. Changes with global or
    unknown dependencies are routed to full capture before reaching here.
    Incremental extraction is strict: a failed object must not silently erase
    its previously displayed geometry.
    """
    diagnostics = _Diagnostics(debug=True)
    from pyedb.grpc.database.layout_changes import PadstackSource

    vias = tuple(source.core for _, source in delta.upserts if isinstance(source, PadstackSource))
    primitives = tuple(source for _, source in delta.upserts if not isinstance(source, PadstackSource))
    info = {}
    polygons, traces, joins, pads = _primitives(
        edb,
        {layer.name for layer in previous.layers},
        normalize_names(nets),
        arc_segments or 8,
        diagnostics,
        progress,
        analytic_traces,
        chord_error if arc_segments is None else None,
        object_info=info,
        source_primitives=primitives,
    )
    if vias:
        # Read small stackup metadata, but never enumerate board pads or
        # components. Component-owned pins use the full-capture fallback.
        layout_layers = edb.stackup.layers
        isolated = SimpleNamespace(
            stackup=SimpleNamespace(layers=layout_layers, signal_layers=edb.stackup.signal_layers),
            layout=SimpleNamespace(core=SimpleNamespace(padstack_instances=vias)),
            components=None,
            isreadonly=False,
        )
        via_pads, via_polygons = _padstacks(
            isolated,
            {layer.name for layer in previous.layers},
            normalize_names(nets),
            arc_segments or 8,
            diagnostics,
            progress,
            None,
            chord_error if arc_segments is None else None,
            info,
            layout_layers,
        )
        pads.extend(via_pads)
        polygons.extend(via_polygons)
    return LayoutScene(
        previous.layers,
        tuple(polygons),
        previous.title,
        tuple(diagnostics),
        traces=tuple(traces),
        joins=tuple(joins),
        pads=tuple(pads),
        object_info=tuple(info.values()),
    )
