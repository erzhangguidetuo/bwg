from datetime import datetime

from pydantic import ConfigDict, Field

from backend.common.schema import SchemaBase


class CreateProductParam(SchemaBase):
    """商品创建参数"""

    name: str
    description: str | None = None
    price: int = Field(ge=1, description='单价（分）')
    stock: int = Field(default=0, ge=0)


class GetProductDetail(SchemaBase):
    """商品详情"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    price: int
    stock: int
    status: int
    created_time: datetime


class OrderItemParam(SchemaBase):
    """订单明细参数"""

    product_id: int
    quantity: int = Field(ge=1, le=99)


class CreateOrderParam(SchemaBase):
    """订单创建参数"""

    items: list[OrderItemParam] = Field(min_length=1)


class GetOrderDetail(SchemaBase):
    """订单详情"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    order_no: str
    user_id: int
    total_amount: int
    status: int
    pay_deadline: datetime
    created_time: datetime
