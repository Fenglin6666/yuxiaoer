# 鱼小二 · 原生闲鱼托管客服（真实通道版）

> 单店主、单机运行。只保留真实链路：扫码登录、Cookie/IM Token 保活、WebSocket 收发、订单同步、卡券自动发货、外部真实数据接口。
>
> 不包含 mock 通道、体验买家、模拟扫码/过期/风控/掉线/死链、演示种子数据。
> 参考纪律：只读研究上游行为，不复制代码；审计见 [AUDIT-UPSTREAM-xianyu-auto-reply.md](docs/AUDIT-UPSTREAM-xianyu-auto-reply.md)。

## 1. 当前保留的能力

| 能力 | 实现 | 状态 |
|---|---|---|
| 扫码登录 | `seller/platform/xianyu/qrlogin.py`：passport `mini_login → generate.do → query.do` | 真实二维码已实测生成 |
| Cookie 保活 | `seller/platform/xianyu/session.py`：`silentHasLogin.do` + `setLoginSettings.do` | 代码完成，待小号联调 |
| IM Token | `seller/platform/xianyu/mtop.py`：`mtop.taobao.idlemessage.pc.login.token` | 代码完成，待小号联调 |
| WebSocket 收发 | `seller/platform/xianyu/ws.py`：`/reg`、心跳、ACK、base64/MessagePack、发送文本 | 帧级测试通过，待小号联调 |
| 订单同步 | `seller/platform/xianyu/orders.py`：`mtop.taobao.idle.trade.merchant.sold.get` | 已实现 |
| 发布上架 | `seller/platform/xianyu/publish.py`：图片上传 + 地址解析 + `idleitem.publish`（个人/鱼小铺） | 已接入，待小号验证 |
| 下架 | `mtop.alibaba.idle.seller.pc.item.batch.offline` | 已接入，待小号验证 |
| 改价 | `mtop.alibaba.idle.seller.pc.item.info.update` | 已接入，待小号验证 |
| 擦亮 | `mtop.taobao.idle.item.polish` | 已接入，待小号验证 |
| 自动发货/卡券 | 复用 `seller/commerce/delivery.py`，真实订单 paid 后进入状态机 | 已实现 |
| 人工接管 | 店主 `人工/恢复`；客服工作台接管 | 已实现 |
| 小二 Agent 对话 | 「让小二做点什么」：上架/改价/下架/发货/日报/擦亮，写操作先确认 | 已实现 |
| 风控熔断 | 单写队列 + 真实错误信号熔断 | 已实现 |
| 通知 | 站内日志 + 企微/Bark/Server酱/ntfy/Telegram/PushPlus/Gotify/邮箱/Webhook | 已实现 |
| 邮箱指令 | SMTP 发告警/回复 + IMAP 收件执行上架/改价/下架等 | 已实现 |
| 外部接口 | 账号、Cookie、订单、消息日志（真实数据子集） | 已实现 |

**已删除**：MockChannel、`/api/sim/*`、体验买家页、模拟扫码/确认登录、模拟过期、模拟风控、模拟掉线、模拟死链、演示重置、演示账号/商品/订单/会话种子、分类/媒体/发布/能力检测等依赖模拟的 external 接口。

## 2. 启动

```powershell
cd D:\yuxiaoer
.\run.ps1
```

默认就是原生模式，首次启动是**空库**：

- 没有账号 → 去「账号与风控」添加账号 → 扫码；
- 没有商品 → 「商品与知识」新增草稿，或真实订单/消息同步后自动创建占位；
- 没有订单/会话 → 等真实 WS/订单同步。

| 地址 | 用途 |
|---|---|
| <http://127.0.0.1:8787> | 控制台 |
| `/docs` | Swagger（外部接口） |
| `/api/health` | 健康检查 |

## 3. 真实联调顺序

1. **账号与风控** → 添加账号 → 扫码登录；
2. 手机确认后自动取 IM Token，账号卡显示 WS 状态；
3. **商品与知识** → 新增商品草稿，或等真实订单/消息同步出占位；
4. 商品详情 →「发布上架」：图片 + 描述自动补参数；发布成功写平台 ID；
5. 实物保持 physical；虚拟商品点「设为虚拟自动发货」并补卡券；
6. 在售商品可「下架」「改价」；也可以在「让小二做点什么」里直接对话；擦亮走每日任务/对话；
7. 买家付款后订单同步 → `paid` → 自动占用卡券并发送 → 本地订单变 `shipped`；
8. 订单履约 → 详情可补发卡券、处理退款、完成、评价；
9. 外部系统调用 `/api/v1/external/*` 查询账号/订单/消息。

