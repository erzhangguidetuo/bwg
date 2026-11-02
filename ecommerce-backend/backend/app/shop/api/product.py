from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.shop.schema.order import CreateProductParam, GetProductDetail
from backend.app.shop.service import product_service
from backend.common.pagination import DependsPagination, PageData
from backend.common.response.response_schema import ResponseModel, ResponseSchemaModel, response_base
from backend.common.security.jwt import CurrentUser
from backend.common.security.permission import RequestPermission
from backend.database.db import CurrentSession, CurrentSessionTransaction

router = APIRouter()


@router.post('', summary='上架商品', dependencies=[DependsJwtAuth, RequestPermission('shop:product:create')])
async def create_product(
    db: CurrentSessionTransaction,
    obj: CreateProductParam,
) -> ResponseSchemaModel[GetProductDetail]:
    product = await product_service.create(db, obj)
    return response_base.success(data=product)


@router.get('/{pk}', summary='商品详情')
async def get_product(
    db: CurrentSession,
    pk: Annotated[int, Depends()],
) -> ResponseSchemaModel[GetProductDetail]:
    product = await product_service.get_detail(db, pk)
    return response_base.success(data=product)
