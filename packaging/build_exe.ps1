# Build dist\edb-layout-viewer\edb-layout-viewer.exe with PyInstaller.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    uv run --with pyinstaller pyinstaller --noconfirm --clean `
        --distpath "$root\dist" --workpath "$root\build" `
        "$PSScriptRoot\edb_layout_viewer.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}
