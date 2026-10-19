# 鱼小二 · 运行手册（真实通道版）

> 版本 v0.3.1。只有原生闲鱼通道，没有 mock/演示数据。

## 1. 启动 / 停止

```powershell
cd D:\yuxiaoer
.\run.ps1
```

手动：

```powershell
$env:PYTHONPATH="D:\yuxiaoer\src"
.\.venv\Scripts\python.exe -m uvicorn yuxiaoer.main:app --host 127.0.0.1 --port 8787
```

停止：前台 `Ctrl+C`；后台：

```powershell
Get-Process python | Where-Object { $_.Path -like "*yuxiaoer*" } | Stop-Process
```

健康检查：

```powershell
Invoke-WebRequest http://127.0.0.1:8787/api/health
Invoke-WebRequest http://127.0.0.1:8787/api/status
```

## 2. 首次启动

首次是空库，没有账号/商品/订单/会话。这是预期行为。

1. 打开 <http://127.0.0.1:8787>；
2. 账号与风控 → 添加账号 → 扫码登录（真实 passport 二维码）；
3. 手机确认后自动取 IM Token，账号卡显示 WS 状态；登录成功后自动同步在售商品、订单、unb/昵称和统计，也可点「同步账号」重跑；
4. 商品与知识：真实订单/买家消息同步后自动出现商品占位；
5. 商品详情绑定平台商品 ID（闲鱼链接 `id=`）；
6. 虚拟商品设为虚拟自动发货并补卡券；
7. 订单同步后自动发货。

## 3. 数据与备份

| 数据 | 位置 |
|---|---|
| SQLite（账号 Cookie/Token、订单、消息、卡券、事件） | `data/yuxiaoer.db`（WAL） |
| 服务日志 | `data/server.out.log` / `data/server.err.log` |
| 知识库 | 同 SQLite FTS 表 |

**备份**：停服务后复制 `data/yuxiaoer.db`；或 `sqlite3 .backup`。
**清空**：停服务，删除 `data/yuxiaoer.db*`，重启；不会生成假数据。

> 数据库含真实 Cookie/Token，禁止提交仓库或发给第三方。

## 4. 常见问题

| 现象 | 处理 |
|---|---|
| 端口 8787 占用 | 找 PID 杀掉或改 `YUXIAOER_PORT` |
| 页面空白/报错 | 强刷 `Ctrl+F5`；看浏览器 Console 与 `data/server.err.log` |
| 账号列表空 | 首次启动正常，先添加账号并扫码 |
| 扫码失败 | 检查网络/代理；`/api/status` 看 `channel.detail`；二维码 300 秒过期重试 |
| 人脸验证 | 平台要求时只显示验证页，用户手机完成；不自动化 |
| WS 连接失败 | 看账号 `ws_state`、服务日志；Cookie/Token 是否有效；重新扫码/刷新 |
| 买家消息没回复 | 频控 2 条/分钟、夜间延迟、outbox；看客服工作台 |
| 订单不同步 | `GET /api/status` 的 `channel.order_sync`；Cookie/Token；`XY_ORDER_SYNC_SECONDS` |
| 订单不自动发货 | 商品是否绑定平台 ID、是否 virtual、卡券是否有库存 |
| 无卡券可发 | 商品详情补卡券；订单详情补发 |
| 风控熔断 | 冷却结束或账号与风控 → 解除熔断；期间写操作 fail-fast 是预期 |
| 通知失败 | 通知渠道测试；查投递日志 error；站内日志渠道始终可用 |
| 外部接口 40001 | `YUXIAOER_EXTERNAL_SECRET` 不一致 |
| 数据库损坏 | 停服务备份后删除 `data/yuxiaoer.db*`，重启为空库 |

## 5. 小二 Agent 对话

「让小二做点什么」支持：

```text
（发图片 + 一段描述）→ 自动补标题/价格/分类/所在地 → 发布预览
发布设置 图片=… 分类ID=… 分类名=… 地址=…   # 可选覆盖
上架：标题 价格 描述
改价 商品名 到 199
下架 商品名
重新上架 商品名
擦亮 / 订单？ / 日报 / 人工 买家 / 恢复 买家
```

上架、改价、下架先出确认卡；发布卡可点「编辑」改标题/价格/图片/分类/地址，确认后才调用原生 mtop。分类自动推荐失败时，才需要手动指定分类 ID。

## 6. 值守任务

| 任务 | 周期 | 手动入口 |
|---|---|---|
| heartbeat / 掉线重连 | 30 分钟 | 设置 / 总览 |
| link_check 链接巡检 | 6 小时 | 设置 |
| polish 每日擦亮 | 每天 10:05（可改） | 「让小二做点什么」里说「擦亮」 |
| daily_report 日报 | 每天 21:00（可改） | 「让小二做点什么」里说「日报」 |

`GET /api/patrol/jobs`；`POST /api/patrol/jobs/{name}/run`；`PATCH` 改时段。

## 7. 邮箱收发

通知渠道 → 邮箱（SMTP/IMAP）：

- SMTP：告警/回复；
- IMAP：每 60 秒收未读邮件，正文作为小二指令；
- 只处理允许发件人；
- 可直接回 `确认 <确认项ID>` / `取消 <确认项ID>` 执行待确认操作；
- 邮件回复会带「确认/取消」链接；链接先打开二次确认页，再点按钮执行；
- 手机点击链接需设置 `YUXIAOER_PUBLIC_URL`；
- 手工检查：`POST /api/notify/email/poll` 或页面「检查邮箱」。

## 8. 外部接口

`/api/v1/external/*` 只有真实数据接口：账号、Cookie、订单、消息日志。
Swagger `/docs`；共享秘钥 `YUXIAOER_EXTERNAL_SECRET`；详见 `docs/EXTERNAL-API.md`。

## 9. 日志与诊断

- 设置页「复制诊断」；
- `GET /api/status`（channel/risk/session/external）；
- `GET /api/events`、`GET /api/tools`；
- 回放：`GET /api/replay/sessions` + `/api/replay/{conversation_id}`；
- 失败事件 `events.status=failed`，同时产生 P1。

## 10. 已知限制

原生发布/下架/改价/擦亮已接 mtop，待小号现场验证。人脸/滑块不自动化；企业微信只出站；无登录鉴权/多租户/向量检索/真实支付退款。原生 WS 现场收发需小号联调。
