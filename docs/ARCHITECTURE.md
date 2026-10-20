# 架构

> 单进程、单店主、单机运行。本文描述当前代码的结构与约束；实现细节以源码为准。

## 1. 定位

鱼小二是一个**闲鱼托管客服 Agent**：

- 买家侧：读消息 → 分类 → 查知识 / 订单 → 回复或转人工；
- 卖家侧：店主用自然语言下指令 → 生成预览 → 确认后调用平台接口；
- 两条链路共用一套 SQLite 数据、事件总线、写队列与审计。

**非目标**：多租户 SaaS、客服中台、爬虫框架、分布式任务系统。

## 2. 运行时

| 维度 | 事实 |
|---|---|
| 进程 | 8787 hub + 每个闲鱼账号一个 8801+ uvicorn 实例 |
| 并发 | 纯 asyncio；没有 Celery / Redis / MQ |
| 存储 | 单文件 SQLite（WAL），一条 aiosqlite 连接；写操作由 `asyncio.Lock` 串行 |
| 调度 | 若干 `asyncio.create_task` 常驻循环，没有独立调度器 |
| 前端 | 无构建 ESM 单页：`index.html` + `js/app.js` + `js/core.js` + `js/pages/` |
| 外部依赖 | 闲鱼 passport / mtop / IM WS；可选 LLM、高德、10 类通知渠道 |

启动顺序（`runtime.py`）：

```text
DB 连接 → 迁移 → 事件总线 → 设置 / 写队列 / 通道
→ 风控 / 告警 / 通知 → LLM → 各业务服务
→ 订阅 order.paid → 引导数据 → 后台循环
```

所有服务挂在 `Runtime` 上，通过构造函数手工注入，没有 DI 容器。

## 3. 分层

```text
main.py
  └─ runtime.py（唯一装配点）
       ├─ api/          控制台路由（按领域拆 9 个模块）
├─ static/       现有 Web（账号切换器在侧边栏，账号实例内部端口 8801+）
├─ control/      8787 hub：注册表、进程守护、按账号代理 /api/*、排期
       ├─ seller/       卖家域：账号、商品、订单、发货、通知、平台协议
       ├─ buyer/        买家域：消息理解、议价、回复
       ├─ shared/       跨域组件：知识库、ToolBox、窄接口
       └─ core/         基础设施：配置、DB、事件、状态机、LLM、设置
```

依赖规则：

1. `core` 不依赖任何业务域；
2. `shared` 可以被买卖两侧引用，但不反向依赖业务域；
3. `buyer` 只通过 `shared/ports.py` 的 `AlertPort` / `MessagingPort` 使用卖家能力，不 import 卖家实现；
4. `seller` 对 `buyer` 只有 `TYPE_CHECKING` 类型引用；
5. 路由层只做参数校验、调用服务、序列化，不写业务 SQL（实体读取与审计走 `api/_helpers.py`）。

## 4. 模块

| 模块 | 职责 |
|---|---|
| `core/db.py` | SQLite 连接、建表 / 迁移、查询封装 |
| `core/events.py` | 事件先落库再投递，启动时重放未完成事件 |
| `core/state.py` | 商品 / 订单状态机，全部是条件 `UPDATE` |
| `core/llm.py` | OpenAI 兼容客户端，记录 `llm_calls`，失败降级 |
| `shared/knowledge.py` | 商品 / FAQ 知识库，FTS5 + 中文 bigram，下架即墓碑 |
| `shared/toolbox.py` | 工具调用契约、步数上限、重复调用检测、落库 |
| `shared/ports.py` | 买家域依赖的告警 / 消息窄接口 |
| `buyer/conversation/gateway.py` | 9 类规则分类，可解释、无 LLM 依赖 |
| `buyer/conversation/normalize.py` | NFKC / 匹配 / 站外拆字 / 价格归一化 |
| `buyer/conversation/slots.py` | 尺码/颜色/预算/订单号/出价抽取 |
| `buyer/conversation/context.py` | `TurnContext`：意图、实体、商品、工具统一传递 |
| `buyer/conversation/small_model.py` | 字符 n-gram 最近邻意图模型（规则 unknown 时兜底） |
| `buyer/conversation/bargain.py` | 议价：解析报价、守底价、反报价 |
| `buyer/conversation/agent.py` | 买家 Agent：分支处理、工具白名单、转人工 |
| `buyer/conversation/ingest.py` | 入口直投：每会话 FIFO、每条消息一个 turn、去重、重启恢复 |
| `seller/agent.py` | 店主指令入口：确认词、固定指令、正则路由、回复 |
| `seller/commands/` | `confirm` 确认门 / `listing` 上架 / `actions` 下架改价发货 / `parsing` 文本解析 |
| `seller/confirmations.py` | 确认项生命周期（30 分钟 TTL） |
| `seller/write_queue.py` | 平台写操作串行队列（最小间隔 + 抖动） |
| `seller/account/accounts.py` | 多账号、扫码登录、保活、同步 |
| `seller/commerce/orders.py` | 订单、履约、退款、评价 |
| `seller/commerce/delivery.py` | 卡券库存、占用、发送、补发 |
| `seller/operations/` | 值守、风控、指标、回放、评测 |
| `seller/platform/xianyu/` | 扫码、mtop、WS、订单、发布、账号同步 |
| `seller/notifications/` | 告警、渠道注册表、邮件网关 |
| `seller/integrations/external_api.py` | 外部数据接口 |
| `api/` | 控制台 74 个路由，统一挂 `/api` |

