from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import date
from decimal import Decimal
from .models import (
    User, Warehouse, Product, Inventory,
    Revision, RevisionAssignment, RevisionItem
)


# ==================== AUTH FORMS ====================

class LoginForm(AuthenticationForm):
    """Login formasi"""
    username = forms.CharField(
        label='Login',
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Login kiriting',
            'autofocus': True
        })
    )
    password = forms.CharField(
        label='Parol',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Parol kiriting'
        })
    )


# ==================== ADMIN: WAREHOUSE FORMS ====================

class WarehouseForm(forms.ModelForm):
    """Ombor yaratish/tahrirlash formasi"""

    class Meta:
        model = Warehouse
        fields = ['name', 'address']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ombor nomini kiriting',
                'required': True
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Manzil (ixtiyoriy)',
                'rows': 3
            }),
        }
        labels = {
            'name': 'Ombor nomi',
            'address': 'Manzil'
        }


# ==================== ADMIN: REVIZOR FORMS ====================

class RevizorCreateForm(forms.ModelForm):
    """Revizor yaratish formasi"""

    password = forms.CharField(
        label='Parol',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Parol kiriting'
        })
    )
    password_confirm = forms.CharField(
        label='Parolni tasdiqlang',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Parolni qayta kiriting'
        })
    )

    class Meta:
        model = User
        fields = ['username', 'full_name']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Login (masalan: revizor1)'
            }),
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'To\'liq ism (masalan: Aliyev Vali)'
            }),
        }
        labels = {
            'username': 'Login',
            'full_name': 'To\'liq ism'
        }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')

        if password and password_confirm:
            if password != password_confirm:
                raise forms.ValidationError('Parollar mos kelmadi!')

        return cleaned_data

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Bu login band!')
        return username

    def save(self, commit=True, created_by=None):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        user.role = 'revizor'
        if created_by:
            user.created_by = created_by
        if commit:
            user.save()
        return user


# ==================== ADMIN: PRODUCT UPLOAD FORMS ====================

class ProductUploadForm(forms.Form):
    """Nomenklatura yuklash formasi (CSV/JSON)"""

    file = forms.FileField(
        label='Fayl tanlang',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.csv,.json'
        }),
        help_text='CSV yoki JSON formatida. Ustunlar: code (kod), name (nom), manufacturer (ishlab chiqaruvchi)'
    )

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            ext = file.name.split('.')[-1].lower()
            if ext not in ['csv', 'json']:
                raise forms.ValidationError('Faqat CSV yoki JSON fayl yuklang!')

            # Fayl hajmi (max 10MB)
            if file.size > 10 * 1024 * 1024:
                raise forms.ValidationError('Fayl hajmi 10MB dan oshmasin!')

        return file


# ==================== ADMIN: INVENTORY UPLOAD FORMS ====================

class InventoryUploadForm(forms.Form):
    """1C dan tovar qoldig'i yuklash formasi"""

    file = forms.FileField(
        label='CSV fayl',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.csv'
        }),
        help_text='Ustunlar: code (kod), series (seriya), expiry_date (srok), quantity (qoldiq)'
    )
    clear_old = forms.BooleanField(
        label='Eski qoldiqlarni o\'chirish',
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        help_text='Yangi yuklashdan oldin eski ma\'lumotlarni tozalash'
    )

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            if not file.name.endswith('.csv'):
                raise forms.ValidationError('Faqat CSV fayl yuklang!')

            if file.size > 10 * 1024 * 1024:
                raise forms.ValidationError('Fayl hajmi 10MB dan oshmasin!')

        return file


# ==================== ADMIN: REVISION FORMS ====================

