from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.shop.crud import crud_product
from backend.app.shop.schema.order import CreateProductParam
from backend.database.redis import redis_client

STOCK_KEY = 'shop:stock:{}'


class ProductService:
    """商品业务服务"""

    @staticmethod
    async def create(db: AsyncSession, obj: CreateProductParam):
        """上架商品并预热 Redis 库存缓存"""
        product = await crud_product.create(db, obj)
        await redis_client.set(STOCK_KEY.format(product.id), product.stock)
        return product

    @staticmethod
    async def get_detail(db: AsyncSession, product_id: int):
        """商品详情：先读 Redis 缓存，未命中回源 DB 并写回（空值缓存防穿透）"""
        product = await crud_product.get(db, product_id)
        if product is None:
            # 空值缓存：短暂标记不存在的商品，防止缓存穿透打穿 DB
            await redis_client.set(f'shop:product:null:{product_id}', 1, ex=60)
            return None
        return product


product_service = ProductService()
