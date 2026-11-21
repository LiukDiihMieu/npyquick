#Requires -Version 5
<#
.SYNOPSIS
Build the npyquick Windows installer.

.DESCRIPTION
wheel -> clean venv -> PyInstaller (onedir) -> Inno Setup, producing
dist\npyquick-<ver>-setup.exe. Run from anywhere; paths resolve to the repo root.

.PARAMETER Python
Interpreter used to create the build venv (default: python). It has to be
Python 3.12: packaging\constraints.txt pins versions resolved for it, and the
script stops if it finds another version. Use a clean python.org install, NOT
conda — conda's C-extensions link against conda libs and can break the frozen
app (the same lesson as the AppImage build).

.PARAMETER Wheel
Optional prebuilt npyquick wheel to bundle. If omitted, one is built with
`python -m build` inside the venv (so the host interpreter needs no `build`).

.PARAMETER Iscc
Path to Inno Setup's ISCC.exe. If omitted, common install locations and PATH
are searched.

.EXAMPLE
packaging\windows\build.ps1
#>
[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$Wheel,
    [string]$Iscc
)
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

# The Python the pinned dependencies are resolved for. Keep in step with the
# --python-version used to generate packaging\constraints.txt.
$RequiredPython = "3.12"
$FoundPython = & $Python -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ($FoundPython -ne $RequiredPython) {
    throw ("'$Python' is Python $FoundPython, but this build needs $RequiredPython " +
           "(the pins in packaging\constraints.txt are resolved for it). " +
           "Pass -Python with a Python $RequiredPython interpreter.")
}

$Work = Join-Path $env:TEMP ("npyquick-build-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $Work | Out-Null
try {
    Write-Host ">> creating clean venv"
    & $Python -m venv "$Work\venv"
    $VPy = "$Work\venv\Scripts\python.exe"
    & $VPy -m pip install --upgrade pip | Out-Null

    if (-not $Wheel) {
        Write-Host ">> building wheel"
        & $VPy -m pip install build | Out-Null
        & $VPy -m build --wheel --outdir "$Work\wheel"
        $Wheel = (Get-ChildItem "$Work\wheel\npyquick-*.whl" | Select-Object -First 1).FullName
    }
    Write-Host ">> wheel: $Wheel"

    # Exact versions come from packaging\constraints.txt, shared with the AppImage
    # and Snap builds, so all three ship the same dependencies.
    & $VPy -m pip install -c packaging\constraints.txt $Wheel pyinstaller
    # Read the version from the installed distribution's metadata (the standard
    # importlib.metadata API — reads .dist-info, never imports package code).
    $Version = (& $VPy -c "from importlib.metadata import version; print(version('npyquick'))").Trim()
    Write-Host ">> version: $Version"

    Write-Host ">> running PyInstaller"
    & "$Work\venv\Scripts\pyinstaller.exe" --noconfirm `
        --distpath "$RepoRoot\dist" --workpath "$Work\build" `
        "packaging\pyinstaller\npyquick.spec"

    if (-not $Iscc) {
        $candidates = @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
            "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
        )
        $Iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
        if (-not $Iscc) {
            $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
            if ($cmd) { $Iscc = $cmd.Source }
        }
    }
    if (-not $Iscc) {
        throw "ISCC.exe (Inno Setup) not found. Install Inno Setup or pass -Iscc <path>."
    }

    Write-Host ">> building installer with $Iscc"
    & $Iscc "/DMyAppVersion=$Version" "packaging\windows\npyquick.iss"
    Write-Host ">> done: dist\npyquick-$Version-setup.exe"
}
finally {
    Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue
}
