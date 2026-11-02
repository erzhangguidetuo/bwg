from datetime import datetime

import sqlalchemy as sa

from sqlalchemy.orm import Mapped, mapped_column

from backend.common.model import DataClassBase, TimeZone, id_key
from backend.utils.timezone import timezone


class Order(DataClassBase):
    """订单表"""

    __tablename__ = 'shop_order'

    id: Mapped[id_key] = mapped_column(init=False)
    order_no: Mapped[str] = mapped_column(sa.String(32), unique=True, comment='订单号')
    user_id: Mapped[int] = mapped_column(comment='下单用户 ID')
    total_amount: Mapped[int] = mapped_column(default=0, comment='订单总金额（分）')
    status: Mapped[int] = mapped_column(default=0, comment='订单状态（0待支付 1已支付 2已取消）')
    pay_deadline: Mapped[datetime] = mapped_column(TimeZone, comment='支付截止时间（超时自动取消）')
    paid_time: Mapped[datetime | None] = mapped_column(TimeZone, init=False, comment='支付时间')
    created_time: Mapped[datetime] = mapped_column(
        TimeZone, init=False, default_factory=timezone.now, comment='创建时间'
    )


class OrderItem(DataClassBase):
    """订单明细表"""

    __tablename__ = 'shop_order_item'

    id: Mapped[id_key] = mapped_column(init=False)
    order_id: Mapped[int] = mapped_column(comment='订单 ID')
    product_id: Mapped[int] = mapped_column(comment='商品 ID')
    quantity: Mapped[int] = mapped_column(default=1, comment='购买数量')
    unit_price: Mapped[int] = mapped_column(comment='成交单价（分，下单时快照）')
