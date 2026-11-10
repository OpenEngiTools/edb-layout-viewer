# Implementation

## Overview

`viewer_adapter` adapts PyEDB gRPC layout data to the detached
`layout_viewer.scene.LayoutScene` model. It keeps EDB capture separate from
geometry conversion and Qt launch code. The public API remains in the
`viewer_adapter` package; importing it does not import Qt.

## Package structure

```text
src/viewer_adapter/
├── __init__.py
├── diagnostics.py
├── layer_metadata.py
├── conversion/
│   └── geometry.py
├── scene/
│   ├── builder.py
│   ├── filters.py
│   └── patching.py
└── viewer/
    ├── _dependencies.py
    └── launch.py
```

- `__init__.py` exposes `launch_viewer` and lazily re-exports
  `scene_from_edb` from `viewer_adapter.scene.builder`.
- `diagnostics.py` handles best-effort capture diagnostics and debug-mode
  logging/re-raising.
- `layer_metadata.py` identifies conducting layers and maps them to board sides.
- `conversion/geometry.py` converts EDB points, arcs, paths, and transforms into
  viewer geometry using millimeters.
- `scene/filters.py` normalizes optional layer and net selections.
- `scene/builder.py` reads EDB primitives, pads, and components and assembles a
  complete `LayoutScene`.
- `scene/patching.py` builds incremental updates from notified layout changes
  without enumerating the full layout.
- `viewer/_dependencies.py` provides the actionable optional-frontend error.
- `viewer/launch.py` configures `SourceCapture` and calls the Qt viewer.

## Architecture and boundaries

The package is an adapter with three main layers:

```text
Public API
  ├── capture request ──> scene builder ──> conversion and metadata helpers
  └── viewer request ───> viewer launch ──> layout-viewer frontend
                              │
                              └──> scene builder / incremental patcher
```

- **Package root** exports `launch_viewer` and lazily re-exports the builder's
  `scene_from_edb` function for direct capture.
- **Scene construction** owns EDB reads and produces detached scene data.
  Geometry, stackup metadata, and filter normalization are helpers beneath this
  layer; they do not depend on viewer launch code.
- **Viewer integration** owns frontend dependency checks, capture scheduling,
  and Qt window creation. Qt is imported only when launching the viewer.
- **Incremental patching** reuses scene extraction helpers but reads only the
  notified objects. It must not enumerate the whole layout as a fallback.

The intended dependency direction is toward the scene and conversion layers:
viewer orchestration may call capture and patching, but scene and conversion
code should not import viewer-launch modules. `LayoutScene` is the handoff
boundary between EDB capture and rendering. The adapter does not take ownership
of the caller's EDB session.

## Data flow

### Full capture

1. `scene/builder.py`'s `scene_from_edb` validates capture options.
2. The builder reads stackup metadata once, applies layer/net filters, then
   extracts primitives, padstacks, and components.
3. Geometry helpers convert source coordinates to millimeters and preserve
   analytic traces where requested.
4. The builder returns a detached `LayoutScene`; it does not own the EDB
   session's lifetime.

### Viewer launch and live updates

1. `launch_viewer` validates arguments and checks that `layout-viewer` is
   installed.
2. For EDB-backed views, it configures `SourceCapture` with the full-capture
   loader and, when supported, the layout-change stream and incremental loader.
3. `scene/patching.py` handles notified upserts. Changes requiring global
   context are expected to be routed to a full capture by the change-stream
   integration.
4. For a supplied `LayoutScene`, no EDB capture or change stream is configured.

## Error behavior

- Invalid public options raise `ValueError`.
- Missing frontend dependencies raise an `ImportError` with an installation
  hint.
- Full capture is best-effort by default: recoverable object failures are added
  to scene diagnostics. `debug=True` logs the traceback and re-raises.
- Incremental capture is strict so a failed update cannot silently discard
  existing geometry.

## Development checks

Install the test extra and run the dependency-light test suite with:

```bash
pip install -e ".[test]"
pytest
```

Check formatting and lint with Ruff:

```bash
ruff check
ruff format --check
```

Full EDB capture and Qt rendering checks require the project dependencies and a
usable EDB design/runtime.
