# Creates a "Veyra ERP" shortcut on your Desktop that starts the program (start_veyra.bat) with the Veyra icon.
$ErrorActionPreference = "Stop"
try {
    $here = Split-Path -Parent $MyInvocation.MyCommand.Path
    $target = Join-Path $here "start_veyra.bat"
    $icon = Join-Path $here "static\img\veyra.ico"
    if (-not (Test-Path $target)) { throw "start_veyra.bat was not found next to this script." }
    $desktop = [Environment]::GetFolderPath("Desktop")
    $path = Join-Path $desktop "Veyra ERP.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath = $target
    $lnk.WorkingDirectory = $here
    if (Test-Path $icon) { $lnk.IconLocation = "$icon,0" }
    $lnk.Description = "Start Veyra ERP"
    $lnk.WindowStyle = 1
    $lnk.Save()
    Write-Host "Shortcut created: $path"
} catch {
    Write-Host "Failed: $($_.Exception.Message)"
    exit 1
}
