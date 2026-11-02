"""
数据模型：设备分类、报修单、处理记录。

三个模型的关系：
    Category  1 ── n  RepairOrder  1 ── n  RepairLog

报修单的核心业务是「状态流转」，所以状态机写在模型里（见 RepairOrder.ALLOWED_TRANSITIONS），
视图层只负责调用，避免把业务规则散落在各个视图里。
"""

import random

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class Category(models.Model):
    """设备分类，例如「空调 / 电脑 / 门禁」"""

    name = models.CharField('分类名称', max_length=32, unique=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '设备分类'
        verbose_name_plural = verbose_name
        ordering = ['id']

    def __str__(self) -> str:
        return self.name


class RepairOrder(models.Model):
    """报修单"""

    # 状态用整数存，通过 CHOICES 显示中文；整数便于排序和统计
    STATUS_PENDING = 0  # 待受理
    STATUS_PROCESSING = 1  # 处理中
    STATUS_DONE = 2  # 已完成
    STATUS_CLOSED = 3  # 已关闭

    STATUS_CHOICES = [
        (STATUS_PENDING, '待受理'),
        (STATUS_PROCESSING, '处理中'),
        (STATUS_DONE, '已完成'),
        (STATUS_CLOSED, '已关闭'),
    ]

    # 状态机：只允许按这个方向流转，防止「已完成的单被改回待受理」这类脏数据
    ALLOWED_TRANSITIONS = {
        STATUS_PENDING: {STATUS_PROCESSING, STATUS_CLOSED},
        STATUS_PROCESSING: {STATUS_DONE, STATUS_CLOSED},
        STATUS_DONE: {STATUS_CLOSED},
        STATUS_CLOSED: set(),
    }

    PRIORITY_CHOICES = [
        ('low', '低'),
        ('normal', '普通'),
        ('high', '紧急'),
    ]

    order_no = models.CharField('报修单号', max_length=20, unique=True, editable=False)
    title = models.CharField('故障标题', max_length=64)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name='orders', verbose_name='设备分类'
    )
    location = models.CharField('故障地点', max_length=64, help_text='例如：3 号教学楼 402')
    description = models.TextField('故障描述')
    image = models.FileField('故障照片', upload_to='repair/%Y%m/', blank=True, null=True)
    priority = models.CharField('紧急程度', max_length=8, choices=PRIORITY_CHOICES, default='normal')
    status = models.IntegerField('状态', choices=STATUS_CHOICES, default=STATUS_PENDING)

    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='repair_orders', verbose_name='报修人'
    )
    handler = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='handled_repair_orders',
        verbose_name='处理人',
    )

    created_at = models.DateTimeField('提交时间', default=timezone.now)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '报修单'
        verbose_name_plural = verbose_name
        # 列表页默认按提交时间倒序，最新的在最上面
        ordering = ['-created_at']
        indexes = [
            # 列表页最常见的组合查询：按状态筛选 + 按时间排序
            models.Index(fields=['status', '-created_at'], name='idx_order_status_time'),
            models.Index(fields=['created_by'], name='idx_order_creator'),
        ]
        permissions = [
            # 自定义权限：只有被授予该权限的账号（维修工/管理员）才能处理别人的报修单
            ('handle_repair_order', '可以受理并处理报修单'),
        ]

    def __str__(self) -> str:
        return f'{self.order_no} {self.title}'

    def get_absolute_url(self) -> str:
        """详情页地址，CreateView 提交成功后靠它跳转"""
        from django.urls import reverse

        return reverse('order-detail', kwargs={'pk': self.pk})

    def save(self, *args, **kwargs):
        if not self.order_no:
            # 时间戳 + 3 位随机数，够用且不依赖数据库自增
            stamp = timezone.localtime().strftime('%Y%m%d%H%M%S')
            self.order_no = f'R{stamp}{random.randint(100, 999)}'
        super().save(*args, **kwargs)

    # ---------- 业务方法 ----------

    def can_transition_to(self, target_status: int) -> bool:
        """当前状态能否流转到目标状态"""
        return target_status in self.ALLOWED_TRANSITIONS.get(self.status, set())

    def next_statuses(self) -> list[tuple[int, str]]:
        """当前状态下，页面上应该显示哪几个操作按钮"""
        allowed = self.ALLOWED_TRANSITIONS.get(self.status, set())
        return [item for item in self.STATUS_CHOICES if item[0] in allowed]

    @property
    def status_label(self) -> str:
        return self.get_status_display()

    @property
    def priority_label(self) -> str:
        return self.get_priority_display()


class RepairLog(models.Model):
    """处理记录：每次状态变更写一条，详情页按时间线展示"""

    order = models.ForeignKey(
        RepairOrder, on_delete=models.CASCADE, related_name='logs', verbose_name='报修单'
    )
    operator = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='操作人')
    from_status = models.IntegerField('原状态', choices=RepairOrder.STATUS_CHOICES)
    to_status = models.IntegerField('新状态', choices=RepairOrder.STATUS_CHOICES)
    note = models.CharField('处理说明', max_length=200, blank=True)
    created_at = models.DateTimeField('操作时间', default=timezone.now)

    class Meta:
        verbose_name = '处理记录'
        verbose_name_plural = verbose_name
        ordering = ['created_at']

    def __str__(self) -> str:
        return f'{self.order.order_no} {self.get_from_status_display()}→{self.get_to_status_display()}'
