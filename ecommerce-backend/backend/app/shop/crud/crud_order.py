import sqlalchemy as sa

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy_crud_plus import CRUDPlus

from backend.app.shop.model.order import Order, OrderItem
from backend.utils.timezone import timezone


class CRUPOrder(CRUDPlus[Order]):
    """订单数据库操作类"""

    async def get(self, db: AsyncSession, order_id: int) -> Order | None:
        return await self.select_model_by_column(db, id=order_id)

    async def get_by_no(self, db: AsyncSession, order_no: str) -> Order | None:
        return await self.select_model_by_column(db, order_no=order_no)

    async def get_list_by_user(self, db: AsyncSession, user_id: int) -> Select:
        return await self.select_order('created_time', 'desc', user_id__eq=user_id)

    async def get_items(self, db: AsyncSession, order_id: int) -> list[tuple[int, int]]:
        """获取订单明细 [(product_id, quantity), ...]"""
        result = await db.execute(
            sa.select(OrderItem.product_id, OrderItem.quantity).where(OrderItem.order_id == order_id)
        )
        return [(row[0], row[1]) for row in result.all()]

    async def get_expired_unpaid(self, db: AsyncSession) -> list[Order]:
        """获取已超时未支付订单（供 Celery Beat 定时任务扫描）"""
        result = await db.execute(
            sa.select(Order).where(
                Order.status == 0,
                Order.pay_deadline < timezone.now(),
            )
        )
        return list(result.scalars().all())

    async def update_status(self, db: AsyncSession, order_id: int, status: int) -> None:
        """更新订单状态（仅待支付状态可流转）"""
        await db.execute(
            sa.update(Order).where(Order.id == order_id, Order.status == 0).values(status=status)
        )

    async def create_with_items(
        self,
        db: AsyncSession,
        order: Order,
        items: list[tuple[int, int, int]],
    ) -> None:
        """
        创建订单及明细

        :param db: 数据库会话
        :param order: 订单模型实例
        :param items: [(product_id, quantity, unit_price), ...]
        """
        db.add(order)
        await db.flush()
        for product_id, quantity, unit_price in items:
            db.add(
                OrderItem(
                    order_id=order.id,
                    product_id=product_id,
                    quantity=quantity,
                    unit_price=unit_price,
                )
            )


crud_order: CRUPOrder = CRUPOrder(Order)
