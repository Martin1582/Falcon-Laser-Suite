$pythonCmd = $null

if (Test-Path ".\.venv\Scripts\python.exe") {
    $pythonCmd = ".\.venv\Scripts\python.exe"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCmd = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} else {
    Write-Error "Kein Python gefunden. Bitte Python installieren oder eine .venv anlegen."
    exit 1
}

& $pythonCmd -c "import serial; import PySide6; import PIL; import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Build-Abhaengigkeiten fehlen - installiere aus requirements-dev.txt ..."
    & $pythonCmd -m pip install -r "requirements-dev.txt"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Installation fehlgeschlagen. Bitte manuell ausfuehren: py -m pip install -r requirements-dev.txt"
        exit 1
    }
}

& $pythonCmd -m pytest -q
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $pythonCmd -m PyInstaller --clean --noconfirm "laser_control.spec"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Build abgeschlossen: dist\LaserControl\LaserControl.exe"
