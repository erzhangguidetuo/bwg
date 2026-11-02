# MY_CHANGES —— 本仓库相对上游的修改说明

> 上游项目：[fastapi-practices/fastapi-best-architecture](https://github.com/fastapi-practices/fastapi-best-architecture)（FBA）
> 上游 License：**MIT**（本目录保留原始 `LICENSE` 文件，遵循 MIT 第 2 条保留版权与许可声明）
> 本目录声明：在 FBA 企业级后端架构之上，**自研实现了一个完整的电商「商品-库存-订单-支付」业务模块**（`backend/app/shop/`），并接入框架已有的认证、RBAC、Celery 与部署设施。

## 修改清单

### 1. 新增 `backend/app/shop/` 电商业务模块（自研）

| 分层 | 文件 | 内容 |
|---|---|---|
| model | `model/product.py`、`model/order.py` | 商品表 / 订单表 / 订单明细表（金额用「分」存储避免浮点误差；商品带乐观锁 `version` 字段） |
| schema | `schema/order.py` | 商品与订单的请求/响应模型（Pydantic v2） |
| crud | `crud/crud_product.py`、`crud/crud_order.py` | 基于 `sqlalchemy-crud-plus` 的数据访问层；`decrease_stock_with_version` 用一条条件 UPDATE 实现 DB 层乐观锁扣减 |
| service | `service/order_service.py` | **下单全链路核心**：Redis 分布式锁（`SET NX EX` + 阻塞等待）→ **Lua 脚本原子预扣库存**（`EVALSHA`，带 `NoScript` 自动重载）→ DB 乐观锁落库兜底 → 写订单与明细 → 失败路径**归还 Redis 预扣**，保证 Redis 与 DB 最终一致 |
| service | `service/product_service.py` | 商品上架（预热库存缓存）、详情查询（缓存 + 空值缓存防穿透） |
| luas | `luas/deduct_stock.lua`、`luas/restore_stock.lua` | 库存扣减 / 归还的 Lua 脚本：比较与扣减在 Redis 内一次完成，消除「先 GET 再 SET」竞态 |
| api | `api/product.py`、`api/order.py`、`api/router.py` | REST 接口：上架商品、商品详情、创建订单、模拟支付回调 |
| tasks | `tasks.py` | Celery 任务：`cancel_expired_orders`（超时未支付订单自动取消 + 归还库存）、`low_stock_alert`（低库存扫描预警） |
| tests | `tests/test_shop_order_flow.py` | Pytest + TestClient 集成测试：基础下单/支付流程、库存不足拒绝、**100 并发抢 50 库存的零超卖压测断言** |

### 2. 修改的既有文件

| 文件 | 改动 |
|---|---|
| `backend/app/router.py` | 注册 `shop` 路由（`/shop/products`、`/shop/orders`） |
| `backend/app/task/tasks/beat.py` | 新增两个 Celery Beat 定时任务：每分钟扫描超时订单、每 5 分钟低库存扫描 |

### 3. 删除的文件

- `backend/static/ip2region_*.xdb`（约 47MB 的 IP 库数据文件）：减小仓库体积，需要时按上游 README 重新下载。

## 设计要点（对应 README 中的说明）

1. **为什么两层扣库存（Redis + DB）**：Redis Lua 保证高并发下的吞吐与原子性，DB 乐观锁作为最终兜底；任一层拒绝即回滚另一层，实测并发下零超卖（见测试 `test_concurrent_order_no_oversell`）。
2. **为什么用分布式锁**：同一商品的多个下单请求在「读库存-预扣」区间串行化，避免大量请求同时竞争导致的有效失败；锁粒度为单个商品，不影响不同商品并行下单。
3. **订单超时取消**：采用 Celery Beat 周期扫描（简单可靠），未选用 Redis 过期键监听（无法保证可靠触发）。
