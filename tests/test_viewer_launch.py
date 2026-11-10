import sys
from types import SimpleNamespace

import pytest

from edb_layout_viewer.viewer import launch


def test_launch_viewer_configures_live_capture_and_delta_loader(monkeypatch):
    changes = object()
    show_options = {}
    scene = object()
    captured = {}

    def fake_layout_changes(edb):
        captured["edb"] = edb
        return changes

    def fake_scene_from_edb(edb, **kwargs):
        captured["full_capture"] = (edb, kwargs)
        return scene

    def fake_scene_patch_from_edb(edb, delta, previous, **kwargs):
        captured["delta_capture"] = (edb, delta, previous, kwargs)
        return "patch"

    monkeypatch.setitem(
        sys.modules,
        "pyedb.grpc.database.layout_changes",
        SimpleNamespace(layout_changes=fake_layout_changes),
    )
    monkeypatch.setitem(
        sys.modules,
        "edb_layout_viewer.scene.builder",
        SimpleNamespace(scene_from_edb=fake_scene_from_edb),
    )
    monkeypatch.setitem(
        sys.modules,
        "edb_layout_viewer.scene.patching",
        SimpleNamespace(scene_patch_from_edb=fake_scene_patch_from_edb),
    )
    monkeypatch.setitem(
        sys.modules,
        "layout_viewer_core.qt.app",
        SimpleNamespace(show_scene=lambda scene, **kwargs: show_options.update({"scene": scene, **kwargs})),
    )
    edb = SimpleNamespace(edbpath="board.aedb")

    result = launch.launch_viewer(edb, live=True, refresh_interval=75)

    assert result is None
    assert show_options["live"] is True
    assert show_options["refresh_interval"] == 75
    capture = show_options["loader"]
    assert capture.changes is changes
    assert capture.delta_loader is not None
    assert capture.loader(None) is scene
    delta = object()
    previous = object()
    assert capture.delta_loader(delta, previous, None) == "patch"
    assert captured["edb"] is edb
    assert captured["full_capture"][0] is edb
    assert captured["delta_capture"][:3] == (edb, delta, previous)


@pytest.mark.parametrize("kwargs", [{"live": True, "scene": object()}, {"edb": None, "scene": None}])
def test_launch_viewer_rejects_invalid_source_options(kwargs):
    with pytest.raises(ValueError):
        launch.launch_viewer(**kwargs)
