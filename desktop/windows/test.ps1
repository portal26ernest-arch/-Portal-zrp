$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path

function Assert-True($Condition,[string]$Message) {
    if (-not $Condition) { throw $Message }
}

foreach ($name in @("PortalDesktop.ps1","install.ps1","uninstall.ps1")) {
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $Here $name),[ref]$null,[ref]$errors) | Out-Null
    Assert-True ($errors.Count -eq 0) ("PowerShell syntax error in " + $name)
}

$plan = & (Join-Path $Here "install.ps1") -PortalUrl "https://portal.example" -Channel staging -Version "3.5-dev-staging" -DryRun | ConvertFrom-Json
Assert-True ($plan.portal_url -eq "https://portal.example") "Install dry-run URL mismatch"
Assert-True (-not $plan.secrets) "Installer must not store secrets"
Assert-True (-not $plan.local_master_database) "Installer must not store master database"

$rejected = $false
try { & (Join-Path $Here "install.ps1") -PortalUrl "http://portal.example" -Channel production -Version "3.6" -DryRun | Out-Null }
catch { $rejected = $true }
Assert-True $rejected "Production HTTP must be rejected"

$rejected = $false
try { & (Join-Path $Here "install.ps1") -PortalUrl "https://user:pass@portal.example" -Channel production -Version "3.6" -DryRun | Out-Null }
catch { $rejected = $true }
Assert-True $rejected "Credential-bearing URL must be rejected"

$rejected = $false
try { & (Join-Path $Here "install.ps1") -PortalUrl "https://portal.example" -Channel production -Version "3.5-dev" -DryRun | Out-Null }
catch { $rejected = $true }
Assert-True $rejected "Production -dev version must be rejected"

$configPath = Join-Path $Here "desktop.json"
try {
    [ordered]@{schema_version=1;portal_url="https://portal.example";channel="staging";version="3.5-dev-staging"} |
        ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8
    $launch = & (Join-Path $Here "PortalDesktop.ps1") -DryRun | ConvertFrom-Json
    Assert-True ($launch.portal_url -eq "https://portal.example/web/") "Launcher must target /web/"
    Assert-True (-not $launch.stores_company_data) "Launcher must not store company data"
    Assert-True (-not $launch.stores_secrets) "Launcher must not store secrets"
}
finally {
    Remove-Item -LiteralPath $configPath -Force -ErrorAction SilentlyContinue
}

$uninstall = & (Join-Path $Here "uninstall.ps1") -DryRun | ConvertFrom-Json
Assert-True (-not $uninstall.recursive_delete) "Uninstall must not recursively delete"
Assert-True (-not $uninstall.removes_company_database) "Uninstall must not remove company DB"

$text = Get-Content -LiteralPath (Join-Path $Here "PortalDesktop.ps1"),(Join-Path $Here "install.ps1"),(Join-Path $Here "uninstall.ps1") -Raw
foreach ($forbidden in @("api.telegram.org","BOT_TOKEN","OWNER_TELEGRAM_ID","portal.db","PGPASSWORD=")) {
    Assert-True (-not $text.Contains($forbidden)) ("Forbidden desktop content: " + $forbidden)
}

Write-Output "PORTAL_WINDOWS_DESKTOP_TEST=PASS"
