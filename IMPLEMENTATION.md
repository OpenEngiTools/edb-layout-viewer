# Implementation

## Overview

`edb_layout_viewer` adapts PyEDB gRPC layout data to the detached
`layout_viewer_core.scene.LayoutScene` model. It keeps EDB capture separate from
geometry conversion and Qt launch code. The public API remains in the
`edb_layout_viewer` package; importing it does not import Qt.

## Package structure

```text
src/edb_layout_viewer/
├── __init__.py
├── diagnostics.py
├── layer_metadata.py
├── conversion/
│   └── geometry.py
├── scene/
│   ├── builder.py
│   ├── _builder/
│   │   ├── __init__.py
│   │   ├── assembly.py
│   │   ├── common.py
│   │   ├── components.py
│   │   ├── geometry.py
│   │   ├── layers.py
│   │   ├── padstack.py
│   │   ├── padstacks.py
│   │   └── primitives.py
│   ├── filters.py
│   └── patching.py
└── viewer/
    ├── _dependencies.py
    └── launch.py
```

- `__init__.py` exposes `launch_viewer` and lazily re-exports
  `scene_from_edb` from `edb_layout_viewer.scene.builder`.
- `diagnostics.py` handles best-effort capture diagnostics and debug-mode
  logging/re-raising.
- `layer_metadata.py` identifies conducting layers and maps them to board sides.
- `conversion/geometry.py` converts EDB points, arcs, paths, and transforms into
  viewer geometry using millimeters.
- `scene/filters.py` normalizes optional layer and net selections.
- `scene/builder.py` is the stable capture entry point and delegates to private
  implementation modules. It also re-exports the primitive and padstack
  capture helpers used by incremental patching.
- `scene/_builder/assembly.py` validates capture options, coordinates the
  extraction passes, and assembles a complete `LayoutScene`.
- `scene/_builder/geometry.py` and `padstack.py` convert source geometry and
  place padstack shapes.
- `scene/_builder/layers.py` resolves layer mappings, component metadata, and
  cached EDB names.
- `scene/_builder/primitives.py`, `padstacks.py`, and `components.py` capture
  the corresponding layout objects.
- `scene/_builder/common.py` holds shared internal sentinels and type aliases.
- `scene/patching.py` builds incremental updates from notified layout changes
  without enumerating the full layout.
- `viewer/_dependencies.py` provides the actionable optional-frontend error.
- `viewer/launch.py` configures `SourceCapture` and calls the Qt viewer.

## Architecture and boundaries

The package is an adapter with three main layers:

```text
Public API
  ├── capture request ──> scene builder ──> conversion and metadata helpers
  └── viewer request ───> viewer launch ──> layout-viewer-core frontend
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

1. `scene/builder.py` exposes `scene_from_edb`, which delegates to
   `scene/_builder/assembly.py` for option validation and coordination.
2. The assembly pass reads stackup metadata once, applies layer/net filters,
   then calls the primitive, padstack, and component capture modules.
3. Geometry and layer helpers convert source coordinates to millimeters,
   resolve mapped layers, and preserve analytic traces where requested.
4. The builder returns a detached `LayoutScene`; it does not own the EDB
   session's lifetime.

### Viewer launch and live updates

1. `launch_viewer` validates arguments and checks that `layout-viewer-core` is
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

From the repository root, run the test suite with `uv` (the sibling
`layout_viewer_core` package is resolved from the local source configured in
`pyproject.toml`):

```bash
uv run --extra test pytest
```

Check formatting and lint with Ruff:

```bash
ruff check
ruff format --check
```

Full EDB capture and Qt rendering checks require the project dependencies and a
usable EDB design/runtime.
