# 运行手册

> 适用版本 v0.3.1。只有原生闲鱼通道，没有 mock 或演示数据。

## 1. 启动与停止

```powershell
cd <项目目录>
.\run.ps1
```

手动启动：

```powershell
$env:PYTHONPATH = "<项目目录>\src"
.\.venv\Scripts\python.exe -m uvicorn yuxiaoer.main:app --host 127.0.0.1 --port 8787
```

停止：前台 `Ctrl+C`。后台：

```powershell
Get-Process python | Where-Object { $_.Path -like "*yuxiaoer*" } | Stop-Process
```

健康检查：

```powershell
Invoke-WebRequest http://127.0.0.1:8787/api/health
Invoke-WebRequest http://127.0.0.1:8787/api/status
```

## 2. 首次启动

首次是空库：没有账号、商品、订单、会话，这是预期行为。

1. 打开 <http://127.0.0.1:8787>；
2. 「账号与风控」→ 添加账号 → 扫码登录；
3. 手机确认后自动取 IM Token，账号卡显示 WS 状态；登录成功后自动同步在售商品、订单、`unb` / 昵称与统计，也可点「同步账号」重跑；
4. 「商品与知识」新增草稿，或等真实订单 / 消息同步出占位商品；
5. 商品详情绑定平台商品 ID（闲鱼链接里的 `id=`）；
6. 虚拟商品点「设为虚拟自动发货」并补卡券；
7. 买家付款后订单同步 → `paid` → 自动发货。

## 3. 数据与备份

| 数据 | 位置 |
|---|---|
| SQLite（账号 Cookie / Token、订单、消息、卡券、事件） | `data/yuxiaoer.db`（WAL） |
| 服务日志 | `data/server.out.log` / `data/server.err.log` |
| 图片附件 | `data/media/` |
| 知识库 | 同 SQLite 的 FTS 表 |

**备份**：停服务后复制 `data/yuxiaoer.db`；运行中可用 `sqlite3 .backup`。

**清空**：停服务，删除 `data/yuxiaoer.db*`，重启；不会生成假数据。

> 数据库含真实 Cookie / Token，禁止提交仓库或发给第三方。

## 4. 控制台鉴权（可选）

默认只监听 `127.0.0.1`。需要局域网 / 公网访问时，在 `.env` 设置：

```dotenv
YUXIAOER_CONSOLE_USER=owner
YUXIAOER_CONSOLE_PASSWORD=change-me
```

两项都设置后，除 `/api/health` 与 `/api/v1/external/*` 外全部要求 Basic Auth，浏览器会自动弹登录框。公网仍建议再加 HTTPS 与反代鉴权。

## 5. 常见问题

| 现象 | 处理 |
|---|---|
| 端口 8787 占用 | 找 PID 杀掉，或改 `YUXIAOER_PORT` |
| 页面空白 / 报错 | `Ctrl+F5` 强刷；看浏览器 Console 与 `data/server.err.log` |
| 账号列表空 | 首次启动正常，先添加账号并扫码 |
| 扫码失败 | 检查网络 / 代理；`/api/status` 看 `channel.detail`；二维码约 3 分钟过期，重试 |
| 人脸验证 | 平台要求时只显示验证页，由用户手机完成，不自动化 |
| WS 连接失败 | 看账号 `ws_state` 与服务日志；Cookie / Token 是否有效；重新扫码或刷新 |
| 买家消息没回复 | 频控 12 条 / 分钟、夜间延迟、outbox；看客服工作台 |
| 订单不同步 | `GET /api/status` 的 `channel.order_sync`；Cookie / Token；`XY_ORDER_SYNC_SECONDS` |
| 订单不自动发货 | 商品是否绑定平台 ID、是否 virtual、卡券是否有库存 |
| 无卡券可发 | 商品详情补卡券；订单详情可补发 |
| 风控熔断 | 冷却结束或「账号与风控」解除；期间写操作 fail-fast 是预期 |
| 通知失败 | 「通知渠道」测试；查投递日志 `error`；站内日志渠道始终可用 |
| 外部接口 40001 | `YUXIAOER_EXTERNAL_SECRET` 不一致 |
| 数据库损坏 | 停服务备份后删除 `data/yuxiaoer.db*`，重启为空库 |

## 6. 小二指令

「让小二做点什么」支持：

```text
（图片 + 描述）→ 自动补标题 / 价格 / 分类 / 所在地 → 发布预览
发布设置 图片=… 分类ID=… 分类名=… 地址=…   # 可选覆盖
上架：标题 价格 描述
改价 商品名 到 199
下架 商品名
重新上架 商品名
擦亮 / 订单？ / 日报 / 人工 买家 / 恢复 买家
```

上架、改价、下架、重新上架都先出确认卡；发布卡可点「编辑」改标题 / 价格 / 图片 / 分类 / 地址，确认后才调用原生 mtop。分类推荐失败时才需要手动指定分类 ID。

## 7. 值守任务

| 任务 | 默认周期 | 手动入口 |
|---|---|---|
| heartbeat / 掉线重连 | 30 分钟 | 设置 / 总览 |
| link_check 链接巡检 | 6 小时 | 设置 |
| polish 每日擦亮 | 每天 10:05（可改） | 「让小二做点什么」说「擦亮」 |
| daily_report 日报 | 每天 21:00（可改） | 「让小二做点什么」说「日报」 |

接口：`GET /api/patrol/jobs`、`POST /api/patrol/jobs/{name}/run`、`PATCH /api/patrol/jobs/{name}`。

## 8. 邮箱收发

「通知渠道」→ 邮箱（SMTP / IMAP）：

- SMTP：发告警、回复 Agent 处理结果；
- IMAP：每 60 秒收未读邮件，正文作为小二指令；
- 只处理「允许发件人」白名单；
- 可直接回 `确认 <确认项ID>` / `取消 <确认项ID>`；
- 邮件回复带「确认 / 取消」链接，链接先打开二次确认页，再点按钮执行；
- 手机点链接需设置 `YUXIAOER_PUBLIC_URL` 为可访问地址；
- 手动检查：`POST /api/notify/email/poll` 或页面「检查邮箱」。

## 9. 外部接口

`/api/v1/external/*`：账号、Cookie、订单、消息日志。共享秘钥 `YUXIAOER_EXTERNAL_SECRET`，Swagger 在 `/docs`，字段说明见 `docs/EXTERNAL-API.md`。

## 10. 日志与诊断

- 设置页「复制诊断」；
- `GET /api/status`：channel / risk / session / queue / outbox；`channel.ws` 里有连接/重连、包/消息、raw 解析失败、`no_chat` / `no_buyer`、历史截断计数，`channel.inbound` 是入站空文本/空 buyer 计数；
- `GET /api/events`、`GET /api/tools`；
- 回放：`GET /api/replay/sessions` + `/api/replay/{conversation_id}`；
- 失败事件 `events.status=failed`，同时产生 P1 告警。

## 11. 测试与升级

```powershell
$env:PYTHONPATH = "<项目目录>\src"
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

当前 40 个测试全部通过。升级：拉取新代码 → 停服务 → `uv pip install -r requirements.txt` → 启动；数据库迁移在启动时自动执行。

## 12. 已知限制

原生发布 / 下架 / 改价 / 擦亮已接 mtop，需用自己的测试账号验证；人脸 / 滑块不自动化；企业微信只做出站；无多租户、向量检索、真实支付退款。控制台默认无鉴权（可选 Basic Auth），公网部署前必须自行加防护。