**自动发货前提**：本地商品绑定平台商品 ID（发布成功会自动写；手工商品需绑定）。

### 3.1 登录后同步账号现状

扫码登录成功后会自动在后台同步：

- 当前账号的**在售商品列表**（鱼小铺卖家接口，失败回落个人版在售列表）；
- 订单（`merchant.sold.get`）；
- 账号标识 `unb`、昵称（从 Cookie 同步）；
- 本地统计：在售数、订单状态分布、会话数。

账号卡会显示「已同步：在售 N · 订单 M」；也可以点 **同步账号** 手动重跑。

商品同步时：

- 平台已有的商品会更新标题、售价、库存、状态；
- 本地已配置的虚拟发货/卡券/描述不会被覆盖；
- 新建商品默认实物，需手工设为虚拟并补卡券。

API：`POST /api/accounts/{account_id}/sync`。

### 3.2 邮箱收发指令

通知渠道新增 **邮箱（SMTP/IMAP）**：

- SMTP：发退款/风险告警、回复 Agent 的处理结果；
- IMAP：轮询未读邮件，把正文当店主指令交给小二；
- 只处理「允许发件人」白名单里的邮件；
- 邮件回复会附带可点击的「确认/取消」链接，也会给出 `确认 <确认项ID>` / `取消 <确认项ID>` 回信格式；
- 邮件客户端预加载链接不会直接执行：链接先打开二次确认页，点按钮才走 POST 执行；
- 邮件里的图片附件会保存为待发布图片，正文按描述自动补参数；
- 邮件回复也是 Agent 的结果，可直接回 `确认` 执行待确认动作。

配置字段：SMTP host/port/账号/授权码、发件地址、收件地址、IMAP host/port/账号/授权码、文件夹、允许发件人。

邮件里的确认链接默认指向 `http://127.0.0.1:8787`；在手机/其他设备点击时，设置 `YUXIAOER_PUBLIC_URL` 为局域网或公网地址（并让服务可访问）。也可以不点链接，直接回信 `确认 <确认项ID>`。

配置保存在 `data/yuxiaoer.db` 的 `notify_channels` 表，服务重启会自动读取；删除数据库才会丢失。

手动检查：通知渠道页 **检查邮箱**，或 `POST /api/notify/email/poll`。后台每 60 秒轮询一次。

### 3.3 让小二做点什么

打开「让小二做点什么」，把**图片 + 一段描述**发给小二即可：

```text
9.9 元虚拟资料，小学奥数全套，拍下自动发
```

Agent 会自动补：

- 标题、商品描述（补发货政策）；
- 价格（描述里有价格就用，没有用默认建议价，确认卡可见）；
- 虚拟/实物、发货方式、成色、分类；
- 分类优先调用平台分类推荐接口；
- 所在地优先从描述里的城市提取，否则用默认地址/上次配置。

生成「发布预览」确认卡，卡上可以直接点 **编辑** 改标题、价格、底价、图片、分类、所在地、发货方式，确认后才真实上传图片并发布。也可以继续用：

```text
发布设置 图片=… 分类ID=… 分类名=… 地址=…   # 可选，覆盖自动参数
上架：标题 9.9 描述
改价 商品名 到 8.8
下架 商品名
重新上架 商品名   # 按保存的图片/分类/地址重新发布新商品，旧下架商品仍在后台
擦亮 / 订单？ / 日报
```

- 分类推荐失败时才需要手动发「发布设置 分类ID=… 分类名=…」；
- 缺图片/描述会直接提示；
- 发布失败原样报错，确认项保留，可修好后重试或取消。

## 4. 目录结构（按领域）

```text
src/yuxiaoer/
  core/                      共享底座
    config.py  db.py  util.py  events.py  state.py  llm.py
    settings_service.py  seed.py
  buyer/                     买家域
    conversation/
      gateway.py             入口分类
      bargain.py             议价规则
      agent.py               买家 Agent
      ingest.py              消息合并/入队
    knowledge/
      service.py             商品/FAQ 检索、同步、墓碑
  seller/                    卖家域
    agent.py                 店主对话 Agent
    confirmations.py         写操作确认门
    write_queue.py           串行写队列
    account/accounts.py      登录/保活/多账号
    commerce/
      orders.py              订单、履约、退款
      delivery.py            卡券自动发货
    conversation/messaging.py 会话/消息/接管
    operations/
      patrol.py  metrics.py  replay.py  risk.py  eval.py
    platform/
      channels.py            通道抽象
      xianyu/                原生扫码、mtop、WS、订单同步、发布
    notifications/
      alerts.py  notifications.py
      email_actions.py  email_gateway.py
    integrations/external_api.py
  api.py                     控制台 API 路由
  runtime.py                 服务装配/生命周期
  main.py                    FastAPI 入口
  static/                    单页控制台
```

