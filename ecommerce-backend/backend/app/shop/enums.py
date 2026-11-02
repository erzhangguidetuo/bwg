from enum import IntEnum


class OrderStatus(IntEnum):
    """订单状态"""

    UNPAID = 0
    PAID = 1
    CANCELLED = 2