## 5. 买家消息链路

```text
WS /s/vulcan
  → ws.normalize_messages（base64 / MessagePack，一帧多条，过滤自己发的回显）
  → NativeXianyuChannel._on_message
       商品：platform_item_id → 本地 item_id，缺失则建占位商品
       去重：messageId，缺失则 sha1(chat_id + ts + text)
  → IngestService
       每会话 FIFO；submit 只入队，商品/会话/去重都在 worker 里
       一条消息一个 turn，不做 debounce、不合并
  → BuyerAgent
       每会话一把 asyncio.Lock 串行；建 turn → classify → 分支 → 工具
  → MessagingService
       夜间模式 / 频控 → 命中则写 outbox 排期
       否则 → WriteQueue → XianyuIM.send_text → 落 messages
```

兜底：

- 推送包解析失败 → 立即补拉一次会话历史；
- 7 秒轮询会话列表 / 消息；
- 重启后重排 `processed=0` 的入站消息；
- outbox 后台 tick，失败退避重试，3 次后标 failed；
- Agent 异常 → 回复“稍等，我让店主看一下” + 转人工 + P1 告警。

分类矩阵（优先级从高到低）：

| 优先级 | 分类 | 动作 |
|---|---|---|
| 1 | `risk` 风险词 | 不回复，P1 |
| 2 | `off_platform` 站外引流 | 不回复，P1 |
| 3 | `human` 要求人工 | 转人工 |
| 4 | `after_sale` 售后 / 物流 | 查订单 + 售后话术 |
| 5 | `bargain` 议价 | 规则引擎算价 |
| 6 | `order` 订单咨询 | 查单 |
| 7 | `chitchat` 寒暄 | 固定话术，不过 Agent |
| 8 | `pre_sale` 商品咨询 | 知识库检索 + 组装 |
| 9 | `unknown` | 谨慎模式 |

工具白名单：`get_item_info` / `kb_search` / `search_items` / `get_order_status` / `create_refund_request`，步数上限 6，重复调用熔断。买家 Agent 没有发布、改价、发货权限。

规则返回 `unknown` 时：轻量字符 n-gram 模型兜底；仍不确定且 LLM 可用时，才走 `_llm_classify`。

## 6. 店主指令链路

```text
控制台「让小二做点什么」/ 邮件正文 / 外部指令
  → SellerAgent.handle
       ① 确认词：确认 / 取消 [+ cfm_id]
       ② 固定指令：帮助 / 待确认 / 日报 / 擦亮 / 发布设置
       ③ 正则路由：重新上架 / 改价 / 下架 / 上架 / 订单 / 发货 / 人工 / 恢复
       ④ 带图片 = 上架意图
       ⑤ 兜底：帮助
  → confirmations 记录（预览 + payload，30 分钟）
  → 店主确认（卡片 / 回信 / 邮件二次确认）
  → 状态机条件 UPDATE（pending_confirm → live）
  → WriteQueue → mtop
```

确认门覆盖：`publish_listing` / `publish_batch` / `offline_item` / `relist_item` / `change_price` / `bargain_price`。取消会回滚商品状态；执行失败保留确认项可重试并 P1 告警；确认 / 驳回写 `audit_logs`。

## 7. 数据与状态

表分组：

| 组 | 表 |
|---|---|
| 账号 | `accounts` `account_events` |
| 商品 / 知识 | `items` `kb_sources` `kb_chunks` `kb_fts` |
| 交易 | `orders` `delivery_cards` `delivery_attempts` |
| 会话 | `conversations` `messages` `outbox` `turns` `tool_calls` |
| 治理 | `confirmations` `alerts` `audit_logs` `events` `idempotency` |
| 运维 | `patrol_jobs` `eval_cases` `eval_runs` `llm_calls` `settings` `notify_channels` `notification_logs` `external_api_logs` |

状态机（`core/state.py`，全部条件 `UPDATE`）：

```text
item:  draft → pending_confirm → live → sold_out / offline
order: new → paid → shipped → delivered → done
       └→ refund_open → refund_resolved / cancelled
```

`rowcount == 0` 视为状态冲突：拒绝动作、写审计、发 P1。这是防“退款后仍自动发货”的核心机制。

## 8. 护栏

