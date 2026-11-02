"""
单元测试。

跑法：
    python manage.py test

覆盖四类最容易出错的地方：
1. 未登录能不能访问（权限屏障）
2. 普通用户会不会看到别人的报修单（越权）
3. 状态机动不动得了（业务规则）
4. 提交报修时，报修人会不会被前端伪造（数据可信）
"""

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from .models import Category, RepairLog, RepairOrder


class RepairTestCase(TestCase):
    """所有用例共用的初始数据"""

    def setUp(self):
        self.category = Category.objects.create(name='空调')

        self.alice = User.objects.create_user('alice', password='pass12345')
        self.bob = User.objects.create_user('bob', password='pass12345')

        # 维修工：额外授予「处理报修单」权限
        self.tech = User.objects.create_user('tech', password='pass12345')
        self.tech.user_permissions.add(Permission.objects.get(codename='handle_repair_order'))

        self.alice_order = self._create_order(self.alice, '图书馆空调不制冷')

    def _create_order(self, user, title):
        return RepairOrder.objects.create(
            title=title,
            category=self.category,
            location='3 号教学楼 402',
            description='开机十分钟后停止出风',
            created_by=user,
        )


class LoginRequiredTests(RepairTestCase):
    def test_anonymous_redirected_to_login(self):
        """未登录访问列表页应跳转登录"""
        response = self.client.get(reverse('order-list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])

    def test_anonymous_cannot_create_order(self):
        response = self.client.get(reverse('order-create'))
        self.assertEqual(response.status_code, 302)


class PermissionScopeTests(RepairTestCase):
    def test_user_sees_only_own_orders(self):
        """普通用户只能看到自己提交的单"""
        self._create_order(self.bob, '宿舍门禁刷不开')

        self.client.login(username='alice', password='pass12345')
        response = self.client.get(reverse('order-list'))

        self.assertEqual(response.status_code, 200)
        orders = list(response.context['orders'])
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].created_by, self.alice)

    def test_handler_sees_all_orders(self):
        """有处理权限的人能看到全部"""
        self._create_order(self.bob, '宿舍门禁刷不开')

        self.client.login(username='tech', password='pass12345')
        response = self.client.get(reverse('order-list'))

        self.assertEqual(response.context['page_obj'].paginator.count, 2)

    def test_cannot_view_others_order_detail(self):
        """直接改 URL 里的 id 也看不到别人的单（返回 404）"""
        self.client.login(username='alice', password='pass12345')
        response = self.client.get(reverse('order-detail', args=[self.alice_order.pk]))
        self.assertEqual(response.status_code, 200)

        self.client.login(username='bob', password='pass12345')
        response = self.client.get(reverse('order-detail', args=[self.alice_order.pk]))
        self.assertEqual(response.status_code, 404)


