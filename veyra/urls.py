from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from core import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.home, name="home"),
    path("inventory/products/", views.product_list, name="product_list"),
    path("inventory/products/<int:pk>/", views.product_detail, name="product_detail"),
    path("sales/orders/", views.sales_orders, name="sales_orders"),
    path("sales/orders/<int:pk>/", views.sales_detail, name="sales_detail"),
    path("sales/orders/<int:pk>/deliver/", views.sales_deliver, name="sales_deliver"),
    path("purchasing/orders/", views.purchase_orders, name="purchase_orders"),
    path("purchasing/orders/<int:pk>/", views.purchase_detail, name="purchase_detail"),
    path("purchasing/orders/<int:pk>/receive/", views.purchase_receive, name="purchase_receive"),
]
