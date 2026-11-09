# Creates "Dragonwilds Helper" on the desktop. Starts the .bat minimized (console stays in the taskbar for errors).
$root = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath("Desktop")
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut((Join-Path $desktop "Dragonwilds Helper.lnk"))
$lnk.TargetPath = Join-Path $root "Start Dragonwilds Helper.bat"
$lnk.WorkingDirectory = $root
$lnk.IconLocation = (Join-Path $root "helper.ico") + ",0"
$lnk.WindowStyle = 7   # minimized
$lnk.Description = "Dragonwilds helper: resource map + recipes overlay"
$lnk.Save()
Write-Output ("created " + $lnk.FullName)
