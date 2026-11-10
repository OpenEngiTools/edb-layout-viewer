# Contributing

## Supported environments

The package requires Python 3.13 or newer. CI exercises Python 3.13 on Linux
and Windows; other Python versions and macOS are not currently in the automated
matrix. Runtime compatibility is bounded to PyEDB 0.87.x,
`layout-viewer-core` 0.1.x, and `ansys-edb-core` 0.3.x. The CI job installs
`layout-viewer-core` from its companion GitHub repository, installs the
current compatible dependency set, and tests the bundled EDB fixture when an
AEDT runtime is installed. That integration test is skipped otherwise.
Rendering and interactive GUI behavior still require a usable Qt/RHI runtime
and should be smoke-tested on the target machine.

## Development setup

This repository expects the sibling `layout_viewer_core` checkout for local
development:

```text
OpenEngiTools/
├── edb-layout-viewer/
└── layout_viewer_core/
```

From the repository root, create the environment and install the development
dependencies:

```bash
uv sync --extra dev
```

The `uv` source override uses the sibling checkout in editable mode. For a
non-`uv` setup, install that checkout and this project:

```bash
python -m pip install -e ../layout_viewer_core
python -m pip install -e ".[dev]"
```

## Checks

Run the same checks as CI:

```bash
uv run --extra dev pytest
uv run --extra dev ruff check
uv run --extra dev ruff format --check
uv run --extra dev python -m build
```

Add or update tests when changing public behavior, capture/conversion logic,
live-update behavior, or supported dependency interfaces. Keep the fixture
tests independent of proprietary design data.

## Release checklist

1. Update the version in `pyproject.toml` and add a dated entry to
   `CHANGELOG.md`.
2. Run the checks above and review the built wheel and source distribution.
3. Have a maintainer publish the package and create a matching version tag.
   Do not commit generated distribution files.
