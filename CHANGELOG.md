# Changelog

Notable changes to this project are documented here.

## Unreleased

- Add Python/Linux/Windows CI, reproducible development checks, and contributor
  and release guidance.
- Bound supported PyEDB, layout-viewer-core, and ansys-edb-core minor versions.
- Require Python 3.13 or newer.
- Add a PyInstaller spec and script to build a windowed Windows executable.
- Close the EDB from the CLI as soon as the layout capture finishes; with
  `--live`, keep it open until the viewer exits.
