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



# ============ TRANSLITERATSIYA ============
LATIN_TO_CYRILLIC = {
    'a': 'а', 'b': 'б', 'v': 'в', 'g': 'г', 'd': 'д',
    'e': 'е', 'yo': 'ё', 'zh': 'ж', 'z': 'з', 'i': 'и',
    'y': 'й', 'k': 'к', 'l': 'л', 'm': 'м', 'n': 'н',
    'o': 'о', 'p': 'п', 'r': 'р', 's': 'с', 't': 'т',
    'u': 'у', 'f': 'ф', 'h': 'х', 'kh': 'х', 'ts': 'ц',
    'ch': 'ч', 'sh': 'ш', 'sch': 'щ', 'shch': 'щ',
    'j': 'дж', 'x': 'кс', 'w': 'в', 'q': 'к', 'c': 'ц',
}

def transliterate_to_cyrillic(text):
    text = text.lower()
    result = ''
    i = 0
    while i < len(text):
        if i + 4 <= len(text) and text[i:i+4] in LATIN_TO_CYRILLIC:
            result += LATIN_TO_CYRILLIC[text[i:i+4]]
            i += 4
        elif i + 3 <= len(text) and text[i:i+3] in LATIN_TO_CYRILLIC:
            result += LATIN_TO_CYRILLIC[text[i:i+3]]
            i += 3
        elif i + 2 <= len(text) and text[i:i+2] in LATIN_TO_CYRILLIC:
            result += LATIN_TO_CYRILLIC[text[i:i+2]]
            i += 2
        elif text[i] in LATIN_TO_CYRILLIC:
            result += LATIN_TO_CYRILLIC[text[i]]
            i += 1
        else:
            result += text[i]
            i += 1
    return result

def is_latin(text):
    return any(c in 'abcdefghijklmnopqrstuvwxyz' for c in text.lower())

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
# ============================================
# YANGILANGAN admin_inventory_upload
# views.py dagi eskisini shu bilan almashtiring
# ============================================
# ============================================
# OPTIMALLASHTIRILGAN admin_inventory_upload
# views.py dagi eskisini shu bilan almashtiring
# ============================================
# ============================================
# TO'LIQ OPTIMALLASHTIRILGAN admin_inventory_upload
# BARCHA 1C FORMATLARINI QO'LLAB-QUVVATLAYDI
# views.py dagi eskisini shu bilan almashtiring
# ============================================

