from pathlib import Path
from shutil import copytree

import pytest
from pyedb import Edb
from pyedb.generic.settings import settings

from edb_layout_viewer.scene.builder import scene_from_edb


def test_scene_from_test_edb(tmp_path):
    if settings.specified_version is None and settings.LATEST_VERSION is None:
        pytest.skip("AEDT runtime is required for real EDB capture.")

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
