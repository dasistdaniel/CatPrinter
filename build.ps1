# Baut dist\CatPrinter.exe (eine Datei, ohne Konsolenfenster).
# Voraussetzung: pip install -r requirements.txt pyinstaller
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m unittest discover tests
if ($LASTEXITCODE -ne 0) { throw "Tests fehlgeschlagen – kein Build." }

python packaging\make_icon.py

python -m PyInstaller `
    --noconfirm --clean `
    --onefile `
    --windowed `
    --name CatPrinter `
    --icon "$PSScriptRoot\packaging\CatPrinter.ico" `
    --paths "$PSScriptRoot" `
    --hidden-import pystray._win32 `
    --workpath build `
    --distpath dist `
    --specpath build `
    packaging\launcher.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller fehlgeschlagen." }

$exe = Get-Item dist\CatPrinter.exe
"Fertig: $($exe.FullName) ({0:N1} MB)" -f ($exe.Length / 1MB)
