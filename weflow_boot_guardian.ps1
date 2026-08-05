<#
.SYNOPSIS
  注册 WeFlow 看门狗 + 微信自启计划任务。
.DESCRIPTION
  - "WeFlow Watchdog"：登录时检查 + 每 15 分钟检查 5031；默认 profile 缺失时只启动一次。
  - "WeChat AutoStart"：默认登录时拉起 Weixin.exe 一次；若同名任务由 PCConfig 双开 owner 管理则保留。
  说明：WeFlow / 微信都是 **GUI 程序**，需要交互会话才能正常渲染，故用 **登录触发(Interactive)**。
  若要真正"非登录(关机重启后无人登录也运行)"，需开 Windows 自动登录
  （见 enable-autologin.ps1，会把密码写入注册表，属安全取舍，自行决定）。
.NOTES  以管理员 PowerShell 运行。
#>
param([string]$User = "$env:USERDOMAIN\$env:USERNAME")
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot; if (-not $root) { $root = 'E:\Projects\Tools\WeFlowBridge' }

$pr = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $pr.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)) { throw '请以管理员 PowerShell 运行。' }

$principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Highest

# 1) WeFlow Watchdog：登录检查 + 每 15 分钟做有界健康检查
$vbs = Join-Path $root 'weflow_heartbeat.vbs'
if (Test-Path $vbs) {
    $wfAction = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument "`"$vbs`""
    $descDetail = "使用 VBS 静默包装器运行，无黑框闪烁"
} else {
    $wfAction = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$root\weflow_heartbeat.ps1`""
    $descDetail = "直接运行 PowerShell 脚本"
}
$wfLogon  = New-ScheduledTaskTrigger -AtLogOn
$wfRepeat = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15)
$wfSet = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -Hidden -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'WeFlow Watchdog' -Action $wfAction -Trigger $wfLogon,$wfRepeat `
    -Principal $principal -Settings $wfSet -Description "WeFlow API(5031) 默认 profile 看门狗 ($descDetail)：登录检查 + 15分钟有界健康检查" -Force | Out-Null
Write-Host "[OK] 已注册 'WeFlow Watchdog'（登录检查 + 15分钟有界健康检查，使用: $(if (Test-Path $vbs) { 'VBS 静默' } else { 'PowerShell' })）" -ForegroundColor Green

# 2) WeChat AutoStart：保留 PCConfig 管理的双开任务；否则维持旧的单次启动行为
$wechatTaskOwnerMarker = 'owner=pcconfig.wechat-dual-autostart.v1'
$pcConfigOwnedWeChatTask = Get-ScheduledTask -TaskName 'WeChat AutoStart' -ErrorAction SilentlyContinue |
    Where-Object { ([string]$_.Description).Contains($wechatTaskOwnerMarker) } |
    Select-Object -First 1

if ($pcConfigOwnedWeChatTask) {
    Write-Host "[SKIP] 已保留 PCConfig 管理的 'WeChat AutoStart' 双开任务" -ForegroundColor Cyan
} else {
    $wx = 'C:\Program Files\Tencent\Weixin\Weixin.exe'
    if (Test-Path $wx) {
        $wxAction  = New-ScheduledTaskAction -Execute $wx
        $wxTrigger = New-ScheduledTaskTrigger -AtLogOn
        Register-ScheduledTask -TaskName 'WeChat AutoStart' -Action $wxAction -Trigger $wxTrigger `
            -Principal $principal -Settings (New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew) `
            -Description '登录时自动启动微信(稳定，无重启看门狗)' -Force | Out-Null
        Write-Host "[OK] 已注册 'WeChat AutoStart'（登录自启）" -ForegroundColor Green
    } else { Write-Host "[WARN] 未找到 $wx，跳过微信自启" -ForegroundColor Yellow }
}

Write-Host "`n验证：" -ForegroundColor Cyan
Get-ScheduledTask | Where-Object { $_.TaskName -in 'WeFlow Watchdog','WeChat AutoStart' } | Select-Object TaskName,State | Format-Table -Auto
