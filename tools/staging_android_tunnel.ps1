param([ValidateSet("status","bind")][string]$Action="bind")
$ErrorActionPreference="Stop"
$adb=(Get-Command adb -ErrorAction SilentlyContinue).Source
if(-not $adb){
  $adb=Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Google.PlatformTools_*\platform-tools\adb.exe" -ErrorAction Stop | Select-Object -First 1 -Expand FullName
}
& $adb devices
if($Action -eq "status"){ & $adb reverse --list; exit $LASTEXITCODE }
& $adb reverse --remove tcp:18767 2>$null
& $adb reverse tcp:18767 tcp:18770
if($LASTEXITCODE -ne 0){ throw "ADB reverse failed" }
$binding=& $adb reverse --list
if($binding -notmatch "tcp:18767\s+tcp:18770"){ throw "ADB reverse verification failed" }
Write-Host "PORTAL staging reverse ready: phone 18767 -> PC 18770"
