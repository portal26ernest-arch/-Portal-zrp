[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$PackagePath,
    [Parameter(Mandatory = $true)][ValidatePattern('^\d+\.\d+\.\d+$')][string]$Version
)

$ErrorActionPreference = 'Stop'
$package = (Resolve-Path -LiteralPath $PackagePath).Path
$checksumPath = "$package.sha256"
if (-not (Test-Path -LiteralPath $checksumPath -PathType Leaf)) {
    throw 'SHA-256 sidecar file is required beside the package.'
}
$expected = ((Get-Content -LiteralPath $checksumPath -TotalCount 1) -split '\s+')[0]
if ($expected -notmatch '^[0-9a-fA-F]{64}$') { throw 'Invalid SHA-256 sidecar format.' }
$actual = (Get-FileHash -LiteralPath $package -Algorithm SHA256).Hash
if (-not [string]::Equals($expected, $actual, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Package checksum mismatch; installation was not changed.'
}

$installRoot = Join-Path $env:LOCALAPPDATA 'PORTAL\Desktop\versions'
$target = Join-Path $installRoot $Version
if (Test-Path -LiteralPath $target) { throw 'This version is already installed; choose a new version.' }
New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
$staging = Join-Path $installRoot ('.staging-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $staging | Out-Null

try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($package)
    try {
        $root = [IO.Path]::GetFullPath($staging).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
        foreach ($entry in $archive.Entries) {
            if ([string]::IsNullOrWhiteSpace($entry.FullName) -or $entry.FullName.Contains('\')) {
                throw 'Unsafe package path.'
            }
            $destination = [IO.Path]::GetFullPath((Join-Path $staging $entry.FullName))
            if (-not $destination.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
                throw 'Package path escapes the installation directory.'
            }
            if ($entry.FullName.EndsWith('/')) {
                New-Item -ItemType Directory -Path $destination -Force | Out-Null
                continue
            }
            New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
            $inputStream = $entry.Open()
            try {
                $outputStream = [IO.File]::Create($destination)
                try { $inputStream.CopyTo($outputStream) } finally { $outputStream.Dispose() }
            } finally { $inputStream.Dispose() }
        }
    } finally { $archive.Dispose() }

    $executable = Join-Path $staging 'PORTAL.Desktop.exe'
    if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
        throw 'Package does not contain PORTAL.Desktop.exe.'
    }
    Move-Item -LiteralPath $staging -Destination $target

    $shortcutDirectory = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\PORTAL'
    New-Item -ItemType Directory -Path $shortcutDirectory -Force | Out-Null
    $shortcutPath = Join-Path $shortcutDirectory 'PORTAL Desktop.lnk'
    $temporaryShortcutPath = Join-Path $shortcutDirectory ('.PORTAL Desktop-' + [guid]::NewGuid().ToString('N') + '.lnk')
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($temporaryShortcutPath)
    $shortcut.TargetPath = Join-Path $target 'PORTAL.Desktop.exe'
    $shortcut.WorkingDirectory = $target
    $shortcut.Description = "PORTAL Desktop $Version"
    $shortcut.Save()
    Move-Item -LiteralPath $temporaryShortcutPath -Destination $shortcutPath -Force
    Write-Output "Installed PORTAL Desktop $Version for the current Windows user. Previous versions remain available for rollback."
} finally {
    if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
}