class CreateOrderTests(RepairTestCase):
    def test_create_order_sets_creator_from_session(self):
        """提交报修时，报修人取自登录状态，前端传什么都不影响"""
        self.client.login(username='alice', password='pass12345')
        response = self.client.post(
            reverse('order-create'),
            {
                'title': '投影仪无信号',
                'category': self.category.pk,
                'location': '1 号教学楼 201',
                'priority': 'high',
                'description': 'HDMI 接口接触不良',
                'created_by': self.bob.pk,  # 伪造字段，应被忽略
            },
        )
        self.assertEqual(response.status_code, 302)

        order = RepairOrder.objects.get(title='投影仪无信号')
        self.assertEqual(order.created_by, self.alice)
        self.assertEqual(order.status, RepairOrder.STATUS_PENDING)
        self.assertTrue(order.order_no.startswith('R'))

    def test_short_title_rejected(self):
        """标题过短会被表单拦下，不会入库"""
        self.client.login(username='alice', password='pass12345')
        response = self.client.post(
            reverse('order-create'),
            {'title': '坏了', 'category': self.category.pk, 'location': 'A', 'description': 'x'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(RepairOrder.objects.filter(title='坏了').exists())


class StatusTransitionTests(RepairTestCase):
    def test_handler_can_move_pending_to_processing(self):
        """合法流转：待受理 → 处理中，并写一条处理记录"""
        self.client.login(username='tech', password='pass12345')
        response = self.client.post(
            reverse('order-change-status', args=[self.alice_order.pk]),
            {'status': RepairOrder.STATUS_PROCESSING, 'note': '已联系报修人'},
        )
        self.assertEqual(response.status_code, 302)

        self.alice_order.refresh_from_db()
        self.assertEqual(self.alice_order.status, RepairOrder.STATUS_PROCESSING)
        self.assertEqual(self.alice_order.handler, self.tech)

        log = RepairLog.objects.get(order=self.alice_order)
        self.assertEqual(log.from_status, RepairOrder.STATUS_PENDING)
        self.assertEqual(log.to_status, RepairOrder.STATUS_PROCESSING)
        self.assertEqual(log.note, '已联系报修人')

    def test_cannot_skip_to_done(self):
        """非法流转：待受理不能直接跳到已完成"""
        self.client.login(username='tech', password='pass12345')
        response = self.client.post(
            reverse('order-change-status', args=[self.alice_order.pk]),
            {'status': RepairOrder.STATUS_DONE},
        )
        self.assertEqual(response.status_code, 302)
        self.alice_order.refresh_from_db()
        self.assertEqual(self.alice_order.status, RepairOrder.STATUS_PENDING)
        self.assertFalse(RepairLog.objects.filter(order=self.alice_order).exists())

    def test_closed_order_cannot_reopen(self):
        """已关闭的单是终态，不能再改"""
        self.alice_order.status = RepairOrder.STATUS_CLOSED
        self.alice_order.save()

        self.client.login(username='tech', password='pass12345')
        self.client.post(
            reverse('order-change-status', args=[self.alice_order.pk]),
            {'status': RepairOrder.STATUS_PROCESSING},
        )
        self.alice_order.refresh_from_db()
        self.assertEqual(self.alice_order.status, RepairOrder.STATUS_CLOSED)

    def test_normal_user_cannot_change_status(self):
        """没有权限的人调这个接口会 403"""
        self.client.login(username='alice', password='pass12345')
        response = self.client.post(
            reverse('order-change-status', args=[self.alice_order.pk]),
            {'status': RepairOrder.STATUS_PROCESSING},
        )
        self.assertEqual(response.status_code, 403)
        self.alice_order.refresh_from_db()
        self.assertEqual(self.alice_order.status, RepairOrder.STATUS_PENDING)


class SearchAndDashboardTests(RepairTestCase):
    def test_search_by_keyword(self):
        self._create_order(self.alice, '宿舍灯管闪烁')

        self.client.login(username='alice', password='pass12345')
        response = self.client.get(reverse('order-list'), {'q': '灯管'})
        self.assertEqual(response.context['page_obj'].paginator.count, 1)

    def test_filter_by_status(self):
        second = self._create_order(self.alice, '饮水机漏水')
        second.status = RepairOrder.STATUS_DONE
        second.save()

        self.client.login(username='alice', password='pass12345')
        response = self.client.get(reverse('order-list'), {'status': RepairOrder.STATUS_DONE})
        self.assertEqual(response.context['page_obj'].paginator.count, 1)
        self.assertEqual(response.context['orders'][0].title, '饮水机漏水')

    def test_dashboard_counts(self):
        done = self._create_order(self.alice, '饮水机漏水')
        done.status = RepairOrder.STATUS_DONE
        done.save()

        self.client.login(username='alice', password='pass12345')
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        totals = response.context['totals']
        self.assertEqual(totals['total'], 2)
        self.assertEqual(totals['pending'], 1)
        self.assertEqual(totals['done'], 1)
