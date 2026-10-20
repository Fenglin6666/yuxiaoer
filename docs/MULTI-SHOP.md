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

## 5. 控制面（下一阶段）

当前需要手工为每个店启动实例。控制面需要做：

- 店铺注册表（shop_id、端口、状态、负责人）；
- 健康检查与进程守护；
- 统一告警、日报、擦亮任务；
- 跨店只读汇总，不共享买家数据；
- 按店权限。

在这些完成前，不建议把几十个店塞进一个进程。

## 6. 注意事项

- 每个店必须使用不同端口；
- 不同店不要共用 `YUXIAOER_DATA_DIR`；
- 擦亮/同步任务要加随机抖动，避免同一时间集中请求平台；
- 商品上千的店，优先用增量同步，不要频繁全量重建索引；
- 多店/店群本身有平台合规风险，账号、资质、经营主体需自行评估。
