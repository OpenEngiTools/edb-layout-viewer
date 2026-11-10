from pathlib import Path
from shutil import copytree

from pyedb import Edb

from edb_layout_viewer.scene.builder import scene_from_edb


def test_scene_from_test_edb(tmp_path):
    fixture = Path(__file__).parent / "data" / "ANSYS_SVP_V1_1.aedb"
    design = copytree(fixture, tmp_path / fixture.name)
    edb = Edb(str(design))
    try:
        scene = scene_from_edb(edb)
    finally:
        edb.close()

    assert scene.title == "main"
    assert scene.layers
    assert scene.traces
    assert scene.polygons
    assert scene.pads
    assert scene.components
