# 多店架构

> 当前阶段：**一店一实例 + 独立数据目录**。控制面/集中调度放在下一阶段。

## 1. 形态

```text
店铺 A  →  python -m uvicorn ... --port 8787  → data/        （default 店）
店铺 B  →  python -m uvicorn ... --port 8788  → data/shops/shop-b/
店铺 C  →  python -m uvicorn ... --port 8789  → data/shops/shop-c/
```

每个实例：

- 独立 SQLite（账号、商品、订单、消息、确认项、审计）；
- 独立 active 账号与 WebSocket；
- 独立写队列、outbox、patrol、通知渠道；
- 独立端口与控制台。

一个店掉线/封号/升级，不影响其他店。

## 2. 启动

```powershell
# 默认店（兼容旧数据）
.\run.ps1

# 新店
.\run.ps1 -ShopId shop-b -Port 8788
.\run.ps1 -ShopId shop-c -Port 8789
```

等价环境变量：

```dotenv
YUXIAOER_SHOP_ID=shop-b
YUXIAOER_PORT=8788
```

数据目录：

```text
default       data/
shop-b        data/shops/shop-b/
```

店铺 ID 只允许字母、数字、下划线、短横线；非法字符会被替换，避免路径穿越。

## 3. 首次启动

每个店都是空库，需要独立：

1. 打开对应端口的控制台；
2. 添加该店账号并扫码；
3. 同步商品；
4. 配置通知、话术、知识库、值守任务。

账号、Cookie、Token 不跨店共享。

## 4. 备份

按店备份：

```text
data/yuxiaoer.db                    default
data/shops/shop-b/yuxiaoer.db       shop-b
```

停服务后复制对应目录即可；不要把所有店指向同一个 `YUXIAOER_DATA_DIR`。

## 5. 控制面

启动：

```powershell
.\run-control.ps1 -Port 8790
```

默认地址 `http://127.0.0.1:8790`，默认账号 `admin`。首次启动前设置密码：

```dotenv
YUXIAOER_CONTROL_PASSWORD=change-me
```

控制面提供：

- **店铺注册表**：`data/control/shops.json`（ID、名称、端口、负责人、擦亮/日报/同步时间、自动启动/重启）；
- **进程守护**：启动/停止/重启，每 10 秒健康检查，异常连续 3 次或进程退出时自动重启；
- **统一排期**：按 `shop_id` 计算确定性抖动，把擦亮/日报时间写回各店 patrol，避免同一时间集中请求平台；每日按抖动时间触发一次商品同步；
- **跨店汇总**：在线状态、未处理告警、当天指标（只读，不改店铺数据）；
- **按店权限**：`data/control/users.json` 保存 PBKDF2 密码哈希；admin 看全部，owner 只看分配店铺。

### 统一工作台

控制面页面顶部是“统一工作台”：

- 店铺下拉：全部店铺或指定店；
- 买家会话：聚合各店 `/api/conversations`，显示店铺、买家、商品、最后一条消息；
- 选中会话：查看消息、人工回复、接管/恢复 AI；
- 店主指令：选具体店铺后，把“把 xxx 下架 / 改价 199 / 发布 …”发给该店小二；
- 待确认项：发布/改价等确认卡可直接确认或取消。

控制面只做代理，不复制会话数据；所有读写仍落在对应店铺的 SQLite。

控制台账号可用管理员 API 创建：

```powershell
# 使用 admin 登录后
POST /api/control/users
{"username":"alice","password":"...","role":"owner","shops":["shop-b"]}
```

### 控制面边界

- 控制面只管理**由它启动**的店铺进程；手工启动的实例需要先停掉，避免端口冲突；
- 控制面自身不是 Windows 服务，机器重启后需要重新启动控制面，或把它注册为服务；
- 店铺实例固定监听 `127.0.0.1`，控制面也默认只监听本机；远程访问请加反代/VPN，不要直接暴露端口。

## 6. 注意事项

- 每个店必须使用不同端口；
- 不同店不要共用 `YUXIAOER_DATA_DIR`；
- 擦亮/同步任务要加随机抖动，避免同一时间集中请求平台；
- 商品上千的店，优先用增量同步，不要频繁全量重建索引；
- 多店/店群本身有平台合规风险，账号、资质、经营主体需自行评估。
