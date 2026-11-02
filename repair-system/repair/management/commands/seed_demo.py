"""
生成演示数据：分类、三个账号、若干条报修单。

    python manage.py seed_demo

账号（密码都是 demo12345）：
    student  普通报修人，只能看自己的单
    teacher  另一个报修人，用来看权限隔离效果
    tech     维修工，拥有「处理报修单」权限，能看到并处理全部单
"""

import random

from datetime import timedelta

from django.contrib.auth.models import Permission, User
from django.core.management.base import BaseCommand
from django.utils import timezone

from repair.models import Category, RepairLog, RepairOrder

CATEGORIES = ['空调', '电脑', '门禁', '照明', '水管']

TITLES = [
    ('图书馆三楼空调不制冷', '空调', '图书馆 3 楼自习区'),
    ('机房 12 号电脑无法开机', '电脑', '实训楼 402 机房'),
    ('宿舍楼门禁刷卡无反应', '门禁', '6 号宿舍楼东门'),
    ('走廊灯管闪烁', '照明', '1 号教学楼 2 层走廊'),
    ('卫生间水管漏水', '水管', '2 号教学楼 1 层'),
    ('投影仪没有信号', '电脑', '1 号教学楼 201'),
    ('饮水机不加热', '空调', '行政楼 3 层'),
    ('教室门锁坏了', '门禁', '4 号教学楼 105'),
]


class Command(BaseCommand):
    help = '生成演示数据（分类 / 账号 / 报修单）'

    def handle(self, *args, **options):
        categories = {}
        for name in CATEGORIES:
            categories[name], _ = Category.objects.get_or_create(name=name)

        student = self._ensure_user('student', '李同学')
        teacher = self._ensure_user('teacher', '王老师')
        tech = self._ensure_user('tech', '张师傅')

        # 授予维修工「处理报修单」权限
        tech.user_permissions.add(Permission.objects.get(codename='handle_repair_order'))

        created = 0
        for index, (title, category_name, location) in enumerate(TITLES):
            if RepairOrder.objects.filter(title=title).exists():
                continue

            creator = student if index % 2 == 0 else teacher
            order = RepairOrder.objects.create(
                title=title,
                category=categories[category_name],
                location=location,
                description=f'{title}，已经影响正常使用，希望尽快安排人员处理。',
                priority=random.choice(['low', 'normal', 'normal', 'high']),
                created_by=creator,
                created_at=timezone.now() - timedelta(days=random.randint(0, 20)),
            )
            created += 1

            # 前几条推演一下状态，让列表页有不同状态的样本
            if index < 2:
                order.status = RepairOrder.STATUS_DONE
                order.handler = tech
                order.save()
                RepairLog.objects.create(
                    order=order,
                    operator=tech,
                    from_status=RepairOrder.STATUS_PENDING,
                    to_status=RepairOrder.STATUS_PROCESSING,
                    note='已到现场查看',
                )
                RepairLog.objects.create(
                    order=order,
                    operator=tech,
                    from_status=RepairOrder.STATUS_PROCESSING,
                    to_status=RepairOrder.STATUS_DONE,
                    note='已维修完成，测试正常',
                )
            elif index < 4:
                order.status = RepairOrder.STATUS_PROCESSING
                order.handler = tech
                order.save()
                RepairLog.objects.create(
                    order=order,
                    operator=tech,
                    from_status=RepairOrder.STATUS_PENDING,
                    to_status=RepairOrder.STATUS_PROCESSING,
                    note='已联系报修人，准备备件',
                )

        self.stdout.write(self.style.SUCCESS(f'完成：{len(categories)} 个分类，{created} 条报修单'))
        self.stdout.write('演示账号（密码都是 demo12345）：')
        self.stdout.write('  student  普通报修人')
        self.stdout.write('  teacher  另一个报修人')
        self.stdout.write('  tech     维修工（可处理全部报修单）')

    @staticmethod
    def _ensure_user(username: str, first_name: str) -> User:
        user, created = User.objects.get_or_create(
            username=username, defaults={'first_name': first_name}
        )
        if created:
            user.set_password('demo12345')
            user.save()
        return user
