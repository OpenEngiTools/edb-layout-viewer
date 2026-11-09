from types import SimpleNamespace

import pytest

from viewer_adapter.diagnostics import _Diagnostics
from viewer_adapter.layer_metadata import _component_sides, _conductor_names


def _edb(layers, signal_layers=()):
    return SimpleNamespace(stackup=SimpleNamespace(layers=layers, signal_layers=signal_layers))


def test_conductor_names_use_signal_membership_and_layer_type_in_stackup_order():
    layers = {
        "dielectric": SimpleNamespace(type="dielectric"),
        "signal_a": SimpleNamespace(type="metal"),
        "conducting": SimpleNamespace(type="conducting"),
        "signal_b": SimpleNamespace(type="metal"),
    }

    result = _conductor_names(_edb(layers, {"signal_a", "signal_b"}), layers)

    assert result == ("signal_a", "conducting", "signal_b")


def test_component_sides_use_first_and_last_conductors():
    layers = {
        "top": SimpleNamespace(type="signal"),
        "inner": SimpleNamespace(type="dielectric"),
        "bottom": SimpleNamespace(type="conducting"),
    }

    result = _component_sides(_edb(layers), _Diagnostics(), layers)

    assert result == {"top": "top", "bottom": "bottom"}


def test_single_conductor_can_be_marked_as_bottom():
    layer = SimpleNamespace(
        type="signal",
        core=SimpleNamespace(top_bottom_association=SimpleNamespace(name="BOTTOM_ASSOCIATED")),
    )
    layers = {"only": layer}

    result = _component_sides(_edb(layers), _Diagnostics(), layers)

    assert result == {"only": "bottom"}


def test_side_association_failure_is_recorded_or_reraised_in_debug_mode():
    class FailingCore:
        @property
        def top_bottom_association(self):
            raise RuntimeError("association unavailable")

    layers = {"only": SimpleNamespace(type="signal", core=FailingCore())}
    edb = _edb(layers)
    diagnostics = _Diagnostics()

    assert _component_sides(edb, diagnostics, layers) == {"only": "top"}
    assert "association unavailable" in diagnostics[0]

    debug_diagnostics = _Diagnostics(debug=True)
    with pytest.raises(RuntimeError, match="association unavailable"):
        _component_sides(edb, debug_diagnostics, layers)
    assert "Traceback" in debug_diagnostics[1]
