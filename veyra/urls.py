from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from accounting import views as accounting_views
from accounts import views as accounts_views
from core import views
from core.forms import VeyraLoginForm

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="login.html", authentication_form=VeyraLoginForm), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/password/", accounts_views.VeyraPasswordChangeView.as_view(), name="password_change"),
    path("", views.home, name="home"),
    path("inventory/products/", views.product_list, name="product_list"),
    path("inventory/products/<int:pk>/", views.product_detail, name="product_detail"),
    path("sales/orders/", views.sales_orders, name="sales_orders"),
    path("sales/orders/<int:pk>/", views.sales_detail, name="sales_detail"),
    path("sales/orders/<int:pk>/confirm/", views.sales_confirm, name="sales_confirm"),
    path("sales/orders/<int:pk>/deliver/", views.sales_deliver, name="sales_deliver"),
    path("purchasing/orders/", views.purchase_orders, name="purchase_orders"),
    path("purchasing/orders/<int:pk>/", views.purchase_detail, name="purchase_detail"),
    path("purchasing/orders/<int:pk>/confirm/", views.purchase_confirm, name="purchase_confirm"),
    path("purchasing/orders/<int:pk>/receive/", views.purchase_receive, name="purchase_receive"),
    path("purchasing/orders/<int:pk>/cancel/", views.purchase_cancel, name="purchase_cancel"),
    path("purchasing/orders/<int:pk>/pay/", views.purchase_pay, name="purchase_pay"),
    path("purchasing/payments/", views.purchase_payments, name="purchase_payments"),
    path("accounts/me/", accounts_views.my_preferences, name="my_preferences"),
    path("accounts/me/logout-all/", accounts_views.logout_all_devices, name="logout_all_devices"),
    path("settings/", views.settings_index, name="settings_index"),
    path("settings/<slug:code>/", views.settings_module, name="settings_module"),
    path("accounting/entries/", accounting_views.journal_list, name="journal_list"),
    path("accounting/trial-balance/", accounting_views.trial_balance_view, name="trial_balance"),
    path("contacts/partners/", views.partner_list, name="partner_list"),
    path("contacts/partners/new/", views.partner_create, name="partner_create"),
    path("contacts/partners/<int:pk>/edit/", views.partner_edit, name="partner_edit"),
    path("inventory/products/new/", views.product_create, name="product_create"),
    path("inventory/products/<int:pk>/edit/", views.product_edit, name="product_edit"),
    path("sales/orders/new/", views.sales_create, name="sales_create"),
    path("sales/orders/<int:pk>/edit/", views.sales_edit, name="sales_edit"),
    path("purchasing/orders/new/", views.purchase_create, name="purchase_create"),
    path("purchasing/orders/<int:pk>/edit/", views.purchase_edit, name="purchase_edit"),
]
