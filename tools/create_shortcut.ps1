# Ажлын ширээн дээр Monspeech-ийн товчлол үүсгэнэ (лого дүрстэй).
# Ажиллуулах:  powershell -NoProfile -File tools\create_shortcut.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\pythonw.exe'
$icon = Join-Path $root 'assets\monspeech.ico'

if (-not (Test-Path $python)) { throw "pythonw.exe олдсонгүй: $python" }
if (-not (Test-Path $icon))   { throw "дүрс олдсонгүй: $icon (эхлээд tools\make_icon.py ажиллуул)" }

$desktop = [Environment]::GetFolderPath('Desktop')
$linkPath = Join-Path $desktop 'Monspeech.lnk'

$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($linkPath)
$link.TargetPath = $python
$link.Arguments = '-m monspeech'
$link.WorkingDirectory = $root
$link.IconLocation = "$icon,0"
$link.Description = 'Monspeech - яриаг курсор дээр текст болгож шивнэ (Win+Alt дарж бариад ярь)'
$link.WindowStyle = 1   # энгийн цонхоор нээнэ — удирдлагын самбар шууд гарна
$link.Save()

Write-Host "Товчлол үүслээ: $linkPath"
