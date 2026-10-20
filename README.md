# 鱼小二

> 单店主、单机运行的**闲鱼托管客服 Agent**：扫码登录 → Cookie / IM Token 保活 → WebSocket 实时收发 → 订单同步 → 卡券自动发货。买家侧自动回复，卖家侧用一句话下指令，所有写操作先过确认门。

- **单机单店主**：FastAPI + SQLite + asyncio，无 Redis / MQ / 多租户。
- **真实通道**：没有 mock 通道、演示账号或种子数据；首次启动就是空库。
- **可审计**：确认项、工具调用、事件、发货尝试全部落库，可按会话回放。

## 1. 功能

| 能力 | 说明 |
|---|---|
| 扫码登录 | 闲鱼 passport 二维码，手机确认后取登录态 |
| 会话保活 | Cookie 续期、IM Token 刷新、WS 重连 |
| 实时消息 | 原生 WebSocket，base64 / MessagePack 解帧，支持多消息与历史补拉 |
| 订单同步 | 定时拉取卖家订单，付款后触发履约 |
| 发布 / 下架 / 改价 / 擦亮 | 原生 mtop 接口；发布支持个人版与鱼小铺 |
| 自动发货 | 虚拟商品绑定卡券库存，订单 `paid` 后自动占用并发送 |
| 人工接管 | 店主在工作台接管 / 恢复，Agent 暂停自动回复 |
| 小二 Agent | 上架、改价、下架、发货、日报、擦亮；写操作出预览卡，确认后执行 |
| 风控护栏 | 单写队列、错误信号熔断、频控、夜间延迟、工具步数上限 |
| 通知 | 站内日志 + 企业微信 / Bark / Server酱 / ntfy / Telegram / PushPlus / Gotify / 邮箱 / 通用 Webhook |
| 邮箱指令 | SMTP 发告警与回复；IMAP 收店主指令，支持回信确认 |
| 外部接口 | 账号、Cookie、订单、消息日志四组真实数据接口 |
| 控制台鉴权 | 可选 Basic Auth，默认只监听 `127.0.0.1` |

## 2. 快速开始

