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
python -m pip install -e ../layout_viewer_core
python -m pip install -e ".[dev]"
```

## Usage

```python
from pyedb import Edb
from edb_layout_viewer import launch_viewer

edb = Edb("my_design.aedb", edbversion="2025.1")
launch_viewer(edb)
```

### Command line

After installation, open a design directly from the shell:

```bash
edb-layout-viewer my_design.aedb --edbversion 2025.1 --layers TOP BOTTOM --nets VCC GND
python -m edb_layout_viewer my_design.aedb
```

Omit the design path to open a file dialog and select the design's `edb.def` file:

```bash
edb-layout-viewer
python -m edb_layout_viewer
```

The viewer opens the selected file's containing directory. Cancelling the dialog
exits without opening an EDB session.

Run `edb-layout-viewer --help` for all options (`--backend`, `--debug`, `--live [true|false]`, default false).

## Implementation

See [IMPLEMENTATION.md](IMPLEMENTATION.md) for the package structure, capture
and update flows, error behavior, and development checks.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, supported
environments, checks, and release guidance. Changes are recorded in
[CHANGELOG.md](CHANGELOG.md).

## License

Apache-2.0. See `LICENSE`.
