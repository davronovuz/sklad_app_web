from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import (
    User, Warehouse, Product, Inventory,
    Revision, RevisionAssignment, RevisionItem,
    RevisionResult, UnaccountedItem
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'full_name', 'role_badge', 'created_by', 'is_active', 'created_at']
    list_filter = ['role', 'is_active', 'created_at']
    search_fields = ['username', 'full_name', 'email']
    ordering = ['-created_at']

    fieldsets = BaseUserAdmin.fieldsets + (
        ('Qo\'shimcha', {'fields': ('role', 'full_name', 'created_by')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Qo\'shimcha', {'fields': ('role', 'full_name')}),
    )

    def role_badge(self, obj):
        if obj.role == 'admin':
            return format_html(
                '<span style="background:#dc3545;color:white;padding:3px 10px;border-radius:3px;">Admin</span>')
        return format_html(
            '<span style="background:#007bff;color:white;padding:3px 10px;border-radius:3px;">Revizor</span>')

    role_badge.short_description = 'Rol'


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ['name', 'address', 'created_by', 'revision_count', 'created_at']
    list_filter = ['created_by', 'created_at']
    search_fields = ['name', 'address']
    ordering = ['-created_at']

    def revision_count(self, obj):
        count = obj.revisions.count()
        return format_html('<span style="font-weight:bold;">{}</span> ta reviziya', count)

    revision_count.short_description = 'Reviziyalar'


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'manufacturer', 'created_at']
    list_filter = ['manufacturer', 'created_at']
    search_fields = ['code', 'name', 'manufacturer']
    ordering = ['code']
    list_per_page = 50


class InventoryInline(admin.TabularInline):
    model = Inventory
    extra = 0
    fields = ['product', 'series', 'expiry_date', 'quantity']
    autocomplete_fields = ['product']


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ['warehouse', 'product', 'series', 'expiry_date', 'quantity_display', 'created_at']
    list_filter = ['warehouse', 'created_at']
    search_fields = ['product__name', 'product__code', 'series']
    autocomplete_fields = ['warehouse', 'product']
    ordering = ['-created_at']
    list_per_page = 50

    def quantity_display(self, obj):
        return format_html('<b>{}</b>', obj.quantity)

    quantity_display.short_description = 'Qoldiq'


class RevisionAssignmentInline(admin.TabularInline):
    model = RevisionAssignment
    extra = 0
    fields = ['revizor', 'status', 'assigned_at', 'completed_at']
    readonly_fields = ['assigned_at', 'completed_at']
    autocomplete_fields = ['revizor']


class RevisionItemInline(admin.TabularInline):
    model = RevisionItem
    extra = 0
    fields = ['revizor', 'product', 'series', 'expiry_date', 'quantity']
    readonly_fields = ['revizor', 'created_at']
    autocomplete_fields = ['product']


@admin.register(Revision)
class RevisionAdmin(admin.ModelAdmin):
    list_display = ['revision_info', 'warehouse', 'status_badge', 'revizor_count', 'items_count', 'created_by',
                    'created_at']
    list_filter = ['status', 'warehouse', 'created_at']
    search_fields = ['warehouse__name', 'revision_number']
    ordering = ['-created_at']
    inlines = [RevisionAssignmentInline, RevisionItemInline]
    actions = ['start_revision', 'complete_revision', 'calculate_results']

    def revision_info(self, obj):
        return format_html('<b>Reviziya №{}</b>', obj.revision_number)

    revision_info.short_description = 'Reviziya'

    def status_badge(self, obj):
        colors = {
            'pending': '#ffc107',
            'in_progress': '#17a2b8',
            'completed': '#28a745',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background:{};color:white;padding:3px 10px;border-radius:3px;">{}</span>',
            color, obj.get_status_display()
        )

    status_badge.short_description = 'Status'

    def revizor_count(self, obj):
        count = obj.assignments.count()
        return f"{count} ta"

    revizor_count.short_description = 'Revizorlar'

    def items_count(self, obj):
        count = obj.items.count()
        return f"{count} ta"

    items_count.short_description = 'Kiritilgan'

    @admin.action(description="Reviziyani boshlash")
    def start_revision(self, request, queryset):
        updated = queryset.filter(status='pending').update(
            status='in_progress',
            started_at=timezone.now()
        )
        self.message_user(request, f"{updated} ta reviziya boshlandi.")

    @admin.action(description="Reviziyani tugatish")
    def complete_revision(self, request, queryset):
        updated = queryset.filter(status='in_progress').update(
            status='completed',
            completed_at=timezone.now()
        )
        self.message_user(request, f"{updated} ta reviziya tugallandi.")

    @admin.action(description="Natijalarni hisoblash")
    def calculate_results(self, request, queryset):
        for revision in queryset:
            self.calculate_revision_results(revision)
        self.message_user(request, f"{queryset.count()} ta reviziya natijalari hisoblandi.")

    def calculate_revision_results(self, revision):
        """Reviziya natijalarini hisoblash"""
        from django.db.models import Sum

        # Avvalgi natijalarni tozalash
        RevisionResult.objects.filter(revision=revision).delete()
        UnaccountedItem.objects.filter(revision=revision).delete()

        # 1C dagi tovarlar (kutilgan)
        inventory_items = Inventory.objects.filter(warehouse=revision.warehouse)

        # Revizorlar kiritgan tovarlar
        revision_items = RevisionItem.objects.filter(revision=revision)

        # Har bir 1C tovar uchun natija
        for inv in inventory_items:
            # Revizorlar shu tovarni qancha sanadi
            actual = revision_items.filter(
                product=inv.product,
                series=inv.series,
                expiry_date=inv.expiry_date
            ).aggregate(total=Sum('quantity'))['total'] or 0

            result, created = RevisionResult.objects.get_or_create(
                revision=revision,
                product=inv.product,
                series=inv.series,
                expiry_date=inv.expiry_date,
                defaults={
                    'expected_quantity': inv.quantity,
                    'actual_quantity': actual,
                }
            )
            if not created:
                result.expected_quantity = inv.quantity
                result.actual_quantity = actual

            result.calculate()

            # Revizorlarni qo'shish
            revizors = revision_items.filter(
                product=inv.product,
                series=inv.series,
                expiry_date=inv.expiry_date
            ).values_list('revizor', flat=True).distinct()
            result.revizors.set(revizors)

        # Hisobda yo'q tovarlar (1C da yo'q, revizor kiritgan)
        for item in revision_items:
            exists_in_inventory = inventory_items.filter(
                product=item.product,
                series=item.series,
                expiry_date=item.expiry_date
            ).exists()

            if not exists_in_inventory:
                UnaccountedItem.objects.get_or_create(
                    revision=revision,
                    product=item.product,
                    series=item.series,
                    expiry_date=item.expiry_date,
                    defaults={
                        'quantity': item.quantity,
                        'revizor': item.revizor,
                    }
                )


