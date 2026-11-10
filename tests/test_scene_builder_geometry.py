import math
from types import SimpleNamespace

import pytest

from viewer_adapter.scene._builder.assembly import scene_from_edb as _assembly_scene_from_edb
from viewer_adapter.scene._builder.geometry import _thermal_relief_outline, _trace_geometry
from viewer_adapter.scene._builder.layers import (
    _component_is_enabled,
    _mapped_layers,
    _padstack_layers,
    _resolve_component,
)
from viewer_adapter.scene._builder.padstack import _pad_template
from viewer_adapter.scene._builder.padstacks import _padstacks as _captured_padstacks
from viewer_adapter.scene._builder.primitives import _primitives as _captured_primitives
from viewer_adapter.scene._builder.primitives import _scene_filters
from viewer_adapter.scene.builder import _padstacks, _primitives, scene_from_edb


def _point(x, y):
    return SimpleNamespace(x=SimpleNamespace(double=x), y=SimpleNamespace(double=y))


def _segment(start, end):
    return SimpleNamespace(start=_point(*start), end=_point(*end), is_segment=lambda: True)


def _path(arcs, caps=("flat", "extended"), corner="round", width=0.001):
    return SimpleNamespace(
        center_line=SimpleNamespace(arc_data=arcs),
        get_end_cap_style=lambda: tuple(SimpleNamespace(name=name) for name in caps),
        corner_style=SimpleNamespace(name=corner),
        width=SimpleNamespace(double=width),
        id=17,
    )


def test_trace_geometry_preserves_line_dimensions_and_end_caps():
    traces, joins = _trace_geometry(_path([_segment((0, 0), (0.01, 0.02))]), "top", "GND")

    assert len(traces) == 1
    assert joins == []
    assert traces[0].start == (0, 0)
    assert traces[0].end == (10, 20)
    assert traces[0].width == 1
    assert traces[0].end_caps == ("flat", "extended")


def test_trace_geometry_preserves_arc_sweep():
    arc = _segment((0.001, 0), (0, 0.001))
    arc.is_segment = lambda: False
    arc.center = _point(0, 0)
    arc.is_ccw = lambda: True

    traces, _ = _trace_geometry(_path([arc]), "top", "GND")

    assert traces[0].center == (0, 0)
    assert traces[0].sweep == pytest.approx(math.pi / 2)


def test_pad_template_scales_circle_dimensions_to_millimeters():
    pad = SimpleNamespace(
        shape="circle",
        offset_x=0.001,
        offset_y=-0.002,
        rotation=0.25,
        parameters_values=[0.003],
    )

    assert _pad_template(pad, 16) == ("circle", (3.0,), (1.0, -2.0), 0.25)


def test_thermal_relief_outline_uses_inner_size_and_isolation_gap():
    points = _thermal_relief_outline(False, inner=2, isolation_gap=0.5, arc_segments=16)

    assert points == ((1.5, 1.5), (-1.5, 1.5), (-1.5, -1.5), (1.5, -1.5))


def test_scene_filters_validate_layer_and_net_names():
    layers = {"top": SimpleNamespace(type="signal"), "dielectric": SimpleNamespace(type="dielectric")}
    edb = SimpleNamespace(
        stackup=SimpleNamespace(layers=layers, signal_layers={"top"}),
        nets=SimpleNamespace(nets={"GND"}),
    )

    assert _scene_filters(edb, None, "GND", layers) == ({"top"}, {"GND"})
    with pytest.raises(ValueError, match="Unknown layers: missing"):
        _scene_filters(edb, "missing", None, layers)
    with pytest.raises(ValueError, match="Unknown nets: VCC"):
        _scene_filters(edb, None, "VCC", layers)


def test_component_helpers_handle_null_and_enabled_state():
    assert _resolve_component(None) is False
    assert _resolve_component(SimpleNamespace(is_null=True)) is False
    component = SimpleNamespace(is_null=False, component_property=SimpleNamespace(enabled=False))
    assert _resolve_component(component) is component
    assert not _component_is_enabled(component)


def test_padstack_layer_mapping_and_span_resolution():
    layers = {"top": SimpleNamespace(id=2)}
    layer_map = SimpleNamespace(
        is_null=False,
        msg=SimpleNamespace(SerializeToString=lambda: b"map"),
        get_mapping_backward=lambda layer_id: [7] if layer_id == 2 else [],
    )
    instance = SimpleNamespace(
        layer_map=layer_map,
        padstack_def=SimpleNamespace(name="via"),
        get_layer_range=lambda: (SimpleNamespace(name="top"), SimpleNamespace(name="bottom")),
    )
    definition = SimpleNamespace(layer_ids=[7], layer_names=["Top"])
    edb = SimpleNamespace(stackup=SimpleNamespace(layers=layers))

    assert _mapped_layers(instance, edb, definition, ["top"], {}, layers) == {"top": "Top"}
    assert _padstack_layers(instance, {"top", "inner", "bottom"}, ("top", "inner", "bottom"), False) == [
        "top",
        "inner",
        "bottom",
    ]


def test_builder_module_preserves_scene_and_patching_entry_points():
    assert scene_from_edb is _assembly_scene_from_edb
    assert _padstacks is _captured_padstacks
    assert _primitives is _captured_primitives
