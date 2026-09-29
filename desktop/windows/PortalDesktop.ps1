[CmdletBinding()]
param([switch]$DryRun)

$ErrorActionPreference = "Stop"
$ConfigPath = Join-Path $PSScriptRoot "desktop.json"
if (-not (Test-Path -LiteralPath $ConfigPath)) { throw "PORTAL desktop configuration is missing. Run install.ps1 first." }

$config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$url = [string]$config.portal_url
if ([string]::IsNullOrWhiteSpace($url)) { throw "portal_url is missing" }

$uri = $null
if (-not [Uri]::TryCreate($url,[UriKind]::Absolute,[ref]$uri)) { throw "portal_url is invalid" }
$loopback = $uri.Host -in @("127.0.0.1","localhost","::1")
if ($uri.Scheme -ne "https" -and -not ($uri.Scheme -eq "http" -and $loopback)) { throw "PORTAL Desktop requires HTTPS; HTTP is allowed only for loopback development." }
if (-not [string]::IsNullOrEmpty($uri.UserInfo) -or -not [string]::IsNullOrEmpty($uri.Query) -or -not [string]::IsNullOrEmpty($uri.Fragment)) { throw "portal_url must not contain credentials, query or fragment." }

$base = $url.TrimEnd("/")
$appUrl = if ($base.EndsWith("/web")) { $base + "/" } elseif ($base.EndsWith("/web/")) { $base } else { $base + "/web/" }

$programFilesX86 = [Environment]::GetFolderPath("ProgramFilesX86")
$edgeCandidates = @(
    (Join-Path $programFilesX86 "Microsoft\Edge\Application\msedge.exe"),
    (Join-Path $env:ProgramFiles "Microsoft\Edge\Application\msedge.exe"),
    (Join-Path $env:LOCALAPPDATA "Microsoft\Edge\Application\msedge.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

if ($DryRun) {
    [pscustomobject]@{
        portal_url = $appUrl
        channel = [string]$config.channel
        version = [string]$config.version
        edge_found = [bool]($edgeCandidates.Count -gt 0)
        stores_company_data = $false
        stores_secrets = $false
    } | ConvertTo-Json -Compress
    exit 0
}

if ($edgeCandidates.Count -gt 0) {
    Start-Process -FilePath $edgeCandidates[0] -ArgumentList @("--app=$appUrl","--no-first-run") | Out-Null
} else {
    Start-Process $appUrl | Out-Null
}