@admin.register(RevisionAssignment)
class RevisionAssignmentAdmin(admin.ModelAdmin):
    list_display = ['revizor', 'revision', 'status_badge', 'assigned_at', 'completed_at']
    list_filter = ['status', 'revision__warehouse', 'assigned_at']
    search_fields = ['revizor__full_name', 'revizor__username']
    autocomplete_fields = ['revision', 'revizor']

    def status_badge(self, obj):
        colors = {
            'assigned': '#ffc107',
            'working': '#17a2b8',
            'completed': '#28a745',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background:{};color:white;padding:3px 10px;border-radius:3px;">{}</span>',
            color, obj.get_status_display()
        )

    status_badge.short_description = 'Status'


@admin.register(RevisionItem)
class RevisionItemAdmin(admin.ModelAdmin):
    list_display = ['product', 'series', 'expiry_date', 'quantity', 'revizor', 'revision', 'created_at']
    list_filter = ['revision', 'revizor', 'created_at']
    search_fields = ['product__name', 'product__code', 'series']
    autocomplete_fields = ['revision', 'revizor', 'product']
    ordering = ['-created_at']
    list_per_page = 50


@admin.register(RevisionResult)
class RevisionResultAdmin(admin.ModelAdmin):
    list_display = ['product', 'series', 'expiry_date', 'expected_quantity', 'actual_quantity', 'difference_display',
                    'status_badge']
    list_filter = ['status', 'revision', 'revision__warehouse']
    search_fields = ['product__name', 'product__code', 'series']
    ordering = ['status', '-difference']
    list_per_page = 50

    def difference_display(self, obj):
        if obj.difference > 0:
            return format_html('<span style="color:#28a745;font-weight:bold;">+{}</span>', obj.difference)
        elif obj.difference < 0:
            return format_html('<span style="color:#dc3545;font-weight:bold;">{}</span>', obj.difference)
        return format_html('<span style="color:#6c757d;">0</span>')

    difference_display.short_description = 'Farq'

    def status_badge(self, obj):
        colors = {
            'correct': '#28a745',
            'shortage': '#dc3545',
            'excess': '#ffc107',
        }
        labels = {
            'correct': 'To\'g\'ri',
            'shortage': 'Kam',
            'excess': 'Ko\'p',
        }
        color = colors.get(obj.status, '#6c757d')
        label = labels.get(obj.status, obj.status)
        return format_html(
            '<span style="background:{};color:white;padding:3px 10px;border-radius:3px;">{}</span>',
            color, label
        )

    status_badge.short_description = 'Natija'


@admin.register(UnaccountedItem)
class UnaccountedItemAdmin(admin.ModelAdmin):
    list_display = ['product', 'series', 'expiry_date', 'quantity', 'revizor', 'revision', 'created_at']
    list_filter = ['revision', 'revizor', 'created_at']
    search_fields = ['product__name', 'product__code', 'series']
    ordering = ['-created_at']
    list_per_page = 50


# Admin site sozlamalari
admin.site.site_header = "Sklad Reviziya Tizimi"
admin.site.site_title = "Reviziya Admin"
admin.site.index_title = "Boshqaruv paneli"