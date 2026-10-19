# 原生闲鱼协议

> 本文记录鱼小二**自己实现**的原生通道：登录、mtop 调用、IM WebSocket、订单同步与商品写操作。
> 协议事实来自公开抓包与黑盒行为观察；代码为独立实现，不包含第三方源码。
> 非官方接口，平台可能随时变更；请用测试账号、控制频率。

## 1. 通道能力

| 能力 | 实现位置 | 状态 |
|---|---|---|
| 扫码登录 | `seller/platform/xianyu/qrlogin.py` | 真实二维码已实测 |
| Cookie 续期 | `seller/platform/xianyu/session.py` | 代码完成，需按账号自测 |
| IM Token | `seller/platform/xianyu/mtop.py` | 代码完成，需按账号自测 |
| WebSocket 收发 | `seller/platform/xianyu/ws.py` | 帧级测试通过，现场需自测 |
| 订单同步 | `seller/platform/xianyu/orders.py` | 已实现 |
| 发布 / 下架 / 改价 / 擦亮 | `seller/platform/xianyu/publish.py` + mtop | 已接入，需测试账号验证 |
| 自动发货 | `seller/commerce/delivery.py` | 已实现 |

## 2. 扫码登录

1. `GET https://passport.goofish.com/mini_login.htm`，从 `window.viewData.loginFormData` 取参数；
2. `GET /newlogin/qrcode/generate.do` → `content.data.codeContent`（二维码内容）；
3. `POST /newlogin/qrcode/query.do` 轮询，`qrCodeStatus`：

   | 状态 | 含义 |
   |---|---|
   | `NEW` | 等待扫码 |
   | `SCANED` | 已扫码，等待手机确认 |
   | `CONFIRMED` | 已确认，可从 Set-Cookie 取 `unb` |
   | `EXPIRED` | 二维码过期 |

4. `CONFIRMED` 后合并 Set-Cookie，得到登录态；`iframeRedirect` 表示人脸验证，不自动化。

## 3. Cookie 与 Token

**Token**

```http
POST https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/
```

- `data = {appKey: "444e9908a51d1cb236a27862abc769c9", deviceId}`；
- `sign = md5(_m_h5_tk前缀 & t & 34839810 & data)`；
- accessToken 在 `data.accessToken`。

**保活**

- `POST https://passport.goofish.com/newlogin/silentHasLogin.do`；
- `POST https://passport.goofish.com/ac/account/setLoginSettings.do`，`status=0`；
- 合并所有 Set-Cookie；`_m_h5_tk` 过期时用新 Cookie 重签一次。

## 4. mtop 调用

所有 mtop 请求共用一套签名与 Cookie：

```text
GET/POST https://h5api.m.goofish.com/h5/{api}/{version}/
query: jsv, appKey, t, sign, v, type, accountSite, dataType, timeout, api, sessionOption
sign: md5(token & t & appKey & data)
```

- `token` 取自 `_m_h5_tk` 的前缀；
- 返回 `ret` 数组：`SUCCESS::调用成功` 之外都按业务错误抛给上层；
- 写操作统一经过 `WriteQueue`，失败不伪装成功。

## 5. WebSocket

**连接**

- `wss://wss-goofish.dingtalk.com/`，握手头带 Cookie；
- `/reg`：`app-key=444e9908a51d1cb236a27862abc769c9`、token、ua、`dt=j`、wv、did、mid；
- `/r/SyncStatus/ackDiff` 同步；
- 心跳 `{"lwp":"/!"}`，15 秒。

**入站**

- `body.syncPushPackage.data[].data` 是 base64；解出后按 JSON 解析，失败再试 MessagePack；
- 一帧可能包含多条消息；
- 业务字段：`1.2` chatId、`1.5` 时间、`1.10` 发送者 / reminder、`1.6.3.5` 内容；
- 过滤自己发送的回显；
- ACK：`{code: 200, headers: {mid, sid, ...}}`。

**发送**

```text
/r/MessageSend/sendByReceiverScope
  cid = chatId@goofish
  contentType = 101
  custom.data = base64(内层 JSON)
  actualReceivers = [buyer, self]
```

## 6. 订单

```http
POST mtop.taobao.idle.trade.merchant.sold.get v1.0
data: {pageNumber, rowsPerPage: 30, orderIds: "", queryCode: "ALL", orderSearchParam: "{}"}
```

- `data.module.items[]`：
  - `commonData`：`orderId` / `itemId` / `orderStatus` / `createTime` / `inRefund`
  - `buyerInfoVO`：`buyerId` / `userNick` / `name` / `phone` / `address`
  - `priceVO`：`totalPrice` / `buyNum`
- 状态映射：

  | 平台状态 | 本地状态 |
  |---|---|
  | 待付款 | `new` |
  | 待发货 | `paid` |
  | 已发货 | `shipped` |
  | 交易成功 | `done` |
  | 交易关闭 | `cancelled` |
  | 退款中 | `refund_open` |
  | 退款成功 | `refund_resolved` |

- 同步后，`paid` 且商品为 virtual 的订单进入自动发货。

## 7. 商品写操作

**图片**

```http
POST https://stream-upload.goofish.com/api/upload.api?floderId=0&appkey=fleamarket&_input_charset=utf-8
multipart: file
→ object.url / pix
```

**发布**

| 场景 | 接口 |
|---|---|
| 个人版 | `mtop.idle.pc.idleitem.publish` v1.0，data 即 payload |
| 鱼小铺 | `mtop.idle.pc.backend.idleitem.publish` v1.0，data `{inputJson: JSON.stringify(payload)}`，header `idle_site_biz_code=COMMONPRO` |

payload 关键字段：

- `itemTextDTO{title, desc, titleDescSeparate}`
- `imageInfoDOList`
- `itemPriceDTO{priceInCent, origPriceInCent}`
- `itemCatDTO`
- `itemLabelExtList`
- `itemAddrDTO{divisionId, gps, poiId, poiName}`
- `itemPostFeeDTO`
- `quantity`

**下架 / 改价 / 擦亮**

| 动作 | 接口 | 关键参数 |
|---|---|---|
| 下架 | `mtop.alibaba.idle.seller.pc.item.batch.offline` v1.0 | `{itemIds: "id1,id2"}` |
| 改价 / 库存 | `mtop.alibaba.idle.seller.pc.item.info.update` v1.0 | `{itemId, price: 元, quantity}` |
| 擦亮 | `mtop.taobao.idle.item.polish` v1.0 | `{itemId}` |

业务错误原样返回 UI，不伪造成功。

## 8. 明确不做

- 人脸验证、滑块、验证码自动化；
- 自动下单、自动关单、自动求小红花；
- 远程 Token 模式（不把完整 Cookie 交给第三方）；
- 密码明文入库、Cookie 明文日志、secret 走 URL。

## 9. 安全默认

- 只有原生闲鱼通道，没有 mock 回退；
- 没有真实 Cookie 的账号不会被拿去请求平台；
- Cookie / Token 只落本机 SQLite；控制台接口不返回原始 Cookie / Token；
- 风控熔断期间所有写操作 fail-fast；
- 外部接口默认秘钥只适合 localhost，公网必须替换并加反代鉴权。
