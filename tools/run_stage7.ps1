[CmdletBinding()]
param(
    [string]$HostName = '178.209.127.247',
    [int]$Port = 22,
    [string]$HostKeyAlias = '',
    [string]$UserName = $(if ($env:PORTAL_STAGE7_SSH_USER) { $env:PORTAL_STAGE7_SSH_USER } else { 'root' }),
    [string]$Branch = 'portal-next-b003',
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

$sshArgs = @('-4','-F','/dev/null','-p',"$Port",'-i',$identityFile,'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o',"UserKnownHostsFile=$knownHosts",'-o','ConnectTimeout=10','-o','ConnectionAttempts=1','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2')
$scpArgs = @('-4','-F','/dev/null','-P',"$Port",'-i',$identityFile,'-B','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o',"UserKnownHostsFile=$knownHosts",'-o','ConnectTimeout=10','-o','ConnectionAttempts=1')
if ($HostKeyAlias) {
    $sshArgs += @('-o',"HostKeyAlias=$HostKeyAlias")
    $scpArgs += @('-o',"HostKeyAlias=$HostKeyAlias")
}
$remote = "${UserName}@${HostName}"
Write-Log "Stage 7 runner started; branch=$Branch commit=$commit host=$HostName"
$connected = $false
foreach ($attempt in 1..3) {
    & $ssh @sshArgs $remote 'true' 2>&1 | ForEach-Object { Write-Log ([string]$_) }
    if ($LASTEXITCODE -eq 0) { $connected = $true; break }
    if ($attempt -lt 3) { Start-Sleep -Seconds (2 * $attempt) }
}
if (-not $connected) { Write-Log 'SSH preflight failed after bounded retries.'; exit 20 }

& $ssh @sshArgs $remote 'install -d -m 0700 /run/portal-stage7-runner' 2>&1 | ForEach-Object { Write-Log ([string]$_) }
if ($LASTEXITCODE -ne 0) { Write-Log 'Could not prepare protected remote staging path.'; exit 21 }
& $scp @scpArgs $deployScript "${remote}:/run/portal-stage7-runner/deploy.sh" 2>&1 | ForEach-Object { Write-Log ([string]$_) }
if ($LASTEXITCODE -ne 0) { Write-Log 'Could not transfer deploy script over verified SSH.'; exit 21 }
$deploy = "chmod 0700 /run/portal-stage7-runner/deploy.sh && PORTAL_STAGE7_BRANCH=$Branch PORTAL_STAGE7_EXPECTED_COMMIT=$commit PORTAL_STAGE7_PILOT_SSLIP=1 PORTAL_STAGE7_PILOT_TUNNEL=1 bash /run/portal-stage7-runner/deploy.sh"
Write-Log "Deploying pinned staging commit $commit with SSLIP pilot enabled."
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
$doh = 'https://1.1.1.1/dns-query'

function Invoke-CurlCapture([string[]]$Arguments) {
    $stdoutPath = [IO.Path]::GetTempFileName()
    $stderrPath = [IO.Path]::GetTempFileName()
    try {
        $proc = Start-Process -FilePath $curl -ArgumentList $Arguments -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
        return [pscustomobject]@{
            ExitCode = $proc.ExitCode
            Stdout = ((Get-Content -LiteralPath $stdoutPath -Raw -ErrorAction SilentlyContinue) + '').Trim()
            Stderr = ((Get-Content -LiteralPath $stderrPath -Raw -ErrorAction SilentlyContinue) + '').Trim()
        }
    } finally {
        Remove-Item $stdoutPath,$stderrPath -Force -ErrorAction SilentlyContinue
    }
}

$ping = $null
$lastPingError = ''
foreach ($attempt in 1..12) {
    $res = Invoke-CurlCapture @('--doh-url',$doh,'--connect-timeout','5','--max-time','8','-fsS',"$publicUrl/api/ping")
    if ($res.ExitCode -eq 0) {
        try {
            $candidate = $res.Stdout | ConvertFrom-Json
            if ($candidate.ok -and -not $candidate.setup_required) {
                $ping = $candidate
                break
            }
            $lastPingError = 'API returned unhealthy state.'
        } catch {
            $lastPingError = 'API returned invalid JSON.'
        }
    } else {
        $lastPingError = $res.Stderr
    }
    if ($attempt -lt 12) { Start-Sleep -Seconds 2 }
}
if (-not $ping) {
    Write-Log "External HTTPS /api/ping did not become ready after bounded retries: $lastPingError"
    exit 23
}

$setupStatus = ''
foreach ($attempt in 1..6) {
    $res = Invoke-CurlCapture @('--doh-url',$doh,'--connect-timeout','5','--max-time','8','-sS','-o','NUL','-w','%{http_code}','-X','POST','-H','Content-Type: application/json','--data','{}',"$publicUrl/api/setup")
    $setupStatus = $res.Stdout
    if ($res.ExitCode -eq 0 -and $setupStatus -eq '403') { break }
    if ($attempt -lt 6) { Start-Sleep -Seconds 2 }
}
if ($setupStatus -ne '403') {
    Write-Log "External /api/setup returned HTTP $setupStatus, expected 403."
    exit 24
}
Write-Log 'STAGE7_API_OK; external HTTPS /api/ping and setup block verified through DNS-over-HTTPS.'
exit 0