买方域只处理消息理解、议价、知识检索与买家回复；卖家域处理账号、商品、订单、发货、通知、平台写操作。`core/` 只放两边共享的基础设施。

买家真实消息链路：

```text
原生 WebSocket /s/vulcan
  → ws.normalize_messages（base64/MessagePack、多消息、过滤自己发的回显）
  → 推送包解析失败时：立即补拉一次会话历史
  → 7 秒轮询会话列表/消息（推送不可靠时的兜底）
  → NativeXianyuChannel._on_message（买家、会话、商品、chat_id）
  → IngestService（合并窗口、去重、重启后恢复未处理消息）
  → BuyerAgent（规则/LLM 分类、知识检索、议价/售后）
  → MessagingService.send_reply
  → XianyuIM.send_text（sendByReceiverScope，真实买家会话）
```

`GET /api/status` 的 `channel.last_inbound_at` 可看最近一条真实入站消息时间；日志搜 `native inbound`。如果 WebSocket 在线但没有该字段，说明还没收到买家消息，不是 AI 没有处理。

## 5. 外部接口（真实数据）

共享秘钥 `YUXIAOER_EXTERNAL_SECRET`，默认 `yx-local-secret`（只适合本机）。业务错误固定 HTTP 200。

| 方法 | 路径 |
|---|---|
| POST | `/api/v1/external/enabled-accounts` |
| POST | `/api/v1/external/account-cookie/sync` |
| GET/POST | `/api/v1/external/orders` |
| GET/POST | `/api/v1/external/message-logs` |

详细 curl：[docs/EXTERNAL-API.md](docs/EXTERNAL-API.md)。

## 6. 配置

| 变量 | 默认 | 说明 |
|---|---|---|
| `YUXIAOER_EXTERNAL_SECRET` | `yx-local-secret` | 外部接口共享秘钥 |
| `XY_APP_KEY` | `34839810` | mtop appKey |
| `XY_WS_URL` | `wss://wss-goofish.dingtalk.com/` | IM WebSocket |
| `XY_ORDER_SYNC_SECONDS` | `60` | 订单同步周期 |
| `AMAP_KEY` | 空 | 可选；不配时用内置城市坐标兜底 |
| `MERGE_WINDOW_SECONDS` | `1.5` | 消息合并窗口 |
| `LLM_ENABLED` | `off` | 可选 LLM；关闭时规则模式 |
| 通知 env | 空 | 见 `.env.example` |

设置页可改：底价折扣、合并窗口、议价轮数、风控冷却、擦亮/日报时间、自动评价、人工输入延迟。

## 7. 测试

```powershell
$env:PYTHONPATH="D:\yuxiaoer\src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

当前保留纯规则/协议测试（20 个）；mock/E2E 演示测试已随模拟功能删除。
真实 WS/订单需要小号现场联调，不以测试代替。

## 8. 边界（诚实声明）

1. 原生**发布/下架/改价/擦亮**已接入 mtop：`idleitem.publish`、`item.batch.offline`、`item.info.update`、`item.polish`；逻辑完成，需小号现场验证。发布需要图片和描述；分类走平台推荐，地址有城市兜底；`AMAP_KEY` 可选。
2. 人脸验证/滑块/验证码：不自动化；扫码要求人脸时只提示，用户自行完成。
3. 企业微信只做出站 webhook，未做入站。
4. 无登录鉴权、多租户、向量检索、真实支付退款、自动关单/自动下单。
5. 原生 WebSocket 现场收发尚未用真实小号验证；逻辑/帧已实现，扫码生成已实测。
6. 外部接口不提供发布/分类；没有数据时返回空列表，不生成假数据。

**风险**：逆向协议可能违反平台用户协议，账号存在被处置风险。请使用小号、控制频率，优先评估官方通道。

---

实现细节：[PROTOCOL-XIANYU.md](docs/PROTOCOL-XIANYU.md) · [IMPLEMENTATION-R1.md](docs/IMPLEMENTATION-R1.md) · 运维：[RUNBOOK.md](RUNBOOK.md)。
