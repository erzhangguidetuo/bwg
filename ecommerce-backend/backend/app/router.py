from fastapi import APIRouter

from backend.app.admin.api.router import v1 as admin_v1
from backend.app.shop.api.router import router as shop_router
from backend.app.task.api.router import v1 as task_v1

router = APIRouter()

router.include_router(admin_v1)
router.include_router(shop_router, prefix='/shop', tags=['商城'])
router.include_router(task_v1)
