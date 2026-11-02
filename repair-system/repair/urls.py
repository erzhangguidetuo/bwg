"""repair 应用的路由。"""

from django.urls import path

from . import views

urlpatterns = [
    path('', views.OrderListView.as_view(), name='order-list'),
    path('orders/new/', views.OrderCreateView.as_view(), name='order-create'),
    path('orders/<int:pk>/', views.OrderDetailView.as_view(), name='order-detail'),
    path('orders/<int:pk>/status/', views.change_status, name='order-change-status'),
    path('dashboard/', views.dashboard, name='dashboard'),
]