@login_required
def admin_inventory_upload(request, warehouse_pk):
    """
    1C dan tovar qoldig'i yuklash - UNIVERSAL

    Qo'llab-quvvatlanadigan formatlar:
    1. Vergul (,) delimiter
    2. Nuqtali vergul (;) delimiter
    3. Sarlavhali va sarlavhasiz
    4. UTF-8, UTF-8-BOM, Windows-1251
    """
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
            # Faylni o'qish
            content = file.read()

            # Encoding aniqlash
            decoded = None
            for encoding in ['utf-8-sig', 'utf-8', 'cp1251', 'latin-1']:
                try:
                    decoded = content.decode(encoding)
                    break
                except:
                    continue

            if not decoded:
                messages.error(request, 'Fayl encodingini aniqlab bo\'lmadi!')
                return redirect('admin_warehouse_detail', pk=warehouse_pk)

            lines = decoded.splitlines()

            if not lines:
                messages.error(request, 'Fayl bo\'sh!')
                return redirect('admin_warehouse_detail', pk=warehouse_pk)

            # Eskisini tozalash
            if clear_old:
                Inventory.objects.filter(warehouse=warehouse).delete()

            # ========== DELIMITER ANIQLASH ==========
            first_line = lines[0]
            delimiter = ';' if ';' in first_line else ','

            # ========== PRODUCTS CACHE ==========
            products_cache = {}
            for p in Product.objects.all().values('id', 'name'):
                name_clean = p['name'].lower().strip()
                products_cache[name_clean] = p['id']

            if not products_cache:
                messages.error(request, 'Nomenklatura bo\'sh! Avval nomenklatura yuklang.')
                return redirect('admin_warehouse_detail', pk=warehouse_pk)

            # ========== MA'LUMOTLARNI YIGISH ==========
            inventory_to_create = []
            count = 0
            skipped = 0
            errors_list = []

            for line_num, line in enumerate(lines, 1):
                line = line.strip()

                # Bo'sh qatorni o'tkazish
                if not line:
                    continue

                # "Итого" qatoriga yetganda to'xtatish
                if 'Итого' in line or 'Мат.отв' in line or 'итого' in line:
                    break

                # Sarlavha qatorlarini o'tkazish
                if any(word in line for word in
                       ['Наименование', 'наименование', 'Остатки по товар', 'Остаток на', ';;К.;', ',,К.,']):
                    continue

                # CSV qatorini parse qilish
                parts = []
                current = ''
                in_quotes = False

                for char in line:
                    if char == '"':
                        in_quotes = not in_quotes
                    elif char == delimiter and not in_quotes:
                        parts.append(current.strip().strip('"'))
                        current = ''
                    else:
                        current += char
                parts.append(current.strip().strip('"'))

                # Ustunlarni olish
                # Format: Куп;Наименование;Производитель;Срок годность;Остаток;Кам
                # Index:   0       1            2             3           4      5

                if len(parts) < 5:
                    continue

                name = parts[1].strip() if len(parts) > 1 else ''
                expiry_str = parts[3].strip() if len(parts) > 3 else ''
                quantity_str = parts[4].strip() if len(parts) > 4 else '0'

                # Bo'sh yoki noto'g'ri nomni o'tkazish
                if not name or name == 'К.' or name == 'K.' or len(name) < 2:
                    continue

                # Tovarni CACHE dan topish
                name_lower = name.lower().strip()
                product_id = products_cache.get(name_lower)

                # Agar topilmasa, qisman qidirish
                if not product_id:
                    for cached_name, cached_id in products_cache.items():
                        if name_lower == cached_name:
                            product_id = cached_id
                            break
                        # Qisman moslik (80% mos bo'lsa)
                        if len(name_lower) > 10:
                            if name_lower[:15] == cached_name[:15]:
                                product_id = cached_id
                                break

                if not product_id:
                    if len(errors_list) < 15:
                        errors_list.append(name[:35])
                    skipped += 1
                    continue

                # Sanani parse qilish
                expiry_date = None
                if expiry_str:
                    for fmt in ['%d.%m.%Y', '%Y-%m-%d', '%d/%m/%Y', '%d.%m.%y']:
                        try:
                            expiry_date = datetime.strptime(expiry_str, fmt).date()
                            break
                        except:
                            continue

                # Miqdorni parse qilish
                try:
                    qty_clean = quantity_str.replace(' ', '').replace(',', '.').replace('\xa0', '')
                    qty = Decimal(qty_clean) if qty_clean else Decimal('0')
                except:
                    qty = Decimal('0')

                if qty <= 0:
                    continue

                # Inventory obyektini yaratish
                inventory_to_create.append(Inventory(
                    warehouse=warehouse,
                    product_id=product_id,
                    series='',
                    expiry_date=expiry_date,
                    quantity=qty
                ))
                count += 1

                # Har 500 tadan BULK INSERT
                if len(inventory_to_create) >= 500:
                    Inventory.objects.bulk_create(
                        inventory_to_create,
                        ignore_conflicts=True
                    )
                    inventory_to_create = []

            # Qolganlarini saqlash
            if inventory_to_create:
                Inventory.objects.bulk_create(
                    inventory_to_create,
                    ignore_conflicts=True
                )

            # ========== NATIJA XABARI ==========
            if count > 0:
                messages.success(request, f'✅ {count} ta qoldiq muvaffaqiyatli yuklandi!')
            else:
                messages.warning(request,
                                 '⚠️ Hech qanday qoldiq yuklanmadi. Tovar nomlari nomenklatura bilan mos kelmagan bo\'lishi mumkin.')

            if skipped > 0:
                messages.warning(request, f'⚠️ {skipped} ta tovar nomenklaturada topilmadi.')

            if errors_list:
                messages.info(request,
                              f'Topilmagan tovarlar: {", ".join(errors_list[:5])}{"..." if len(errors_list) > 5 else ""}')

        except Exception as e:
            messages.error(request, f'Xatolik: {str(e)}')

        return redirect('admin_warehouse_detail', pk=warehouse_pk)

    return render(request, 'sklad/admin/inventory_upload.html', {'warehouse': warehouse})

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
    query = request.GET.get('q', '').strip()

    if len(query) < 1:
        return JsonResponse({'products': []})

    search_queries = [query]
    if is_latin(query):
        search_queries.append(transliterate_to_cyrillic(query))

    q_filter = Q()
    for q in search_queries:
        q_filter |= Q(name__icontains=q)
        q_filter |= Q(code__icontains=q)

    products = Product.objects.filter(q_filter).order_by('name')[:30]

    result = [{
        'id': p.id,
        'code': p.code,
        'name': p.name,
        'manufacturer': p.manufacturer or '',
    } for p in products]

    return JsonResponse({'products': result})


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
# ============================================
# YANGILANGAN calculate_revision_results
# views.py dagi eskisini shu bilan almashtiring
# ============================================

