# 原生闲鱼协议：事实与实现边界（clean-room）

> 目的：记录本项目**自己实现**的原生通道依据，避免把 AGPL 上游代码带进产品。
> 事实来源：公开上游 `zhinianboke/xianyu-auto-reply` 的只读行为研究 + 公开抓包字段；实现为本项目独立代码。
> 研究日期：2026-10-17。

## 1. 已实现

| 能力 | 实现 | 状态 |
|---|---|---|
| 扫码登录 | `seller/platform/xianyu/qrlogin.py`：passport mini_login → generate.do → query.do 轮询 | 已验证可生成真实二维码、状态 waiting |
| Cookie 续期 | `seller/platform/xianyu/session.py`：silentHasLogin.do + setLoginSettings.do | 代码完成，待小号联调 |
| IM Token | `seller/platform/xianyu/mtop.py`：`mtop.taobao.idlemessage.pc.login.token` | 代码完成，待小号联调 |
| WebSocket 收/发 | `seller/platform/xianyu/ws.py`：`/reg`、心跳、ACK、base64/MessagePack、`sendByReceiverScope` | 代码 + 帧单测完成，待小号联调 |
| 订单同步 | `seller/platform/xianyu/orders.py`：`mtop.taobao.idle.trade.merchant.sold.get` | 代码 + 夹具测试完成 |
| 发布/下架/改价 | `seller/platform/xianyu/publish.py` + `mtop` seller 接口 | 已接入，待小号验证 |
| 自动发货 | 复用 `seller/commerce/delivery.py` / `seller/commerce/orders.py`，订单同步后进入现有履约状态机 | 测试完成 |
| 外部 API | `seller/integrations/external_api.py`：账号/Cookie/订单/消息日志 | 契约测试删除，按真实数据验证 |

## 2. 协议事实（实现所用）

### 扫码
- `GET https://passport.goofish.com/mini_login.htm`，从 `window.viewData.loginFormData` 取参数；
- `GET /newlogin/qrcode/generate.do` → `content.data.codeContent`；
- `POST /newlogin/qrcode/query.do` → `qrCodeStatus`：`NEW/SCANED/CONFIRMED/EXPIRED`；
- `CONFIRMED` 后从 Set-Cookie 取 `unb`；`iframeRedirect` 为人脸验证，不自动化。

### Token / Cookie
- `POST https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/`
  - data `{appKey:"444e9908a51d1cb236a27862abc769c9", deviceId}`
  - `sign=md5(_m_h5_tk前缀 & t & 34839810 & data)`
  - accessToken 在 `data.accessToken`；
- `POST https://passport.goofish.com/newlogin/silentHasLogin.do`；
- `POST https://passport.goofish.com/ac/account/setLoginSettings.do`，`status=0`；
- 合并所有 Set-Cookie；`_m_h5_tk` 过期时用新 Cookie 重签一次。

### WebSocket
- `wss://wss-goofish.dingtalk.com/`，握手头只带 Cookie；
- `/reg`：app-key `444e9908a51d1cb236a27862abc769c9`、token、ua、dt=j、wv、did、mid；
- `/r/SyncStatus/ackDiff` 同步；
- 心跳 `{"lwp":"/!"}` 15s；
- 入站 `body.syncPushPackage.data[].data` base64 → JSON；失败走 MessagePack；
- 业务字段：`1.2` chatId、`1.5` 时间、`1.10` 发送者/reminder、`1.6.3.5` 内容；
- ACK `{code:200, headers:{mid,sid,...}}`；
- 发送 `/r/MessageSend/sendByReceiverScope`，cid=`chatId@goofish`，contentType=101，custom.data=base64(内层 JSON)，actualReceivers=[buyer,self]。

### 订单
- `mtop.taobao.idle.trade.merchant.sold.get` v1.0，data：
  `{pageNumber, rowsPerPage:30, orderIds:"", queryCode:"ALL", orderSearchParam:"{}"}`；
- `data.module.items[]`：`commonData.orderId/itemId/orderStatus/createTime/inRefund`、
  `buyerInfoVO.buyerId/userNick/name/phone/address`、`priceVO.totalPrice/buyNum`；
- 状态映射：待付款→new、待发货→paid、已发货→shipped、交易成功→done、
  交易关闭→cancelled、退款中→refund_open、退款成功→refund_resolved；
- 订单同步后，paid 且 virtual 的商品进入现有自动发货。

### 发布 / 下架 / 改价 / 擦亮
- 图片先上传 `https://stream-upload.goofish.com/api/upload.api?floderId=0&appkey=fleamarket&_input_charset=utf-8`，multipart 字段 `file`，返回 `object.url/pix`；
- 发布个人版：`mtop.idle.pc.idleitem.publish` v1.0，data 直接是 payload；
- 发布鱼小铺：`mtop.idle.pc.backend.idleitem.publish` v1.0，data `{inputJson: JSON.stringify(payload)}`，header `idle_site_biz_code=COMMONPRO`；
- payload 关键字段：`itemTextDTO{title,desc,titleDescSeparate}`、`imageInfoDOList`、`itemPriceDTO{priceInCent,origPriceInCent}`、`itemCatDTO`、`itemLabelExtList`、`itemAddrDTO{divisionId,gps,poiId,poiName}`、`itemPostFeeDTO`、`quantity`；
- 下架：`mtop.alibaba.idle.seller.pc.item.batch.offline` v1.0，data `{itemIds:"id1,id2"}`；
- 改价/库存：`mtop.alibaba.idle.seller.pc.item.info.update` v1.0，data `{itemId,price:元,quantity}`；
- 擦亮：`mtop.taobao.idle.item.polish` v1.0，data `{itemId}`；
- 业务错误原样抛给 UI；不伪造成功。

## 3. 明确不做

- 人脸验证自动化、滑块/验证码破解；
- 自动下单（会生成真实未付款订单）、自动关单、自动求小红花；
- 远程 Token 模式（避免把完整 Cookie 交给第三方）；
- 密码明文入库、Cookie 明文日志、secret 走 URL。

## 4. 安全默认

- 只有 `xianyu` 原生模式；没有 mock 回退；
- 没有真实 Cookie 的账号不会被拿去请求平台；
- Cookie/Token 只落本机 SQLite；API 不返回原始 Cookie/Token；
- 风控熔断期间所有写动作 fail-fast；
- 外部接口默认 secret 只适合 localhost，公网必须替换并加反代鉴权。
