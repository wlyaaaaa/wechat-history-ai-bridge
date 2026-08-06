# WeFlow 多 profile 看门狗与自启

> 让一个或多个 WeFlow API profile 与微信在登录后稳定启动。供 OpenClaw 等本机服务稳定取数。

## 计划任务（由 `weflow_boot_guardian.ps1` 注册）
| 任务 | 触发 | 作用 |
|------|------|------|
| **WeFlow Watchdog** | 登录 + 每 15 分钟 | 默认检查 5031；端口不通且目标 profile 缺失时只启动一次 `WeFlow.exe` |
| **WeChat AutoStart** | 登录 | 默认拉起 `Weixin.exe` 一次；若同名任务由 PCConfig 双开 owner 管理则原样保留 |

### 与 PCConfig 微信双开的兼容边界

- PCConfig 管理的双开任务在 Description 中带 marker：`owner=pcconfig.wechat-dual-autostart.v1`。
- 检测到该 marker 时，本脚本会保留 PCConfig 管理的双开任务，不使用 `-Force` 覆盖它。
- 没有该 marker（包括项目原有独立任务）时，仍按原行为注册单次启动任务，保持旧用法兼容。

## 多 profile heartbeat

`weflow_heartbeat.ps1` 的零参数调用保持兼容：仍检查端口 5031、匹配没有
`--user-data-dir` 的默认 profile，并写入原日志。参数如下：

| 参数 | 说明 |
|------|------|
| `-Port` | API 端口；默认 5031 |
| `-UserDataDir` | 可选独立 profile 目录；提供时会传给 WeFlow 的 `--user-data-dir` |
| `-InstanceName` | 可选日志实例名，不参与 profile 匹配 |
| `-LogPath` | 可选独立日志路径 |
| `-NoProxyServer` | 可选；启动 Electron 时绕过系统代理，不依赖或猜测代理端口 |
| `-HiddenLaunch` | 可选；让后台任务启动的 WeFlow 窗口保持隐藏 |

例如，为一个使用 16000 端口的独立 profile 运行一次有界检查（示例目录不代表
本机真实 profile）：

```powershell
$secondaryProfile = Join-Path $env:LOCALAPPDATA 'WeFlowProfiles\secondary'
powershell -NoProfile -ExecutionPolicy Bypass `
  -File E:\Projects\Tools\WeFlowBridge\weflow_heartbeat.ps1 `
  -Port 16000 `
  -UserDataDir $secondaryProfile `
  -InstanceName 'secondary-16000' `
  -LogPath (Join-Path $env:LOCALAPPDATA 'WeFlowBridge\weflow_16000.log')
```

健康检查先请求回环地址的 `/health`，失败后才做有界 TCP 探测。端口不通时，
脚本只匹配目标 profile 的主进程：其他 WeFlow 实例不会阻止它启动。目标进程已在
运行时本轮退出并记录异常；目标进程缺失时只启动一次，使用 WeFlow 安装目录作为
WorkingDirectory，并在有界等待后回读端口，不会无限重启。

显式传入 `-UserDataDir` 时，profile 目录不存在时失败关闭（退出码 2），不会让
Electron 静默创建空 profile。profile 的迁移、登录态和 API 端口设置由其内容 owner
先完成；heartbeat 只消费已经存在的 profile 目录。

`weflow_boot_guardian.ps1` 继续只注册零参数的默认 5031 任务。其他 profile 应由其
配置 owner 使用上述参数注册独立任务，并使用独立 `-InstanceName` / `-LogPath`。

## 安装与静默执行优化

### 静默执行包装器 (`weflow_heartbeat.vbs`)
为了避免 Windows 计划任务在后台每 15 分钟执行 PowerShell 检查时在桌面短暂闪烁出现黑框（控制台窗口），项目中提供了一个 **VBScript 静默包装器**：
- `weflow_heartbeat.vbs` 会在后台静默调用 `weflow_heartbeat.ps1`，不创建任何可见窗口；零参数调用保持兼容，也会安全透传多 profile 参数。
- `weflow_boot_guardian.ps1` 注册计划任务时，会自动检测此 VBS 文件；若存在则以 `wscript.exe` 注册该静默任务。

### 安装命令
请以**管理员权限**打开 PowerShell 并运行：
```powershell
powershell -ExecutionPolicy Bypass -File E:\Projects\Tools\WeFlowBridge\weflow_boot_guardian.ps1
```

## 关于"非登录运行"
WeFlow / 微信都是 **GUI 程序**，需要**交互会话**才能正常渲染与登录，所以看门狗用
**登录触发（Interactive）**——你登录（或开机自动登录）后即自动拉起。

要实现真正"关机重启后无人操作也运行"，需开 **Windows 自动登录**：
```powershell
powershell -ExecutionPolicy Bypass -File E:\Projects\Tools\WeFlowBridge\enable-autologin.ps1
```
> ⚠️ 自动登录会把密码以可逆方式存入注册表（`HKLM\...\Winlogon`），属安全取舍，仅在物理安全的机器上用。撤销：`AutoAdminLogon=0` 并删除 `DefaultPassword`。

## 排查
```powershell
Get-ScheduledTask 'WeFlow Watchdog','WeChat AutoStart' | Format-Table TaskName,State
Get-Content E:\Projects\Tools\WeFlowBridge\logs\weflow_heartbeat.log -Tail 20
powershell -File E:\Projects\Tools\WeFlowBridge\probe-weflow.ps1     # API 健康自检
```
> 注：WeFlow 的 API 服务首次需在 **WeFlow → 设置 → API 服务 → 启动服务** 打开一次（之后随 WeFlow 启动）。
