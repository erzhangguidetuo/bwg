import sqlalchemy as sa

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy_crud_plus import CRUDPlus

from backend.app.shop.model.product import Product
from backend.app.shop.schema.order import CreateProductParam


class CRUDProduct(CRUDPlus[Product]):
    """商品数据库操作类"""

    async def get(self, db: AsyncSession, product_id: int) -> Product | None:
        return await self.select_model_by_column(db, id=product_id)

    async def get_list(self, db: AsyncSession, status: int | None = None) -> Select:
        filters = {'status__eq': status} if status is not None else {}
        return await self.select_order('created_time', 'desc', **filters)

    async def create(self, db: AsyncSession, obj: CreateProductParam) -> Product:
        return await self.create_model(db, obj)

    async def decrease_stock_with_version(
        self, db: AsyncSession, product_id: int, quantity: int
    ) -> bool:
        """
        数据库层乐观锁扣减库存（Redis 预扣成功后的落库兜底）

        :param db: 数据库会话
        :param product_id: 商品 ID
        :param quantity: 扣减数量
        :return: 是否扣减成功
        """
        result = await db.execute(
            sa.update(Product)
            .where(
                Product.id == product_id,
                Product.stock >= quantity,
                Product.status == 1,
            )
            .values(stock=Product.stock - quantity, version=Product.version + 1)
        )
        return result.rowcount > 0

    async def restore_stock(self, db: AsyncSession, product_id: int, quantity: int) -> None:
        """归还库存（订单取消）"""
        await db.execute(
            sa.update(Product)
            .where(Product.id == product_id)
            .values(stock=Product.stock + quantity, version=Product.version + 1)
        )


crud_product: CRUDProduct = CRUDProduct(Product)