def calculate_revision_results(revision):
    """
    Reviziya natijalarini hisoblash - TZ bo'yicha

    MUHIM: Revizor partiyalarni ajratmaydi!
    - 1C da bir tovar bir nechta partiyada bo'lishi mumkin
    - Revizor umumiy sonni kiritadi
    - Tizim TOVAR BO'YICHA JAMI solishtiriladi
    - Farq birinchi partiyaga yoziladi
    """

    # Avvalgi natijalarni tozalash
    RevisionResult.objects.filter(revision=revision).delete()
    UnaccountedItem.objects.filter(revision=revision).delete()

    warehouse = revision.warehouse

    # 1. 1C dagi tovarlar - TOVAR BO'YICHA GURUHLAB
    inventory_by_product = {}
    inventory_items = Inventory.objects.filter(warehouse=warehouse).select_related('product')

    for inv in inventory_items:
        product_id = inv.product_id
        if product_id not in inventory_by_product:
            inventory_by_product[product_id] = {
                'product': inv.product,
                'total_qty': Decimal('0'),
                'items': []  # Har bir partiya
            }
        inventory_by_product[product_id]['total_qty'] += inv.quantity
        inventory_by_product[product_id]['items'].append({
            'series': inv.series,
            'expiry_date': inv.expiry_date,
            'quantity': inv.quantity
        })

    # 2. Revizorlar kiritgan tovarlar - TOVAR BO'YICHA JAMI
    revision_items = RevisionItem.objects.filter(revision=revision).select_related('product', 'revizor')

    revizor_by_product = {}
    revizor_names_by_product = {}

    for item in revision_items:
        product_id = item.product_id
        if product_id not in revizor_by_product:
            revizor_by_product[product_id] = Decimal('0')
            revizor_names_by_product[product_id] = set()
        revizor_by_product[product_id] += item.quantity
        revizor_names_by_product[product_id].add(item.revizor)

    # 3. Har bir 1C tovar uchun natija yaratish
    for product_id, inv_data in inventory_by_product.items():
        product = inv_data['product']
        expected_total = inv_data['total_qty']  # 1C jami
        actual_total = revizor_by_product.get(product_id, Decimal('0'))  # Revizor jami

        difference = actual_total - expected_total

        # Status aniqlash
        if difference == 0:
            status = 'correct'
        elif difference < 0:
            status = 'shortage'
        else:
            status = 'excess'

        # Har bir partiya uchun natija yozish
        # Farq BIRINCHI partiyaga yoziladi (TZ bo'yicha)
        items = inv_data['items']

        for i, item in enumerate(items):
            if i == 0:
                # Birinchi partiyaga farq yoziladi
                item_difference = difference
                item_status = status
            else:
                # Boshqa partiyalar "to'g'ri" bo'ladi
                item_difference = Decimal('0')
                item_status = 'correct'

            result = RevisionResult.objects.create(
                revision=revision,
                product=product,
                series=item['series'],
                expiry_date=item['expiry_date'],
                expected_quantity=item['quantity'],
                actual_quantity=item['quantity'] + item_difference if i == 0 else item['quantity'],
                difference=item_difference,
                status=item_status
            )

            # Revizorlarni qo'shish
            if product_id in revizor_names_by_product:
                result.revizors.set(revizor_names_by_product[product_id])

    # 4. Hisobda yo'q tovarlar (1C da yo'q, lekin revizor kiritgan)
    for product_id, actual_qty in revizor_by_product.items():
        if product_id not in inventory_by_product:
            # 1C da yo'q tovar
            product = Product.objects.get(pk=product_id)

            # Revizor ma'lumotlarini olish
            items = RevisionItem.objects.filter(
                revision=revision,
                product_id=product_id
            )

            for item in items:
                UnaccountedItem.objects.create(
                    revision=revision,
                    product=product,
                    series=item.series,
                    expiry_date=item.expiry_date,
                    quantity=item.quantity,
                    revizor=item.revizor
                )