from django import forms
from .models import Dish, Restaurant


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


class CustomUserCreationForm(forms.Form):
    pass


class CustomSetPasswordForm(forms.Form):
    pass
