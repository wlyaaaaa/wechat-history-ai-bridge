# AGENTS.md — WeFlow API 给 AI Agent 的速查

> 一页纸够你上手；要细节看 [README.md](README.md)（尤其 §4.5 完整端点地图）。
> **基线：WeFlow `26.7.3` / ProductVersion `26.7.3.0`，实测 2026-07-09。** 换版本先跑 `probe-weflow.ps1` 复核。
> 机器可读边界看 [project_manifest.json](project_manifest.json)。机器接口契约看 [docs/openapi.yaml](docs/openapi.yaml)，AI envelope schema 看 [schemas/ai-consumer-envelope.v2.schema.json](schemas/ai-consumer-envelope.v2.schema.json)。收尾审计看 [docs/closeout_audit.md](docs/closeout_audit.md)。AI 消费契约看 [docs/ai_consumer_contract.md](docs/ai_consumer_contract.md)，公开仓库隐私边界看 [docs/privacy_boundary.md](docs/privacy_boundary.md)。实际 AI 调用层是 `E:\.agents\plugins\weflow-toolkit`（`weflow-toolkit v0.2+`）。

## 它是什么
本机 `http://127.0.0.1:5031` 上的 WeFlow HTTP API —— 把**本地微信（4.0+）的聊天记录、联系人、群成员、朋友圈**映射成 REST 接口。只监听回环，外网不可达。解密由 WeFlow 内部完成，**密钥不是接口入参**。

本仓库是 WeFlow 数据源适配器项目，负责公开安全文档、自检、看门狗和 AI 消费契约；它不是原始微信数据仓库，也不是 PersonalOS / CareerCapital / SocialCapital / LifeCases 的长期事实库。WeFlow/WeLive 拥有源数据、解密与导出实现，WeFlowBridge 只拥有版本绑定的适配、交接及验证合同。经用户明确授权时，消费合同允许 PersonalOS 的私密晚绑定运行根保存按账号隔离、版本绑定、校验通过的不可变来源包；PersonalOS 拥有该私密包及其可替换派生表示，但这不把原始载荷带入本公开仓库，也不建立第二套可写 WeFlow 状态。

## 鉴权（必读）
除 `/health` 外所有接口都要 token，无 token → `401`。token 三种写法都行：
- 请求头 `Authorization: Bearer <token>`（推荐）
- query `?access_token=<token>`（**SSE 推送只能用这种**，浏览器 EventSource 不能设头）
- body 字段 `access_token`

**token 从本地 `.env` 读，禁止写进代码 / 仓库 / 日志。**

## 优先用这些（实测稳定）
| 目的 | 调用 |
|------|------|
| 服务在线？ | `GET /health`（无需 token） |
| 会话列表 | `GET /api/v1/sessions?keyword=&limit=` |
| AI 会话索引 | `GET /api/v1/sessions?format=chatlab`（ChatLab Pull 会话列表） |
| AI 增量消息 | `GET /api/v1/sessions/{id}/messages?since=&end=&limit=&offset=`（ChatLab Pull，含 `sync.watermark`） |
| 联系人 | `GET /api/v1/contacts?keyword=&limit=` |
| 群成员画像 | `GET /api/v1/group-members?talker=<群id>`（含 `isOwner`/`messageCount`） |
| 朋友圈时间线 / 统计 | `GET /api/v1/sns/timeline?limit=` · `GET /api/v1/sns/export/stats` |

## 谨慎用（实测不稳定）
- `GET|POST /api/v1/messages?talker=<id>` — 取消息。**最新消息**优先不带 `start/end`，直接 `limit=100`，返回数组按 `createTime` 降序理解，最新在索引 `0`；再用会话 `lastTimestamp` 与第一条消息 `createTime` 自检。需要复杂参数时可用 `POST` JSON body。保留 `replyToMessageId` / `quote` 供 AI 还原回复链；要媒体加 `&media=1`，但公开仓库只保存 `media_manifest`，不保存媒体。
- **历史区间/批量回溯**优先用 ChatLab Pull：`GET /api/v1/sessions/{id}/messages?since=<unix>&end=<unix>&limit=5000&offset=0`，保留 `sync.hasMore` / `sync.nextSince` / `sync.nextOffset` / `sync.watermark`。只有需要 keyword、legacy JSON 或媒体导出时才回退 `/api/v1/messages?start=&end=`。实时读库有竞态，返回 0 时先重试几次 / 换会话，不要直接结论为无消息。

## 写操作 / 流（知道即可，别误调）
- `POST /api/v1/sns/export`（导出）、`DELETE /api/v1/sns/post/{id}`（删朋友圈）、`POST /api/v1/sns/block-delete/{install,uninstall}`（防删钩子）。
- `GET /api/v1/push/messages?access_token=<token>` — SSE 实时推送（事件 `message.new`/`message.revoke`）。需在 WeFlow 设置开「主动推送」开关，否则 `403 {"error":"Message push is disabled"}`。

## 30 秒 quickstart（PowerShell）
```powershell
$cfg=@{}; Get-Content "E:\Projects\Tools\WeFlowBridge\.env" | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object { $k,$v=$_ -split '=',2; $cfg[$k.Trim()]=$v.Trim() }
$base=$cfg['WEFLOW_BASE_URL']; $H=@{ Authorization="Bearer $($cfg['WEFLOW_TOKEN'])" }
Invoke-RestMethod "$base/health"
Invoke-RestMethod "$base/api/v1/sessions?limit=5" -Headers $H
# 最新消息：不带 start/end
Invoke-RestMethod "$base/api/v1/messages?talker=<id>&limit=100" -Headers $H
# 历史/批量：优先 ChatLab Pull
Invoke-RestMethod "$base/api/v1/sessions/<id>/messages?since=1760000000&end=1760003600&limit=5000&offset=0" -Headers $H
```

## curl
```bash
curl -H "Authorization: Bearer $WEFLOW_TOKEN" "http://127.0.0.1:5031/api/v1/sessions?limit=5"
```

## 典型流程
`sessions` 定位会话 → 判断当前库 →（群聊先 `group-members` 拿成员画像）→ 最新消息用无日期 `messages?limit=100` 并做 `lastTimestamp` 自检 → 历史/批量读取用 ChatLab Pull → 按 [docs/ai_consumer_contract.md](docs/ai_consumer_contract.md) 输出 `request_method`、`endpoint_family`、`sync_watermark`、`media_manifest` 等消费字段；朋友圈走 `sns/timeline` + `sns/export/stats`。

默认不要输出或保存完整原文。公开提交前按 [docs/privacy_boundary.md](docs/privacy_boundary.md) 检查，禁止提交 `.env`、token、raw messages、screenshots、database、exports 或媒体。

## 自检
`powershell -ExecutionPolicy Bypass -File E:\Projects\Tools\WeFlowBridge\probe-weflow.ps1`

文档/边界契约测试：
`python -m unittest E:\Projects\Tools\WeFlowBridge\tests\test_project_contracts.py`

本地 CI / 公开边界扫描：
`powershell -ExecutionPolicy Bypass -File E:\Projects\Tools\WeFlowBridge\tools\test-ci-local.ps1`
