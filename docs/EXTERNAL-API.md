# 外部接口（真实数据子集）

> 本项目只保留有真实数据来源的接口；模拟分类、媒体上传、发布、能力检测已删除。

## 1. 鉴权与响应

- 共享秘钥：`YUXIAOER_EXTERNAL_SECRET`，默认 `yx-local-secret`（只适合本机）。
- 位置：JSON body 或 GET query；没有 Header/JWT。
- 业务错误与参数错误固定 **HTTP 200**：

```json
{"success": false, "code": 40008, "message": "请求参数page不正确", "data": null}
```

## 2. 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/external/enabled-accounts` | 账号列表（含禁用） |
| POST | `/api/v1/external/account-cookie/sync` | 回传账号 Cookie（校验 `unb`） |
| GET/POST | `/api/v1/external/orders` | 订单查询（真实同步订单） |
| GET/POST | `/api/v1/external/message-logs` | 真实自动回复/自动发货日志 |

完整 Swagger：<http://127.0.0.1:8787/docs>。

## 3. 最小 curl

```bash
BASE=http://127.0.0.1:8787
KEY=yx-local-secret

curl -X POST $BASE/api/v1/external/enabled-accounts \
  -H 'Content-Type: application/json' -d '{"secret_key":"'$KEY'"}'

curl -X POST $BASE/api/v1/external/orders \
  -H 'Content-Type: application/json' -d '{"secret_key":"'$KEY'","page":1,"page_size":20}'

curl -X POST $BASE/api/v1/external/message-logs \
  -H 'Content-Type: application/json' \
  -d '{"secret_key":"'$KEY'","item_id":"<平台商品ID>","message_type":"auto_reply"}'
```

## 4. 说明

- 订单与消息来自真实原生同步；没有数据时返回空列表，不生成假数据。
- `auto_reply` 只返回成功自动回复；`auto_delivery` 来自卡券发货尝试。
- 发布/改价/下架/擦亮需要等原生发布协议联调，当前不提供外部接口，也不会假装成功。
- 账号 Cookie 只落本机 SQLite；接口会校验 `unb`，不写明文日志。
- 返回订单含收货 PII，不要转发第三方。
