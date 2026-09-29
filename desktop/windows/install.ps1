[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$PortalUrl,
    [ValidateSet("staging","production")][string]$Channel = "staging",
    [string]$Version = "3.5-dev-staging",
    [switch]$DesktopShortcut,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$uri = $null
if (-not [Uri]::TryCreate($PortalUrl,[UriKind]::Absolute,[ref]$uri)) { throw "PortalUrl is invalid" }
$loopback = $uri.Host -in @("127.0.0.1","localhost","::1")
if ($uri.Scheme -ne "https" -and -not ($uri.Scheme -eq "http" -and $loopback -and $Channel -eq "staging")) { throw "HTTPS is required. Plain HTTP is allowed only for loopback staging development." }
if (-not [string]::IsNullOrEmpty($uri.UserInfo) -or -not [string]::IsNullOrEmpty($uri.Query) -or -not [string]::IsNullOrEmpty($uri.Fragment)) { throw "PortalUrl must not contain credentials, query or fragment." }
if ($Channel -eq "production" -and $Version -match "-dev") { throw "Production desktop package cannot use a -dev version." }

$installRoot = Join-Path $env:LOCALAPPDATA "Programs\PORTAL"
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$launcher = Join-Path $installRoot "PortalDesktop.ps1"
$configPath = Join-Path $installRoot "desktop.json"
$shortcutPath = Join-Path $startMenu "PORTAL.lnk"
$desktopPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "PORTAL.lnk"

$plan = [ordered]@{
    install_root = $installRoot
    portal_url = $PortalUrl.TrimEnd("/")
    channel = $Channel
    version = $Version
    start_menu_shortcut = $shortcutPath
    desktop_shortcut = [bool]$DesktopShortcut
    secrets = $false
    local_master_database = $false
}
if ($DryRun) { $plan | ConvertTo-Json -Compress; exit 0 }

New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "PortalDesktop.ps1") -Destination $launcher -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "uninstall.ps1") -Destination (Join-Path $installRoot "uninstall.ps1") -Force

[ordered]@{
    schema_version = 1
    portal_url = $PortalUrl.TrimEnd("/")
    channel = $Channel
    version = $Version
} | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8

$shell = New-Object -ComObject WScript.Shell
function New-PortalShortcut([string]$Path) {
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $launcher + '"'
    $shortcut.WorkingDirectory = $installRoot
    $shortcut.Description = "PORTAL"
    $shortcut.Save()
}
New-PortalShortcut $shortcutPath
if ($DesktopShortcut) { New-PortalShortcut $desktopPath }

$plan | ConvertTo-Json -Compress
