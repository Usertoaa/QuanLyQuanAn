from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, SetPasswordForm
from django.utils.html import format_html
from .models import Dish, Restaurant


# ============================================
# CUSTOM PASSWORD WIDGET
# ============================================

class PasswordInputWithToggle(forms.PasswordInput):
    """Custom Password Input widget với nút toggle hiển thị/ẩn mật khẩu"""
    
    def render(self, name, value, attrs=None, renderer=None):
        # Render password input
        input_html = super().render(name, value, attrs, renderer)
        
        # Tạo toggle button
        toggle_id = f'{name}_toggle'
        toggle_btn = format_html(
            '<button type="button" class="btn-password-toggle" id="{}" title="Hiển thị/ẩn mật khẩu">'
            '<i class="fas fa-eye"></i>'
            '</button>',
            toggle_id
        )
        
        # Wrapper HTML
        wrapper = format_html(
            '<div class="password-input-wrapper">{}{}</div>',
            input_html,
            toggle_btn
        )
        
        return wrapper


class DishImportForm(forms.Form):
    """Form để upload file Excel nhập dữ liệu các món ăn"""
    excel_file = forms.FileField(
        label='Chọn file Excel',
        required=True,
        widget=forms.FileInput(attrs={
            'accept': '.xlsx,.xls',
            'class': 'form-control',
            'id': 'excelFile'
        })
    )
    
    def clean_excel_file(self):
        file = self.cleaned_data['excel_file']
        
        # Kiểm tra định dạng file
        allowed_extensions = ['xlsx', 'xls']
        file_extension = file.name.split('.')[-1].lower()
        
        if file_extension not in allowed_extensions:
            raise forms.ValidationError(
                "Vui lòng upload file Excel (.xlsx hoặc .xls)"
            )
        
        # Kiểm tra kích thước file (max 5MB)
        if file.size > 5 * 1024 * 1024:
            raise forms.ValidationError(
                "Kích thước file không được vượt quá 5MB"
            )
        
        return file


class DishForm(forms.ModelForm):
    """Form để tạo/chỉnh sửa một món ăn"""
    class Meta:
        model = Dish
        fields = ['name', 'description', 'price', 'image', 'is_available', 'is_price_representative']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Tên món ăn'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Mô tả chi tiết về món ăn'
            }),
            'price': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Giá tiền (VNĐ)',
                'min': '0'
            }),
            'image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'is_available': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_price_representative': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }


class CustomUserCreationForm(UserCreationForm):
    """Form đăng ký tài khoản người dùng"""
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Email',
            'autocomplete': 'email'
        })
    )
    username = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Tên đăng nhập',
            'autocomplete': 'username'
        })
    )
    password1 = forms.CharField(
        label='Mật khẩu',
        widget=PasswordInputWithToggle(attrs={
            'class': 'form-control password-input',
            'placeholder': 'Mật khẩu',
            'autocomplete': 'new-password',
            'id': 'id_password1'
        })
    )
    password2 = forms.CharField(
        label='Xác nhận mật khẩu',
        widget=PasswordInputWithToggle(attrs={
            'class': 'form-control password-input',
            'placeholder': 'Xác nhận mật khẩu',
            'autocomplete': 'new-password',
            'id': 'id_password2'
        })
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Email này đã được sử dụng!')
        return email

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Tên đăng nhập này đã tồn tại!')
        return username

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError('Mật khẩu không khớp!')
        
        return cleaned_data


class CustomSetPasswordForm(SetPasswordForm):
    """Form đặt lại mật khẩu"""
    new_password1 = forms.CharField(
        label='Mật khẩu mới',
        widget=PasswordInputWithToggle(attrs={
            'class': 'form-control password-input',
            'placeholder': 'Mật khẩu mới',
            'autocomplete': 'new-password',
            'id': 'id_new_password1'
        })
    )
    new_password2 = forms.CharField(
        label='Xác nhận mật khẩu mới',
        widget=PasswordInputWithToggle(attrs={
            'class': 'form-control password-input',
            'placeholder': 'Xác nhận mật khẩu mới',
            'autocomplete': 'new-password',
            'id': 'id_new_password2'
        })
    )

    class Meta:
        model = User
        fields = ('new_password1', 'new_password2')

