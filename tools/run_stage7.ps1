[CmdletBinding()]
param(
    [string]$HostName = '178.209.127.247',
    [int]$Port = 22,
    [string]$HostKeyAlias = '',
    [string]$UserName = $(if ($env:PORTAL_STAGE7_SSH_USER) { $env:PORTAL_STAGE7_SSH_USER } else { 'root' }),
    [string]$Branch = 'main',
    [string]$Domain = $(if ($env:PORTAL_STAGE7_DOMAIN) { $env:PORTAL_STAGE7_DOMAIN } else { '' }),
    [bool]$UseBannerRelay = $true,
    [switch]$UseCloudflareTunnel,
    [string]$IdentityFile = $(if ($env:PORTAL_STAGE7_SSH_KEY) { $env:PORTAL_STAGE7_SSH_KEY } else { Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..')).Path 'infra_vps_01' }),
    [string]$KnownHostsFile = $(if ($env:PORTAL_STAGE7_KNOWN_HOSTS) { $env:PORTAL_STAGE7_KNOWN_HOSTS } else { Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..')).Path 'infra_vps_01_known_hosts' }),
    [string]$SshPath = $(if (Test-Path 'C:\Program Files\Git\usr\bin\ssh.exe') { 'C:\Program Files\Git\usr\bin\ssh.exe' } else { (Get-Command ssh.exe -ErrorAction Stop).Source }),
    [string]$ScpPath = $(if (Test-Path 'C:\Program Files\Git\usr\bin\scp.exe') { 'C:\Program Files\Git\usr\bin\scp.exe' } else { (Get-Command scp.exe -ErrorAction Stop).Source })
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$knownHosts = $KnownHostsFile
$identityFile = $IdentityFile
$ssh = $SshPath
$scp = $ScpPath
$deployScript = Join-Path $repo 'server\vps_stage7_staging_deploy.sh'
$transferScript = $null
$logDir = Join-Path $repo 'reports'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logPath = Join-Path $logDir ("stage7-runner-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))

function Write-Log([string]$Message) {
    $line = "{0} {1}" -f (Get-Date -Format 'o'), $Message
    Add-Content -LiteralPath $logPath -Value $line -Encoding utf8
    Write-Host $line
}

if (-not (Test-Path -LiteralPath $knownHosts -PathType Leaf)) { throw 'Pinned known_hosts file is missing.' }
if (-not (Test-Path -LiteralPath $identityFile -PathType Leaf)) { throw 'Pinned SSH identity file is missing.' }
if ($Domain -and ($Domain -notmatch '^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$' -or $Domain.Contains('..'))) {
    throw 'PORTAL_STAGE7_DOMAIN must be a plain DNS hostname.'
}
$currentBranch = (& git -C $repo branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $currentBranch -ne $Branch) { throw "Expected branch $Branch; found $currentBranch." }
& git -C $repo diff --quiet
if ($LASTEXITCODE -ne 0) { throw 'Tracked working-tree changes must be committed before deployment.' }
& git -C $repo diff --cached --quiet
if ($LASTEXITCODE -ne 0) { throw 'Staged changes must be committed before deployment.' }
$commit = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $commit -notmatch '^[0-9a-f]{40}$') { throw 'Could not resolve pinned commit.' }
$workingDeployHash = (& git -C $repo hash-object -- $deployScript).Trim()
$committedDeployHash = (& git -C $repo rev-parse "${commit}:server/vps_stage7_staging_deploy.sh").Trim()
if ($LASTEXITCODE -ne 0 -or $workingDeployHash -ne $committedDeployHash) {
    throw 'The deploy script differs from the pinned commit; commit it before deployment.'
}
$relayProcess = $null
try {
    $normalizedDeploy = ([System.IO.File]::ReadAllText($deployScript, [System.Text.Encoding]::UTF8) -replace "`r`n", "`n")
    $transferScript = Join-Path $env:TEMP ("portal-stage7-deploy-{0}-{1}.sh" -f $commit, [guid]::NewGuid().ToString('N'))
    [System.IO.File]::WriteAllText($transferScript, $normalizedDeploy, [System.Text.UTF8Encoding]::new($false))
    $connectionHost = $HostName
    $connectionPort = $Port
    if ($UseBannerRelay) {
        if ($HostName -ne '178.209.127.247' -or $Port -ne 22) {
            throw 'Banner relay is pinned to the configured PORTAL VPS; use -UseBannerRelay:$false for a different host.'
        }
        $python = (Get-Command python.exe -ErrorAction Stop).Source
        $relayScript = Join-Path $repo 'tools\ssh_banner_first_relay.py'
        $relayOutLog = Join-Path $logDir ("stage7-relay-{0}.out.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
        $relayErrLog = Join-Path $logDir ("stage7-relay-{0}.err.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
        $relayProcess = Start-Process -FilePath $python -ArgumentList @("`"$relayScript`"") -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $relayOutLog -RedirectStandardError $relayErrLog
        $connectionHost = '127.0.0.1'
        $connectionPort = 2223
        $HostKeyAlias = $HostName
        $listenerReady = $false
        foreach ($attempt in 1..20) {
            $probe = [System.Net.Sockets.TcpClient]::new()
            try { $probe.Connect('127.0.0.1', 2223); $listenerReady = $true; break }
            catch { Start-Sleep -Milliseconds 250 }
            finally { $probe.Dispose() }
        }
        if (-not $listenerReady) { throw 'Pinned local SSH banner relay did not start.' }
    }
    $sshArgs = @('-4','-F','/dev/null','-p',"$connectionPort",'-i',$identityFile,'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o',"UserKnownHostsFile=$knownHosts",'-o','ConnectTimeout=10','-o','ConnectionAttempts=1','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2')
    $scpArgs = @('-4','-F','/dev/null','-P',"$connectionPort",'-i',$identityFile,'-B','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o',"UserKnownHostsFile=$knownHosts",'-o','ConnectTimeout=10','-o','ConnectionAttempts=1')
    if ($HostKeyAlias) {
        $sshArgs += @('-o',"HostKeyAlias=$HostKeyAlias")
        $scpArgs += @('-o',"HostKeyAlias=$HostKeyAlias")
    }
    $remote = "${UserName}@${connectionHost}"
    Write-Log "Stage 7 runner started; branch=$Branch commit=$commit host=$HostName port=$connectionPort relay=$UseBannerRelay"
    $connected = $false
    foreach ($attempt in 1..3) {
        & $ssh @sshArgs $remote 'true' 2>&1 | ForEach-Object { Write-Log ([string]$_) }
        if ($LASTEXITCODE -eq 0) { $connected = $true; break }
        if ($attempt -lt 3) { Start-Sleep -Seconds (2 * $attempt) }
    }
    if (-not $connected) { Write-Log 'SSH preflight failed after bounded retries.'; exit 20 }

& $ssh @sshArgs $remote 'install -d -m 0700 /run/portal-stage7-runner' 2>&1 | ForEach-Object { Write-Log ([string]$_) }
if ($LASTEXITCODE -ne 0) { Write-Log 'Could not prepare protected remote staging path.'; exit 21 }
& $scp @scpArgs $transferScript "${remote}:/run/portal-stage7-runner/deploy.sh" 2>&1 | ForEach-Object { Write-Log ([string]$_) }
if ($LASTEXITCODE -ne 0) { Write-Log 'Could not transfer deploy script over verified SSH.'; exit 21 }
$sslipPilot = if ($Domain -or $UseCloudflareTunnel) { '0' } else { '1' }
$tunnelPilot = if ($UseCloudflareTunnel) { '1' } else { '0' }
$pilotMode = if ($Domain) { "domain=$Domain" } elseif ($UseCloudflareTunnel) { 'Cloudflare Quick Tunnel' } else { 'SSLIP pilot' }
$deploy = "chmod 0700 /run/portal-stage7-runner/deploy.sh && PORTAL_STAGE7_BRANCH=$Branch PORTAL_STAGE7_EXPECTED_COMMIT=$commit PORTAL_STAGE7_DOMAIN=$Domain PORTAL_STAGE7_PILOT_SSLIP=$sslipPilot PORTAL_STAGE7_PILOT_TUNNEL=$tunnelPilot bash /run/portal-stage7-runner/deploy.sh"
Write-Log "Deploying pinned staging commit $commit with HTTPS pilot mode: $pilotMode."
& $ssh @sshArgs $remote $deploy 2>&1 | ForEach-Object { Write-Log ([string]$_) }
$deployExit = $LASTEXITCODE
if ($deployExit -ne 0) { Write-Log "Remote deploy failed with exit code $deployExit."; exit $deployExit }

$result = ((& $ssh @sshArgs $remote 'cat /srv/portal-stage7/STAGE7_RESULT.txt' 2>&1 | Out-String) -replace "`r", "").Trim()
$resultExit = $LASTEXITCODE
if ($resultExit -ne 0) { Write-Log 'Could not read STAGE7_RESULT.txt.'; exit 21 }
Write-Log 'Remote result follows:'
$result -split "`r?`n" | ForEach-Object { Write-Log $_ }
if ($result -notmatch "(?m)^commit=$commit$" -or $result -notmatch '(?m)^production_database_touched=no$' -or $result -notmatch '(?m)^https_status=ok$') {
    Write-Log 'Stage 7 result did not satisfy pinned commit, HTTPS, and production safety checks.'
    exit 22
}
if ($result -notmatch '(?m)^public_url=(https://[^\s]+)$') { Write-Log 'HTTPS public URL missing from result.'; exit 22 }
$publicUrl = $Matches[1].TrimEnd('/')
$curl = (Get-Command curl.exe -ErrorAction Stop).Source
$pingJson = ''
$pingExit = 1
foreach ($attempt in 1..5) {
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $pingJson = (& $curl --connect-timeout 8 --max-time 15 -fsS "$publicUrl/api/ping" 2>&1 | Out-String).Trim()
        $pingExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($pingExit -eq 0) { break }
    if ($attempt -lt 5) {
        $delay = @(2,4,8,12)[$attempt - 1]
        Write-Log "External HTTPS /api/ping retry $attempt/5 in ${delay}s after DNS or connect error."
        Start-Sleep -Seconds $delay
    }
}
if ($pingExit -ne 0) { Write-Log "External HTTPS /api/ping failed after bounded retries: $pingJson"; exit 23 }
try {
    $ping = $pingJson | ConvertFrom-Json
} catch {
    Write-Log 'External HTTPS /api/ping returned invalid JSON.'
    exit 23
}
if (-not $ping.ok -or $ping.setup_required) {
    Write-Log 'External HTTPS /api/ping was unhealthy or setup is incomplete.'
    exit 23
}
$setupStatus = ''
$setupExit = 1
foreach ($attempt in 1..3) {
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $setupStatus = (& $curl --connect-timeout 8 --max-time 15 -sS -o NUL -w '%{http_code}' -X POST -H 'Content-Type: application/json' --data '{}' "$publicUrl/api/setup" 2>&1 | Out-String).Trim()
        $setupExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($setupExit -eq 0 -and $setupStatus -eq '403') { break }
    if ($attempt -lt 3) { Start-Sleep -Seconds (2 * $attempt) }
}
if ($setupExit -ne 0 -or $setupStatus -ne '403') {
    Write-Log "External /api/setup returned HTTP $setupStatus, expected 403."
    exit 24
}
Write-Log 'STAGE7_API_OK; external HTTPS certificate, /api/ping and /api/setup block verified.'
exit 0
} finally {
    if ($null -ne $relayProcess -and -not $relayProcess.HasExited) {
        Stop-Process -Id $relayProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($transferScript -and (Test-Path -LiteralPath $transferScript)) {
        Remove-Item -LiteralPath $transferScript -Force -ErrorAction SilentlyContinue
    }
}
