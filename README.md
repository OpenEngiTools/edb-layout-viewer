# edb-layout-viewer

**Explore Ansys EDB layouts in an interactive Qt viewer.**

Open an existing design to inspect its traces, polygons, padstacks, and
components.

## Install

Requires Python 3.13 or newer. Install the package and its runtime dependencies
from this repository:

```bash
python -m pip install "git+https://github.com/OpenEngiTools/edb-layout-viewer.git"
```

Opening a design also requires a usable Ansys EDB runtime.

## Use

Open an `.aedb` design from the command line:

```bash
edb-layout-viewer path/to/my_design.aedb
```

You can also select the design's `edb.def` file in a dialog by omitting the
path:

```bash
edb-layout-viewer
```

Use `--help` to see all options. For example, filter the displayed layout by
layer and net, specify an EDB version, or enable automatic refresh after
supported geometry edits:

```bash
edb-layout-viewer path/to/my_design.aedb --edbversion 2025.1 --layers TOP BOTTOM --nets VCC GND --live
```

Automatic refresh is disabled by default. Rendering backend can be selected
with `--backend auto`, `--backend vulkan`, `--backend d3d11`, or
`--backend metal`.

The viewer can also be launched from Python when you already have a PyEDB
session:

```python
from pyedb import Edb
from edb_layout_viewer import launch_viewer

edb = Edb("my_design.aedb", edbversion="2025.1")
launch_viewer(edb)
```

The adapter converts EDB layout data into the viewer's detached `LayoutScene`
model and can apply incremental updates from PyEDB's layout-change stream.

## Architecture

```text
PyEDB
  EDB layout data and change events
          │
          ▼
edb-layout-viewer
  capture, filtering, and geometry conversion
          │
          ▼
LayoutScene
  detached scene-data boundary
          │
          ▼
layout-viewer-core
  Qt/RHI viewer
```

The adapter owns scene capture and conversion; `layout-viewer-core` owns
rendering. The scene is detached from the EDB session, whose lifetime remains
the caller's responsibility. Importing `edb_layout_viewer` does not load Qt;
Qt is loaded when the viewer is launched.

## Development setup

The project requires Python 3.13 or newer and `uv`. For local development,
check out `layout_viewer_core` beside this repository:

```text
OpenEngiTools/
├── edb-layout-viewer/
└── layout_viewer_core/
```

From the repository root, synchronize the project and its development
dependencies:

```bash
uv sync --extra dev
```

## Development checks

Run the test suite, lint and formatting checks, and package build with:

```bash
uv run --extra dev pytest
uv run --extra dev ruff check
uv run --extra dev ruff format --check
uv run --extra dev python -m build
```

The EDB integration test uses the bundled fixture and is skipped when an AEDT
runtime is unavailable. Interactive rendering should also be smoke-tested with
a usable Qt/RHI runtime.

## Further documentation

- [Implementation](IMPLEMENTATION.md) — package structure, data flows, and
  design boundaries.
- [Contributing](CONTRIBUTING.md) — supported environments, checks, and
  release guidance.
- [Changelog](CHANGELOG.md) — project changes.

## License

Apache-2.0. See [LICENSE](LICENSE).
