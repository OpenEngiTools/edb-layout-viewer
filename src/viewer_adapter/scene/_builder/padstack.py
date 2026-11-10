"""Padstack placement and pad-geometry helpers for scene construction."""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from ansys.edb.core.definition.padstack_def_data import PadGeometryType as CorePadGeometryType
from ansys.edb.core.definition.padstack_def_data import PadType as CorePadType
from ansys.edb.core.geometry.polygon_data import PolygonData as CorePolygonData
from layout_viewer.scene import ScenePad, ScenePolygon
from pyedb.misc.utilities import arc_segment_count

from viewer_adapter.scene._builder.geometry import (
    _nsided_polygon_points,
    _rotate,
    _rounded_outline,
    _thermal_relief_outline,
    _xy,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from ansys.edb.core.definition.padstack_def_data import PadstackDefData
    from ansys.edb.core.hierarchy.component_group import ComponentGroup
    from ansys.edb.core.primitive.padstack_instance import PadstackInstance
    from layout_viewer.scene import Point

    Placement = tuple[Callable[[Point], Point], Callable[[Point], Point], float]
    PadTemplate = tuple[str, tuple[Any, ...], Point, float]
    HoleProfile = tuple[str, float, float, float, float]
    PinOwner = dict[str, Any]
    ComponentBasis = tuple[tuple[Point, Point], Point]
    PadstackDefinition = tuple[PadstackDefData, dict[str, SimpleNamespace], float, Point]

_THERMAL_RELIEF_SHAPES = {"round45", "round90", "square45", "square90"}


def _placement(
    instance: PadstackInstance,
    component_cache: dict[int, ComponentBasis],
    component: ComponentGroup | bool | None = None,
    component_id: int | None = None,
) -> Placement:
    get_position = getattr(instance, "get_position_and_rotation", None)
    if callable(get_position):
        state = tuple(value.double for value in get_position())
        position = tuple(v * 1000 for v in state[:2])
        rotation = state[2]
    else:
        position = tuple(float(v) * 1000 for v in instance.position)
        rotation = float(instance.rotation)
    basis = ((1, 0), (0, 1))
    component = False if component is None else component
    if component:
        key = component.edb_uid if component_id is None else component_id
        if key not in component_cache:
            from ansys.edb.core.geometry.point_data import PointData

            transform = component.transform
            if transform.is_null:
                component_cache[key] = basis, (0.0, 0.0)
            else:
                from viewer_adapter.conversion.geometry import transform_basis_points

                points = transform_basis_points(transform)
                if points is None:
                    points = [transform.transform_point(PointData(p)) for p in ((0, 0), (1, 0), (0, 1))]
                origin, x, y = points
                ox, oy = origin.x.double, origin.y.double
                component_cache[key] = (
                    ((x.x.double - ox, x.y.double - oy), (y.x.double - ox, y.y.double - oy)),
                    (ox * 1000, oy * 1000),
                )
        basis, origin = component_cache[key]
        if callable(get_position):
            px, py = position
            position = (
                origin[0] + basis[0][0] * px + basis[1][0] * py,
                origin[1] + basis[0][1] * px + basis[1][1] * py,
            )

    def vector(point: Point) -> Point:
        x, y = _rotate(point, rotation)
        return basis[0][0] * x + basis[1][0] * y, basis[0][1] * x + basis[1][1] * y

    def world(point: Point) -> Point:
        x, y = vector(point)
        return position[0] + x, position[1] + y

    scale = math.hypot(*basis[0])
    return world, vector, scale


def _pad_template(pad: SimpleNamespace, arc_segments: int, chord_error: float | None = None) -> PadTemplate | None:
    shape = pad.shape
    if shape in {"no_shape", "geometry", "no_geometry"}:
        return None
    offset = (float(pad.offset_x) * 1000, float(pad.offset_y) * 1000)
    rotation = float(pad.rotation)
    if shape == "polygon":
        if chord_error is not None:
            from pyedb.grpc.database.primitive.primitive import Primitive

            x, y = Primitive._get_points_for_plot(
                None, pad.polygon_data.points, arc_segments, chord_error=chord_error / 1000
            )

            return shape, tuple((px * 1000, py * 1000) for px, py in zip(x, y)), offset, rotation
        polygon = pad.polygon_data.without_arcs(max_arc_angle=math.tau / arc_segments, max_points=arc_segments)
        return shape, tuple(_xy(p) for p in polygon.points), offset, rotation
    if shape == "nsided_polygon":
        # ``num_sides`` is a plain count, not a length, and must not be unit-scaled.
        size, num_sides = pad.parameters_values or (0.0, 0)
        return "polygon", _nsided_polygon_points(float(size) * 1000, float(num_sides)), offset, rotation
    values = tuple(float(v) * 1000 for v in (pad.parameters_values or ()))
    if shape in {"round45", "round90", "square45", "square90"}:
        inner, _channel_width, isolation_gap = values
        ring = _thermal_relief_outline(shape.startswith("round"), inner, isolation_gap, arc_segments)
        return "polygon", ring, offset, rotation
    if shape not in {"circle", "square", "rectangle", "oval", "bullet"}:
        raise ValueError(f"Unsupported pad shape {shape!r}.")
    return shape, values, offset, rotation


def _pad_parameter_value(data: PadstackDefData, layer_name: str | None, pad_type: CorePadType) -> list[Any] | None:
    """Read raw pad parameters, normalizing the polygon variant to a consistent 5-item layout."""
    try:
        p_val = data.get_pad_parameters(layer_name, pad_type)
    except Exception:  # noqa: BLE001
        return None
    if not p_val:
        return None
    if isinstance(p_val[0], CorePolygonData):
        p_val = [CorePadGeometryType.PADGEOMTYPE_POLYGON, *p_val]
    return p_val


def _pad_param(
    data: PadstackDefData, layer_name: str | None, pad_type: CorePadType = CorePadType.REGULAR_PAD
) -> SimpleNamespace:
    """Local, read-only stand-in for ``PadProperties`` built directly from raw pad parameters."""
    p_val = _pad_parameter_value(data, layer_name, pad_type)
    if p_val is None:
        return SimpleNamespace(
            shape="no_shape", offset_x=0.0, offset_y=0.0, rotation=0.0, polygon_data=None, parameters_values=None
        )
    geom_type, params = p_val[0], p_val[1]
    polygon = params if isinstance(params, CorePolygonData) else None
    # ``NSIDED_POLYGON`` would otherwise collide with ``POLYGON`` once reduced to its last
    # underscore-separated word, even though it carries size/side-count parameters, not polygon data.
    if geom_type == CorePadGeometryType.PADGEOMTYPE_NSIDED_POLYGON:
        shape = "nsided_polygon"
    else:
        shape = geom_type.name.split("_")[-1].lower()
    return SimpleNamespace(
        shape=shape,
        offset_x=p_val[2].double,
        offset_y=p_val[3].double,
        rotation=p_val[4].double,
        polygon_data=polygon,
        parameters_values=None if polygon is not None else [v.double for v in params],
    )


def _hole_param(data: PadstackDefData) -> SimpleNamespace:
    """Hole geometry; ``get_hole_parameters()`` is ``get_pad_parameters(None, PadType.HOLE)``."""
    return _pad_param(data, None, CorePadType.HOLE)


def _hole_diameter(hole: SimpleNamespace) -> float | None:
    """Effective circular drill diameter of a hole, or ``None`` when absent or polygonal."""
    values = hole.parameters_values
    if hole.shape in {"no_shape", "geometry"} or not values:
        return None
    if hole.shape in {"rectangle", "oval", "bullet"}:
        return max(values[0], values[1])
    # Circle/square/nsided-polygon/thermal shapes lead with diameter, size or inner size.
    return values[0]


def _hole_profile(hole: SimpleNamespace) -> HoleProfile | None:
    """Return a noncircular hole profile ``(shape, size_x, size_y, corner, rotation)`` in mm, else ``None``."""
    if hole.shape not in {"rectangle", "oval", "bullet"}:
        return None
    values = hole.parameters_values
    corner = 0.0 if hole.shape == "rectangle" else values[2] * 1000
    return hole.shape, values[0] * 1000, values[1] * 1000, corner, hole.rotation


def _padstack_definition(
    instance: PadstackInstance,
    definitions: dict[Any, Any],
    diagnostics: list[str],
    name: str | None = None,
    padstack_def: Any = None,
) -> PadstackDefinition:
    """Cache pad and drill data shared by instances of a definition, read directly from raw core."""
    padstack_def = instance.padstack_def if padstack_def is None else padstack_def
    name = name or padstack_def.name
    if name not in definitions:
        data = padstack_def.data
        hole = _hole_param(data)
        diameter = _hole_diameter(hole)
        if hole.shape == "polygon":
            diagnostics.append(f"Padstack definition {name}: polygonal drill profile is not displayed.")
        by_layer = {layer: _pad_param(data, layer) for layer in data.layer_names}
        if any(pad.shape in _THERMAL_RELIEF_SHAPES for pad in by_layer.values()):
            diagnostics.append(
                f"Padstack definition {name}: round45/round90/square45/square90 pads are approximated as a "
                "plain circle/square outline; thermal-relief spokes are not rendered."
            )
        definitions[name] = (
            data,
            by_layer,
            float(diameter or 0) * 500,
            (hole.offset_x * 1000, hole.offset_y * 1000),
        )
        definitions[("hole_profile", name)] = _hole_profile(hole)
    return definitions[name]


def _cached_pad_template(
    name: str,
    definition_layer: str,
    by_layer: dict[str, SimpleNamespace],
    templates: dict[Any, PadTemplate | None],
    arc_segments: int,
    chord_error: float | None = None,
) -> PadTemplate | None:
    """Cache each definition layer's geometry, including absent copper."""
    key = (name, definition_layer, chord_error)
    if key not in templates:
        pad = by_layer.get(definition_layer, by_layer.get("Default"))
        templates[key] = None if pad is None else _pad_template(pad, arc_segments, chord_error)
    return templates[key]


def _append_padstack_geometry(
    instance: PadstackInstance,
    layer: str,
    net: str | None,
    template: PadTemplate | None,
    placement: Placement,
    hole_radius: float,
    hole_center: Point,
    arc_segments: int,
    pin_owner: PinOwner,
    geometry: tuple[list[ScenePad], list[ScenePolygon]],
    chord_error: float | None = None,
    *,
    object_id: int | None = None,
    hole_profile: HoleProfile | None = None,
    hole_offset: Point = (0.0, 0.0),
) -> None:
    """Place a layer's copper and retain independent drill coverage.

    A noncircular ``hole_profile`` is cut out of the copper as a polygon hole, since analytic pads only
    support circular drills.
    """
    world, vector, scale = placement
    pads, polygons = geometry
    object_id = instance.edb_uid if object_id is None else object_id
    if hole_profile is not None and template is not None and hole_radius > 0:
        shape, dimensions, offset, rotation = template
        if shape == "polygon":
            outline = dimensions
        elif shape in {"circle", "square", "rectangle", "oval", "bullet"}:
            if shape == "circle":
                outline = tuple(
                    (
                        dimensions[0] / 2 * math.cos(i * math.tau / arc_segments),
                        dimensions[0] / 2 * math.sin(i * math.tau / arc_segments),
                    )
                    for i in range(arc_segments)
                )
            elif shape == "square":
                outline = _rounded_outline("rectangle", dimensions[0], dimensions[0], 0, arc_segments)
            else:
                corner = dimensions[2] if shape in {"oval", "bullet"} else 0
                outline = _rounded_outline(shape, dimensions[0], dimensions[1], corner, arc_segments)
        else:
            outline = None
        if outline is not None:
            ring = tuple(world(tuple(a + b for a, b in zip(_rotate(p, rotation), offset))) for p in outline)
            h_shape, size_x, size_y, corner, h_rotation = hole_profile
            hole_ring = tuple(
                world(tuple(a + b for a, b in zip(_rotate(p, h_rotation), hole_offset)))
                for p in _rounded_outline(h_shape, size_x, size_y, corner, arc_segments)
            )
            polygons.append(ScenePolygon(object_id, layer, net, ring, (hole_ring,), category="pad", **pin_owner))
            return
    if template is None:
        # Keep nonfunctional pads absent while retaining drill marks.
        if hole_radius > 0:
            pads.append(
                ScenePad(
                    object_id,
                    layer,
                    net,
                    hole_center,
                    (hole_radius * 2 * scale,) * 2,
                    hole_radius=hole_radius * scale,
                )
            )
        return
    shape, dimensions, offset, rotation = template
    if shape == "polygon":
        ring = tuple(world(tuple(a + b for a, b in zip(_rotate(p, rotation), offset))) for p in dimensions)
        holes = ()
        if hole_radius > 0:
            segments = (
                arc_segments if chord_error is None else arc_segment_count(hole_radius * scale, math.tau, chord_error)
            )
            holes = (
                tuple(
                    (
                        hole_center[0] + hole_radius * scale * math.cos(i * math.tau / segments),
                        hole_center[1] + hole_radius * scale * math.sin(i * math.tau / segments),
                    )
                    for i in range(segments)
                ),
            )
            pads.append(
                ScenePad(
                    object_id,
                    layer,
                    net,
                    hole_center,
                    (hole_radius * 2 * scale,) * 2,
                    hole_radius=hole_radius * scale,
                )
            )
        polygons.append(ScenePolygon(object_id, layer, net, ring, holes, category="pad", **pin_owner))
        return
    center = world(offset)
    axis = vector(_rotate((1, 0), rotation))
    angle = math.atan2(axis[1], axis[0])
    size = (dimensions[0],) * 2 if shape in {"circle", "square"} else dimensions[:2]
    corner = dimensions[2] if shape in {"oval", "bullet"} else 0
    corner = min(corner, min(size) / 2)
    pads.append(
        ScenePad(
            object_id,
            layer,
            net,
            center,
            tuple(v * scale for v in size),
            "rectangle" if shape == "square" else shape,
            angle,
            corner * scale,
            hole_radius * scale,
            hole_center,
            **pin_owner,
        )
    )
