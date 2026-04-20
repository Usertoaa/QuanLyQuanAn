from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, PasswordResetForm
from django.core.exceptions import ValidationError
import re


class CustomUserCreationForm(UserCreationForm):
    """
    Form đăng ký tùy chỉnh với email và xác thực
    """
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nhập email của bạn',
            'autocomplete': 'email'
        }),
        help_text='Chúng tôi sẽ gửi link xác thực đến email này'
    )
    
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Tên đăng nhập',
            'autocomplete': 'username'
        }),
        help_text='Dùng chữ cái, số và @/./+/-/_ (tối đa 150 ký tự)'
    )
    
    password1 = forms.CharField(
        label='Mật khẩu',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nhập mật khẩu',
            'autocomplete': 'new-password'
        }),
        help_text='Mật khẩu phải chứa ít nhất 8 ký tự'
    )
    
    password2 = forms.CharField(
        label='Xác nhận mật khẩu',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nhập lại mật khẩu',
            'autocomplete': 'new-password'
        })
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError('Email này đã được đăng ký. Vui lòng sử dụng email khác hoặc đăng nhập.')
        return email

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if not re.match(r'^[\w.@+-]+$', username):
            raise ValidationError('Tên đăng nhập chỉ có thể chứa chữ cái, số và @/./+/-/_')
        return username

    def clean_password1(self):
        password1 = self.cleaned_data.get('password1')
        if len(password1) < 8:
            raise ValidationError('Mật khẩu phải có ít nhất 8 ký tự.')
        if password1.isdigit():
            raise ValidationError('Mật khẩu không thể chỉ toàn số.')
        return password1

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user


class CustomPasswordResetForm(PasswordResetForm):
    """
    Form yêu cầu reset mật khẩu tùy chỉnh
    """
    email = forms.EmailField(
        label='Email',
        max_length=254,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nhập email của bạn',
            'autocomplete': 'email'
        })
    )

    def clean_email(self):
        email = self.cleaned_data['email']
        if not User.objects.filter(email=email, is_active=True).exists():
            raise ValidationError('Không tìm thấy tài khoản với email này.')
        return email


class CustomSetPasswordForm(forms.Form):
    """
    Form đặt lại mật khẩu
    """
    new_password1 = forms.CharField(
        label='Mật khẩu mới',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nhập mật khẩu mới',
            'autocomplete': 'new-password'
        }),
        help_text='Mật khẩu phải chứa ít nhất 8 ký tự'
    )
    
    new_password2 = forms.CharField(
        label='Xác nhận mật khẩu mới',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nhập lại mật khẩu mới',
            'autocomplete': 'new-password'
        })
    )

    def clean_new_password1(self):
        password = self.cleaned_data.get('new_password1')
        if len(password) < 8:
            raise ValidationError('Mật khẩu phải có ít nhất 8 ký tự.')
        if password.isdigit():
            raise ValidationError('Mật khẩu không thể chỉ toàn số.')
        return password

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('new_password1')
        password2 = cleaned_data.get('new_password2')

        if password1 and password2 and password1 != password2:
            raise ValidationError('Hai mật khẩu không khớp.')
        return cleaned_data
