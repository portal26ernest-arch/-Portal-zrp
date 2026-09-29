[CmdletBinding()]
param([switch]$DryRun)

$ErrorActionPreference = "Stop"
$installRoot = $PSScriptRoot
$startMenuShortcut = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\PORTAL.lnk"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "PORTAL.lnk"
$knownFiles = @(
    (Join-Path $installRoot "PortalDesktop.ps1"),
    (Join-Path $installRoot "desktop.json"),
    (Join-Path $installRoot "README.md")
)

if ($DryRun) {
    [ordered]@{
        install_root = $installRoot
        known_files = $knownFiles
        remove_start_menu = $startMenuShortcut
        remove_desktop = $desktopShortcut
        recursive_delete = $false
        removes_company_database = $false
    } | ConvertTo-Json -Compress
    exit 0
}

Remove-Item -LiteralPath $startMenuShortcut -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $desktopShortcut -Force -ErrorAction SilentlyContinue
foreach ($file in $knownFiles) {
    Remove-Item -LiteralPath $file -Force -ErrorAction SilentlyContinue
}
Write-Output "PORTAL shortcuts and known wrapper files were removed. The uninstall script itself may be deleted manually after it exits."
