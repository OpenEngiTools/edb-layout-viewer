"""Layer and component metadata resolution for scene construction."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ansys.edb.core.database import ProductIdType
from ansys.edb.core.layer.layer import Layer as CoreLayer
from ansys.edb.core.primitive.padstack_instance import PadstackInstance as CorePadstackInstance
from ansys.edb.core.primitive.primitive import Primitive as CorePrimitive
from ansys.edb.core.session import StubAccessor, StubType

from viewer_adapter.scene._builder.common import _UNSET

if TYPE_CHECKING:
    from ansys.edb.core.definition.padstack_def_data import PadstackDefData
    from ansys.edb.core.hierarchy.component_group import ComponentGroup
    from ansys.edb.core.primitive.padstack_instance import PadstackInstance
    from ansys.edb.core.primitive.primitive import Primitive
    from pyedb.grpc.edb import Edb

    from viewer_adapter.scene._builder.common import PinOwner

_PADSTACK_INSTANCE_STUB = StubAccessor(StubType.padstack_instance)
_PRIMITIVE_STUB = StubAccessor(StubType.primitive)


def _mapped_layers(
    instance: PadstackInstance,
    edb: Edb,
    definition: PadstackDefData,
    layers: list[str],
    cache: dict[Any, dict[str, str]],
    layout_layers: dict[str, Any] | None = None,
    name: str | None = None,
) -> dict[str, str]:
    """Resolve explicit definition-to-layout mappings, including permuted names."""
    layer_map = getattr(instance, "layer_map", None)
    if layer_map is None or layer_map.is_null:
        return {layer: layer for layer in layers}
    key = (name or instance.padstack_def.name, layer_map.msg.SerializeToString(), tuple(layers))
    if key not in cache:
        data = definition
        names = dict(zip(data.layer_ids, data.layer_names))
        mapped = {}
        for layer in layers:
            source_layers = edb.stackup.layers if layout_layers is None else layout_layers
            ids = layer_map.get_mapping_backward(source_layers[layer].id)
            candidates = [names[layer_id] for layer_id in ids if layer_id in names]
            if len(candidates) > 1:
                raise ValueError(f"Ambiguous padstack layer mapping on {layer}.")
            mapped[layer] = candidates[0] if candidates else layer
        cache[key] = mapped
    return cache[key]


def _padstack_instance_name(instance: PadstackInstance) -> str | None:
    """Return the AEDT display name of a raw padstack instance, mirroring ``PadstackInstance.name``."""
    name = getattr(instance, "name", None)
    if name:
        return name
    try:
        value = instance.get_product_property(ProductIdType.DESIGNER, 11)
    except Exception:  # noqa: BLE001
        return None
    return str(value).strip("'") if value else None


def _resolve_component(raw_component: ComponentGroup | None) -> ComponentGroup | bool:
    """Return the raw component, or ``False`` when the instance has no component."""
    if raw_component is None or getattr(raw_component, "is_null", True):
        return False
    return raw_component


def _component_is_enabled(component: ComponentGroup) -> bool:
    """Mirror ``Component.is_enabled`` by reading the raw component property directly."""
    comp_prop = getattr(component, "component_property", None)
    return getattr(comp_prop, "enabled", True)


def _component_placement_layer_name(component: ComponentGroup) -> str:
    """Mirror ``Component.placement_layer`` (a layer name) without a pyedb wrapper."""
    layer = getattr(component, "placement_layer", None)
    return getattr(layer, "name", layer)


def _pin_owner(
    instance: PadstackInstance,
    sides: dict[str, str],
    cache: dict[int, PinOwner | None],
    component: ComponentGroup | bool | None = None,
    component_id: int | None = None,
    instance_name: str | None = _UNSET,
) -> PinOwner:
    """Keep component-pin ownership separate from the physical copper pad layer."""
    if not getattr(instance, "is_layout_pin", False):
        return {}
    component = False if component is None else component
    if not component:
        return {}
    component_id = component.edb_uid if component_id is None else component_id
    if component_id not in cache:
        layer = _component_placement_layer_name(component)
        cache[component_id] = (
            {"component": component.name, "component_layer": layer, "component_side": sides[layer]}
            if _component_is_enabled(component) and layer in sides
            else None
        )
    owner = cache[component_id]
    if owner is None:
        return {}
    if instance_name is _UNSET:
        instance_name = _padstack_instance_name(instance)
    return dict(owner, pin_name=instance_name)


def _cached_name(obj: Any, cache: dict[int, str]) -> str:
    """Read ``obj.name`` once per server object; ``.id`` is the local handle, not a server call."""
    key = getattr(obj, "id", None)
    if not isinstance(key, int) or not key:
        return obj.name
    name = cache.get(key)
    if name is None:
        name = cache[key] = obj.name
    return name


def _primitive_layer_name(primitive: Primitive, layer_names: dict[int, str] | None) -> str:
    """Return the primitive's layer name without ``Layer.cast()`` and repeated name calls."""
    if layer_names is not None and isinstance(primitive, CorePrimitive):
        msg = _PRIMITIVE_STUB.__get__().GetLayer(primitive.msg)
        if msg.id:
            name = layer_names.get(msg.id)
            if name is None:
                name = layer_names[msg.id] = CoreLayer(msg).name
            return name
    return primitive.layer.name


