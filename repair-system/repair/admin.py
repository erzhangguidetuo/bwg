"""admin 后台：几乎不用写代码就得到一个可用的管理界面，用来维护分类、分配处理人。"""

from django.contrib import admin

from .models import Category, RepairLog, RepairOrder


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'created_at')
    search_fields = ('name',)


class RepairLogInline(admin.TabularInline):
    """在报修单编辑页里直接看到处理历史"""

    model = RepairLog
    extra = 0
    can_delete = False
    readonly_fields = ('operator', 'from_status', 'to_status', 'note', 'created_at')


@admin.register(RepairOrder)
class RepairOrderAdmin(admin.ModelAdmin):
    list_display = (
        'order_no',
        'title',
        'category',
        'status',
        'priority',
        'created_by',
        'handler',
        'created_at',
    )
    list_filter = ('status', 'priority', 'category')
    search_fields = ('order_no', 'title', 'description')
    date_hierarchy = 'created_at'
    readonly_fields = ('order_no', 'created_at', 'updated_at')
    inlines = [RepairLogInline]
    # 列表页里直接改优先级，不用点进去
    list_editable = ('priority',)
    autocomplete_fields = ('created_by', 'handler')


@admin.register(RepairLog)
class RepairLogAdmin(admin.ModelAdmin):
    list_display = ('order', 'operator', 'from_status', 'to_status', 'created_at')
    list_filter = ('to_status',)
