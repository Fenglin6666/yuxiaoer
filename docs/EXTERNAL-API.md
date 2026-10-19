# 外部接口

基址：`http://127.0.0.1:8787/api/v1`。只提供**真实数据**：账号、Cookie、订单、消息日志。不提供发布 / 改价 / 下架等写接口。

## 1. 鉴权

- 共享秘钥：`YUXIAOER_EXTERNAL_SECRET`（默认 `yx-local-secret`，只适合本机）。
- 位置：POST 放 JSON 的 `secret_key`；GET 放 query 的 `secret_key`。
- 校验：非空、长度 ≤ 128、常量时间比较；失败返回 `code=40001`。
- 鉴权失败不会返回 HTTP 401，仍然走 HTTP 200 响应包（见下）。

## 2. 响应格式

所有业务响应固定 HTTP 200：

```json
{
  "success": true,
  "code": 200,
  "message": "查询成功",
  "data": {}
}
```

失败：

```json
{
  "success": false,
  "code": 40001,
  "message": "秘钥不存在",
  "data": null
}
```

| code | 含义 |
|---|---|
| 200 | 成功 |
| 40001 | 秘钥缺失 / 长度超限 / 本机未配置 / 不匹配 |
| 40002 | 闲鱼账号 ID 为空 / 超长 / 不存在 |
| 40007 | Cookie 超长 / 格式错误 / 缺少 `unb` / 与账号不匹配 |
| 40008 | 请求参数缺失或不合法 |

## 3. 账号列表

`POST /api/v1/external/enabled-accounts`

```json
{"secret_key": "yx-local-secret"}
```

响应 `data`：

```json
{
  "accounts": [
    {
      "account_id": "2200xxxxxx",
      "remark": "测试号",
      "enabled": true,
      "status": "active",
      "status_name": "启用",
      "disable_reason": ""
    }
  ],
  "total": 1,
  "enabled_total": 1,
  "disabled_total": 0
}
```

`account_id` 取账号的 `platform_user_id`（`unb`），没有时回退本地 id。`enabled` 同时要求账号状态在线、会话已认证、无禁用原因。

## 4. 回传 Cookie

`POST /api/v1/external/account-cookie/sync`

```json
{
  "secret_key": "yx-local-secret",
  "account_id": "2200xxxxxx",
  "cookies": "unb=2200xxxxxx; _m_h5_tk=...; cookie2=..."
}
```

- `account_id` 可用 `platform_user_id` 或本地账号 id；
- Cookie 必须包含 `unb`，且与账号的 `platform_user_id` 一致；
- 成功后更新登录态、刷新各 Token 过期时间，写 `account_events`；
- 响应 `data` 为 `null`，`message` 为 `Cookie 已更新`。

## 5. 订单查询

`POST /api/v1/external/orders`

```json
{
  "secret_key": "yx-local-secret",
  "item_ids": ["<平台商品ID>"],
  "order_no": "平台订单号",
  "page": 1,
  "page_size": 20
}
```

`GET /api/v1/external/orders?secret_key=...&item_id=<ID>&page=1&page_size=20`

- `item_id` 可重复；GET 同时兼容 `item_ids`；
- `order_no` 同时匹配平台订单号与本地订单 id；
- `page_size` 1–100，默认 20。

响应 `data`：

```json
{
  "list": [],
  "orders": [],
  "total": 0,
  "page": 1,
  "page_size": 20,
  "total_pages": 0
}
```

单条订单字段（节选）：

| 字段 | 说明 |
|---|---|
| `id` / `order_no` / `order_id` | 本地 id / 平台订单号 |
| `item_id` / `item_title` | 平台商品 id / 标题 |
| `status` | `pending_payment` `pending_ship` `shipped` `completed` `refunding` `refunded` `cancelled` |
| `buyer_id` / `buyer_nick` / `chat_id` | 买家标识与会话 |
| `quantity` / `amount` / `currency` | 数量 / 金额（字符串，CNY） |
| `account_id` / `account_name` | 所属账号 |
| `delivery_method` / `delivery_content` / `delivery_send_status` | 发货方式 / 卡券内容 / 发送状态 |
| `receiver_address` | 收货地址（PII） |
| `placed_at` / `synced_at` | 下单 / 同步时间 |

## 6. 消息日志

`POST /api/v1/external/message-logs`

```json
{
  "secret_key": "yx-local-secret",
  "item_id": "<平台商品ID或本地商品ID>",
  "message_type": "auto_reply",
  "page": 1,
  "page_size": 20
}
```

`GET /api/v1/external/message-logs?secret_key=...&item_id=<ID>&message_type=auto_reply`

- `message_type`：`auto_reply`（自动回复）或 `auto_delivery`（卡券发货）；
- 返回结构同订单：`list` / `logs` / `total` / `page` / `page_size` / `total_pages`。

单条日志字段（节选）：

| 字段 | 说明 |
|---|---|
| `id` / `order_no` | 日志 id / 关联订单 |
| `source_message` / `source_message_time` | 触发回复的买家消息 |
| `reply_text` / `reply_image_url` | 回复内容 |
| `send_status` / `process_status` / `error_message` | 发送与处理结果 |
| `matched_keyword` / `matched_rule_type` | 命中的规则 |
| `ai_model_name` / `ai_provider_name` | LLM 信息（规则模式为空） |
| `account_id` / `chat_id` / `item_id` / `item_title` | 归属 |
| `created_at` / `updated_at` | 时间 |

`auto_delivery` 来自 `delivery_attempts`：`process_status` 为 `success`（已发送）或 `failed`；`reply_text` 为卡券内容摘要，`error_message` 为失败原因。

## 7. curl 示例

```bash
BASE=http://127.0.0.1:8787/api/v1
KEY=yx-local-secret

curl -s -X POST $BASE/external/enabled-accounts \
  -H 'Content-Type: application/json' \
  -d "{\"secret_key\":\"$KEY\"}"

curl -s "$BASE/external/orders?secret_key=$KEY&page=1&page_size=20"

curl -s -X POST $BASE/external/message-logs \
  -H 'Content-Type: application/json' \
  -d "{\"secret_key\":\"$KEY\",\"item_id\":\"<平台商品ID>\",\"message_type\":\"auto_reply\"}"
```

## 8. 说明

- 订单 / 消息来自真实同步；没有数据时返回空列表，不生成假数据。
- `auto_reply` 只包含状态为 `sent` / `delivered` 的自动回复，排除系统消息与虚拟发货消息。
- 所有调用写 `external_api_logs`（端点、客户端 IP、掩码秘钥、账号、结果），便于审计。
- 订单含收货 PII，不要转发第三方。
- 公网部署时：替换默认秘钥、加反代鉴权 / HTTPS，并设置控制台 Basic Auth。
