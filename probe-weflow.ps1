# probe-weflow.ps1 - WeFlow API self-check
# Reads local .env, probes endpoints, and never hard-codes secrets.

param(
    [switch]$Json,
    [ValidateSet('MetadataOnly','FullProbe')]
    [string]$Mode = 'FullProbe',
    [switch]$NoMessages
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$effectiveNoMessages = $NoMessages -or $Mode -eq 'MetadataOnly'
$requiredEndpointNames = @(
    'GET /health',
    'GET /api/v1/sessions?limit=3',
    'GET /api/v1/sessions?format=chatlab',
    'GET /api/v1/contacts?limit=3',
    'GET /api/v1/sns/export/stats'
)

function Get-RequiredEndpointFailures([object[]]$EndpointResults) {
    $results = @($EndpointResults)
    $failures = [System.Collections.Generic.List[string]]::new()
    foreach ($requiredName in $requiredEndpointNames) {
        $match = @($results | Where-Object { $_.name -eq $requiredName } | Select-Object -First 1)
        if ($match.Count -ne 1 -or -not [bool]($match[0].ok)) {
            $failures.Add($requiredName)
        }
    }
    return @($failures)
}

function Get-Shape($value) {
    if ($null -eq $value) { return '' }
    return (($value.PSObject.Properties.Name | Select-Object -First 10) -join ',')
}

function Get-ResultCount($value) {
    if ($null -eq $value) { return $null }
    foreach ($name in @('count', 'total')) {
        if ($null -ne $value.$name) { return [int]$value.$name }
    }
    foreach ($name in @('sessions', 'contacts', 'messages', 'data', 'timeline', 'members')) {
        if ($value.$name) { return @($value.$name).Count }
    }
    return $null
}

function Get-RedactedBaseUrl([string]$value) {
    if ([string]::IsNullOrWhiteSpace($value)) { return 'http://127.0.0.1:5031' }
    try {
        $uri = [uri]$value
        $port = if ($uri.IsDefaultPort) { '' } else { ":$($uri.Port)" }
        return "$($uri.Scheme)://$($uri.Host)$port"
    } catch {
        return '<invalid-base-url>'
    }
}

function New-EndpointResult(
    [string]$Name,
    [string]$Method,
    [string]$EndpointFamily,
    [bool]$Ok,
    $Payload = $null,
    $HttpStatus = $null
) {
    [ordered]@{
        name = $Name
        method = $Method
        endpoint_family = $EndpointFamily
        ok = $Ok
        http_status = $HttpStatus
        shape = Get-Shape $Payload
        count = Get-ResultCount $Payload
        sync_present = [bool]($Payload -and $Payload.sync)
    }
}

function Write-ProbeResult($ok, $name, $shape, $note = '') {
    if ($ok) {
        $suffix = if ($shape) { " [$shape]" } else { '' }
        Write-Host "[OK ] $name$suffix" -ForegroundColor Green
    } else {
        Write-Host "[ERR] $name -> $note" -ForegroundColor Red
    }
}

function Invoke-JsonRequest(
    [string]$Name,
    [string]$Method,
    [string]$EndpointFamily,
    [string]$Url,
    [hashtable]$Headers,
    $Body = $null
) {
    try {
        $invokeArgs = @{
            Uri = $Url
            Headers = $Headers
            TimeoutSec = 8
            Method = $Method
        }
        if ($null -ne $Body) {
            $invokeArgs['ContentType'] = 'application/json'
            $invokeArgs['Body'] = ($Body | ConvertTo-Json -Compress)
        }
        $payload = Invoke-RestMethod @invokeArgs
        return [ordered]@{
            payload = $payload
            result = (New-EndpointResult $Name $Method $EndpointFamily $true $payload 200)
        }
    } catch {
        $code = $null
        try { $code = $_.Exception.Response.StatusCode.value__ } catch { $code = $null }
        return [ordered]@{
            payload = $null
            result = (New-EndpointResult $Name $Method $EndpointFamily $false $null $code)
        }
    }
}

function Try-Get($name, $url, $headers) {
    try {
        $r = Invoke-RestMethod -Uri $url -Headers $headers -TimeoutSec 8
        Write-ProbeResult $true $name (Get-Shape $r)
        return $r
    } catch {
        $code = $_.Exception.Response.StatusCode.value__ 2>$null
        Write-ProbeResult $false $name '' "$($_.Exception.Message)$(if($code){" (HTTP $code)"})"
        return $null
    }
}

function Try-Post($name, $url, $headers, $body) {
    try {
        $bodyJson = $body | ConvertTo-Json -Compress
        $r = Invoke-RestMethod -Uri $url -Method Post -Headers $headers -ContentType 'application/json' -Body $bodyJson -TimeoutSec 8
        Write-ProbeResult $true $name (Get-Shape $r)
        return $r
    } catch {
        $code = $_.Exception.Response.StatusCode.value__ 2>$null
        Write-ProbeResult $false $name '' "$($_.Exception.Message)$(if($code){" (HTTP $code)"})"
        return $null
    }
}

$envPath = Join-Path $PSScriptRoot '.env'
$envExists = Test-Path $envPath

if (-not $envExists) {
    if ($Json) {
        [ordered]@{
            schema_version = 'weflow-probe.v1'
            ok = $false
            required_endpoint_failures = @($requiredEndpointNames)
            weflow_baseline = @{
                version = '26.7.3'
                product_version = '26.7.3.0'
                verified_on = '2026-07-09'
            }
            env_file_present = $false
            base_url_redacted = 'http://127.0.0.1:5031'
            token_present = $false
            mode = $Mode
            no_messages = [bool]$effectiveNoMessages
            privacy = @{
                redacted = $true
                message_text_printed = $false
                raw_media_paths_included = $false
                token_printed = $false
            }
            endpoint_results = @()
            error = 'missing_env'
        } | ConvertTo-Json -Depth 8
        exit 1
    }
    Write-Host "Missing .env. Copy .env.example to .env and fill local values." -ForegroundColor Red
    exit 1
}

$cfg = @{}
Get-Content $envPath | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object {
    $k, $v = $_ -split '=', 2
    $cfg[$k.Trim()] = $v.Trim()
}
$base = $cfg['WEFLOW_BASE_URL']
$token = $cfg['WEFLOW_TOKEN']
if (-not $base) { $base = 'http://127.0.0.1:5031' }

$headers = @{}
if ($token -and $token -ne '__FILL_ME__') { $headers['Authorization'] = "Bearer $token" }

if ($Json) {
    $endpointResults = [System.Collections.Generic.List[object]]::new()
    $health = Invoke-JsonRequest 'GET /health' 'GET' 'health' "$base/health" @{}
    $endpointResults.Add($health.result)

    $sessions = $null
    if ($health.result.ok) {
        $sessionsResult = Invoke-JsonRequest 'GET /api/v1/sessions?limit=3' 'GET' 'sessions' "$base/api/v1/sessions?limit=3" $headers
        $sessions = $sessionsResult.payload
        $endpointResults.Add($sessionsResult.result)

        $sessionsPost = Invoke-JsonRequest 'POST /api/v1/sessions' 'POST' 'sessions' "$base/api/v1/sessions" $headers @{ limit = 1 }
        $endpointResults.Add($sessionsPost.result)

        $chatlabSessions = Invoke-JsonRequest 'GET /api/v1/sessions?format=chatlab' 'GET' 'sessions' "${base}/api/v1/sessions?format=chatlab&limit=1" $headers
        $endpointResults.Add($chatlabSessions.result)

        $contacts = Invoke-JsonRequest 'GET /api/v1/contacts?limit=3' 'GET' 'contacts' "$base/api/v1/contacts?limit=3" $headers
        $endpointResults.Add($contacts.result)

        $stats = Invoke-JsonRequest 'GET /api/v1/sns/export/stats' 'GET' 'sns' "$base/api/v1/sns/export/stats" $headers
        $endpointResults.Add($stats.result)

        $groupTalker = $null
        if ($sessions -and $sessions.sessions) {
            $candidate = $sessions.sessions | Where-Object { $_.username -like '*@chatroom' } | Select-Object -First 1
            if ($candidate) { $groupTalker = $candidate.username }
        }
        if ($groupTalker) {
            $groupMembers = Invoke-JsonRequest 'GET /api/v1/group-members (redacted group)' 'GET' 'group_members' "$base/api/v1/group-members?talker=$groupTalker" $headers
            $endpointResults.Add($groupMembers.result)

            $groupPost = Invoke-JsonRequest 'POST /api/v1/group-members (redacted group)' 'POST' 'group_members' "$base/api/v1/group-members" $headers @{ chatroomId = $groupTalker; includeMessageCounts = $true }
            $endpointResults.Add($groupPost.result)

            if (-not $effectiveNoMessages) {
                $latest = Invoke-JsonRequest 'GET /api/v1/messages (redacted group, latest)' 'GET' 'messages' "${base}/api/v1/messages?talker=$groupTalker&limit=5" $headers
                $endpointResults.Add($latest.result)

                $encodedTalker = [uri]::EscapeDataString($groupTalker)
                $pull = Invoke-JsonRequest 'GET /api/v1/sessions/{id}/messages (ChatLab Pull)' 'GET' 'chatlab_pull' "${base}/api/v1/sessions/$encodedTalker/messages?limit=1" $headers
                $endpointResults.Add($pull.result)
            }
        }
    }

    $requiredEndpointFailures = @(
        Get-RequiredEndpointFailures -EndpointResults @($endpointResults)
    )
    $probeOk = $requiredEndpointFailures.Count -eq 0
    [ordered]@{
        schema_version = 'weflow-probe.v1'
        ok = $probeOk
        required_endpoint_failures = $requiredEndpointFailures
        weflow_baseline = @{
            version = '26.7.3'
            product_version = '26.7.3.0'
            verified_on = '2026-07-09'
        }
        env_file_present = $true
        base_url_redacted = Get-RedactedBaseUrl $base
        token_present = [bool]$headers.Count
        mode = $Mode
        no_messages = [bool]$effectiveNoMessages
        privacy = @{
            redacted = $true
            message_text_printed = $false
            raw_media_paths_included = $false
            token_printed = $false
        }
        endpoint_results = @($endpointResults)
    } | ConvertTo-Json -Depth 8

    if (-not $probeOk) { exit 1 }
    exit 0
}

Write-Host "Base: $base   Token: $(if($headers.Count){'loaded'}else{'missing'})`n" -ForegroundColor Cyan

$h = Try-Get 'GET /health' "$base/health" @{}
if ($null -eq $h) {
    Write-Host "`nService may be offline. Start WeFlow API service in local settings." -ForegroundColor Yellow
    exit 1
}
$requiredEndpointFailures = [System.Collections.Generic.List[string]]::new()

$s = Try-Get 'GET /api/v1/sessions?limit=3' "${base}/api/v1/sessions?limit=3" $headers
if ($s) { Write-Host "     session_count: $($s.count) / total: $($s.total)" }
if ($null -eq $s) { $requiredEndpointFailures.Add('GET /api/v1/sessions?limit=3') }

$sp = Try-Post 'POST /api/v1/sessions' "${base}/api/v1/sessions" $headers @{ limit = 1 }
if ($sp) { Write-Host "     POST sessions probe: OK" }

$sc = Try-Get 'GET /api/v1/sessions?format=chatlab' "${base}/api/v1/sessions?format=chatlab&limit=1" $headers
if ($sc -and $sc.sessions) { Write-Host "     ChatLab Pull session_index_count: $(@($sc.sessions).Count)" }
if ($null -eq $sc) { $requiredEndpointFailures.Add('GET /api/v1/sessions?format=chatlab') }

$c = Try-Get 'GET /api/v1/contacts?limit=3' "${base}/api/v1/contacts?limit=3" $headers
if ($c) { Write-Host "     contact_count: $($c.count)" }
if ($null -eq $c) { $requiredEndpointFailures.Add('GET /api/v1/contacts?limit=3') }

$grp = $null
$grpSession = $null
if ($s -and $s.sessions) {
    $grpSession = $s.sessions | Where-Object { $_.username -like '*@chatroom' } | Select-Object -First 1
    if ($grpSession) { $grp = $grpSession.username }
}
if (-not $grp) {
    $moreSessions = Try-Get 'GET /api/v1/sessions?limit=30' "$base/api/v1/sessions?limit=30" $headers
    if ($moreSessions -and $moreSessions.sessions) {
        $grpSession = $moreSessions.sessions | Where-Object { $_.username -like '*@chatroom' } | Select-Object -First 1
        if ($grpSession) { $grp = $grpSession.username }
    }
}
if ($grp) {
    $gm = Try-Get 'GET /api/v1/group-members (redacted group)' "${base}/api/v1/group-members?talker=$grp" $headers
    if ($gm) { Write-Host "     group_member_count: $($gm.count)  fromCache=$($gm.fromCache)" }

    $gmp = Try-Post 'POST /api/v1/group-members (redacted group)' "${base}/api/v1/group-members" $headers @{ chatroomId = $grp; includeMessageCounts = $true }
    if ($gmp) { Write-Host "     POST group-members probe: OK" }
}

$es = Try-Get 'GET /api/v1/sns/export/stats' "${base}/api/v1/sns/export/stats" $headers
if ($es) { Write-Host "     sns_stats: totalPosts=$($es.data.totalPosts) totalFriends=$($es.data.totalFriends) myPosts=$($es.data.myPosts)" }
if ($null -eq $es) { $requiredEndpointFailures.Add('GET /api/v1/sns/export/stats') }

if ($grp -and -not $effectiveNoMessages) {
    $latest = Try-Get 'GET /api/v1/messages (redacted group, latest no date)' "${base}/api/v1/messages?talker=$grp&limit=5" $headers
    if ($latest) {
        $items = @()
        if ($latest.messages) { $items = @($latest.messages) }
        elseif ($latest.data) { $items = @($latest.data) }
        $latestCount = if ($null -ne $latest.count) { $latest.count } else { $items.Count }
        Write-Host "     latest_message_count: $latestCount (createTime descending; newest at index 0)"
        if ($items.Count -gt 0 -and $items[0].createTime) {
            $newest = [int64]$items[0].createTime
            $sessionLast = $grpSession.lastTimestamp
            Write-Host "     latest matches session.lastTimestamp: $($newest -eq [int64]$sessionLast)"
        }
    }

    $mp = Try-Post 'POST /api/v1/messages (redacted group, latest no date)' "${base}/api/v1/messages" $headers @{ talker = $grp; limit = 1 }
    if ($mp) { Write-Host "     POST messages probe: OK" }

    $encodedTalker = [uri]::EscapeDataString($grp)
    $pull = Try-Get 'GET /api/v1/sessions/{id}/messages (ChatLab Pull)' "${base}/api/v1/sessions/$encodedTalker/messages?limit=1" $headers
    if ($pull) {
        $pullCount = if ($pull.messages) { @($pull.messages).Count } else { 0 }
        $hasSync = $null -ne $pull.sync
        Write-Host "     ChatLab Pull message_count: $pullCount  sync=$hasSync"
    }

    if ($Mode -eq 'FullProbe') {
        $m = Try-Get 'GET /api/v1/messages (redacted group, legacy wide window)' "${base}/api/v1/messages?talker=$grp&start=20250101&end=20261231&limit=5" $headers
        if ($m) { Write-Host "     legacy_window_message_count: $($m.count) (0 can be normal read-race behavior)" }
    }
}

if ($requiredEndpointFailures.Count -gt 0) {
    Write-Host "`nProbe incomplete. Required endpoint failures: $($requiredEndpointFailures -join ', ')" -ForegroundColor Red
    exit 1
}

Write-Host "`nProbe complete. Endpoint baseline: WeFlow 26.7.3 / 2026-07-09; re-probe after version changes." -ForegroundColor Cyan
exit 0