def _layer_names_by_id(layout_layers: dict[str, Any]) -> dict[int, str]:
    """Seed the layer ID-to-name cache from stackup layers already in memory (``.id`` is local)."""
    names = {}
    for name, layer in layout_layers.items():
        layer_id = getattr(layer, "id", None)
        if isinstance(layer_id, int) and layer_id:
            names[layer_id] = name
    return names


def _layer_range_names(instance: PadstackInstance, layer_names: dict[int, str] | None) -> tuple[str, str] | None:
    """Return the instance's ``(first, last)`` layer names, or ``None`` when it has no range.

    ``PadstackInstance.get_layer_range()`` casts both layers to their concrete
    type and every ``.name`` read is another server call (7 calls per
    instance). On a real core instance, read the range message once and
    resolve names from ``layer_names``, an ID-to-name cache shared across
    instances; other objects fall back to the public API.
    """
    if layer_names is not None and type(instance) is CorePadstackInstance:
        params = _PADSTACK_INSTANCE_STUB.__get__().GetLayerRange(instance.msg)
        result = []
        for msg in (params.top_layer, params.bottom_layer):
            if not msg.id:
                return None
            name = layer_names.get(msg.id)
            if name is None:
                name = layer_names[msg.id] = CoreLayer(msg).name
            result.append(name)
        return result[0], result[1]
    layer_range = instance.get_layer_range()
    if not layer_range:
        return None
    first, last = (layer.name for layer in layer_range)
    return first, last


def _padstack_layers(
    instance: PadstackInstance,
    selected_layers: set[str],
    conductors: tuple[str, ...],
    extended_ranges: bool,
    layer_names: dict[int, str] | None = None,
) -> list[str]:
    """Include conducting layers within the instance's physical span."""
    instance_layers = None
    get_range = getattr(instance, "get_layer_range", None)
    if callable(get_range):
        layer_range = _layer_range_names(instance, layer_names)
        if not layer_range:
            return []
        first, last = layer_range
        if first in conductors and last in conductors:
            start, stop = sorted((conductors.index(first), conductors.index(last)))
            instance_layers = conductors[start : stop + 1]
    elif extended_ranges:
        first, last = getattr(instance, "start_layer", None), getattr(instance, "stop_layer", None)
        if first in conductors and last in conductors:
            start, stop = sorted((conductors.index(first), conductors.index(last)))
            instance_layers = conductors[start : stop + 1]
    return [name for name in (instance_layers or ()) if name in selected_layers]
