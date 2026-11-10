# Copyright (C) 2023 - 2026 Contributors.
# SPDX-License-Identifier: Apache-2.0

"""Build viewer scenes from the public EDB gRPC layout API."""

from __future__ import annotations

import math
from collections import Counter
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Callable, Iterable, Iterator

from ansys.edb.core.database import ProductIdType
from layout_viewer.progress import progress_items
from layout_viewer.scene import (
    LayoutScene,
    SceneComponent,
    SceneJoin,
    SceneLayer,
    SceneObjectInfo,
    ScenePad,
    ScenePolygon,
    SceneTrace,
    union_bounds,
)

from viewer_adapter.diagnostics import _Diagnostics, _record_exception
from viewer_adapter.layer_metadata import _component_sides, _conductor_names
from viewer_adapter.scene.filters import normalize_names

from viewer_adapter.scene._builder.common import _UNSET
from viewer_adapter.scene._builder.layers import (
    _cached_name,
    _layer_names_by_id,
    _mapped_layers,
    _padstack_instance_name,
    _padstack_layers,
    _pin_owner,
    _primitive_layer_name,
    _resolve_component,
)

from viewer_adapter.scene._builder.geometry import (
    _contour,
    _trace_geometry,
)
from viewer_adapter.scene._builder.padstack import (
    _append_padstack_geometry,
    _cached_pad_template,
    _padstack_definition,
    _placement,
)

if TYPE_CHECKING:
    from ansys.edb.core.definition.padstack_def_data import PadstackDefData
    from ansys.edb.core.hierarchy.component_group import ComponentGroup
    from ansys.edb.core.primitive.padstack_instance import PadstackInstance
    from ansys.edb.core.primitive.primitive import Primitive
    from layout_viewer.scene import Point
    from pyedb.grpc.edb import Edb

    Progress = Callable[[str, int, int], None]
    Placement = tuple[Callable[[Point], Point], Callable[[Point], Point], float]
    PadTemplate = tuple[str, tuple[Any, ...], Point, float]
    HoleProfile = tuple[str, float, float, float, float]
    PinOwner = dict[str, Any]
    ComponentBasis = tuple[tuple[Point, Point], Point]
    PadstackDefinition = tuple[PadstackDefData, dict[str, SimpleNamespace], float, Point]
    ScenePrimitives = tuple[list[ScenePolygon], list[SceneTrace], list[SceneJoin], list[ScenePad]]


def _padstack_pin_owner(
    instance: PadstackInstance,
    sides: dict[str, str],
    cache: dict[int, PinOwner | None],
    component: ComponentGroup | bool | None,
    diagnostics: list[str],
    component_id: int | None = None,
    instance_name: str | None = _UNSET,
) -> PinOwner:
    """Retain padstack geometry when optional component-pin metadata is unavailable."""
    try:
        return _pin_owner(instance, sides, cache, component, component_id, instance_name)
    except Exception as exc:
        _record_exception(diagnostics, f"Padstack {instance.edb_uid}: component pin metadata unavailable ({exc}).", exc)
        return {}


def _readonly_components(edb: Edb) -> dict[int, Any] | None:
    """Index existing component wrappers for read-only padstack capture."""
    component_manager = getattr(edb, "components", None)
    return (
        {
            component.core.edb_uid: component
            for component in component_manager.instances.values()
            if getattr(getattr(component, "core", None), "edb_uid", None)
        }
        if component_manager is not None and getattr(edb, "isreadonly", False)
        else None
    )


def _padstack_component(
    raw_component: ComponentGroup | None, components: dict[int, Any] | None, component_id: int | None = None
) -> Any:  # noqa: ANN401
    """Reuse a capture's component wrapper; ``False`` means the instance has no component."""
    if components is None or raw_component is None:
        return None
    if raw_component.is_null:
        return False
    return components.get(raw_component.edb_uid if component_id is None else component_id)


