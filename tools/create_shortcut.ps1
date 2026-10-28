# Creates "Veyra ERP.lnk" on the Desktop: starts start_veyra.bat and uses the Veyra icon.
$root    = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath("Desktop")
$target  = Join-Path $root "start_veyra.bat"
$icon    = Join-Path $root "static\img\veyra.ico"

if (-not (Test-Path $target)) { Write-Host "start_veyra.bat not found next to this script." -ForegroundColor Red; exit 1 }

$shell = New-Object -ComObject WScript.Shell
$link  = $shell.CreateShortcut((Join-Path $desktop "Veyra ERP.lnk"))
$link.TargetPath       = $target
$link.WorkingDirectory = $root
$link.IconLocation     = "$icon,0"
$link.Description      = "Veyra ERP"
$link.WindowStyle      = 1
$link.Save()

Write-Host "Done. The 'Veyra ERP' icon is now on your Desktop:" -ForegroundColor Green
Write-Host "  $desktop"
