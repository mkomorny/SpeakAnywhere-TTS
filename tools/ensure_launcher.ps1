# Recreate SpeakAnywhere.exe as a unique-path copy of pythonw.exe so Windows
# taskbar / tray identity stays separate from Live Actions Helper and other pythonw apps.
# The copy is made self-contained (python DLLs + pyvenv.cfg pointing home at the real install)
# so it keeps working even when the Python install lives in a different folder than before.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dest = Join-Path $root "SpeakAnywhere.exe"

# Prefer the newest real install; skip WindowsApps stubs.
$candidates = @()
$candidates += Get-ChildItem (Join-Path $env:LOCALAPPDATA "Python") -Directory -Filter "pythoncore-*" -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName "pythonw.exe" }
$candidates += Get-ChildItem (Join-Path $env:LOCALAPPDATA "Programs\Python") -Directory -Filter "Python3*" -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName "pythonw.exe" }
$pythonw = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $pythonw) {
    $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue | Where-Object { $_.Source -notmatch "WindowsApps" } | Select-Object -First 1
    if ($cmd) { $pythonw = $cmd.Source }
}
if (-not $pythonw) {
    Write-Error "pythonw.exe not found. Install Python 3.12+ or update this script."
    exit 1
}
$pyHome = Split-Path -Parent $pythonw
$dlls = @(Get-ChildItem $pyHome -Filter "python3*.dll" | Select-Object -ExpandProperty Name)
$dlls += "vcruntime140.dll", "vcruntime140_1.dll"

$cfg = Join-Path $root "pyvenv.cfg"
$cfgText = "home = $pyHome`r`ninclude-system-site-packages = true`r`n"
$needCopy = -not (Test-Path $dest)
if (-not $needCopy) { $needCopy = (Get-Item $dest).Length -ne (Get-Item $pythonw).Length }
if (-not (Test-Path $cfg) -or (Get-Content $cfg -Raw) -ne $cfgText) { $needCopy = $true }

if ($needCopy) {
    Get-Process SpeakAnywhere -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $dest } | Stop-Process -Force -ErrorAction SilentlyContinue
    Copy-Item -Force $pythonw $dest
    foreach ($d in $dlls) {
        $src = Join-Path $pyHome $d
        if (Test-Path $src) { Copy-Item -Force $src $root }
    }
    Set-Content -Path $cfg -Value $cfgText -NoNewline -Encoding ascii
    Write-Host "[SpeakAnywhere] Launcher refreshed: $dest (from $pyHome)"
} else {
    Write-Host "[SpeakAnywhere] Launcher OK: $dest"
}
exit 0