def _padstack_object_info(
    instance: PadstackInstance,
    object_id: int,
    component: ComponentGroup | bool | None,
    net: str,
    hole_radius: float,
    placement: Placement,
    span: list[str],
    object_info: dict[int, SceneObjectInfo] | None,
    diagnostics: list[str],
    reference: str | None = _UNSET,
    instance_name: str | None = _UNSET,
) -> None:
    """Capture optional inspector properties without discarding valid geometry."""
    if object_info is not None:
        try:
            if reference is _UNSET:
                reference = getattr(component, "name", None) if component else None
            if instance_name is _UNSET:
                instance_name = _padstack_instance_name(instance)
            object_info[object_id] = SceneObjectInfo(
                object_id,
                "pad" if component or hole_radius == 0 else "via",
                net,
                drill_diameter=hole_radius * placement[2] * 2,
                start_layer=span[0],
                stop_layer=span[-1],
                component=reference,
                pin_name=instance_name if component else None,
                name=None if component else instance_name,
            )
        except Exception as exc:
            _record_exception(diagnostics, f"Padstack {object_id}: inspection properties unavailable ({exc}).", exc)


def _record_padstack_geometry(
    component_geometry: dict[Any, Any] | None,
    object_id: int,
    component: ComponentGroup | bool | None,
    net: str,
    placement: Placement,
    pads: list[ScenePad],
    polygons: list[ScenePolygon],
    component_id: int | None = None,
) -> None:
    """Accumulate pin envelopes for the component pass, including copper-free pins."""
    if component_geometry is not None:
        bounds = union_bounds([item.bounds for item in (*pads, *polygons)])
        approximate = bounds is None
        if approximate:
            x, y = placement[0]((0, 0))
            bounds = (x, y, x, y)
        instance_geometry = {"bounds": bounds, "nets": {net} if net else set(), "approximate": approximate}
        component_geometry.setdefault("instances", {})[object_id] = instance_geometry
        if component:
            record = component_geometry.setdefault(
                component.edb_uid if component_id is None else component_id,
                {"bounds": bounds, "nets": set(), "approximate": False},
            )
            record["bounds"] = union_bounds([record["bounds"], bounds])
            record["nets"].update(instance_geometry["nets"])
            record["approximate"] |= approximate


