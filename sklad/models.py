from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import date


class User(AbstractUser):
    """Foydalanuvchi modeli - Admin va Revizor"""

    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('revizor', 'Revizor'),
    ]

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='revizor', verbose_name='Rol')
    full_name = models.CharField(max_length=255, blank=True, verbose_name='To\'liq ism')
    created_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_users',
        verbose_name='Kim yaratdi'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Foydalanuvchi'
        verbose_name_plural = 'Foydalanuvchilar'

    def __str__(self):
        return f"{self.full_name or self.username} ({self.get_role_display()})"

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_revizor(self):
        return self.role == 'revizor'


class Warehouse(models.Model):
    """Ombor (Sklad) modeli"""

    name = models.CharField(max_length=255, verbose_name='Ombor nomi')
    address = models.TextField(blank=True, verbose_name='Manzil')
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='warehouses',
        verbose_name='Yaratuvchi'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Ombor'
        verbose_name_plural = 'Omborlar'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class Product(models.Model):
    """Nomenklatura - Tovarlar ro'yxati (barcha omborlar uchun umumiy)"""

    code = models.CharField(max_length=50, unique=True, verbose_name='Kod/Nomer')
    name = models.CharField(max_length=500, verbose_name='Tovar nomi')
    manufacturer = models.CharField(max_length=255, blank=True, verbose_name='Ishlab chiqaruvchi')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Tovar'
        verbose_name_plural = 'Tovarlar (Nomenklatura)'
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class Inventory(models.Model):
    """1C dan yuklangan tovar qoldig'i"""

    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='inventory',
        verbose_name='Ombor'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='inventory',
        verbose_name='Tovar'
    )
    series = models.CharField(max_length=100, blank=True, verbose_name='Seriya')
    expiry_date = models.DateField(null=True, blank=True, verbose_name='Yaroqlilik muddati')
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Qoldiq (1C bo\'yicha)'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Tovar qoldig\'i'
        verbose_name_plural = 'Tovar qoldiqlari (1C)'
        unique_together = ['warehouse', 'product', 'series', 'expiry_date']

    def __str__(self):
        return f"{self.product.name} | Seriya: {self.series} | Qoldiq: {self.quantity}"


class Revision(models.Model):
    """Reviziya"""

    STATUS_CHOICES = [
        ('pending', 'Kutilmoqda'),
        ('in_progress', 'Jarayonda'),
        ('completed', 'Tugallangan'),
    ]

    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='revisions',
        verbose_name='Ombor'
    )
    revision_number = models.PositiveIntegerField(verbose_name='Reviziya raqami')
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Status'
    )
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='Boshlangan vaqt')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Tugagan vaqt')
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='created_revisions',
        verbose_name='Yaratuvchi'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Reviziya'
        verbose_name_plural = 'Reviziyalar'
        ordering = ['-created_at']
        unique_together = ['warehouse', 'revision_number']

    def __str__(self):
        return f"Reviziya №{self.revision_number} | {self.warehouse.name} | {self.created_at.strftime('%d.%m.%Y')}"

    def save(self, *args, **kwargs):
        if not self.revision_number:
            last = Revision.objects.filter(warehouse=self.warehouse).order_by('-revision_number').first()
            self.revision_number = (last.revision_number + 1) if last else 1
        super().save(*args, **kwargs)


class RevisionAssignment(models.Model):
    """Reviziyaga tayinlangan revizorlar"""

    STATUS_CHOICES = [
        ('assigned', 'Tayinlangan'),
        ('working', 'Ishlayapti'),
        ('completed', 'Tugatdi'),
    ]

    revision = models.ForeignKey(
        Revision,
        on_delete=models.CASCADE,
        related_name='assignments',
        verbose_name='Reviziya'
    )
    revizor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='assignments',
        verbose_name='Revizor'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='assigned',
        verbose_name='Status'
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Revizor tayinlash'
        verbose_name_plural = 'Revizor tayinlashlari'
        unique_together = ['revision', 'revizor']

    def __str__(self):
        return f"{self.revizor.full_name} -> {self.revision}"


class RevisionItem(models.Model):
    """Revizor kiritgan tovar ma'lumotlari"""

    revision = models.ForeignKey(
        Revision,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Reviziya'
    )
    revizor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='revision_items',
        verbose_name='Revizor'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='revision_items',
        verbose_name='Tovar'
    )
    series = models.CharField(max_length=100, blank=True, verbose_name='Seriya')
    expiry_date = models.DateField(
        verbose_name='Yaroqlilik muddati',
        validators=[
            MinValueValidator(date(2025, 1, 1)),
            MaxValueValidator(date(2050, 12, 31))
        ]
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name='Soni'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Reviziya yozuvi'
        verbose_name_plural = 'Reviziya yozuvlari'
        # Bir xil tovar + seriya + srok = bitta yozuv (avtomatik qo'shiladi)
        unique_together = ['revision', 'revizor', 'product', 'series', 'expiry_date']

    def __str__(self):
        return f"{self.product.name} | {self.series} | {self.quantity}"


class RevisionResult(models.Model):
    """Reviziya natijasi - avtomatik hisoblanadi"""

    revision = models.ForeignKey(
        Revision,
        on_delete=models.CASCADE,
        related_name='results',
        verbose_name='Reviziya'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='revision_results',
        verbose_name='Tovar'
    )
    series = models.CharField(max_length=100, blank=True, verbose_name='Seriya')
    expiry_date = models.DateField(null=True, blank=True, verbose_name='Yaroqlilik muddati')

    # 1C dan (kutilgan)
    expected_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='1C bo\'yicha qoldiq'
    )

    # Revizorlar sanadi (haqiqiy)
    actual_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Haqiqiy qoldiq'
    )

    # Farq
    difference = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Farq'
    )

    # Status: tugri, kam, kop
    STATUS_CHOICES = [
        ('correct', 'To\'g\'ri'),
        ('shortage', 'Kam'),
        ('excess', 'Ko\'p'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='correct')

    # Qaysi revizor(lar) sanadi
    revizors = models.ManyToManyField(User, related_name='results', blank=True)

    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Reviziya natijasi'
        verbose_name_plural = 'Reviziya natijalari'
        unique_together = ['revision', 'product', 'series', 'expiry_date']

    def __str__(self):
        return f"{self.product.name} | {self.get_status_display()} | Farq: {self.difference}"

    def calculate(self):
        """Farqni hisoblash"""
        self.difference = self.actual_quantity - self.expected_quantity
        if self.difference == 0:
            self.status = 'correct'
        elif self.difference < 0:
            self.status = 'shortage'
        else:
            self.status = 'excess'
        self.save()


class UnaccountedItem(models.Model):
    """Hisobda yo'q tovarlar (1C da yo'q, omborda bor)"""

    revision = models.ForeignKey(
        Revision,
        on_delete=models.CASCADE,
        related_name='unaccounted_items',
        verbose_name='Reviziya'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='unaccounted_items',
        verbose_name='Tovar'
    )
    series = models.CharField(max_length=100, blank=True, verbose_name='Seriya')
    expiry_date = models.DateField(null=True, blank=True, verbose_name='Yaroqlilik muddati')
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Soni'
    )
    revizor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='unaccounted_items',
        verbose_name='Revizor'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Hisobda yo\'q tovar'
        verbose_name_plural = 'Hisobda yo\'q tovarlar'

    def __str__(self):
        return f"NEUCHTEN: {self.product.name} | {self.quantity}"