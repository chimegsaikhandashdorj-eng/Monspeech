# Monspeech.exe бүтээнэ — Python суулгаагүй компьютер дээр ажиллах ганц файл.
#
# Ажиллуулах:  powershell -NoProfile -File tools\build_exe.ps1
#
# Үр дүн:  dist\Monspeech.exe

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    throw "Виртуал орчин олдсонгүй: $python`nЭхлээд: python -m venv .venv"
}

Write-Host "== Бүтээх сангуудыг шалгаж байна =="
# Модуль байгаа эсэхийг stderr үүсгэхгүйгээр шалгана: `python -m PyInstaller`
# нь байхгүй үед алдаа бичдэг ба PowerShell түүнийг таслах алдаа гэж үздэг.
$found = & $python -c "import importlib.util as u; print('yes' if u.find_spec('PyInstaller') else 'no')"
if ($found -ne 'yes') {
    Write-Host "PyInstaller суулгаж байна..."
    & $python -m pip install -q -r (Join-Path $root 'requirements-dev.txt')
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller суусангүй" }
}

Write-Host "== Хуучин бүтээлтийг цэвэрлэж байна =="
foreach ($folder in @('build', 'dist')) {
    $path = Join-Path $root $folder
    if (Test-Path $path) { Remove-Item $path -Recurse -Force }
}

Write-Host "== Багцалж байна (хэдэн минут болно) =="
Push-Location $root
try {
    & $python -m PyInstaller --clean --noconfirm (Join-Path $root 'tools\monspeech.spec')
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller алдаа өглөө (код $LASTEXITCODE)" }
} finally {
    Pop-Location
}

$exe = Join-Path $root 'dist\Monspeech.exe'
if (-not (Test-Path $exe)) { throw "Файл үүсээгүй: $exe" }

$mb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host ""
Write-Host "Бэлэн боллоо: $exe  ($mb МБ)" -ForegroundColor Green
Write-Host "Энэ ганц файлыг хуулж өгөхөд хангалттай — Python шаардахгүй."
