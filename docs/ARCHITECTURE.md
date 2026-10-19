# 鱼小二 · 架构梳理

> 梳理日期：2026-10-18 ｜ 版本 v0.3.1 ｜ 依据：源码实读 + 运行实例 `/api/status` + 数据库实况
>
> 规模：Python 12,193 行 / 前端 2,757 行 / 56 个模块 / 80 个 HTTP 路由 / 20 个单测（全绿）

---

## 1. 一句话定位

单店主、单机运行的**闲鱼托管客服 Agent**：一条原生协议链路（扫码登录 → Cookie/Token 保活 → WebSocket 收发 → mtop 写操作），两个 Agent（买家侧自动回复、卖家侧指令执行），所有"钱路动作"过确认门。

**不是**：多租户 SaaS、爬虫框架、客服中台。没有 mock 通道、没有演示数据，空库启动是预期行为。

---

## 2. 运行时形态

| 维度 | 事实 |
|---|---|
| 进程 | 单进程 uvicorn + FastAPI，`127.0.0.1:8787` |
| 并发模型 | 纯 asyncio；无 Celery / Redis / MQ |
| 存储 | 单文件 SQLite（WAL），一条 aiosqlite 连接，写操作走 `asyncio.Lock` |
| 调度 | 6 组 `asyncio.create_task` 常驻循环（见 §7），无独立调度器 |
| 前端 | 无构建单页：`index.html` + `app.js`（1,897 行）+ `styles.css`（860 行），hash 路由 9 个页面 |
| 外部依赖 | 闲鱼 passport / mtop / IM WS；可选 LLM（OpenAI 兼容）；可选高德；9 类通知渠道 |

启动顺序（`runtime.py`）：`DB 连接 → 迁移 → 事件总线 → 设置/队列/通道 → 风险/告警/通知 → LLM → 各业务服务 → 订阅 order.paid → 引导数据 → 后台循环`。所有服务是 `Runtime` 上的公开属性，彼此**靠构造函数手工注入**，没有 DI 容器。

---

## 3. 分层结构

```
api.py (1,240 行, 74 路由)      external_api.py (638 行, 6 路由)
        │                                │
        └────────── runtime.py (279 行, 唯一装配点) ──────────┐
                                                              │
  buyer/  (1,393 行)                    seller/  (7,879 行)   │
  ├ conversation/gateway.py  规则分类    ├ agent.py      指令路由 + 执行
  ├ conversation/ingest.py   合并窗口    ├ confirmations.py 确认门
  ├ conversation/agent.py    买家 Agent  ├ write_queue.py   串行写
  ├ conversation/bargain.py  议价引擎    ├ commerce/     订单/发货
  └ knowledge/service.py     FTS 检索    ├ operations/   值守/风控/评测/回放
                                        ├ notifications/ 告警/邮件
  core/ (1,342 行)                      └ platform/xianyu/ 原生协议
  config · db · state · events · llm · settings · util · seed
```

**分层意图**：`core` 只放共享底座（不反向依赖任何域，已核实无违规）；`buyer` 只做消息理解与回复；`seller` 承担账号、商品、订单、发货、通知、平台写操作。

**分层实况（与意图不符，见 §9）**：`buyer → seller` 有 4 处依赖（`AlertService`、`ConfirmationService`、`MessagingService`），`seller → buyer` 有 5 处（`ToolBox`、`KnowledgeService`、`BuyerAgent`）。两个域实际是**双向耦合**，只是目录分开。

---

## 4. 核心链路一：买家消息（读为主，写只发消息）

```
原生 WS /s/vulcan
  → ws.normalize_messages      解 base64 / MessagePack，一帧可含多条，过滤自己发的回显
  → NativeXianyuChannel._on_message
       商品：platform_item_id → 本地 item_id，缺失则建占位商品 xyitem_<id>
       去重：external_id = messageId，缺失则 sha1(chat_id+ts+text)
  → IngestService.submit_buyer_message
       ensure_conversation → add_inbound → 1.5s debounce（设置项 merge_window_seconds）
       处理期间新消息到达 → 处理完再起一轮
  → BuyerAgent.handle_pending（每会话一把 asyncio.Lock，串行）
       建 turns 记录 → classify() 规则分类 → 分支 → ToolBox 记 tool_calls
  → MessagingService.send_reply
       夜间模式(01:00-07:00) / 频控(2 条/分钟) → 命中则写 outbox 排期
       否则 → WriteQueue 串行 → XianyuIM.send_text → 落 messages
```

**兜底与自愈**：
- 推送包解析失败 → 立即补拉一次会话历史；另有 7 秒轮询会话列表兜底
- 重启后 `IngestService.recover_pending()` 重新排期 `processed=0` 的入站消息
- outbox 后台 0.8s tick，失败退避 30s×attempts，3 次后标 failed
- 异常兜底：回复"稍等，我让店主来看一下这条消息～"+ 转人工 + P1 告警

