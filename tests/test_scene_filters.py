import pytest

from edb_layout_viewer.scene.filters import normalize_names


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("GND", {"GND"}),
        (["GND", "VCC", "GND"], {"GND", "VCC"}),
    ],
)
def test_normalize_names(value, expected):
    assert normalize_names(value) == expected
