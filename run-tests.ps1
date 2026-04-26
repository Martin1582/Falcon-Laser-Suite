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

& $pythonCmd -m pytest -q
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
