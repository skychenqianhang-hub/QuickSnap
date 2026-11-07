# Install -> first run -> uninstall test for the QuickSnap installer.
#   powershell -ExecutionPolicy Bypass -File tools_dev\installer_roundtrip_test.ps1 <setup.exe> <test-install-dir>
# Backs up %APPDATA%\QuickSnap\config.json and puts it back at the end.
param([string]$Setup, [string]$Dir)

$ErrorActionPreference = "Continue"
$cfgDir = Join-Path $env:APPDATA "QuickSnap"
$cfg = Join-Path $cfgDir "config.json"
$backup = "$cfg.roundtrip-backup"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$uninstKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{28AA2EB5-F581-4FD7-9FBE-105AEBD95AFC}_is1"
$fail = 0
function Check($name, $ok) { if ($ok) { "ok   $name" } else { "FAIL $name"; $script:fail++ } }

if (Test-Path $cfg) { Copy-Item $cfg $backup -Force }
$autostartBefore = (Get-ItemProperty $runKey -ErrorAction SilentlyContinue).QuickSnap

try {
    # 1. silent install (Chinese, default tasks = start with Windows ticked)
    $p = Start-Process $Setup -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LANG=chinesesimplified", "/DIR=`"$Dir`"" -Wait -PassThru
    Check "installer exit code 0" ($p.ExitCode -eq 0)
    $exe = Join-Path $Dir "QuickSnap.exe"
    Check "program installed" (Test-Path $exe)
    Check "uninstall entry" (Test-Path $uninstKey)
    $run = (Get-ItemProperty $runKey -ErrorAction SilentlyContinue).QuickSnap
    Check "auto-start entry points at installed exe" ($run -eq "`"$exe`" --autostart")
    $choices = Join-Path $cfgDir "installer.json"
    Check "installer left its choices" (Test-Path $choices)
    if (Test-Path $choices) { "     installer.json: " + (Get-Content $choices -Raw -Encoding UTF8).Trim() }

    # 2. first run of the installed program picks the choices up
    $app = Start-Process $exe -ArgumentList "--autostart" -PassThru
    Start-Sleep -Seconds 4
    Check "installed program running" (-not $app.HasExited)
    Check "choices file used up" (-not (Test-Path $choices))
    $c = Get-Content $cfg -Raw -Encoding UTF8 | ConvertFrom-Json
    Check "language from installer = zh" ($c.language -eq "zh")
    "     save_dir now: " + $c.save_dir

    # 3. silent uninstall while it is running: must close it and clean up
    $uninst = Join-Path $Dir "unins000.exe"
    $u = Start-Process $uninst -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait -PassThru
    Start-Sleep -Seconds 2
    Check "uninstaller exit code 0" ($u.ExitCode -eq 0)
    Check "running program was closed" ($app.HasExited)
    Check "program files removed" (-not (Test-Path $exe))
    Check "uninstall entry removed" (-not (Test-Path $uninstKey))
    Check "auto-start entry removed" ($null -eq (Get-ItemProperty $runKey -ErrorAction SilentlyContinue).QuickSnap)
    Check "settings kept" (Test-Path $cfg)
}
finally {
    if (Test-Path $backup) { Move-Item $backup $cfg -Force; "     settings restored from backup" }
    if ($autostartBefore) { Set-ItemProperty $runKey -Name QuickSnap -Value $autostartBefore }
    Get-Process QuickSnap -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Dir*" } | Stop-Process -Force
}
if ($fail -eq 0) { "ROUNDTRIP PASSED" } else { "ROUNDTRIP: $fail FAILED" }
