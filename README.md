# 鱼小二

> 个人使用的**多闲鱼账号托管客服 Agent**。一个 Web 管理多个真实闲鱼账号：扫码登录、Cookie / IM Token 保活、WebSocket 实时收发、订单同步、自动发货；买家侧自动回复，卖家侧用一句话下指令，所有平台写操作先过确认门。

- **真实通道**：没有 mock、演示账号或种子数据，首次启动就是空库。
- **一个入口**：`http://127.0.0.1:8787`，本机直接使用，无登录。
- **账号隔离**：一个真实闲鱼账号一个实例，独立 SQLite、Cookie、WebSocket、值守 Agent。
- **可审计**：确认项、工具调用、事件、发货尝试全部落库，可按会话回放。

---

## 1. 功能

| 能力 | 说明 |
|---|---|
| 扫码登录 | 闲鱼 passport 二维码，手机确认后获取登录态 |
| 会话保活 | Cookie 续期、IM Token 刷新、WS 断线重连 |
| 实时消息 | 原生 WebSocket，base64 / MessagePack 解帧，支持多消息与历史补拉 |
| 订单同步 | 定时拉取卖家订单，付款后触发履约 |
| 商品操作 | 发布、下架、改价、擦亮，走原生 mtop 接口 |
| 自动发货 | 虚拟商品绑定卡券库存，订单 `paid` 后自动占用并发送 |
| 买家 Agent | 规则分类 → 小模型 → 可选 LLM；商品问答、议价、售后、转人工 |
| 人工接管 | 工作台接管 / 恢复，接管期间 Agent 暂停自动回复 |
| 店主小二 | 自然语言下指令，先生成预览卡，确认后执行 |
| 多账号 | 一个闲鱼账号一个实例；工作台顶部切换账号，数据互不串 |
| 风控护栏 | 单写队列、频控、夜间延迟、错误熔断、工具步数上限 |
| 通知 | 企业微信 / Bark / Server酱 / ntfy / Telegram / PushPlus / Gotify / 邮件 / Webhook |
| 外部接口 | 账号、Cookie、订单、消息日志四组真实数据接口 |

---

## 2. 快速开始

