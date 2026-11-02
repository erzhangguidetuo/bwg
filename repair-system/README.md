# 设备报修管理系统

一个基于 **Django 5.2** 的设备报修工单系统：报修人提交故障单，维修人员受理、处理、完成，
全程留痕（处理记录时间线），并带数据看板。

面向校园 / 中小企业的内部运维场景，功能完整、开箱即用。

## 功能

- **报修单管理**：提交（支持上传故障照片）、列表（搜索 + 状态筛选 + 分页）、详情
- **状态流转**：`待受理 → 处理中 → 已完成 → 已关闭`，内置状态机校验，禁止跳步与倒退
- **处理留痕**：每次状态变更写入处理记录，详情页按时间线展示（操作人 / 时间 / 备注）
- **权限控制**：普通用户只能看到自己提交的单；拥有「处理报修单」权限的账号（维修工）可查看并处理全部
- **数据看板**：按状态统计总量、按设备分类分布（一次 GROUP BY 完成，不在模板里循环查库）
- **Django Admin 后台**：维护设备分类、指派处理人、查看处理历史

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.10+ / Django 5.2（MTV） |
| 数据库 | SQLite（零配置，可平滑换成 MySQL / PostgreSQL） |
| 前端 | Django 模板 + Bootstrap 5（CDN 引入，无前端构建流程） |
| 认证 | Django 自带 auth（session + 密码哈希） |
| 权限 | 自定义 Permission `handle_repair_order`，视图层统一过滤 |
| 测试 | Django TestCase，14 个用例覆盖权限 / 状态机 / 越权 |

**零第三方依赖**：除 Django 本身外不引入任何包，clone 下来装一个 Django 就能跑。

## 快速开始

```bash
# 1. 安装（建议虚拟环境）
pip install django==5.2.18

# 2. 初始化数据库
python manage.py migrate

# 3. 生成演示数据（3 个账号 + 8 条报修单）
python manage.py seed_demo

# 4. 启动
python manage.py runserver
```

打开 http://127.0.0.1:8000 ，演示账号（密码均为 `demo12345`）：

| 账号 | 角色 | 能看到什么 |
|---|---|---|
| `student` | 普通报修人 | 只有自己的报修单 |
| `teacher` | 普通报修人 | 只有自己的报修单 |
| `tech` | 维修工 | 全部报修单，可以受理 / 处理 / 关闭 |

后台：http://127.0.0.1:8000/admin/（可用以上账号登录，`tech` 建议配合超级管理员使用）

## 运行测试

```bash
python manage.py test
```

## 项目结构

```
repair-system/
├── config/                  # 项目配置（settings / 根路由 / wsgi）
├── repair/                  # 业务应用
│   ├── models.py            # 3 个模型：Category / RepairOrder / RepairLog
│   ├── views.py             # 列表 / 详情 / 创建（CBV）+ 状态流转 / 看板（函数视图）
│   ├── forms.py             # ModelForm，字段白名单 + 标题长度校验
│   ├── admin.py             # 后台注册，含处理记录 Inline
│   ├── tests.py             # 14 个用例
│   └── management/commands/seed_demo.py   # 演示数据命令
├── templates/               # 全局模板（base + 登录）与 repair 应用模板
└── static/css/style.css     # 仅放 Bootstrap 覆盖不了的自定义样式
```

## 几个设计决策

**1. 状态机写在模型里，而不是视图里**

`RepairOrder.ALLOWED_TRANSITIONS` 定义了合法流转方向，`can_transition_to()` 供视图调用。
业务规则收在一处，将来加「验收」环节只改模型，不用翻视图。

**2. 权限过滤只写在一个地方**

`visible_orders(user)` 是唯一决定「谁能看到哪些单」的函数，列表、详情、看板全部复用。
详情页同样走这个过滤——否则直接改 URL 里的 id 就能看到别人的单（用例
`test_cannot_view_others_order_detail` 专门验证这一点）。

**3. 报修人取自登录状态，不信任前端**

`CreateView.form_valid()` 里强制 `form.instance.created_by = self.request.user`，
前端就算伪造 `created_by` 字段也会被忽略（见 `test_create_order_sets_creator_from_session`）。

**4. 列表页查询优化**

`select_related('category', 'created_by', 'handler')` 一次 JOIN 取回关联对象，避免模板里
逐行查库（N+1）；按 `status + created_at` 建了组合索引，对应列表页最常见的筛选排序组合。

## License

MIT
