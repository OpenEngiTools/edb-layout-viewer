"""Padstack traversal and geometry collection."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from layout_viewer_core.progress import progress_items
from layout_viewer_core.scene import SceneObjectInfo, ScenePad, ScenePolygon, union_bounds

from edb_layout_viewer.diagnostics import _record_exception
from edb_layout_viewer.layer_metadata import _component_sides, _conductor_names
from edb_layout_viewer.scene._builder.common import _UNSET
from edb_layout_viewer.scene._builder.layers import (
    _cached_name,
    _layer_names_by_id,
    _mapped_layers,
    _padstack_instance_name,
    _padstack_layers,
    _pin_owner,
    _resolve_component,
)
from edb_layout_viewer.scene._builder.padstack import (
    _append_padstack_geometry,
    _cached_pad_template,
    _padstack_definition,
    _placement,
)

if TYPE_CHECKING:
    from ansys.edb.core.hierarchy.component_group import ComponentGroup
    from ansys.edb.core.primitive.padstack_instance import PadstackInstance
    from pyedb.grpc.edb import Edb

    from edb_layout_viewer.scene._builder.common import PinOwner, Placement, Progress


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
    except Exception as exc:  # noqa: BLE001
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
) -> Any:
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
        except Exception as exc:  # noqa: BLE001
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
                except Exception:  # noqa: BLE001, S110
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
                except Exception as exc:  # noqa: BLE001
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
        except Exception as exc:  # noqa: BLE001
            _record_exception(diagnostics, f"Padstack {instance.edb_uid}: {exc}", exc)
    return pads, polygons