**买家 Agent 的分支矩阵**（`gateway.classify` 纯规则、可解释、无 LLM 依赖）：

| 优先级 | 分类 | 动作 | 处理 |
|---|---|---|---|
| 1 | `risk` 风险词（举报/骗子/起诉…） | silent | 不回复，P1 |
| 2 | `off_platform` 站外引流（微信/QQ/转账…） | silent | 不回复，P1 |
| 3 | `human` 要求人工 | agent | 转人工接管 |
| 4 | `after_sale` 售后/物流 | agent | 查订单 + 售后话术 |
| 5 | `bargain` 议价 | agent | 规则引擎算价，必要时确认门 |
| 6 | `order` 订单咨询 | agent | 查单 |
| 7 | `chitchat` 纯寒暄 | template | 固定话术直发，不过 Agent |
| 8 | `pre_sale` 商品咨询 | agent | 知识库检索 + 组装 |
| 9 | `unknown` | agent | **谨慎模式**（更保守的话术/转人工） |

LLM 只在 `unknown` 时做可选兜底分类与润色，规则模式下全链路可跑通。

**工具白名单**（步数上限 6，重复调用即熔断转人工）：`get_item_info` / `get_order_status` / `create_refund_request` / `escalate_human`。买家 Agent **没有**发布、改价、发货权限。

---

## 5. 核心链路二：店主指令（写为主，必过确认门）

```
控制台「让小二做点什么」/ 邮件 IMAP 正文 / 外部指令
  → SellerAgent.handle(text, images)
       ① 确认词优先：确认/取消 [+ cfm_id]
       ② 固定指令：帮助 / 待确认 / 日报 / 擦亮 / 发布设置
       ③ 正则路由：重新上架 / 改价 / 下架 / 上架 / 订单 / 发货 / 人工 / 恢复
       ④ 带图片 = 上架意图（不需要"上架"前缀）
       ⑤ 兜底：帮助
  → 生成 confirmations 记录（预览 + payload，30 分钟 TTL）
  → 店主确认（卡片按钮 / 说"确认" / 邮件回信 / 邮件链接二次确认页）
  → SellerAgent.resolve → _execute_<kind>
       状态机条件 UPDATE（pending_confirm → live）→ WriteQueue → mtop
```

**确认门覆盖的写动作**：`publish_listing` / `publish_batch` / `offline_item` / `relist_item` / `change_price` / `bargain_price`。取消有副作用回滚（商品退回 `draft`）；执行失败保留确认项可重试，同时 P1 告警；确认/驳回全部写 `audit_logs`。

**发布链路**：图片上传 → 地址解析（描述城市 → 默认地址 → 高德兜底）→ 分类推荐（mtop 接口，失败才需手填）→ `idleitem.publish`（个人 / 鱼小铺）→ 回写 `platform_item_id`。

---

## 6. 数据模型与状态机

**表分组（26 张）**：

| 组 | 表 |
|---|---|
| 账号 | `accounts` `account_events` |
| 商品/知识 | `items` `kb_sources` `kb_chunks` `kb_fts`(FTS5) |
| 交易 | `orders` `delivery_cards` `delivery_attempts` |
| 会话 | `conversations` `messages` `outbox` `turns` `tool_calls` |
| 治理 | `confirmations` `alerts` `audit_logs` `events` `idempotency` |
| 运维 | `patrol_jobs` `eval_cases` `eval_runs` `llm_calls` `settings` `notify_channels` `notification_logs` `external_api_logs` |

**状态机**（`core/state.py`，全部是"条件 UPDATE"，不用先查后写）：

```
item:  draft → pending_confirm → live → sold_out / offline
order: new → paid → shipped → delivered → done
       └→ refund_open → refund_resolved / cancelled
```

`rowcount == 0` 即视为状态冲突：动作被拒绝、写 `audit_logs(result=conflict)`、发 P1 告警。这是防"退款后仍自动发货"的核心机制。

**事件总线**（`core/events.py`）：事件先落 `events` 表再同步投递处理器；失败标 `failed` + P1；启动时 `replay_pending()` 重放。单进程低吞吐下比引入 MQ 更可靠，代价是**处理器异常不自动重试**（只有启动时重放）。

---

## 7. 常驻后台任务

| 循环 | 周期 | 作用 |
|---|---|---|
| `outbox` | 0.8s | 投递频控/夜间排期的回复 |
| `patrol` | 5s tick | 到点执行 heartbeat / link_check / polish / daily_report |
| `session-keeper` | 30 min | Cookie 保活、Token 刷新（H5 1.5–2.5h、WS 10–14h 随机抖动） |
| `email-gateway` | 60s | IMAP 收未读，白名单发件人正文当指令 |
| `xianyu-native-connect` / `-reconnect` | 事件驱动 | WS 建连、掉线重连 |
| `xianyu-order-sync` | 60s | `merchant.sold.get` 拉订单，付款即触发自动发货 |
| `xianyu-ws` + `xianyu-heartbeat` + `xianyu-history` | 15s / 7s | 心跳、历史补拉 |

