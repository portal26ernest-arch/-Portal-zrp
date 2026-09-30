[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$InstallerPath)

$ErrorActionPreference = 'Stop'
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('portal-installer-test-' + [guid]::NewGuid().ToString('N'))
$oldLocalAppData = $env:LOCALAPPDATA
$oldAppData = $env:APPDATA
$env:LOCALAPPDATA = Join-Path $testRoot 'local'
$env:APPDATA = Join-Path $testRoot 'roaming'
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null

function New-TestPackage([string]$Name, [string]$EntryName, [string]$Contents) {
    $source = Join-Path $testRoot ("source-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $source | Out-Null
    $file = Join-Path $source $EntryName
    New-Item -ItemType Directory -Path (Split-Path -Parent $file) -Force | Out-Null
    Set-Content -LiteralPath $file -Value $Contents -NoNewline
    $package = Join-Path $testRoot $Name
    Compress-Archive -Path "$source/*" -DestinationPath $package
    $hash = (Get-FileHash -LiteralPath $package -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath "$package.sha256" -Value "$hash  $Name" -NoNewline
    return $package
}

try {
    $valid = New-TestPackage 'valid.zip' 'PORTAL.Desktop.exe' 'fixture executable'
    & $InstallerPath -PackagePath $valid -Version '1.2.3' | Out-Null
    $installed = Join-Path $env:LOCALAPPDATA 'PORTAL\Desktop\versions\1.2.3\PORTAL.Desktop.exe'
    if ((Get-Content -LiteralPath $installed -Raw) -ne 'fixture executable') { throw 'Valid package did not install intact.' }
    $shortcut = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\PORTAL\PORTAL Desktop.lnk'
    if (-not (Test-Path -LiteralPath $shortcut -PathType Leaf)) { throw 'Per-user Start Menu shortcut was not created.' }

    try {
        & $InstallerPath -PackagePath $valid -Version '1.2.3' | Out-Null
        throw 'Duplicate version should be rejected.'
    } catch {
        if ($_.Exception.Message -eq 'Duplicate version should be rejected.') { throw }
    }

    $badHash = New-TestPackage 'bad-hash.zip' 'PORTAL.Desktop.exe' 'must not install'
    Set-Content -LiteralPath "$badHash.sha256" -Value (('0' * 64) + '  bad-hash.zip') -NoNewline
    try {
        & $InstallerPath -PackagePath $badHash -Version '1.2.4' | Out-Null
        throw 'Invalid checksum should be rejected.'
    } catch {
        if ($_.Exception.Message -eq 'Invalid checksum should be rejected.') { throw }
    }
    if (Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA 'PORTAL\Desktop\versions\1.2.4')) {
        throw 'Checksum failure left an installed version behind.'
    }

    $traversal = Join-Path $testRoot 'traversal.zip'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::Open($traversal, [IO.Compression.ZipArchiveMode]::Create)
    try {
        $entry = $archive.CreateEntry('..\escaped.exe')
        $stream = $entry.Open()
        try {
            $bytes = [Text.Encoding]::UTF8.GetBytes('must remain outside install root')
            $stream.Write($bytes, 0, $bytes.Length)
        } finally { $stream.Dispose() }
    } finally { $archive.Dispose() }
    $hash = (Get-FileHash -LiteralPath $traversal -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath "$traversal.sha256" -Value "$hash  traversal.zip" -NoNewline
    try {
        & $InstallerPath -PackagePath $traversal -Version '1.2.5' | Out-Null
        throw 'Archive traversal should be rejected.'
    } catch {
        if ($_.Exception.Message -eq 'Archive traversal should be rejected.') { throw }
    }
    if ((Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA 'PORTAL\Desktop\versions\1.2.5')) -or
        (Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA 'PORTAL\Desktop\versions\escaped.exe'))) {
        throw 'Archive traversal left an installed version or escaped file behind.'
    }
    Write-Output 'Windows installer contracts passed: checksum, versioned install, shortcut, duplicate-version rejection, and archive traversal rejection.'
} finally {
    $env:LOCALAPPDATA = $oldLocalAppData
    $env:APPDATA = $oldAppData
    if (Test-Path -LiteralPath $testRoot) { Remove-Item -LiteralPath $testRoot -Recurse -Force }
}
