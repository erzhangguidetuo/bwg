from typing import Annotated

from fastapi import APIRouter, Depends, Request

from backend.app.shop.schema.order import CreateOrderParam, CreateProductParam, GetOrderDetail, GetProductDetail
from backend.app.shop.service import order_service, product_service
from backend.common.response.response_schema import ResponseModel, ResponseSchemaModel, response_base
from backend.common.security.jwt import DependsJwtAuth
from backend.common.security.permission import RequestPermission
from backend.database.db import CurrentSession, CurrentSessionTransaction

product_router = APIRouter()
order_router = APIRouter()


@product_router.post('', summary='上架商品', dependencies=[DependsJwtAuth, RequestPermission('shop:product:create')])
async def create_product(
    db: CurrentSessionTransaction,
    obj: CreateProductParam,
) -> ResponseSchemaModel[GetProductDetail]:
    product = await product_service.create(db, obj)
    return response_base.success(data=product)


@product_router.get('/{pk}', summary='商品详情')
async def get_product(
    db: CurrentSession,
    pk: int,
) -> ResponseSchemaModel[GetProductDetail]:
    product = await product_service.get_detail(db, pk)
    return response_base.success(data=product)


@order_router.post('', summary='创建订单', dependencies=[DependsJwtAuth])
async def create_order(
    request: Request,
    db: CurrentSessionTransaction,
    obj: CreateOrderParam,
) -> ResponseSchemaModel[GetOrderDetail]:
    """下单接口：Redis 分布式锁 + Lua 原子扣减 + DB 乐观锁兜底，保证并发下零超卖"""
    order = await order_service.create(db, request.user.id, obj)
    return response_base.success(data=order)


@order_router.post('/{order_no}/pay', summary='模拟支付回调', dependencies=[DependsJwtAuth])
async def pay_order(
    db: CurrentSessionTransaction,
    order_no: str,
) -> ResponseModel:
    await order_service.mock_pay(db, order_no)
    return response_base.success()
