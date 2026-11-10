from types import SimpleNamespace

from layout_viewer_core.scene import LayoutScene

from edb_layout_viewer.scene import patching


def test_scene_patch_processes_only_notified_objects(monkeypatch):
    class PadstackSource:
        def __init__(self, core):
            self.core = core

    import sys

    monkeypatch.setitem(
        sys.modules,
        "pyedb.grpc.database.layout_changes",
        SimpleNamespace(PadstackSource=PadstackSource),
    )
    via = PadstackSource("via-core")
    primitive = object()
    delta = SimpleNamespace(upserts=(("via-id", via), ("primitive-id", primitive)))
    previous = LayoutScene((SimpleNamespace(name="top"),), (), "board")
    calls = {}

    def capture_primitives(
        edb, layers, nets, arc_segments, diagnostics, progress, analytic_traces, chord_error, **kwargs
    ):
        calls["primitive_sources"] = kwargs["source_primitives"]
        calls["primitive_layers"] = layers
        return [], [], [], []

    def capture_padstacks(
        edb, layers, nets, arc_segments, diagnostics, progress, pad_filter, chord_error, info, layout_layers
    ):
        calls["padstack_edb"] = edb
        calls["padstack_layers"] = layers
        calls["layout_layers"] = layout_layers
        return [], []

    monkeypatch.setattr(patching, "_primitives", capture_primitives)
    monkeypatch.setattr(patching, "_padstacks", capture_padstacks)
    edb = SimpleNamespace(
        stackup=SimpleNamespace(layers={"top": "top-layer"}, signal_layers={"top"}),
    )

    scene = patching.scene_patch_from_edb(edb, delta, previous)

    assert calls["primitive_sources"] == (primitive,)
    assert calls["primitive_layers"] == {"top"}
    assert calls["padstack_layers"] == {"top"}
    assert calls["layout_layers"] is edb.stackup.layers
    assert calls["padstack_edb"].layout.core.padstack_instances == ("via-core",)
    assert scene.layers is previous.layers
    assert scene.title == previous.title
    assert scene.diagnostics == ()