1. **单写队列**：平台写操作串行；消息发送 0.3s + 0.15s 抖动，发布/改价等仍为 2s + 0–1.5s 抖动；
2. **风控熔断**：错误文本匹配风控信号 → 冷却（默认 30 分钟），期间写操作 fail-fast；
3. **频控与夜间**：默认 12 条 / 分钟（`YUXIAOER_REPLY_RATE_LIMIT`）；01:00–07:00 不回复，排到 07:30；
4. **确认门**：钱路动作先出预览，30 分钟 TTL，可编辑后执行；
5. **工具步数上限 + 重复调用熔断**：买家 6 步、卖家 8 步；
6. **乐观锁状态机**：并发 / 乱序下宁可拒绝；
7. **审计留痕**：`audit_logs` + `tool_calls` + `turns` + `events` + `delivery_attempts`。

## 9. 后台任务

| 循环 | 周期 | 作用 |
|---|---|---|
| outbox | 0.8s | 投递频控 / 夜间排期回复 |
| patrol | 5s tick | heartbeat / link_check / polish / daily_report |
| session-keeper | 30 min | Cookie 保活、Token 刷新 |
| email-gateway | 60s | IMAP 收未读，白名单发件人正文当指令 |
| WS connect / reconnect | 事件驱动 | 建连、掉线重连 |
| order-sync | 60s | 拉订单，付款触发自动发货 |
| heartbeat / history | 15s / 7s | 心跳、历史补拉 |

历史补拉按会话轮转，每个会话有独立游标；一轮没有覆盖全部会话时全局 cutoff 不前进，避免“只看了前 20 个会话”丢掉其余会话。单会话超过 50 条时记 `history_truncated` 告警。

## 10. 可复用组件

| 组件 | 位置 | 扩展方式 |
|---|---|---|
| 渠道发送器注册表 | `seller/notifications/channels.py` | 写 `send_xxx(cfg, msg)` + 注册 `SENDERS` |
| 实体 / 审计助手 | `api/_helpers.py` | 新路由用 `item_or_404` / `order_or_404` / `audit` |
| 指令共享助手 | `seller/commands/_shared.py` | 新写操作准备 `preview` + 文案，调 `propose()` |
| 跨域窄接口 | `shared/ports.py` | 先加 Protocol，再在 runtime 注入 |
| 工具调用记录 | `shared/toolbox.py` | 共用 `ToolBox.call`，步数 / 重复检测一处维护 |

## 11. 扩展点

**新增通知渠道**：在 `channels.py` 写发送函数 → 注册 `SENDERS` → 在 `KINDS` 加展示名。无需改 `NotificationService`。

**新增店主写操作**：在 `seller/commands/` 加方法 → 用 `propose()` 生成确认卡 → 在 `confirm.py` 的 `_execute` 加分支 → 在 `SellerAgent.handle` 加路由。

**新增控制台接口**：在 `api/` 对应领域模块加路由 → 复用 `_helpers` 取实体 / 审计 → 在 `api/__init__.py` 的模块列表已自动挂载。

**接入新平台**：实现 `seller/platform/channels.py` 的 `BaseChannel`，在 `build_channel` 返回新实现；业务层不感知平台。

## 12. 已知限制

1. 默认只监听 `127.0.0.1`；可选 Basic Auth，不是完整账号体系。
2. 单账号仍是单进程、单 SQLite；多账号通过“一账号一实例 + 控制台”扩展，不做共享进程多租户。
3. 买家 → 卖家仍有 4 个窄接口依赖（告警 / 确认 / 消息），已收口到 Protocol。
4. 真实 WS / 订单 / 发布仍需测试账号现场验证；单测覆盖的是规则与协议帧。
5. 事件处理器失败只标 failed + 告警，没有自动重试队列（启动时重放）。
6. 评测集为空时，`/api/eval/run` 返回 0/0。

## 13. 多账号控制台

```text
控制台 :8787（唯一入口，本机免登录）
  ├─ registry：data/control/accounts.json（账号实例：本地名/端口）
  ├─ supervisor：每个真实闲鱼账号一个 uvicorn 子进程（8801+）+ 10s 健康检查 + 异常重启
  ├─ scheduler：按账号计算抖动，PATCH 各账号 patrol 擦亮/日报时间
  ├─ proxy：把现有 static 前端的 /api/* 转发到当前选中账号；扫码走 hub 账号接口
  └─ aggregator：只读拉取各账号 /api/status、/api/alerts、/api/overview
```

现有 static 前端不合并数据库：控制台按账号实例代理现有 `/api/*`，页面、会话和消息仍归属对应账号。

- 账号实例 = 独立 `data/shops/<id>/yuxiaoer.db` + 独立端口 + 独立 active 闲鱼账号；
- 账号身份来自真实扫码登录，不存在“本地注册店铺”；
- 控制台只管理自己启动的进程；手工实例需先停，避免端口冲突；
- 没有本地用户/角色/多租户，控制台只监听 `127.0.0.1`；
- 控制台自身不是系统服务，机器重启后需重新拉起。




