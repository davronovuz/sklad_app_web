from django.urls import path
from . import views

urlpatterns = [
    # ==================== AUTH ====================
    path('', views.login_view, name='login'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # ==================== ADMIN: DASHBOARD ====================
    path('admin-panel/', views.admin_dashboard, name='admin_dashboard'),

    # ==================== ADMIN: WAREHOUSE (OMBOR) ====================
    path('admin-panel/warehouse/create/', views.admin_warehouse_create, name='admin_warehouse_create'),
    path('admin-panel/warehouse/<int:pk>/', views.admin_warehouse_detail, name='admin_warehouse_detail'),
    path('admin-panel/warehouse/<int:pk>/edit/', views.admin_warehouse_edit, name='admin_warehouse_edit'),
    path('admin-panel/warehouse/<int:pk>/delete/', views.admin_warehouse_delete, name='admin_warehouse_delete'),

    # ==================== ADMIN: PRODUCTS (NOMENKLATURA) ====================
    path('admin-panel/products/', views.admin_products, name='admin_products'),
    path('admin-panel/products/upload/', views.admin_products_upload, name='admin_products_upload'),

    # ==================== ADMIN: INVENTORY (1C QOLDIQ) ====================
    path('admin-panel/warehouse/<int:warehouse_pk>/inventory/upload/', views.admin_inventory_upload,
         name='admin_inventory_upload'),



    # ==================== ADMIN: REVIZORS ====================
    path('admin-panel/revizors/', views.admin_revizors, name='admin_revizors'),
    path('admin-panel/revizors/create/', views.admin_revizor_create, name='admin_revizor_create'),
    path('admin-panel/revizors/<int:pk>/delete/', views.admin_revizor_delete, name='admin_revizor_delete'),

    # ==================== ADMIN: REVISION ====================
    path('admin-panel/warehouse/<int:warehouse_pk>/revision/create/', views.admin_revision_create,
         name='admin_revision_create'),
    path('admin-panel/revision/<int:pk>/', views.admin_revision_detail, name='admin_revision_detail'),
    path('admin-panel/revision/<int:pk>/start/', views.admin_revision_start, name='admin_revision_start'),
    path('admin-panel/revision/<int:pk>/complete/', views.admin_revision_complete, name='admin_revision_complete'),
    path('admin-panel/revision/<int:pk>/results/', views.admin_revision_results, name='admin_revision_results'),
    path('admin-panel/revision/<int:pk>/export/', views.admin_revision_export, name='admin_revision_export'),
    path('admin-panel/revision/<int:pk>/unaccounted/export/', views.admin_unaccounted_export,
         name='admin_unaccounted_export'),

    # Ombor bo'yicha umumiy natijalar
    path('admin-panel/warehouse/<int:warehouse_pk>/combined-results/',
         views.admin_warehouse_combined_results,
         name='admin_warehouse_combined_results'),

    path('admin-panel/warehouse/<int:warehouse_pk>/combined-results/export/',
         views.admin_warehouse_combined_export,
         name='admin_warehouse_combined_export'),

    # ==================== REVIZOR: DASHBOARD ====================
    path('revizor/', views.revizor_dashboard, name='revizor_dashboard'),

    # ==================== REVIZOR: WORK ====================
    path('revizor/work/<int:assignment_pk>/', views.revizor_work, name='revizor_work'),
    path('revizor/items/<int:revision_pk>/', views.revizor_items, name='revizor_items'),
    path('revizor/complete/<int:assignment_pk>/', views.revizor_complete, name='revizor_complete'),
    path('revizor/export/<int:revision_pk>/', views.revizor_export, name='revizor_export'),

    # ==================== REVIZOR: AJAX ====================
    path('api/products/search/', views.revizor_search_products, name='revizor_search_products'),
    path('api/items/add/', views.revizor_add_item, name='revizor_add_item'),
    path('api/items/<int:pk>/update/', views.revizor_update_item, name='revizor_update_item'),
    path('api/items/<int:pk>/delete/', views.revizor_delete_item, name='revizor_delete_item'),
]