class RevisionCreateForm(forms.Form):
    """Reviziya yaratish formasi"""

    revizors = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        label='Revizorlarni tanlang',
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'form-check-input'
        }),
        help_text='Kamida bitta revizor tanlang'
    )

    def __init__(self, *args, admin_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if admin_user:
            self.fields['revizors'].queryset = User.objects.filter(
                role='revizor',
                created_by=admin_user,
                is_active=True
            )

    def clean_revizors(self):
        revizors = self.cleaned_data.get('revizors')
        if not revizors:
            raise forms.ValidationError('Kamida bitta revizor tanlang!')
        return revizors


class RevisionFilterForm(forms.Form):
    """Reviziya natijalarini filtrlash formasi"""

    STATUS_CHOICES = [
        ('', 'Barchasi'),
        ('correct', 'To\'g\'ri'),
        ('shortage', 'Kam'),
        ('excess', 'Ko\'p'),
    ]

    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        label='Status',
        widget=forms.Select(attrs={
            'class': 'form-select',
            'onchange': 'this.form.submit()'
        })
    )
    search = forms.CharField(
        required=False,
        label='Qidirish',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Tovar nomi, kod yoki seriya...'
        })
    )


# ==================== REVIZOR: ITEM FORMS ====================

class RevisionItemForm(forms.ModelForm):
    """Revizor tovar kiritish formasi"""

    product_search = forms.CharField(
        label='Tovar qidirish',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Tovar nomini yoki kodini kiriting...',
            'autocomplete': 'off',
            'id': 'product-search'
        })
    )

    class Meta:
        model = RevisionItem
        fields = ['product', 'series', 'expiry_date', 'quantity']
        widgets = {
            'product': forms.HiddenInput(attrs={
                'id': 'product-id'
            }),
            'series': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Seriya raqami'
            }),
            'expiry_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'min': '2025-01-01',
                'max': '2050-12-31'
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Soni',
                'min': '0.01',
                'step': '0.01'
            }),
        }
        labels = {
            'series': 'Seriya',
            'expiry_date': 'Yaroqlilik muddati',
            'quantity': 'Soni'
        }

    def clean_expiry_date(self):
        expiry_date = self.cleaned_data.get('expiry_date')
        if expiry_date:
            if expiry_date.year < 2025:
                raise forms.ValidationError('Srok 2025 dan kam bo\'lmasin!')
            if expiry_date.year > 2050:
                raise forms.ValidationError('Srok 2050 dan oshmasin!')
        return expiry_date

    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity')
        if quantity is not None and quantity <= 0:
            raise forms.ValidationError('Miqdor 0 dan katta bo\'lishi kerak!')
        return quantity


class RevisionItemUpdateForm(forms.Form):
    """Tovar sonini yangilash formasi"""

    quantity = forms.DecimalField(
        label='Yangi miqdor',
        min_value=Decimal('0.01'),
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0.01',
            'step': '0.01'
        })
    )


# ==================== CONFIRMATION FORMS ====================

class ConfirmDeleteForm(forms.Form):
    """O'chirishni tasdiqlash formasi"""

    confirm = forms.BooleanField(
        label='Ha, o\'chirishni tasdiqlayman',
        required=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )


class ConfirmCompleteForm(forms.Form):
    """Tugatishni tasdiqlash formasi"""

    confirm = forms.BooleanField(
        label='Ha, tugatishni tasdiqlayman',
        required=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )


# ==================== SEARCH FORMS ====================

class ProductSearchForm(forms.Form):
    """Tovar qidirish formasi"""

    q = forms.CharField(
        label='',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Tovar nomi, kod yoki ishlab chiqaruvchi...',
            'autocomplete': 'off'
        })
    )


# ==================== EXPORT FORMS ====================

class ExportForm(forms.Form):
    """Eksport formati tanlash"""

    FORMAT_CHOICES = [
        ('csv', 'CSV'),
        ('xlsx', 'Excel (XLSX)'),
    ]

    format = forms.ChoiceField(
        choices=FORMAT_CHOICES,
        label='Format',
        initial='csv',
        widget=forms.RadioSelect(attrs={
            'class': 'form-check-input'
        })
    )