param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("KEYSTORE_B64","KEY_ALIAS","CERT_SHA256")]
    [string]$Value
)

$ErrorActionPreference = "Stop"
$dir = Join-Path $env:USERPROFILE "Documents\PORTAL-Release-Prep\production-signing"
$p12 = Join-Path $dir "portal-release.p12"
$cert = Join-Path $dir "CERT_SHA256.txt"

switch ($Value) {
    "KEYSTORE_B64" {
        if (-not (Test-Path $p12)) { throw "Сначала создайте portal-release.p12" }
        [Convert]::ToBase64String([IO.File]::ReadAllBytes($p12)) | Set-Clipboard
        Write-Host "PORTAL_ANDROID_KEYSTORE_B64 скопирован в буфер обмена."
    }
    "KEY_ALIAS" {
        "portal-release" | Set-Clipboard
        Write-Host "PORTAL_ANDROID_KEY_ALIAS скопирован в буфер обмена."
    }
    "CERT_SHA256" {
        if (-not (Test-Path $cert)) { throw "CERT_SHA256.txt не найден" }
        (Get-Content $cert -Raw).Trim() | Set-Clipboard
        Write-Host "PORTAL_ANDROID_CERT_SHA256 скопирован в буфер обмена."
    }
}
