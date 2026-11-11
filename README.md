# EDB Layout Viewer

EDB Layout Viewer is a Python application for interactively viewing Ansys EDB
printed-circuit-board designs. It displays layout geometry such as traces,
polygons, padstacks, and components.

## Quickstart

Requires Python 3.13 or newer. Opening a design also requires a usable Ansys
EDB runtime and a desktop environment supported by Qt.

### Install

Install the viewer and its dependencies from this repository:

```bash
python -m pip install "git+https://github.com/OpenEngiTools/edb-layout-viewer.git"
```

### Run from the command line

Pass the path to an `.aedb` design directory:

```bash
edb-layout-viewer path/to/my_design.aedb
```

You can also run the viewer without a path and select the design's `edb.def`
file in the dialog:

```bash
edb-layout-viewer
```

Use `edb-layout-viewer --help` to see options, including filters for layers
and nets.

### Run from a Python IDE

Install the package into the Python interpreter configured in your IDE. Create
a Python file, update the design path, and run it:

```python
from pyedb import Edb
from edb_layout_viewer import launch_viewer

edb = Edb("path/to/my_design.aedb")
launch_viewer(edb, block=True)
```

The `Edb` session remains under your script's control while the viewer is
open.

## More information

- [Contributing](CONTRIBUTING.md)
- [Implementation](IMPLEMENTATION.md)
- [Changelog](CHANGELOG.md)

## License

Apache-2.0. See [LICENSE](LICENSE).
