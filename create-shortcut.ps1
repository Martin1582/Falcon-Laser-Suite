$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$startScript = Join-Path $projectDir "start.ps1"
$desktopPath = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "Laser Control.lnk"

if (-not (Test-Path $startScript)) {
    Write-Error "start.ps1 not found at: $startScript"
    exit 1
}

$powershellExe = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`""

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $powershellExe
$shortcut.Arguments = $arguments
$shortcut.WorkingDirectory = $projectDir
$shortcut.Description = "Start Laser Control app"

# If app.ico exists in the project root, use it.
$customIcon = Join-Path $projectDir "app.ico"
if (Test-Path $customIcon) {
    $shortcut.IconLocation = $customIcon
} else {
    # Fallback Windows icon from shell32.dll
    $shortcut.IconLocation = "$env:WINDIR\System32\shell32.dll,220"
}

$shortcut.Save()
Write-Host "Shortcut created: $shortcutPath"