def _padstacks(
    edb: Edb,
    selected_layers: set[str],
    selected_nets: set[str] | None,
    arc_segments: int,
    diagnostics: list[str],
    progress: Progress | None = None,
    component_geometry: dict[Any, Any] | None = None,
    chord_error: float | None = None,
    object_info: dict[int, SceneObjectInfo] | None = None,
    layout_layers: dict[str, Any] | None = None,
) -> tuple[list[ScenePad], list[ScenePolygon]]:
    pads, polygons = [], []
    definitions, templates, component_cache, mapping_cache = {}, {}, {}, {}
    pin_components = {}
    layout_layers = edb.stackup.layers if layout_layers is None else layout_layers
    sides = _component_sides(edb, diagnostics, layout_layers)
    conductors = _conductor_names(edb, layout_layers)
    extended_ranges = bool(set(conductors).difference(edb.stackup.signal_layers))
    core_layout = getattr(getattr(edb, "layout", None), "core", None)
    if core_layout is None:
        return pads, polygons
    component_objects = _readonly_components(edb)
    layer_names = _layer_names_by_id(layout_layers)
    net_names, component_names, definition_names = {}, {}, {}
    for instance in progress_items(lambda: core_layout.padstack_instances, progress, "Reading pads and vias"):
        try:
            object_id = instance.edb_uid
            # Fetch .net once: it is a separate GetNet round-trip to the EDB server.
            instance_net = instance.net
            net = "" if getattr(instance_net, "is_null", False) else _cached_name(instance_net, net_names)
            if selected_nets is not None and net not in selected_nets:
                continue
            span = _padstack_layers(instance, set(conductors), conductors, extended_ranges, layer_names)
            layers = [layer for layer in span if layer in selected_layers]
            if not layers:
                continue
            padstack_def = instance.padstack_def
            name = _cached_name(padstack_def, definition_names)
            definition, by_layer, hole_radius, hole_offset = _padstack_definition(
                instance, definitions, diagnostics, name, padstack_def
            )
            mapped = _mapped_layers(instance, edb, definition, layers, mapping_cache, layout_layers, name)
            enabled, diameter = instance.get_hole_overrides()
            hole_profile = definitions.get(("hole_profile", name))
            if enabled:
                hole_radius = diameter.double * 500
                hole_profile = None
            raw_component = getattr(instance, "component", None)
            # Read the component's persistent ID once; every helper below keys on it.
            component_id = (
                raw_component.edb_uid
                if raw_component is not None and not getattr(raw_component, "is_null", True)
                else None
            )
            component = _padstack_component(raw_component, component_objects, component_id)
            if component is None:
                component = _resolve_component(raw_component)
            elif component is not False:
                # Readonly-mode cache stores wrapped Component objects; normalize to raw core.
                component = getattr(component, "core", component)
            if not component:
                component_id = None
            placement = _placement(instance, component_cache, component, component_id)
            reference = instance_name = _UNSET
            if object_info is not None:
                # Shared by the pin owner and the inspector entry; on failure each helper retries and reports.
                try:
                    instance_name = _padstack_instance_name(instance)
                    if component:
                        if component_id is None:
                            reference = getattr(component, "name", None)
                        else:
                            if component_id not in component_names:
                                component_names[component_id] = getattr(component, "name", None)
                            reference = component_names[component_id]
                except Exception:
                    pass
            pin_owner = _padstack_pin_owner(
                instance, sides, pin_components, component, diagnostics, component_id, instance_name
            )
            hole_center = placement[0](hole_offset)
            _padstack_object_info(
                instance,
                object_id,
                component,
                net,
                hole_radius,
                placement,
                span,
                object_info,
                diagnostics,
                reference,
                instance_name,
            )
            pad_start, polygon_start = len(pads), len(polygons)
            for layer in layers:
                try:
                    scale_bound = math.ceil(placement[2] * 1e9) / 1e9
                    local_error = None if chord_error is None else chord_error / scale_bound
                    template = _cached_pad_template(name, mapped[layer], by_layer, templates, arc_segments, local_error)
                    _append_padstack_geometry(
                        instance,
                        layer,
                        net,
                        template,
                        placement,
                        hole_radius,
                        hole_center,
                        arc_segments,
                        pin_owner,
                        (pads, polygons),
                        chord_error,
                        object_id=object_id,
                        hole_profile=hole_profile,
                        hole_offset=hole_offset,
                    )
                except Exception as exc:
                    _record_exception(diagnostics, f"Padstack {object_id}, layer {layer}: {exc}", exc)
            _record_padstack_geometry(
                component_geometry,
                object_id,
                component,
                net,
                placement,
                pads[pad_start:],
                polygons[polygon_start:],
                component_id,
            )
        except Exception as exc:
            _record_exception(diagnostics, f"Padstack {instance.edb_uid}: {exc}", exc)
    return pads, polygons


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
        except Exception as exc:
            _record_exception(diagnostics, f"Component {reference}: {exc}", exc)
    if approximate_count:
        diagnostics.append(f"{approximate_count} component envelopes estimated from pin positions for fast display.")
    return tuple(result)


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


_PRIMITIVE_NAME_PREFIX = {"path": "line", "rectangle": "rect", "polygon": "poly", "bondwire": "bwr"}


def _primitive_name(primitive: Primitive, primitive_type: str | None = None) -> str:
    """Return the AEDT display name, falling back to its default ``<type>_<uid>`` without writing it back."""
    try:
        name = primitive.get_product_property(ProductIdType.DESIGNER, 1).strip("'")
    except Exception:
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
                    except Exception as exc:
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
                except Exception as exc:
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
        except Exception as exc:
            _record_exception(diagnostics, f"Primitive {primitive.id}: {exc}", exc)
    diagnostics.extend(f"Skipped {count} {kind} object(s)." for kind, count in sorted(skipped.items()))
    return polygons, traces, joins, pads


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
