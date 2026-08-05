# =====================================================================
<#
.SYNOPSIS
  检查一个 WeFlow profile 的 API，并在该 profile 缺失时启动一次。
.DESCRIPTION
  默认检查 127.0.0.1:5031 和默认 profile。可用独立端口与 --user-data-dir
  管理多个 WeFlow profile。脚本只匹配目标 profile，不会因其他 WeFlow
  实例存在而拒绝启动；启动后只做有界等待与端口回读，不循环重启。
.PARAMETER Port
  目标 WeFlow API 端口，默认 5031。
.PARAMETER UserDataDir
  可选的独立 profile 目录；未提供时匹配没有 --user-data-dir 的默认实例。
.PARAMETER InstanceName
  可选的日志实例名，不参与进程匹配。
.PARAMETER LogPath
  可选日志路径；默认 <project>\logs\weflow_heartbeat.log。
#>
[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 5031,

    [AllowNull()]
    [string]$UserDataDir,

    [AllowNull()]
    [string]$InstanceName,

    [AllowNull()]
    [string]$LogPath
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$root = $PSScriptRoot
if (-not $root) { $root = 'E:\Projects\Tools\WeFlowBridge' }

$exe = 'C:\Program Files\WeFlow\WeFlow.exe'
$workingDirectory = Split-Path -Parent $exe
$HttpTimeoutSeconds = 2
$TcpTimeoutMilliseconds = 1500
$StartupWaitSeconds = 15
$ProbeIntervalMilliseconds = 1000

function ConvertTo-NormalizedProfilePath {
    param([AllowNull()][string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) { return $null }
    $candidate = $Path.Trim().Trim([char[]]@('"'))
    try {
        return [System.IO.Path]::GetFullPath($candidate).TrimEnd([char[]]@('\', '/'))
    } catch {
        return $candidate.TrimEnd([char[]]@('\', '/'))
    }
}

$effectiveUserDataDir = ConvertTo-NormalizedProfilePath -Path $UserDataDir
$instanceLabel = if (-not [string]::IsNullOrWhiteSpace($InstanceName)) {
    $InstanceName.Trim()
} elseif ($effectiveUserDataDir) {
    "profile-$Port"
} else {
    'default'
}

$effectiveLogPath = if ([string]::IsNullOrWhiteSpace($LogPath)) {
    Join-Path (Join-Path $root 'logs') 'weflow_heartbeat.log'
} else {
    [System.IO.Path]::GetFullPath($LogPath)
}
$logDirectory = Split-Path -Parent $effectiveLogPath
if ($logDirectory) {
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
}

function Write-HeartbeatLog {
    param([string]$Message)

    $line = '{0}  [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $instanceLabel, $Message
    Add-Content -LiteralPath $effectiveLogPath -Value $line -Encoding UTF8
}

if ($effectiveUserDataDir -and
    -not (Test-Path -LiteralPath $effectiveUserDataDir -PathType Container)) {
    Write-HeartbeatLog "[ERR] required profile directory is missing; refusing to create an empty profile"
    exit 2
}

function Test-WeFlowHealth {
    param([ValidateRange(1, 65535)][int]$Port)

    $healthUri = 'http://127.0.0.1:{0}/health' -f $Port
    try {
        $response = Invoke-WebRequest -Uri $healthUri -Method Get -UseBasicParsing `
            -TimeoutSec $HttpTimeoutSeconds -ErrorAction Stop
        if ([int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 300) {
            return $true
        }
    } catch {
        # HTTP 失败后回退到同一端口的有界 TCP 探测。
    }

    $tcpClient = [System.Net.Sockets.TcpClient]::new()
    try {
        $connectTask = $tcpClient.ConnectAsync('127.0.0.1', $Port)
        if (-not $connectTask.Wait($TcpTimeoutMilliseconds)) { return $false }
        return $tcpClient.Connected
    } catch {
        return $false
    } finally {
        $tcpClient.Dispose()
    }
}

function Get-TargetWeFlowProcess {
    param([AllowNull()][string]$UserDataDir)

    $targetProfilePath = ConvertTo-NormalizedProfilePath -Path $UserDataDir
    $userDataPattern = '(?i)(?:^|\s)--user-data-dir(?:=|\s+)(?:"(?<quoted>[^"]+)"|(?<plain>[^\s"]+))'
    $processes = @(Get-CimInstance -ClassName Win32_Process -Filter "Name = 'WeFlow.exe'" -ErrorAction SilentlyContinue)

    foreach ($process in $processes) {
        $commandLine = ([string]$process.CommandLine)
        if ([string]::IsNullOrWhiteSpace($commandLine)) { continue }
        if ($commandLine -match '(?i)(?:^|\s)--type(?:=|\s)') { continue }

        $profileMatch = [regex]::Match($commandLine, $userDataPattern)
        if (-not $targetProfilePath) {
            if (-not $profileMatch.Success) { return $process }
            continue
        }

        if (-not $profileMatch.Success) { continue }
        $processProfilePath = if ($profileMatch.Groups['quoted'].Success) {
            $profileMatch.Groups['quoted'].Value
        } else {
            $profileMatch.Groups['plain'].Value
        }
        $normalizedProcessProfilePath = ConvertTo-NormalizedProfilePath -Path $processProfilePath
        if ([System.StringComparer]::OrdinalIgnoreCase.Equals($normalizedProcessProfilePath, $targetProfilePath)) {
            return $process
        }
    }

    return $null
}

if (Test-WeFlowHealth -Port $Port) {
    Write-HeartbeatLog "[OK] WeFlow API $Port 健康"
    exit 0
}

Write-HeartbeatLog "[WARN] $Port 无响应；检查目标 profile"
$targetProfileProcess = Get-TargetWeFlowProcess -UserDataDir $effectiveUserDataDir
if ($targetProfileProcess) {
    Write-HeartbeatLog "[INFO] 目标 profile 进程已运行但端口未通；本轮不重复启动"
    exit 1
}

if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    Write-HeartbeatLog "[ERR] 找不到 WeFlow.exe"
    exit 1
}

$startParameters = @{
    FilePath = $exe
    WorkingDirectory = $workingDirectory
    PassThru = $true
    ErrorAction = 'Stop'
}
if ($effectiveUserDataDir) {
    $startParameters['ArgumentList'] = @("--user-data-dir=`"$effectiveUserDataDir`"")
}

try {
    $startedProcess = Start-Process @startParameters
    Write-HeartbeatLog "[INFO] 已启动目标 profile；等待 API 端口恢复"
} catch {
    Write-HeartbeatLog "[ERR] 目标 profile 启动失败"
    exit 1
}

$startupDeadline = (Get-Date).AddSeconds($StartupWaitSeconds)
while ((Get-Date) -lt $startupDeadline) {
    Start-Sleep -Milliseconds $ProbeIntervalMilliseconds
    if (Test-WeFlowHealth -Port $Port) {
        Write-HeartbeatLog "[OK] WeFlow 已拉起，$Port 恢复"
        exit 0
    }
    if ($startedProcess.HasExited) { break }
}

if (Test-WeFlowHealth -Port $Port) {
    Write-HeartbeatLog "[OK] WeFlow 已拉起，$Port 恢复"
    exit 0
}

Write-HeartbeatLog "[WARN] 已启动目标 profile，但 $Port 在有界等待后仍未恢复"
exit 1
