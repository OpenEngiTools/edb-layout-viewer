"""Primitive filtering and geometry collection."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from typing import TYPE_CHECKING, Any

from ansys.edb.core.database import ProductIdType
from layout_viewer.progress import progress_items
from layout_viewer.scene import SceneJoin, SceneObjectInfo, ScenePad, ScenePolygon, SceneTrace

from viewer_adapter.diagnostics import _record_exception
from viewer_adapter.layer_metadata import _conductor_names
from viewer_adapter.scene._builder.geometry import _contour, _trace_geometry
from viewer_adapter.scene._builder.layers import _cached_name, _primitive_layer_name
from viewer_adapter.scene.filters import normalize_names

if TYPE_CHECKING:
    from ansys.edb.core.primitive.primitive import Primitive
    from pyedb.grpc.edb import Edb

    Progress = Callable[[str, int, int], None]
    ScenePrimitives = tuple[list[ScenePolygon], list[SceneTrace], list[SceneJoin], list[ScenePad]]

_PRIMITIVE_NAME_PREFIX = {"path": "line", "rectangle": "rect", "polygon": "poly", "bondwire": "bwr"}


def _scene_filters(
    edb: Edb,
    layers: str | Iterable[str] | None,
    nets: str | Iterable[str] | None,
    layout_layers: dict[str, Any] | None = None,
) -> tuple[set[str], set[str] | None]:
    """Normalize filters and reject names outside the source layout."""
    selected_layers, selected_nets = normalize_names(layers), normalize_names(nets)
    source_layers = edb.stackup.layers if layout_layers is None else layout_layers
    if selected_layers is None:
        selected_layers = set(_conductor_names(edb, source_layers))
    unknown = selected_layers.difference(source_layers)
    if unknown:
        raise ValueError(f"Unknown layers: {', '.join(sorted(unknown))}")
    if selected_nets is not None:
        unknown = selected_nets.difference(edb.nets.nets)
        if unknown:
            raise ValueError(f"Unknown nets: {', '.join(sorted(unknown))}")
    return selected_layers, selected_nets


def _selected_primitives(
    edb: Edb,
    selected_layers: set[str],
    selected_nets: set[str] | None,
    skipped: Counter[str],
    progress: Progress | None = None,
    priority_layer: str | None = None,
    layer_names: dict[int, str] | None = None,
    source_primitives=None,
) -> Iterator[tuple[Primitive, str, str, str]]:
    """Filter source primitives and count unsupported copper geometry."""
    net_names = {}

    def load() -> list[tuple[Primitive, Any, str | None, bool | None]]:
        # Keep the resolved net object instead of re-fetching it later: each
        # ``.net`` access is a separate GetNet round-trip to the EDB server.
        source = []
        for primitive in edb.layout.core.primitives if source_primitives is None else source_primitives:
            net = primitive.net
            if not net.is_null:
                source.append((primitive, net))
        if priority_layer is None:
            return [(primitive, net, None, None) for primitive, net in source]
        records = []
        for primitive, net in source:
            void = primitive.is_void
            records.append((primitive, net, None if void else _primitive_layer_name(primitive, layer_names), void))
        records.sort(key=lambda item: item[2] != priority_layer)
        return records

    for primitive, net, layer_name, void in progress_items(load, progress, "Reading polygons"):
        if void is None:
            void = primitive.is_void
        if void:
            continue
        if layer_name is None:
            layer_name = _primitive_layer_name(primitive, layer_names)
        if layer_name not in selected_layers:
            continue
        net_name = _cached_name(net, net_names)
        if selected_nets is not None and net_name not in selected_nets:
            continue
        primitive_type = primitive.primitive_type.name.lower()
        if primitive_type not in {"polygon", "rectangle", "circle", "path"}:
            skipped[primitive_type] += 1
            continue
        if primitive.is_negative:
            skipped["negative primitive"] += 1
            continue
        yield primitive, primitive_type, layer_name, net_name


def _primitive_name(primitive: Primitive, primitive_type: str | None = None) -> str:
    """Return the AEDT display name, falling back to its default ``<type>_<uid>`` without writing it back."""
    try:
        name = primitive.get_product_property(ProductIdType.DESIGNER, 1).strip("'")
    except Exception:  # noqa: BLE001
        name = ""
    if not name:
        kind = primitive.primitive_type.name.lower() if primitive_type is None else primitive_type
        name = f"{_PRIMITIVE_NAME_PREFIX.get(kind, kind)}__{primitive.edb_uid}"
    return name


def _primitives(
    edb: Edb,
    selected_layers: set[str],
    selected_nets: set[str] | None,
    arc_segments: int,
    diagnostics: list[str],
    progress: Progress | None = None,
    analytic_traces: bool = True,
    chord_error: float | None = None,
    on_preview: Callable[[list[ScenePolygon], list[SceneTrace], list[SceneJoin], list[ScenePad]], None] | None = None,
    priority_layer: str | None = None,
    object_info: dict[int, SceneObjectInfo] | None = None,
    layer_names: dict[int, str] | None = None,
    source_primitives=None,
) -> ScenePrimitives:
    """Capture analytic geometry with source contours as a fallback."""
    polygons, traces, joins, pads = [], [], [], []
    skipped = Counter()
    published = False
    for primitive, primitive_type, layer_name, net_name in _selected_primitives(
        edb, selected_layers, selected_nets, skipped, progress, priority_layer, layer_names, source_primitives
    ):
        if on_preview is not None and not published and layer_name != priority_layer:
            on_preview(polygons, traces, joins, pads)
            published = True
        try:
            object_id = primitive.id
            if object_info is not None:
                kind = "trace" if primitive_type == "path" else "pad" if primitive_type == "circle" else "zone"
                name = _primitive_name(primitive, primitive_type)
                info = SceneObjectInfo(object_id, kind, net_name, name=name)
                if kind == "trace":
                    from viewer_adapter.conversion.geometry import trace_dimensions

                    try:
                        width, length = trace_dimensions(primitive)
                        info = SceneObjectInfo(object_id, kind, net_name, width=width, length=length, name=name)
                    except Exception as exc:  # noqa: BLE001
                        _record_exception(
                            diagnostics, f"Trace {primitive.id}: inspection properties unavailable ({exc}).", exc
                        )
                object_info[object_id] = info
            has_voids = getattr(primitive, "has_voids", None)
            voids = primitive.voids if has_voids is None else None
            has_voids = bool(voids) if has_voids is None else has_voids
            if primitive_type == "path" and not has_voids and analytic_traces:
                try:
                    path_traces, path_joins = _trace_geometry(primitive, layer_name, net_name)
                    traces.extend(path_traces)
                    joins.extend(path_joins)
                    continue
                except Exception as exc:  # noqa: BLE001
                    _record_exception(diagnostics, f"Path {primitive.id}: using source boundary coverage ({exc}).", exc)
            if primitive_type == "circle" and not has_voids:
                x, y, radius = (v.double * 1000 for v in primitive.get_parameters())
                pads.append(ScenePad(object_id, layer_name, net_name, (x, y), (radius * 2,) * 2))
                continue
            polygons.append(
                ScenePolygon(
                    object_id=object_id,
                    layer=layer_name,
                    net=net_name,
                    exterior=_contour(primitive, arc_segments, chord_error),
                    holes=(
                        tuple(
                            _contour(void, arc_segments, chord_error)
                            for void in (primitive.voids if voids is None else voids)
                        )
                        if has_voids
                        else ()
                    ),
                    category="trace" if primitive_type == "path" else "pad" if primitive_type == "circle" else "zone",
                )
            )
        except Exception as exc:  # noqa: BLE001
            _record_exception(diagnostics, f"Primitive {primitive.id}: {exc}", exc)
    diagnostics.extend(f"Skipped {count} {kind} object(s)." for kind, count in sorted(skipped.items()))
    return polygons, traces, joins, pads
