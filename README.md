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

Pass `block=False` to keep working with the session while the window stays
open, for example in IPython or Jupyter with Qt event-loop integration
(`%gui qt`) or inside an existing Qt application:

```python
window = launch_viewer(edb, block=False)  # returns once the initial capture finishes

# ... edit the design with PyEDB ...
window.refresh()  # redraw from the current EDB state
```

Keep a reference to the returned window so it is not garbage-collected. The
window only stays responsive, and `live=True` updates only apply, while a Qt
event loop is running. If a Qt event loop is already running, `block=False` is
required.

## Windows executable

Build a windowed, one-folder executable with PyInstaller:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_exe.ps1
```

The output is `dist\edb-layout-viewer\edb-layout-viewer.exe`; distribute the
whole `dist\edb-layout-viewer` folder. Run it without arguments to pick an
`edb.def` file, or pass the same arguments as the CLI. The target machine still
needs an Ansys Electronics Desktop installation for the EDB runtime. Output and
errors are written to `edb-layout-viewer.log` next to the executable, and
errors are also shown in a dialog.

## More information

- [Contributing](CONTRIBUTING.md)
- [Implementation](IMPLEMENTATION.md)
- [Changelog](CHANGELOG.md)

## License

Apache-2.0. See [LICENSE](LICENSE).
