# 鱼小二 · 架构梳理

> 梳理日期：2026-10-18 ｜ 结构重整：2026-10-19（api 包 / seller mixin / shared 层）｜ 版本 v0.3.1
>
> 规模：Python 12,651 行 / 前端约 2,826 行 / 78 个模块 / 82 个 HTTP 操作 / 33 个单测（全绿）

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
| 前端 | 无构建 ESM 单页：`index.html` + `js/app.js`（入口）+ `js/core.js` + `js/pages/`（9 个页面）+ `styles.css`，hash 路由 9 个页面 |
| 外部依赖 | 闲鱼 passport / mtop / IM WS；可选 LLM（OpenAI 兼容）；可选高德；9 类通知渠道 |

启动顺序（`runtime.py`）：`DB 连接 → 迁移 → 事件总线 → 设置/队列/通道 → 风险/告警/通知 → LLM → 各业务服务 → 订阅 order.paid → 引导数据 → 后台循环`。所有服务是 `Runtime` 上的公开属性，彼此**靠构造函数手工注入**，没有 DI 容器。

---

## 3. 分层结构

```
api/ 包（9 个领域路由 + 2 个内部模块）      external_api.py (639 行, 6 路由)
  system · conversations · seller_chat
  catalog · orders · accounts
  notify · ops · settings
        │
        └────────── runtime.py (280 行, 唯一装配点) ──────────┐
                                                              │
  core/ (1,351 行)          shared/ (376 行)                  │
  config · db · state       knowledge · toolbox               │
  events · llm · settings                                     │
  util · seed                                                 │
                                                              │
  buyer/ (1,042 行)                    seller/ (8,037 行)     │
  ├ conversation/gateway.py  规则分类    ├ agent.py      入口/路由（181 行）
  ├ conversation/ingest.py   合并窗口    ├ commands/     confirm·listing·actions·parsing
  ├ conversation/agent.py    买家 Agent  ├ confirmations.py 确认门
  └ conversation/bargain.py  议价引擎    ├ commerce/     订单/发货
                                        ├ operations/   值守/风控/评测/回放
                                        ├ notifications/ 告警/邮件
                                        └ platform/xianyu/ 原生协议
```

**分层意图**：`core` 只放共享底座（不反向依赖任何域，已核实无违规）；`shared` 放跨域但不属于任何一方的组件（知识库、工具调用记录）；`buyer` 只做消息理解与回复；`seller` 承担账号、商品、订单、发货、通知、平台写操作。

**分层实况**：`buyer → seller` 仍有 4 处（`AlertService`、`ConfirmationService`、`MessagingService`），属于买家回复链路的必要依赖；`seller → buyer` 的运行时依赖为 0（`eval.py` 仅 `TYPE_CHECKING` 类型引用）。原先"目录级隔离"的一半问题已消除。

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
| 1 | ~~无任何鉴权~~ **已提供可选 Basic Auth** | `YUXIAOER_CONSOLE_USER/PASSWORD` 两项都设置后，除 `/api/health` 与外部接口外全部要求 Basic 凭据；默认关闭 | 默认仍靠 `127.0.0.1`；暴露到局域网/公网时务必设置 |
| 2 | ~~两个巨型 Agent 文件~~ **已处理** | 2026-10-19：`seller/agent.py` 1,191 → 181 行，拆成 `commands/` 4 个 mixin；`api.py` 1,241 行 → `api/` 9 个领域路由 | 剩余热点：`buyer/conversation/agent.py` 637 行 |
| 3 | ~~域边界是目录级的~~ **已部分处理** | `ToolBox`/`KnowledgeService` 迁到 `shared/`；`seller → buyer` 运行时依赖归零；`buyer → seller` 仍有 4 处（告警/确认/消息） | 剩余 4 条是买家回复链路的必要依赖，下一步可用协议接口反转 |
| 4 | **事件处理器无重试** | `events._dispatch` 失败仅标 failed + 告警 | `order.paid` 处理器异常 → 自动发货静默丢失，只能人工补发 |
| 5 | ~~前端单文件 1,897 行~~ **已处理** | 2026-10-19：拆成 `js/core.js`（265 行）+ `js/pages/*.js`（9 个页面）+ `js/app.js`（入口 51 行），原生 ESM、无构建 | 全局 `S` 仍是单例状态，但每个页面只依赖 core；仍需浏览器逐页回归 |
| 6 | **依赖声明不全** | `websockets` 未在 `pyproject.toml` / `requirements.txt` 中直接声明，靠 `uvicorn[standard]` 间接带入 | 换部署方式（如 `uvicorn` 非 standard）会运行时报错 |
| 7 | ~~示例配置含真实密钥~~ **已处理** | 2026-10-19：`.env.example` 的 `AMAP_KEY` 已清空 | 仓库已初始化 git 并推到私有远端 |
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

1. **前端 ESM 拆分已完成**：`js/app.js`（入口/路由）+ `js/core.js` + `js/pages/*.js`；下一步是浏览器逐页回归与状态按页收窄
2. **鉴权**：已提供可选 Basic Auth；若监听 0.0.0.0 或走反代，建议强制开启（或再加一层反代鉴权）
3. **事件处理器加重试**：`events.attempts` 已有字段，补 3 次退避即可
4. **补评测用例**（议价守住底价 / 站外引流静默 / 售后转人工），把 `eval_cases` 从空表填起来
5. **补测试**：当前 33 个单测覆盖 12.6k 行；优先给 `api/` 路由加 ASGI 冒烟、给 `commands/` 加参数补全测试

---

## 12. 可复用组件（2026-10-19 抽取）

| 组件 | 位置 | 解决什么 | 怎么扩 |
|---|---|---|---|
| 渠道发送器注册表 | `seller/notifications/channels.py` | 10 类通知渠道的重复 HTTP/重试样板 | 写一个 `send_xxx(cfg, msg)` 并注册到 `SENDERS` |
| API 实体/审计助手 | `api/_helpers.py` | 取实体 + 404 + 审计 SQL 的复制 | 新路由直接用 `item_or_404` / `order_or_404` / `audit` |
| 指令共享助手 | `seller/commands/_shared.py` | 下架/重上/改价复制三遍的流程 | 新写操作只准备 `preview` 与文案，调用 `propose()` |
| 跨域窄接口 | `shared/ports.py` | 买家域 import 卖家实现 | 新依赖先加 Protocol，再由 runtime 注入 |
| 工具调用记录 | `shared/toolbox.py` | 买卖两侧各写一份工具落库 | 共用 `ToolBox.call`，步数/重复检测一处维护 |
