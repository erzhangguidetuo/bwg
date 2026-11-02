import uuid

from datetime import timedelta
from pathlib import Path

import redis.exceptions

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.shop.crud import crud_order, crud_product
from backend.app.shop.enums import OrderStatus
from backend.app.shop.model.order import Order
from backend.app.shop.schema.order import CreateOrderParam
from backend.database.redis import redis_client
from backend.utils.timezone import timezone

# Lua 脚本预加载：EVALSHA 比 EVAL 少传脚本体，高并发下节省带宽
_LUA_DIR = Path(__file__).parent.parent / 'luas'
_DEDUCT_STOCK_SHA: str | None = None
_RESTORE_STOCK_SHA: str | None = None

STOCK_KEY = 'shop:stock:{}'
ORDER_LOCK_KEY = 'shop:lock:stock:{}'
PAY_DEADLINE_MINUTES = 15


async def _load_script(path: Path) -> str:
    """脚本 SCRIPT LOAD 加载并缓存 SHA（Redis 重启后自动重载）"""
    global _DEDUCT_STOCK_SHA, _RESTORE_STOCK_SHA  # noqa: PLW0603
    with open(path, encoding='utf-8') as f:
        script = f.read()
    return await redis_client.script_load(script)


async def deduct_stock_in_redis(product_id: int, quantity: int) -> int:
    """
    Redis 层原子预扣库存

    :return: 扣减后的剩余库存
    :raises HTTPException: 库存键不存在或库存不足
    """
    global _DEDUCT_STOCK_SHA
    if _DEDUCT_STOCK_SHA is None:
        _DEDUCT_STOCK_SHA = await _load_script(_LUA_DIR / 'deduct_stock.lua')
    try:
        result = await redis_client.evalsha(_DEDUCT_STOCK_SHA, 1, STOCK_KEY.format(product_id), quantity)
    except redis.exceptions.NoScriptError:
        # 脚本缓存失效（Redis 重启 / 主从切换），回退 EVAL 重载
        with open(_LUA_DIR / 'deduct_stock.lua', encoding='utf-8') as f:
            result = await redis_client.eval(f.read(), 1, STOCK_KEY.format(product_id), quantity)
        _DEDUCT_STOCK_SHA = None
    if result == -1:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='商品库存数据不存在')
    if result == -2:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='库存不足')
    return int(result)


async def restore_stock_in_redis(product_id: int, quantity: int) -> None:
    """取消订单时归还 Redis 库存"""
    global _RESTORE_STOCK_SHA
    if _RESTORE_STOCK_SHA is None:
        _RESTORE_STOCK_SHA = await _load_script(_LUA_DIR / 'restore_stock.lua')
    try:
        await redis_client.evalsha(_RESTORE_STOCK_SHA, 1, STOCK_KEY.format(product_id), quantity)
    except redis.exceptions.NoScriptError:
        with open(_LUA_DIR / 'restore_stock.lua', encoding='utf-8') as f:
            await redis_client.eval(f.read(), 1, STOCK_KEY.format(product_id), quantity)
        _RESTORE_STOCK_SHA = None


async def warm_up_stock_cache(db: AsyncSession, product_id: int) -> None:
    """商品上架/库存变更时预热缓存：DB 为准覆盖 Redis"""
    product = await crud_product.get(db, product_id)
    if product is not None:
        await redis_client.set(STOCK_KEY.format(product_id), product.stock)


class OrderService:
    """订单业务服务"""

    @staticmethod
    async def create(db: AsyncSession, user_id: int, obj: CreateOrderParam) -> Order:
        """
        创建订单（下单全链路）

        流程：Redis 分布式锁 → Lua 原子预扣库存 → DB 乐观锁落库 → 写订单与明细 → 释放锁
        任一步失败均回滚 Redis 预扣，保证两边最终一致。
        """
        product_ids = [item.product_id for item in obj.items]
        products = {}
        for pid in product_ids:
            product = await crud_product.get(db, pid)
            if product is None or product.status != 1:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'商品不存在或已下架: {pid}')
            products[pid] = product

        total_amount = sum(products[item.product_id].price * item.quantity for item in obj.items)
        order_no = f"{timezone.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:8].upper()}"

        # 1. 分布式锁：同一商品的并发下单串行化，避免多请求同时预扣导致误判
        locks = []
        try:
            for pid in dict.fromkeys(product_ids):
                lock = redis_client.lock(
                    ORDER_LOCK_KEY.format(pid), timeout=10, blocking_timeout=5
                )
                acquired = await lock.acquire(blocking=True)
                if not acquired:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='下单排队超时，请重试')
                locks.append(lock)

            # 2. Redis Lua 原子预扣
            for item in obj.items:
                await deduct_stock_in_redis(item.product_id, item.quantity)

            # 3. DB 乐观锁落库兜底 + 写订单
            try:
                for item in obj.items:
                    ok = await crud_product.decrease_stock_with_version(
                        db, item.product_id, item.quantity
                    )
                    if not ok:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT, detail='库存不足'
                        )
                order = Order(
                    order_no=order_no,
                    user_id=user_id,
                    total_amount=total_amount,
                    pay_deadline=timezone.now() + timedelta(minutes=PAY_DEADLINE_MINUTES),
                )
                await crud_order.create_with_items(
                    db,
                    order,
                    [(i.product_id, i.quantity, products[i.product_id].price) for i in obj.items],
                )
                return order
            except Exception:
                # 4. 落库失败 → 归还 Redis 预扣，保证不超卖也不少卖
                for item in obj.items:
                    await restore_stock_in_redis(item.product_id, item.quantity)
                raise
        finally:
            for lock in locks:
                try:
                    await lock.release()
                except Exception:  # noqa: S110
                    # 锁超时自动释放，忽略释放异常
                    pass

    @staticmethod
    async def cancel_expired_orders(db: AsyncSession) -> int:
        """
        取消全部超时未支付订单并归还库存

        :return: 取消的订单数
        """
        expired_orders = await crud_order.get_expired_unpaid(db)
        for order in expired_orders:
            items = await crud_order.get_items(db, order.id)
            for product_id, quantity in items:
                await crud_product.restore_stock(db, product_id, quantity)
                await restore_stock_in_redis(product_id, quantity)
            await crud_order.update_status(db, order.id, OrderStatus.CANCELLED)
        return len(expired_orders)

    @staticmethod
    async def mock_pay(db: AsyncSession, order_no: str) -> None:
        """模拟支付回调：校验订单存在且未超时后，将状态置为已支付"""
        order = await crud_order.get_by_no(db, order_no)
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='订单不存在')
        if order.status != 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='订单状态不可支付')
        if order.pay_deadline < timezone.now():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='订单已超时，请重新下单')
        await crud_order.update_status(db, order.id, OrderStatus.PAID)


order_service = OrderService()
