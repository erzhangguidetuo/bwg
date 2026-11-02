import asyncio

from backend.app.shop.service.order_service import order_service
from backend.app.task.celery import celery_app
from backend.database.db import async_engine


@celery_app.task(name='backend.app.shop.tasks.cancel_expired_orders')
def cancel_expired_orders() -> int:
    """
    定时取消超时未支付订单并归还库存

    由 Celery Beat 每分钟调度；任务内自建 DB 会话，
    不与 Web 进程共享连接池。
    """
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    async def _run() -> int:
        async with session_factory() as db:
            async with db.begin():
                return await order_service.cancel_expired_orders(db)

    return asyncio.run(_run())


@celery_app.task(name='backend.app.shop.tasks.low_stock_alert')
def low_stock_alert(threshold: int = 10) -> list[int]:
    """
    低库存预警：扫描 Redis 库存键，低于阈值返回商品 ID 列表
    （生产环境可在后续节点接入邮件 / 飞书 webhook 通知）
    """
    from backend.database.redis import get_redis_url

    async def _run() -> list[int]:
        import redis.asyncio as aredis

        client = aredis.from_url(get_redis_url(), decode_responses=True)
        try:
            keys = [k async for k in client.scan_iter('shop:stock:*')]
            low = []
            for key in keys:
                stock = int(await client.get(key) or 0)
                if stock < threshold:
                    low.append(int(key.rsplit(':', 1)[-1]))
            return low
        finally:
            await client.aclose()

    return asyncio.run(_run())
