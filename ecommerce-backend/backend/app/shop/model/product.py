from datetime import datetime

import sqlalchemy as sa

from sqlalchemy.orm import Mapped, mapped_column

from backend.common.model import DataClassBase, TimeZone, id_key
from backend.utils.timezone import timezone


class Product(DataClassBase):
    """商品表"""

    __tablename__ = 'shop_product'

    id: Mapped[id_key] = mapped_column(init=False)
    name: Mapped[str] = mapped_column(sa.String(128), comment='商品名称')
    description: Mapped[str | None] = mapped_column(sa.String(512), comment='商品描述')
    price: Mapped[int] = mapped_column(comment='单价（分，避免浮点误差）')
    stock: Mapped[int] = mapped_column(default=0, comment='库存数量')
    # 乐观锁版本号：Redis 预扣后落库兜底，防止极端情况下超卖
    version: Mapped[int] = mapped_column(default=0, comment='乐观锁版本号')
    status: Mapped[int] = mapped_column(default=1, comment='上架状态（0下架 1上架）')
    created_time: Mapped[datetime] = mapped_column(
        TimeZone, init=False, default_factory=timezone.now, comment='创建时间'
    )
