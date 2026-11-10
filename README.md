# edb-layout-viewer

EDB &rarr; layout-viewer-core scene adapter.

This package bridges PyEDB gRPC layout data and the
Qt/RHI `layout-viewer-core` frontend. It converts EDB geometry (traces, polygons, padstacks,
components) into the detached `layout_viewer_core.scene.LayoutScene` representation, and
subscribes to PyEDB's layout-change event stream (`pyedb.grpc.database.layout_changes`)
to support live, incremental viewer updates.

Importing `edb_layout_viewer` does not load Qt; only `launch_viewer()` does, and it raises
an actionable `ImportError` if `layout-viewer-core` is not installed.

## Installation

```bash
python -m pip install -e ../layout-viewer-core
python -m pip install -e ".[test]"
```

## Usage

```python
from pyedb import Edb
from edb_layout_viewer import launch_viewer

edb = Edb("my_design.aedb", edbversion="2025.1")
launch_viewer(edb)
```

## Implementation

See [IMPLEMENTATION.md](IMPLEMENTATION.md) for the package structure, capture
and update flows, error behavior, and development checks.

## License

Apache-2.0. See `LICENSE`.
