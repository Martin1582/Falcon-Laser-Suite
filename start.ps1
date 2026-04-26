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

& $pythonCmd -c "import serial" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "pyserial fehlt - installiere Abhaengigkeiten aus requirements.txt ..."
    & $pythonCmd -m pip install -r "requirements.txt"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Installation fehlgeschlagen. Bitte manuell ausfuehren: py -m pip install -r requirements.txt"
        exit 1
    }
}

& $pythonCmd "main.py"