要求：**Python 3.12+**、[uv](https://github.com/astral-sh/uv)。

```powershell
cd <项目目录>
.\run.ps1
```

首次运行会自动创建 `.venv` 并安装依赖。启动后打开：

```text
http://127.0.0.1:8787
```

### 接入第一个闲鱼账号

1. 点顶栏右侧的账号按钮；
2. 「添加并启动」创建一个本地账号实例；
3. 点该实例的「扫码」；
4. 用真实闲鱼 App 扫码，手机确认；
5. 登录成功后自动同步商品；
6. 在「客服工作台」或「让小二做点什么」页面顶部选择该账号。

> “添加账号”只创建本地实例，不会创建闲鱼账号；真实身份始终来自闲鱼扫码。

---

## 3. 多账号结构

```text
浏览器
  └─ 8787 多账号 Web / Hub
       ├─ /api/hub/*       账号实例管理、扫码
       └─ /api/*           按 X-Account-Id 代理到当前账号
            ├─ 8801  账号 A → data/
            ├─ 8802  账号 B → data/shops/acct_2/
            └─ 8803  账号 C → data/shops/acct_3/
```

- 8787 是唯一 Web 入口，不跑买家 Agent；
- 账号实例内部端口从 8801 开始，不需要手工访问；
- 每个账号独立 SQLite、WebSocket、写队列、值守任务；
- 账号切换在业务页面顶部完成，不在侧边栏用下拉框；
- 侧边栏只显示当前账号状态。

数据目录：

```text
data/                         默认账号
data/shops/<account_id>/      新增账号
data/control/accounts.json    账号实例注册表
data/control/logs/            各实例日志
```

---

## 4. Web 页面

| 页面 | 作用 |
|---|---|
| 总览 | 运行状态、今日指标、告警、实时事件 |
| 客服工作台 | 账号标签、买家会话、上下文、人工接管、手动回复 |
| 让小二做点什么 | 账号标签、自然语言下指令、确认卡、业务侧栏 |
| 商品与知识 | 商品状态、知识库、发布 / 改价 / 下架 / 卡券 |
| 订单履约 | 待发货、退款、补发、完成、评价 |
| 观测评测 | 事件、工具调用、回放、黄金集评测 |
| 账号与风控 | 当前账号的登录、保活、同步、熔断 |
| 通知渠道 | 多渠道配置、测试、投递日志、邮箱轮询 |
| 设置 | 托管策略、LLM、诊断信息 |

前端是原生 ESM，无构建；视觉层在 `static/styles/pearl.css`，采用浅色珍珠玻璃、蓝色主操作、青柠状态色与等宽读数。

---

## 5. 两条核心链路

**买家消息**

```text
WS 帧
  → 解包 / 过滤回显
  → 每条消息独立入队（同会话 FIFO、去重、重启恢复）
  → BuyerAgent（规则 → 小模型 → 可选 LLM）
  → 商品检索 / 知识库 / 议价 / 售后 / 转人工
  → MessagingService（频控、夜间排期、outbox）
  → WriteQueue → 闲鱼 IM
```

**店主指令**

```text
控制台 / 邮件 / 外部指令
  → SellerAgent 路由
  → 确认卡（预览 + payload，30 分钟 TTL）
  → 店主确认
  → 状态机条件更新 → WriteQueue → mtop
```

---

## 6. 目录结构

```text
src/yuxiaoer/
  core/          配置、SQLite、事件总线、状态机、LLM、设置
  shared/        知识库、工具调用记录、跨域窄接口
  buyer/         消息理解、实体槽位、议价、买家 Agent、入口直投
  seller/
    agent.py     店主指令入口
    commands/    确认门、上架、下架改价发货、文本解析
    account/     登录、保活、多账号
    commerce/    订单履约、卡券发货
    operations/  值守、风控、评测、回放、指标
    platform/    通道抽象 + 原生闲鱼协议
    notifications/ 告警、渠道发送器、邮件网关
    integrations/ 外部接口
  api/           账号实例 API（system / conversations / catalog / orders /
                 accounts / notify / ops / settings / seller_chat）
  control/       8787 hub：注册表、进程守护、API 代理、排期
  static/        无构建 Web（app.js / core.js / hub.js / pages / pearl.css）
  runtime.py     单账号实例装配与生命周期
  main.py        单账号实例 FastAPI（由 hub 内部启动）
tests/           70 个单元测试
docs/            架构、多账号、协议、外部接口
RUNBOOK.md       运维手册
```

---

## 7. 配置

复制 `.env.example` 为 `.env` 后按需修改。常用项：

| 变量 | 默认 | 说明 |
|---|---|---|
| `YUXIAOER_CONTROL_PORT` | `8787` | 多账号 Web 入口端口 |
| `YUXIAOER_CONTROL_AUTOSTART` | `1` | 启动时自动拉起已登记账号 |
| `YUXIAOER_CONTROL_DIR` | `data/control` | 注册表、日志目录 |
| `YUXIAOER_ACCOUNTS_DIR` | `data/shops` | 新增账号的数据根目录 |
| `YUXIAOER_PUBLIC_URL` | `http://127.0.0.1:8787` | 邮件确认链接的对外地址 |
| `YUXIAOER_EXTERNAL_SECRET` | `yx-local-secret` | 外部接口共享秘钥，公网必须替换 |
| `YUXIAOER_REPLY_RATE_LIMIT` | `12` | 每个会话每分钟最多自动回复条数 |
| `XY_APP_KEY` | `34839810` | mtop appKey |
| `XY_WS_URL` | `wss://wss-goofish.dingtalk.com/` | IM WebSocket |
| `XY_ORDER_SYNC_SECONDS` | `60` | 订单同步周期 |
| `AMAP_KEY` | 空 | 可选；不配时用内置城市坐标兜底 |
| `LLM_ENABLED` | `auto` | `off` 为纯规则模式；配置 Key 后可启用 |
| 通知 env | 空 | 企业微信 / Bark / Server酱 / ntfy / Telegram / PushPlus / Gotify / 邮件 |

---

## 8. 数据与备份

- SQLite 使用 WAL；
- 账号 Cookie / Token 只在本地数据库；
- 停服务后按目录复制即可备份：

```text
data/
data/shops/<account_id>/
data/control/accounts.json
```

数据库包含真实登录态，禁止提交仓库或发给第三方。

---

## 9. 测试

```powershell
$env:PYTHONPATH="<项目目录>\src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

当前 **70 个测试**，覆盖规则分类、归一化、实体抽取、轻量意图模型、商品索引、多账号数据目录、控制台注册表 / 排期 / 账号切换与 API 代理、议价、中文分词、mtop 签名、WS 解帧、订单字段、通知渠道、入口直投与历史补拉轮转。

真实扫码、WS 收发、发布 / 下架 / 改价 / 擦亮仍需用自己的测试账号现场验证。

---

## 10. 外部接口

`/api/v1/external/*` 提供账号、Cookie、订单、消息日志四组接口，共享秘钥鉴权，业务错误固定 HTTP 200。详见 [docs/EXTERNAL-API.md](docs/EXTERNAL-API.md)。

---

## 11. 边界与风险

1. **仅限本人闲鱼账号、单机使用**。没有多租户、本地用户体系、向量检索。
2. **不自动化**人脸验证、滑块、验证码；需要时由用户手机完成。
3. **不做**自动下单、自动关单、真实支付退款。
4. 8787 默认只监听 `127.0.0.1`，无登录；不要直接暴露到公网。
5. 多账号同时在线 = 多个独立实例同时运行，不是单进程多开。
6. 一个实例同一时间只连一个 active 闲鱼账号。
7. 外部接口返回订单可能含收货信息，不要转发第三方。

> **风险提示**：直连平台私有协议可能违反平台用户协议，账号存在被处置风险。请使用测试账号、控制频率，并优先评估官方通道。

---

## 12. 文档

- [架构](docs/ARCHITECTURE.md)
- [多账号](docs/MULTI-SHOP.md)
- [原生协议](docs/PROTOCOL-XIANYU.md)
- [外部接口](docs/EXTERNAL-API.md)
- [运维手册](RUNBOOK.md)
