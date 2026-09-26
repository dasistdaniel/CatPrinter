# Legt eine Verknüpfung im Autostart-Ordner an, die den Druckserver bei der
# Anmeldung unsichtbar startet (keine Adminrechte nötig).
# Entfernen:  .\autostart.ps1 -Remove
param([switch]$Remove)

$link = Join-Path ([Environment]::GetFolderPath("Startup")) "Cat Printer Server.lnk"
if ($Remove) {
    Remove-Item $link -ErrorAction SilentlyContinue
    "Autostart entfernt."
    return
}

$python = (Get-Command python -ErrorAction Stop).Source
$pythonw = Join-Path (Split-Path $python) "pythonw.exe"
if (-not (Test-Path $pythonw)) { throw "pythonw.exe nicht gefunden neben $python" }
$log = Join-Path $env:APPDATA "CatPrinterDriver\server.log"
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($link)
$lnk.TargetPath = $pythonw
$lnk.Arguments = "-m catprinter serve --log-file `"$log`""
$lnk.WorkingDirectory = $PSScriptRoot   # damit "-m catprinter" gefunden wird
$lnk.Description = "Cat Printer IPP-Server"
$lnk.Save()
"Autostart eingerichtet: $link"
"Log: $log"
