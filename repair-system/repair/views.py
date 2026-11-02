"""
视图层。

权限过滤只写在一个地方（visible_orders），列表页、详情页、看板都复用它，
这样以后改规则（比如再加一个「院系管理员只能看本院系的单」）只需要改一处。
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView

from .forms import RepairOrderForm
from .models import Category, RepairLog, RepairOrder


def can_handle(user) -> bool:
    """
    是否具备「处理报修单」的权限。

    用的是 Django 自带的权限系统（auth_permission 表）：
    自定义权限写在 RepairOrder.Meta.permissions 里，在 admin 后台给账号勾选即可授予。
    超级管理员自动拥有全部权限，所以不用单独判断 is_superuser。
    """
    return user.is_authenticated and user.has_perm('repair.handle_repair_order')


def visible_orders(user) -> QuerySet[RepairOrder]:
    """当前用户能看到的报修单：有处理权限的看全部，普通用户只看自己提交的"""
    # select_related 把分类、报修人、处理人一次查出来，避免列表页 N+1 查询
    queryset = RepairOrder.objects.select_related('category', 'created_by', 'handler')
    if can_handle(user):
        return queryset
    return queryset.filter(created_by=user)


class OrderListView(LoginRequiredMixin, ListView):
    """报修单列表：支持关键词搜索和状态筛选，每页 10 条"""

    model = RepairOrder
    template_name = 'repair/order_list.html'
    context_object_name = 'orders'
    paginate_by = 10

    def get_queryset(self):
        queryset = visible_orders(self.request.user)

        keyword = self.request.GET.get('q', '').strip()
        if keyword:
            queryset = queryset.filter(
                Q(order_no__icontains=keyword)
                | Q(title__icontains=keyword)
                | Q(description__icontains=keyword)
            )

        status = self.request.GET.get('status', '')
        if status.isdigit() and int(status) in dict(RepairOrder.STATUS_CHOICES):
            queryset = queryset.filter(status=int(status))

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 模板里需要用它来高亮当前筛选的标签
        context['current_status'] = self.request.GET.get('status', '')
        context['keyword'] = self.request.GET.get('q', '')
        context['status_choices'] = RepairOrder.STATUS_CHOICES
        context['can_handle'] = can_handle(self.request.user)
        return context


class OrderDetailView(LoginRequiredMixin, DetailView):
    """报修单详情：处理记录按时间线展示"""

    model = RepairOrder
    template_name = 'repair/order_detail.html'
    context_object_name = 'order'

    def get_queryset(self):
        # 关键：详情页也走同一套权限过滤，否则改一下 URL 里的 id 就能看到别人的单
        return visible_orders(self.request.user).prefetch_related('logs__operator')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object
        context['next_statuses'] = order.next_statuses() if can_handle(self.request.user) else []
        context['can_handle'] = can_handle(self.request.user)
        return context


class OrderCreateView(LoginRequiredMixin, CreateView):
    """提交报修单"""

    model = RepairOrder
    form_class = RepairOrderForm
    template_name = 'repair/order_form.html'

    def form_valid(self, form):
        # 报修人由登录状态决定，不能让前端传，否则可以冒充别人提单
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f'报修单 {self.object.order_no} 提交成功，等待受理')
        return response

    def get_success_url(self) -> str:
        return self.object.get_absolute_url()


@login_required
@require_POST
def change_status(request: HttpRequest, pk: int) -> HttpResponse:
    """
    状态流转。

    做了三层校验，缺一层都可能被绕过：
    1. 权限：只能操作自己能看到的单
    2. 参数：目标状态必须是合法值
    3. 状态机：不能跳步或倒退（规则在模型里）
    """
    order = get_object_or_404(visible_orders(request.user), pk=pk)

    if not can_handle(request.user):
        raise PermissionDenied('只有维修人员可以变更报修单状态')

    raw_status = request.POST.get('status', '')
    if not raw_status.isdigit():
        messages.error(request, '状态参数不合法')
        return redirect(order)

    target_status = int(raw_status)
    if not order.can_transition_to(target_status):
        messages.error(request, f'不能从「{order.status_label}」直接改为该状态')
        return redirect(order)

    note = request.POST.get('note', '').strip()[:200]
    from_status = order.status

    order.status = target_status
    # 谁把单接下的，就记谁为处理人
    if target_status == RepairOrder.STATUS_PROCESSING and order.handler_id is None:
        order.handler = request.user
    order.save()

    RepairLog.objects.create(
        order=order,
        operator=request.user,
        from_status=from_status,
        to_status=target_status,
        note=note,
    )
    messages.success(request, f'已更新为「{order.status_label}」')
    return redirect(order)


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    """数据看板：按状态和分类统计，普通用户只统计自己的单"""
    queryset = visible_orders(request.user)

    totals = queryset.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status=RepairOrder.STATUS_PENDING)),
        processing=Count('id', filter=Q(status=RepairOrder.STATUS_PROCESSING)),
        done=Count('id', filter=Q(status=RepairOrder.STATUS_DONE)),
        closed=Count('id', filter=Q(status=RepairOrder.STATUS_CLOSED)),
    )

    # 每个分类下有多少单：一次 GROUP BY 查完，不在模板里循环查库
    by_category = (
        Category.objects.annotate(order_count=Count('orders', filter=Q(orders__in=queryset)))
        .filter(order_count__gt=0)
        .order_by('-order_count')
    )

    context = {
        'totals': totals,
        'by_category': by_category,
        'recent_orders': queryset[:5],
        'can_handle': can_handle(request.user),
    }
    return render(request, 'repair/dashboard.html', context)
