from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Sum, Q
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
import csv
import json
from datetime import datetime
from decimal import Decimal
from .models import (
    User, Warehouse, Product, Inventory,
    Revision, RevisionAssignment, RevisionItem,
    RevisionResult, UnaccountedItem
)


# ==================== AUTH ====================

def login_view(request):
    """Login sahifasi - Admin va Revizor uchun"""
    if request.user.is_authenticated:
        if request.user.is_admin:
            return redirect('admin_dashboard')
        return redirect('revizor_dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)
            messages.success(request, f'Xush kelibsiz, {user.full_name or user.username}!')
            if user.is_admin:
                return redirect('admin_dashboard')
            return redirect('revizor_dashboard')
        else:
            messages.error(request, 'Login yoki parol xato!')

    return render(request, 'sklad/login.html')


@login_required
def logout_view(request):
    """Chiqish"""
    logout(request)
    messages.info(request, 'Tizimdan chiqdingiz.')
    return redirect('login')


# ==================== ADMIN VIEWS ====================

@login_required
def admin_dashboard(request):
    """Admin bosh sahifa - omborlar ro'yxati"""
    if not request.user.is_admin:
        return redirect('revizor_dashboard')

    warehouses = Warehouse.objects.filter(created_by=request.user).order_by('-created_at')
    revizors = User.objects.filter(role='revizor', created_by=request.user)

    context = {
        'warehouses': warehouses,
        'revizors': revizors,
        'total_warehouses': warehouses.count(),
        'total_revizors': revizors.count(),
    }
    return render(request, 'sklad/admin/dashboard.html', context)


@login_required
def admin_warehouse_create(request):
    """Yangi ombor yaratish"""
    if not request.user.is_admin:
        return redirect('revizor_dashboard')

    if request.method == 'POST':
        name = request.POST.get('name')
        address = request.POST.get('address', '')

        if name:
            warehouse = Warehouse.objects.create(
                name=name,
                address=address,
                created_by=request.user
            )
            messages.success(request, f'"{name}" ombori yaratildi!')
            return redirect('admin_warehouse_detail', pk=warehouse.pk)
        else:
            messages.error(request, 'Ombor nomini kiriting!')

    return render(request, 'sklad/admin/warehouse_form.html')


@login_required
def admin_warehouse_detail(request, pk):
    """Ombor tafsilotlari va reviziyalar"""
    if not request.user.is_admin:
        return redirect('revizor_dashboard')

    warehouse = get_object_or_404(Warehouse, pk=pk, created_by=request.user)
    revisions = warehouse.revisions.all().order_by('-created_at')
    inventory_count = warehouse.inventory.count()

    context = {
        'warehouse': warehouse,
        'revisions': revisions,
        'inventory_count': inventory_count,
    }
    return render(request, 'sklad/admin/warehouse_detail.html', context)


@login_required
def admin_warehouse_edit(request, pk):
    """Ombor tahrirlash"""
    if not request.user.is_admin:
        return redirect('revizor_dashboard')

    warehouse = get_object_or_404(Warehouse, pk=pk, created_by=request.user)

    if request.method == 'POST':
        name = request.POST.get('name')
        address = request.POST.get('address', '')

        if name:
            warehouse.name = name
            warehouse.address = address
            warehouse.save()
            messages.success(request, 'Ombor yangilandi!')
            return redirect('admin_warehouse_detail', pk=pk)

    return render(request, 'sklad/admin/warehouse_form.html', {'warehouse': warehouse})


@login_required
def admin_warehouse_delete(request, pk):
    """Ombor o'chirish"""
    if not request.user.is_admin:
        return redirect('revizor_dashboard')

    warehouse = get_object_or_404(Warehouse, pk=pk, created_by=request.user)

    if request.method == 'POST':
        name = warehouse.name
        warehouse.delete()
        messages.success(request, f'"{name}" ombori o\'chirildi!')
        return redirect('admin_dashboard')

    return render(request, 'sklad/admin/warehouse_confirm_delete.html', {'warehouse': warehouse})


# ==================== NOMENKLATURA ====================

@login_required
def admin_products(request):
    """Nomenklatura ro'yxati"""
    if not request.user.is_admin:
        return redirect('revizor_dashboard')

    products = Product.objects.all().order_by('code')
    paginator = Paginator(products, 50)
    page = request.GET.get('page')
    products = paginator.get_page(page)

    return render(request, 'sklad/admin/products.html', {'products': products})


@login_required
def admin_products_upload(request):
    """Nomenklatura yuklash (CSV)"""
    if not request.user.is_admin:
        return redirect('revizor_dashboard')

    if request.method == 'POST':
        file = request.FILES.get('file')
        if not file:
            messages.error(request, 'Fayl tanlanmadi!')
            return redirect('admin_products')

        try:
            # Faylni o'qish
            content = file.read()

            # Encoding aniqlash
            try:
                decoded = content.decode('utf-8-sig')
            except:
                try:
                    decoded = content.decode('cp1251')  # Windows Cyrillic
                except:
                    decoded = content.decode('latin-1')

            lines = decoded.splitlines()

            if file.name.endswith('.csv'):
                # Delimiter aniqlash (vergul yoki nuqtali vergul)
                first_line = lines[0] if lines else ''
                delimiter = ';' if ';' in first_line else ','

                reader = csv.DictReader(lines, delimiter=delimiter)
                count = 0
                errors = []

                for i, row in enumerate(reader, start=2):
                    # Turli nom variantlari
                    code = (
                        row.get('code') or
                        row.get('kod') or
                        row.get('Code') or
                        row.get('CODE') or
                        row.get('№') or
                        row.get('нумерация') or
                        row.get('Нумерация') or
                        row.get('\ufeffcode') or  # BOM bilan
                        row.get('\ufeff№') or
                        list(row.values())[0] if row else None  # Birinchi ustun
                    )

                    name = (
                        row.get('name') or
                        row.get('nom') or
                        row.get('Name') or
                        row.get('NAME') or
                        row.get('товар номи') or
                        row.get('Товар номи') or
                        row.get('наименование') or
                        row.get('Наименование') or
                        row.get('tovar') or
                        list(row.values())[1] if len(row) > 1 else None  # Ikkinchi ustun
                    )

                    manufacturer = (
                        row.get('manufacturer') or
                        row.get('ishlab_chiqaruvchi') or
                        row.get('Manufacturer') or
                        row.get('ишлаб чикарувчи') or
                        row.get('Ишлаб чикарувчи') or
                        row.get('производитель') or
                        row.get('Производитель') or
                        list(row.values())[2] if len(row) > 2 else ''  # Uchinchi ustun
                    )

                    if code and name:
                        code_clean = str(code).strip()
                        name_clean = str(name).strip()
                        manufacturer_clean = str(manufacturer).strip() if manufacturer else ''

                        if code_clean and name_clean:
                            Product.objects.update_or_create(
                                code=code_clean,
                                defaults={
                                    'name': name_clean,
                                    'manufacturer': manufacturer_clean
                                }
                            )
                            count += 1
                    else:
                        if i <= 5:  # Faqat birinchi 5 ta xatoni ko'rsat
                            errors.append(f"Qator {i}: code={code}, name={name}")

                if count > 0:
                    messages.success(request, f'{count} ta tovar yuklandi!')
                else:
                    messages.error(request, 'Hech qanday tovar yuklanmadi. CSV formatini tekshiring.')

                if errors:
                    messages.warning(request, f'Xatolar: {"; ".join(errors)}')

            elif file.name.endswith('.json'):
                data = json.loads(decoded)
                count = 0

                for item in data:
                    code = item.get('code') or item.get('kod')
                    name = item.get('name') or item.get('nom')
                    manufacturer = item.get('manufacturer') or item.get('ishlab_chiqaruvchi') or ''

                    if code and name:
                        Product.objects.update_or_create(
                            code=str(code).strip(),
                            defaults={
                                'name': str(name).strip(),
                                'manufacturer': str(manufacturer).strip()
                            }
                        )
                        count += 1

                messages.success(request, f'{count} ta tovar yuklandi!')
            else:
                messages.error(request, 'Faqat CSV yoki JSON fayl yuklang!')

        except Exception as e:
            messages.error(request, f'Xatolik: {str(e)}')

        return redirect('admin_products')

    return render(request, 'sklad/admin/products_upload.html')

# ==================== INVENTORY (1C QOLDIQ) ====================

@login_required
def admin_inventory_upload(request, warehouse_pk):
    """1C dan tovar qoldig'i yuklash"""
    if not request.user.is_admin:
        return redirect('revizor_dashboard')

    warehouse = get_object_or_404(Warehouse, pk=warehouse_pk, created_by=request.user)

    if request.method == 'POST':
        file = request.FILES.get('file')
        clear_old = request.POST.get('clear_old') == 'on'

        if not file:
            messages.error(request, 'Fayl tanlanmadi!')
            return redirect('admin_warehouse_detail', pk=warehouse_pk)

        try:
            # Eskisini tozalash
            if clear_old:
                Inventory.objects.filter(warehouse=warehouse).delete()

            decoded = file.read().decode('utf-8-sig').splitlines()
            reader = csv.DictReader(decoded, delimiter=';')
            count = 0
            errors = []

            for row in reader:
                code = row.get('code') or row.get('kod') or row.get('нумерация') or row.get('№')
                series = row.get('series') or row.get('seriya') or row.get('серия') or ''
                expiry = row.get('expiry_date') or row.get('srok') or row.get('срок') or ''
                quantity = row.get('quantity') or row.get('ostatok') or row.get('остатка') or row.get('qoldiq') or '0'

                if not code:
                    continue

                # Tovarni topish
                product = Product.objects.filter(code=str(code).strip()).first()
                if not product:
                    errors.append(f"Tovar topilmadi: {code}")
                    continue

                # Sanani parse qilish
                expiry_date = None
                if expiry:
                    for fmt in ['%d.%m.%Y', '%Y-%m-%d', '%d/%m/%Y']:
                        try:
                            expiry_date = datetime.strptime(str(expiry).strip(), fmt).date()
                            break
                        except:
                            continue

                # Miqdorni parse qilish
                try:
                    qty = Decimal(str(quantity).replace(',', '.').strip())
                except:
                    qty = Decimal('0')

                Inventory.objects.update_or_create(
                    warehouse=warehouse,
                    product=product,
                    series=str(series).strip(),
                    expiry_date=expiry_date,
                    defaults={'quantity': qty}
                )
                count += 1

            messages.success(request, f'{count} ta qoldiq yuklandi!')
            if errors:
                messages.warning(request, f'Xatolar: {", ".join(errors[:5])}...')

        except Exception as e:
            messages.error(request, f'Xatolik: {str(e)}')

        return redirect('admin_warehouse_detail', pk=warehouse_pk)

    return render(request, 'sklad/admin/inventory_upload.html', {'warehouse': warehouse})


# ==================== REVIZOR MANAGEMENT ====================

@login_required
def admin_revizors(request):
    """Revizorlar ro'yxati"""
    if not request.user.is_admin:
        return redirect('revizor_dashboard')

    revizors = User.objects.filter(role='revizor', created_by=request.user)
    return render(request, 'sklad/admin/revizors.html', {'revizors': revizors})


@login_required
def admin_revizor_create(request):
    """Yangi revizor yaratish"""
    if not request.user.is_admin:
        return redirect('revizor_dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        full_name = request.POST.get('full_name')

        if not username or not password:
            messages.error(request, 'Login va parolni kiriting!')
            return render(request, 'sklad/admin/revizor_form.html')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Bu login band!')
            return render(request, 'sklad/admin/revizor_form.html')

        user = User.objects.create_user(
            username=username,
            password=password,
            full_name=full_name or username,
            role='revizor',
            created_by=request.user
        )
        messages.success(request, f'Revizor "{full_name}" yaratildi! Login: {username}')
        return redirect('admin_revizors')

    return render(request, 'sklad/admin/revizor_form.html')


@login_required
def admin_revizor_delete(request, pk):
    """Revizor o'chirish"""
    if not request.user.is_admin:
        return redirect('revizor_dashboard')

    revizor = get_object_or_404(User, pk=pk, role='revizor', created_by=request.user)

    if request.method == 'POST':
        name = revizor.full_name
        revizor.delete()
        messages.success(request, f'Revizor "{name}" o\'chirildi!')
        return redirect('admin_revizors')

    return render(request, 'sklad/admin/revizor_confirm_delete.html', {'revizor': revizor})


# ==================== REVISION MANAGEMENT ====================

@login_required
def admin_revision_create(request, warehouse_pk):
    """Yangi reviziya yaratish"""
    if not request.user.is_admin:
        return redirect('revizor_dashboard')

    warehouse = get_object_or_404(Warehouse, pk=warehouse_pk, created_by=request.user)
    revizors = User.objects.filter(role='revizor', created_by=request.user)

    if request.method == 'POST':
        selected_revizors = request.POST.getlist('revizors')

        if not selected_revizors:
            messages.error(request, 'Kamida bitta revizor tanlang!')
            return render(request, 'sklad/admin/revision_form.html', {
                'warehouse': warehouse,
                'revizors': revizors
            })

        # Reviziya yaratish
        revision = Revision.objects.create(
            warehouse=warehouse,
            created_by=request.user,
            status='pending'
        )

        # Revizorlarni tayinlash
        for revizor_id in selected_revizors:
            RevisionAssignment.objects.create(
                revision=revision,
                revizor_id=revizor_id
            )

        messages.success(request, f'Reviziya №{revision.revision_number} yaratildi!')
        return redirect('admin_revision_detail', pk=revision.pk)

    return render(request, 'sklad/admin/revision_form.html', {
        'warehouse': warehouse,
        'revizors': revizors
    })


@login_required
def admin_revision_detail(request, pk):
    """Reviziya tafsilotlari"""
    if not request.user.is_admin:
        return redirect('revizor_dashboard')

    revision = get_object_or_404(Revision, pk=pk, created_by=request.user)
    assignments = revision.assignments.select_related('revizor')
    items = revision.items.select_related('product', 'revizor').order_by('-created_at')[:50]

    context = {
        'revision': revision,
        'assignments': assignments,
        'items': items,
        'items_count': revision.items.count(),
    }
    return render(request, 'sklad/admin/revision_detail.html', context)


@login_required
def admin_revision_start(request, pk):
    """Reviziyani boshlash"""
    if not request.user.is_admin:
        return redirect('revizor_dashboard')

    revision = get_object_or_404(Revision, pk=pk, created_by=request.user)

    if revision.status == 'pending':
        revision.status = 'in_progress'
        revision.started_at = timezone.now()
        revision.save()

        # Barcha revizorlarni "working" statusiga
        revision.assignments.update(status='working')

        messages.success(request, 'Reviziya boshlandi!')

    return redirect('admin_revision_detail', pk=pk)


@login_required
def admin_revision_complete(request, pk):
    """Reviziyani tugatish"""
    if not request.user.is_admin:
        return redirect('revizor_dashboard')

    revision = get_object_or_404(Revision, pk=pk, created_by=request.user)

    if revision.status == 'in_progress':
        revision.status = 'completed'
        revision.completed_at = timezone.now()
        revision.save()

        # Natijalarni hisoblash
        calculate_revision_results(revision)

        messages.success(request, 'Reviziya tugallandi va natijalar hisoblandi!')

    return redirect('admin_revision_results', pk=pk)


@login_required
def admin_revision_results(request, pk):
    """Reviziya natijalari"""
    if not request.user.is_admin:
        return redirect('revizor_dashboard')

    revision = get_object_or_404(Revision, pk=pk, created_by=request.user)

    # Filter
    status_filter = request.GET.get('status', '')
    search = request.GET.get('search', '')

    results = RevisionResult.objects.filter(revision=revision).select_related('product')

    if status_filter:
        results = results.filter(status=status_filter)

    if search:
        results = results.filter(
            Q(product__name__icontains=search) |
            Q(product__code__icontains=search) |
            Q(series__icontains=search)
        )

    results = results.order_by('status', 'product__name')

    # Statistika
    stats = {
        'total': results.count(),
        'correct': results.filter(status='correct').count(),
        'shortage': results.filter(status='shortage').count(),
        'excess': results.filter(status='excess').count(),
    }

    # Hisobda yo'q tovarlar
    unaccounted = UnaccountedItem.objects.filter(revision=revision).select_related('product', 'revizor')

    context = {
        'revision': revision,
        'results': results,
        'stats': stats,
        'unaccounted': unaccounted,
        'status_filter': status_filter,
        'search': search,
    }
    return render(request, 'sklad/admin/revision_results.html', context)


@login_required
def admin_revision_export(request, pk):
    """Natijalarni CSV ga eksport"""
    if not request.user.is_admin:
        return redirect('revizor_dashboard')

    revision = get_object_or_404(Revision, pk=pk, created_by=request.user)
    results = RevisionResult.objects.filter(revision=revision).select_related('product')

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response[
        'Content-Disposition'] = f'attachment; filename="revision_{revision.revision_number}_{revision.created_at.strftime("%Y%m%d")}.csv"'

    writer = csv.writer(response, delimiter=';')
    writer.writerow(
        ['№', 'Tovar nomi', 'Ishlab chiqaruvchi', 'Seriya', 'Srok', '1C qoldiq', 'Haqiqiy', 'Farq', 'Natija'])

    status_labels = {'correct': 'To\'g\'ri', 'shortage': 'Kam', 'excess': 'Ko\'p'}

    for i, r in enumerate(results, 1):
        writer.writerow([
            i,
            r.product.name,
            r.product.manufacturer,
            r.series,
            r.expiry_date.strftime('%d.%m.%Y') if r.expiry_date else '',
            r.expected_quantity,
            r.actual_quantity,
            r.difference,
            status_labels.get(r.status, r.status)
        ])

    return response


@login_required
def admin_unaccounted_export(request, pk):
    """Hisobda yo'q tovarlarni eksport"""
    if not request.user.is_admin:
        return redirect('revizor_dashboard')

    revision = get_object_or_404(Revision, pk=pk, created_by=request.user)
    items = UnaccountedItem.objects.filter(revision=revision).select_related('product', 'revizor')

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="unaccounted_{revision.revision_number}.csv"'

    writer = csv.writer(response, delimiter=';')
    writer.writerow(['№', 'Tovar nomi', 'Ishlab chiqaruvchi', 'Seriya', 'Srok', 'Soni', 'Revizor'])

    for i, item in enumerate(items, 1):
        writer.writerow([
            i,
            item.product.name,
            item.product.manufacturer,
            item.series,
            item.expiry_date.strftime('%d.%m.%Y') if item.expiry_date else '',
            item.quantity,
            item.revizor.full_name
        ])

    return response


# ==================== REVIZOR VIEWS ====================

@login_required
def revizor_dashboard(request):
    """Revizor bosh sahifa"""
    if request.user.is_admin:
        return redirect('admin_dashboard')

    # Revizorga tayinlangan faol reviziyalar
    assignments = RevisionAssignment.objects.filter(
        revizor=request.user,
        status__in=['assigned', 'working']
    ).select_related('revision', 'revision__warehouse')

    context = {
        'assignments': assignments,
    }
    return render(request, 'sklad/revizor/dashboard.html', context)


@login_required
def revizor_work(request, assignment_pk):
    """Revizor ish paneli - tovar kiritish"""
    if request.user.is_admin:
        return redirect('admin_dashboard')

    assignment = get_object_or_404(
        RevisionAssignment,
        pk=assignment_pk,
        revizor=request.user
    )

    # Reviziya boshlanganmi?
    if assignment.revision.status != 'in_progress':
        messages.warning(request, 'Reviziya hali boshlanmagan yoki tugagan!')
        return redirect('revizor_dashboard')

    # Statusni yangilash
    if assignment.status == 'assigned':
        assignment.status = 'working'
        assignment.save()

    products = Product.objects.all().order_by('name')

    context = {
        'assignment': assignment,
        'revision': assignment.revision,
        'products': products,
    }
    return render(request, 'sklad/revizor/work.html', context)



@login_required
def revizor_search_products(request):
    """Tovar qidirish (AJAX) - yaxshilangan"""
    if request.user.is_admin:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    query = request.GET.get('q', '').strip()

    if len(query) < 1:
        return JsonResponse({'products': []})

    # Qidiruv so'zlarini ajratish
    words = query.lower().split()

    # Boshlang'ich queryset
    products = Product.objects.all()

    # Har bir so'z uchun filter
    for word in words:
        products = products.filter(
            Q(name__icontains=word) |
            Q(code__icontains=word) |
            Q(manufacturer__icontains=word)
        )

    # Relevantlik bo'yicha saralash:
    # 1. Nom boshidan mos kelsa - birinchi
    # 2. Nom ichida mos kelsa - keyin
    # 3. Kod yoki manufacturer - oxirida

    from django.db.models import Case, When, Value, IntegerField

    products = products.annotate(
        relevance=Case(
            # Nom aynan shu so'z bilan boshlansa
            When(name__istartswith=query, then=Value(1)),
            # Nom ichida birinchi so'z bilan boshlansa
            When(name__istartswith=words[0] if words else '', then=Value(2)),
            # Nom ichida mos kelsa
            When(name__icontains=query, then=Value(3)),
            # Kod mos kelsa
            When(code__icontains=query, then=Value(4)),
            # Boshqa
            default=Value(5),
            output_field=IntegerField(),
        )
    ).order_by('relevance', 'name')[:30]

    data = [{
        'id': p.id,
        'code': p.code,
        'name': p.name,
        'manufacturer': p.manufacturer or '',
    } for p in products]

    return JsonResponse({'products': data})


@login_required
@require_POST
def revizor_add_item(request):
    """Tovar qo'shish (AJAX)"""
    if request.user.is_admin:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    try:
        data = json.loads(request.body)

        revision_id = data.get('revision_id')
        product_id = data.get('product_id')
        series = data.get('series', '').strip()
        expiry_date_str = data.get('expiry_date', '')
        quantity = data.get('quantity', 0)

        # Validatsiya
        revision = get_object_or_404(Revision, pk=revision_id, status='in_progress')
        product = get_object_or_404(Product, pk=product_id)

        # Revizor tayinlanganmi?
        assignment = RevisionAssignment.objects.filter(
            revision=revision,
            revizor=request.user
        ).first()

        if not assignment:
            return JsonResponse({'error': 'Siz bu reviziyaga tayinlanmagansiz!'}, status=403)

        # Sanani parse
        expiry_date = None
        if expiry_date_str:
            try:
                expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                # Validatsiya: 2025-2050
                if expiry_date.year < 2025 or expiry_date.year > 2050:
                    return JsonResponse({'error': 'Srok 2025-2050 oralig\'ida bo\'lishi kerak!'}, status=400)
            except:
                return JsonResponse({'error': 'Noto\'g\'ri sana formati!'}, status=400)

        # Miqdor
        try:
            qty = Decimal(str(quantity))
            if qty <= 0:
                return JsonResponse({'error': 'Miqdor 0 dan katta bo\'lishi kerak!'}, status=400)
        except:
            return JsonResponse({'error': 'Noto\'g\'ri miqdor!'}, status=400)

        # Mavjud yozuvni tekshirish (bir xil partiya = qo'shiladi)
        existing = RevisionItem.objects.filter(
            revision=revision,
            revizor=request.user,
            product=product,
            series=series,
            expiry_date=expiry_date
        ).first()

        if existing:
            existing.quantity += qty
            existing.save()
            item = existing
            message = f'{product.name} yangilandi. Jami: {existing.quantity}'
        else:
            item = RevisionItem.objects.create(
                revision=revision,
                revizor=request.user,
                product=product,
                series=series,
                expiry_date=expiry_date,
                quantity=qty
            )
            message = f'{product.name} qo\'shildi!'

        return JsonResponse({
            'success': True,
            'message': message,
            'item': {
                'id': item.id,
                'product_name': item.product.name,
                'manufacturer': item.product.manufacturer,
                'series': item.series,
                'expiry_date': item.expiry_date.strftime('%d.%m.%Y') if item.expiry_date else '',
                'quantity': float(item.quantity),
            }
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def revizor_items(request, revision_pk):
    """Revizor kiritgan tovarlar ro'yxati (Obzor revizii)"""
    if request.user.is_admin:
        return redirect('admin_dashboard')

    revision = get_object_or_404(Revision, pk=revision_pk)

    # Revizor tayinlanganmi?
    assignment = RevisionAssignment.objects.filter(
        revision=revision,
        revizor=request.user
    ).first()

    if not assignment:
        messages.error(request, 'Siz bu reviziyaga tayinlanmagansiz!')
        return redirect('revizor_dashboard')

    items = RevisionItem.objects.filter(
        revision=revision,
        revizor=request.user
    ).select_related('product').order_by('-created_at')

    context = {
        'revision': revision,
        'assignment': assignment,
        'items': items,
        'total_items': items.count(),
        'total_quantity': items.aggregate(total=Sum('quantity'))['total'] or 0,
    }
    return render(request, 'sklad/revizor/items.html', context)


@login_required
@require_POST
def revizor_update_item(request, pk):
    """Tovar sonini yangilash (AJAX)"""
    if request.user.is_admin:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    item = get_object_or_404(RevisionItem, pk=pk, revizor=request.user)

    if item.revision.status != 'in_progress':
        return JsonResponse({'error': 'Reviziya tugagan!'}, status=400)

    try:
        data = json.loads(request.body)
        quantity = Decimal(str(data.get('quantity', 0)))

        if quantity <= 0:
            return JsonResponse({'error': 'Miqdor 0 dan katta bo\'lishi kerak!'}, status=400)

        item.quantity = quantity
        item.save()

        return JsonResponse({'success': True, 'quantity': float(item.quantity)})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def revizor_delete_item(request, pk):
    """Tovarni o'chirish (AJAX)"""
    if request.user.is_admin:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    item = get_object_or_404(RevisionItem, pk=pk, revizor=request.user)

    if item.revision.status != 'in_progress':
        return JsonResponse({'error': 'Reviziya tugagan!'}, status=400)

    item.delete()
    return JsonResponse({'success': True})


@login_required
@require_POST
def revizor_complete(request, assignment_pk):
    """Revizorning ishini tugatish"""
    if request.user.is_admin:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    assignment = get_object_or_404(
        RevisionAssignment,
        pk=assignment_pk,
        revizor=request.user
    )

    if assignment.status == 'completed':
        messages.warning(request, 'Siz allaqachon tugatgansiz!')
        return redirect('revizor_dashboard')

    assignment.status = 'completed'
    assignment.completed_at = timezone.now()
    assignment.save()

    # Barcha revizorlar tugatdimi?
    revision = assignment.revision
    all_completed = not revision.assignments.exclude(status='completed').exists()

    if all_completed:
        revision.status = 'completed'
        revision.completed_at = timezone.now()
        revision.save()
        calculate_revision_results(revision)

    messages.success(request, 'Reviziya tugallandi!')
    return redirect('revizor_dashboard')


@login_required
def revizor_export(request, revision_pk):
    """Revizor o'z ma'lumotlarini eksport"""
    if request.user.is_admin:
        return redirect('admin_dashboard')

    revision = get_object_or_404(Revision, pk=revision_pk)
    items = RevisionItem.objects.filter(
        revision=revision,
        revizor=request.user
    ).select_related('product')

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="my_revision_{revision.revision_number}.csv"'

    writer = csv.writer(response, delimiter=';')
    writer.writerow(['№', 'Tovar nomi', 'Ishlab chiqaruvchi', 'Seriya', 'Srok', 'Soni'])

    for i, item in enumerate(items, 1):
        writer.writerow([
            i,
            item.product.name,
            item.product.manufacturer,
            item.series,
            item.expiry_date.strftime('%d.%m.%Y') if item.expiry_date else '',
            item.quantity
        ])

    return response


# ==================== HELPER FUNCTIONS ====================

def calculate_revision_results(revision):
    """Reviziya natijalarini hisoblash"""

    # Avvalgi natijalarni tozalash
    RevisionResult.objects.filter(revision=revision).delete()
    UnaccountedItem.objects.filter(revision=revision).delete()

    # 1C dagi tovarlar
    inventory_items = Inventory.objects.filter(warehouse=revision.warehouse)

    # Revizorlar kiritgan tovarlar
    revision_items = RevisionItem.objects.filter(revision=revision)

    # Har bir 1C tovar uchun natija
    for inv in inventory_items:
        actual = revision_items.filter(
            product=inv.product,
            series=inv.series,
            expiry_date=inv.expiry_date
        ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

        result = RevisionResult.objects.create(
            revision=revision,
            product=inv.product,
            series=inv.series,
            expiry_date=inv.expiry_date,
            expected_quantity=inv.quantity,
            actual_quantity=actual,
        )
        result.calculate()

        # Revizorlarni qo'shish
        revizor_ids = revision_items.filter(
            product=inv.product,
            series=inv.series,
            expiry_date=inv.expiry_date
        ).values_list('revizor_id', flat=True).distinct()
        result.revizors.set(revizor_ids)

    # Hisobda yo'q tovarlar
    for item in revision_items:
        exists = inventory_items.filter(
            product=item.product,
            series=item.series,
            expiry_date=item.expiry_date
        ).exists()

        if not exists:
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