要求：Python 3.12+、[uv](https://github.com/astral-sh/uv)（用于创建虚拟环境与装依赖）。

```powershell
cd <项目目录>
.\run.ps1
```

启动后：

| 地址 | 用途 |
|---|---|
| <http://127.0.0.1:8787> | 控制台 |
| <http://127.0.0.1:8787/docs> | Swagger（外部接口） |
| <http://127.0.0.1:8787/api/health> | 健康检查 |

首次启动是空库：

1. 「账号与风控」→ 添加账号 → 扫码登录；手机确认后自动取 IM Token；
2. 「商品与知识」新增草稿，或等真实订单 / 消息同步后自动生成占位商品；
3. 商品详情可「发布上架」，或在「让小二做点什么」发图片 + 描述；
4. 虚拟商品点「设为虚拟自动发货」并补卡券；
5. 买家付款后订单同步 → `paid` → 自动占用卡券并发送 → 本地订单变 `shipped`；
6. 外部系统调用 `/api/v1/external/*` 查询账号 / 订单 / 消息。

## 3. 控制台

| 页面 | 作用 |
|---|---|
| 总览 | 运行状态、今日指标、告警、实时事件 |
| 客服工作台 | 买家会话、上下文、人工接管、手动回复 |
| 让小二做点什么 | 用自然语言下指令，确认卡上可编辑后再执行 |
| 商品与知识 | 商品状态、知识库、发布 / 改价 / 下架 / 卡券 |
| 订单履约 | 待发货、退款、补发、完成、评价 |
| 观测评测 | 事件、工具调用、回放、黄金集评测 |
| 账号与风控 | 多账号登录、保活、同步、熔断 |
| 通知渠道 | 10 类渠道配置、测试、投递日志、邮箱轮询 |
| 设置 | 托管策略、LLM、诊断信息 |

## 4. 两条核心链路

**买家消息**

```text
WS /s/vulcan
  → normalize_messages（base64 / MessagePack，过滤自己发的回显）
  → NativeXianyuChannel（买家、会话、商品、chat_id）
  → IngestService（1.5s 合并、去重、重启恢复）
  → BuyerAgent（规则分类 → 知识检索 / 议价 / 售后）
  → MessagingService（频控、夜间排期、outbox）
  → WriteQueue → XianyuIM.send_text
```

**店主指令**

```text
控制台 / 邮件 / 外部指令
  → SellerAgent.handle（确认词 → 固定指令 → 正则路由）
  → confirmations（预览 + payload，30 分钟 TTL）
  → 店主确认（卡片 / 回信 / 邮件链接二次确认）
  → 状态机条件 UPDATE → WriteQueue → mtop
```

## 5. 目录结构

```text
src/yuxiaoer/
  core/          配置、SQLite、事件总线、状态机、LLM、设置
  shared/        知识库、工具调用记录、跨域窄接口
  buyer/         消息理解、议价、买家 Agent、消息合并
  seller/
    agent.py     入口路由 + 回复
    commands/    确认门 / 上架 / 下架改价发货 / 文本解析
    account/     登录、保活、多账号
    commerce/    订单履约、卡券发货
    operations/  值守、风控、评测、回放、指标
    platform/    通道抽象 + 原生闲鱼协议
    notifications/ 告警、渠道发送器、邮件网关
    integrations/  外部接口
  api/           控制台路由（system / conversations / catalog / orders /
                 accounts / notify / ops / settings / seller_chat）
  static/        无构建控制台（js/app.js + js/core.js + js/pages/）
  runtime.py     服务装配与生命周期
  main.py        FastAPI 入口
tests/           44 个单元测试
docs/            架构、协议、外部接口
RUNBOOK.md       运维手册
```

## 6. 配置

复制 `.env.example` 为 `.env` 后按需修改。常用项：

| 变量 | 默认 | 说明 |
|---|---|---|
| `YUXIAOER_PORT` | `8787` | 控制台端口 |
| `YUXIAOER_PUBLIC_URL` | `http://127.0.0.1:8787` | 邮件确认链接的对外地址 |
| `YUXIAOER_CONSOLE_USER` / `YUXIAOER_CONSOLE_PASSWORD` | 空 | 可选控制台 Basic Auth；两项都设置才启用 |
| `YUXIAOER_EXTERNAL_SECRET` | `yx-local-secret` | 外部接口共享秘钥，公网必须替换 |
| `XY_APP_KEY` | `34839810` | mtop appKey |
| `XY_WS_URL` | `wss://wss-goofish.dingtalk.com/` | IM WebSocket |
| `XY_ORDER_SYNC_SECONDS` | `60` | 订单同步周期 |
| `AMAP_KEY` | 空 | 可选；不配时用内置城市坐标兜底 |
| `MERGE_WINDOW_SECONDS` | `1.5` | 买家消息合并窗口 |
| `MERGE_MAX_SECONDS` | `6` | 连续消息不断重置合并窗口时的最大等待上限 |
| `LLM_ENABLED` | `off` | 可选 LLM；关闭时纯规则模式 |
| 通知 env | 空 | 见 `.env.example` |

## 7. 测试

```powershell
$env:PYTHONPATH="<项目目录>\src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

当前 44 个测试，覆盖规则分类、议价、中文分词、mtop 签名、WS 解帧、订单字段、控制台鉴权、通知渠道注册表、指令共享助手、合并窗口上限与历史补拉轮转。真实 WS / 订单 / 发布需要用自己的测试账号现场验证，单测不替代联调。

## 8. 外部接口

`/api/v1/external/*` 提供账号、Cookie、订单、消息日志四组接口，共享秘钥鉴权，业务错误固定 HTTP 200。详见 [docs/EXTERNAL-API.md](docs/EXTERNAL-API.md)。

## 9. 边界与风险

1. **仅限本人店铺、单机使用**。没有多租户、账号体系、向量检索。
2. **不自动化**人脸验证、滑块、验证码；需要时由用户手机完成。
3. **不做**自动下单、自动关单、真实支付退款。
4. 原生 WS 现场收发、发布 / 下架 / 改价 / 擦亮需要用自己的测试账号验证；扫码生成已实测。
5. 企业微信只做出站 webhook，未做入站。
6. 控制台默认只监听 `127.0.0.1`；暴露到局域网 / 公网前请设置 Basic Auth 或加反代鉴权。
7. 外部接口返回订单含收货信息，不要转发第三方。

> **风险提示**：直连平台私有协议可能违反平台用户协议，账号存在被处置风险。请使用测试账号、控制频率，并优先评估官方通道。

## 10. 文档

- [架构](docs/ARCHITECTURE.md)
- [原生协议](docs/PROTOCOL-XIANYU.md)
- [外部接口](docs/EXTERNAL-API.md)
- [运维手册](RUNBOOK.md)