值守四任务：`heartbeat`(30min) / `link_check`(6h) / `polish`(每日 10:05) / `daily_report`(每日 21:00)，均可在控制台改时段与手动触发。

---

## 8. 护栏体系（这个项目的设计重心）

1. **单写队列** `WriteQueue`：所有平台写操作串行 + 最小间隔 2.0s + 0-1.5s 抖动，兼作风控纪律与并发控制
2. **风控熔断** `RiskGuard`：错误文本匹配风控信号（挤爆/滑块/验证码/429…）→ 熔断冷却（默认 30min），期间写操作 fail-fast
3. **频控与夜间**：2 条/分钟硬编码上限；01:00-07:00 不回复，排到 07:30
4. **确认门**：所有钱路动作先出预览，30 分钟 TTL，可编辑后再执行
5. **工具步数上限** + **重复调用熔断**：买家 6 步、卖家 8 步
6. **乐观锁状态机**：并发/乱序下宁可拒绝，不做半成品
7. **审计与留痕**：`audit_logs` + `tool_calls` + `turns` + `events` + `delivery_attempts`，可回放整轮

---

## 9. 结构性问题（按优先级）

| # | 问题 | 证据 | 影响 |
|---|---|---|---|
| 1 | **无任何鉴权** | `api.py` 无 middleware / Depends；80 个路由全裸 | 监听 127.0.0.1 时风险可控；一旦按 `YUXIAOER_PUBLIC_URL` 暴露到局域网/公网，任何人可发消息、改价、上架、看 Cookie |
| 2 | **两个巨型 Agent 文件** | `seller/agent.py` 1,190 行；`buyer/agent.py` 688 行 | 指令路由、业务执行、文案拼装、参数补全混在一个类；改一个意图要读整文件 |
| 3 | **域边界是目录级的** | `buyer` 4 处依赖 `seller`，`seller` 5 处依赖 `buyer` | README 声称的双域隔离不成立；`ToolBox` 定义在 buyer 却被 seller 复用 |
| 4 | **事件处理器无重试** | `events._dispatch` 失败仅标 failed + 告警 | `order.paid` 处理器异常 → 自动发货静默丢失，只能人工补发 |
| 5 | **前端单文件 1,897 行** | `static/app.js` 无模块化、无构建 | 9 个页面共享一个全局 `S` 状态；后续加页面成本递增 |
| 6 | **依赖声明不全** | `websockets` 未在 `pyproject.toml` / `requirements.txt` 中直接声明，靠 `uvicorn[standard]` 间接带入 | 换部署方式（如 `uvicorn` 非 standard）会运行时报错 |
| 7 | **示例配置含真实密钥** | `.env.example` 里 `AMAP_KEY=ef9c...` 是有效值 | `.gitignore` 只忽略 `.env`，示例文件会被提交 |
| 8 | **关键参数硬编码** | 频控 2/min、步数 6/8、合并窗口默认值在 `config.py`，不在 `EDITABLE_SETTINGS` | 调参要改代码重启 |
| 9 | **WAL 无显式 checkpoint** | 全库搜不到 `wal_checkpoint`；实测 db 356KB / wal 4.1MB | 当前水位在 SQLite 自动 checkpoint（1000 页）附近，尚未失控；长期高写入需关注 |
| 10 | **评测闭环空转** | `eval_cases` 表 0 条；删除演示数据时把用例也删了 | `POST /api/eval/run` 恒返回 0/0，评测能力等于不存在 |

---

## 10. 运行实例快照（2026-10-18 15:35）

```
version 0.3.1 · mode xianyu · channel 在线（WebSocket 已连接）
账号 1 个（已激活，已同步：在售 1 · 订单 0）· 最近入站 15:29
items 3（draft 2 / live 1）· orders 0 · delivery_cards 0
conversations 2 · messages 24 · turns 5 · tool_calls 6
alerts 2 · events 68 · confirmations 2 · kb 1 源 1 块
risk 未熔断 · queue 正常 · outbox 无积压 · LLM 规则模式
```

真实链路已验证到：扫码登录、WS 连接、真实买家消息入站（`native inbound`）、消息回复。**尚未验证**：真实订单同步（订单 0）、自动发货（无卡券）、发布/下架/改价/擦亮（需小号现场）。

---

## 11. 如果要继续演进，优先级建议

1. **加鉴权**（本机 token 或反代 Basic Auth）——这是唯一"一条命令就能被打穿"的风险
2. **补 3 条评测用例**（议价守住底价 / 站外引流静默 / 售后转人工），把 `eval_cases` 从空表填起来
3. **拆 seller/agent.py**：`intent_router.py`（正则路由）+ `listing.py`（发布参数补全）+ `commands.py`（改价/下架/发货）
4. **事件处理器加重试**：`events.attempts` 已有字段，补 3 次退避即可
5. **把 `ToolBox` 移到 `core/`**，切断 buyer↔seller 的第一条反向依赖
