from fastapi import APIRouter

from backend.app.shop.api.order import order_router, product_router

router = APIRouter()
router.include_router(product_router, prefix='/products', tags=['商品'])
router.include_router(order_router, prefix='/orders', tags=['订单'])
