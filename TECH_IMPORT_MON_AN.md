# 🔧 Tài Liệu Kỹ Thuật - Chức Năng Import Dữ Liệu Các Món Ăn từ Excel

## 📚 Mục Lục

1. [Tổng Quan](#tổng-quan)
2. [Kiến Trúc](#kiến-trúc)
3. [Các Thành Phần](#các-thành-phần)
4. [Cách Sử Dụng](#cách-sử-dụng)
5. [API Reference](#api-reference)
6. [Xử Lý Lỗi](#xử-lý-lỗi)
7. [Mở Rộng](#mở-rộng)

---

## 🎯 Tổng Quan

### Mục Đích
Cho phép admin nhập dữ liệu hàng loạt các món ăn từ file Excel thay vì phải nhập từng món một.

### Yêu Cầu
- Django 6.0+
- Python 3.8+
- openpyxl >= 3.10.10
- pandas >= 2.1.4

### Lợi Ích
- ✅ Tiết kiệm thời gian (nhập 100 món chỉ trong vài giây)
- ✅ Giảm lỗi nhập liệu
- ✅ Hỗ trợ cập nhật dữ liệu hiện có
- ✅ Báo cáo lỗi chi tiết

---

## 🏗️ Kiến Trúc

### Cấu Trúc Dữ Liệu

```
┌─────────────────────────────────────┐
│       Excel File (.xlsx)             │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  DishImportHandler (import_dishes... │  ← Xử lý chính
│  - validate_file()                  │
│  - import_dishes()                  │
│  - parse_price()                    │
│  - parse_boolean()                  │
└──────────────┬──────────────────────┘
               │
               ▼
         ┌──────────────┐
         │  Dish Model  │
         │  (Database)  │
         └──────────────┘
```

### Luồng Xử Lý

```
1. User tải file Excel
   ↓
2. Form validation (DishImportForm)
   ↓
3. Tạo DishImportHandler instance
   ↓
4. Validate file structure
   ↓
5. Duyệt từng dòng dữ liệu
   ├─→ Parse giá tiền
   ├─→ Parse boolean values
   ├─→ Validate required fields
   └─→ Update/Create Dish
   ↓
6. Trả kết quả & thông báo cho user
```

---

## 📦 Các Thành Phần

### 1. **Module: `import_dishes_from_excel.py`**

#### Class: `DishImportHandler`

```python
class DishImportHandler:
    """Xử lý import dữ liệu các món ăn từ file Excel"""
    
    REQUIRED_COLUMNS = ['Tên Món', 'Giá Tiền']
    OPTIONAL_COLUMNS = ['Mô Tả', 'Còn Món', 'Dùng Làm Giá Đại Diện']
```

**Thuộc tính:**
- `excel_file`: UploadedFile từ form
- `restaurant`: Instance của Restaurant model
- `errors`: List các lỗi
- `warnings`: List các cảnh báo
- `success_count`: Số lượng món import thành công
- `data`: DataFrame từ pandas

**Phương thức Chính:**

| Phương Thức | Mô Tả | Return |
|-------------|-------|--------|
| `__init__(excel_file, restaurant)` | Khởi tạo handler | None |
| `validate_file()` | Kiểm tra file hợp lệ | bool |
| `import_dishes()` | Thực hiện import | dict |
| `parse_price(value)` | Chuyển đổi giá tiền | int \| None |
| `parse_boolean(value)` | Chuyển đổi boolean | bool |

#### Hàm: `create_sample_excel_template(output)`

Tạo file Excel mẫu với:
- 2 sheets: "Thực Đơn" và "Hướng Dẫn"
- Định dạng và styling sẵn
- Dữ liệu mẫu
- Hướng dẫn chi tiết

**Tham số:**
- `output`: str (đường dẫn file) hoặc BytesIO object

---

### 2. **Form: `DishImportForm`** (trong `forms.py`)

```python
class DishImportForm(forms.Form):
    excel_file = forms.FileField(...)
```

**Validations:**
- ✅ Định dạng: .xlsx, .xls
- ✅ Kích thước: ≤ 5MB
- ✅ File không trống

---

### 3. **Views** (trong `views.py`)

#### `admin_import_dishes(request, pk)`
- **Method**: GET, POST
- **Permission**: @login_required, @user_passes_test(lambda u: u.is_superuser)
- **Purpose**: Hiển thị form & xử lý upload file
- **Template**: `admin_import_dishes.html`

#### `download_sample_dishes_template(request, pk)`
- **Method**: GET
- **Permission**: @login_required, @user_passes_test(lambda u: u.is_superuser)
- **Purpose**: Tải file Excel mẫu
- **Return**: FileResponse

---

### 4. **Template: `admin_import_dishes.html`**

Giao diện bao gồm:
- 📋 Form upload file
- 📖 Hướng dẫn chi tiết
- 📚 Bảng giải thích các cột
- ⚠️ Lưu ý quan trọng
- 📥 Nút download file mẫu

---

### 5. **URL Patterns** (trong `urls.py`)

```python
path('my-admin/restaurant/<int:pk>/menu/import/', views.admin_import_dishes, name='admin_import_dishes'),
path('my-admin/restaurant/<int:pk>/menu/import/download-template/', views.download_sample_dishes_template, name='download_sample_dishes_template'),
```

---

## 🔄 Cách Sử Dụng

### Sử Dụng DishImportHandler

```python
from restaurants.import_dishes_from_excel import DishImportHandler
from restaurants.models import Restaurant

# Lấy quán ăn
restaurant = Restaurant.objects.get(pk=1)

# Tạo handler
handler = DishImportHandler(excel_file, restaurant)

# Thực hiện import
result = handler.import_dishes()

# Kiểm tra kết quả
if result['success']:
    print(f"✅ Import {result['success_count']} món thành công")
else:
    print(f"❌ Lỗi: {result['errors']}")
```

### Kết Quả Return

```python
{
    'success': bool,                    # Có lỗi không
    'errors': list,                    # Danh sách lỗi
    'warnings': list,                  # Danh sách cảnh báo
    'success_count': int,              # Số lượng thành công
    'failed_count': int,               # Số lượng thất bại
    'total': int,                      # Tổng số
    'message': str,                    # Thông báo người dùng
}
```

### Tạo File Excel Mẫu

```python
from restaurants.import_dishes_from_excel import create_sample_excel_template
from io import BytesIO

# Cách 1: Lưu thành file
create_sample_excel_template('/path/to/template.xlsx')

# Cách 2: Lưu vào BytesIO (để gửi về client)
output = BytesIO()
create_sample_excel_template(output)
output.seek(0)
# Gửi output về client
```

---

## 📖 API Reference

### DishImportHandler Methods

#### `validate_file() -> bool`

**Mô Tả**: Kiểm tra file Excel có hợp lệ không

**Logic**:
1. Đọc file Excel bằng pandas
2. Kiểm tra file có dữ liệu
3. Kiểm tra các cột bắt buộc có tồn tại
4. Thêm lỗi vào `self.errors` nếu không hợp lệ

**Return**: 
- `True` nếu file hợp lệ
- `False` nếu có lỗi

**Ví dụ**:
```python
if handler.validate_file():
    print("✅ File hợp lệ")
else:
    print(f"❌ Lỗi: {handler.errors}")
```

---

#### `import_dishes() -> dict`

**Mô Tả**: Thực hiện import dữ liệu các món ăn

**Logic**:
1. Gọi `validate_file()`
2. Nếu lỗi, return kết quả với lỗi
3. Duyệt từng dòng trong DataFrame
4. Gọi `_import_single_dish()` cho mỗi dòng
5. Sử dụng transaction để đảm bảo tính toàn vẹn

**Return**: Dictionary với kết quả

**Ví dụ**:
```python
result = handler.import_dishes()
if result['success_count'] > 0:
    messages.success(request, result['message'])
if result['errors']:
    for error in result['errors']:
        messages.error(request, error)
```

---

#### `parse_price(value) -> int | None`

**Mô Tả**: Chuyển đổi giá tiền từ nhiều định dạng

**Xử Lý**:
- `pd.NaN` → None
- String "50000" → 50000
- String "50.000" → 50000
- String "50,000" → 50000
- Float 50000.0 → 50000
- Giá âm → None

**Ví dụ**:
```python
assert handler.parse_price("50000") == 50000
assert handler.parse_price("50.000") == 50000
assert handler.parse_price(50000.5) == 50000
assert handler.parse_price("-100") is None
```

---

#### `parse_boolean(value, default=True) -> bool`

**Mô Tả**: Chuyển đổi giá trị thành boolean

**Xử Lý**:
- `pd.NaN` → `default`
- bool → return as-is
- int/float: `0` → False, khác `0` → True
- String:
  - True: "yes", "y", "true", "1", "có", "c", "đúng"
  - False: "no", "n", "false", "0", etc.
  - Default: không khớp → `default`

**Ví dụ**:
```python
assert handler.parse_boolean("Có") == True
assert handler.parse_boolean("Yes") == True
assert handler.parse_boolean("No") == False
assert handler.parse_boolean("abc", default=True) == True
```

---

#### `_import_single_dish(row, row_number) -> None`

**Mô Tả**: Import một món ăn từ dòng dữ liệu (Private method)

**Logic**:
1. Parse tên món
2. Parse giá tiền
3. Validate dữ liệu bắt buộc
4. Parse các trường tùy chọn
5. Gọi `Dish.objects.update_or_create()`

**Raises**:
- ValueError nếu dữ liệu không hợp lệ

**Side Effects**:
- Tăng `self.success_count`
- Thêm warning nếu món đã tồn tại

---

#### `create_sample_excel_template(output) -> None`

**Mô Tả**: Tạo file Excel mẫu

**Features**:
- Sheet 1 "Thực Đơn": Dữ liệu mẫu + hướng dẫn
- Sheet 2 "Hướng Dẫn": Hướng dẫn chi tiết
- Định dạng:
  - Header: màu xanh, chữ trắng
  - Instructions: màu xám, chữ nhỏ
  - Data: thường
- Column widths tự động điều chỉnh
- Border và alignment chuẩn

**Ví dụ**:
```python
# Lưu file
create_sample_excel_template('template.xlsx')

# Gửi về client
excel_file = BytesIO()
create_sample_excel_template(excel_file)
response = FileResponse(
    excel_file,
    filename='template.xlsx'
)
```

---

## 🚨 Xử Lý Lỗi

### Các Lỗi Có Thể Xảy Ra

| Lỗi | Nguyên Nhân | Giải Pháp |
|-----|-----------|----------|
| File không có dữ liệu | File trống | Thêm dữ liệu vào file |
| Thiếu cột bắt buộc | Header sai | Sử dụng file mẫu |
| Tên món không hợp lệ | Cell trống hoặc NaN | Điền đủ tên món |
| Giá tiền không hợp lệ | Không phải số hoặc âm | Nhập giá dương |
| Exception khi lưu | Transaction fail | Kiểm tra database |

### Xử Lý Error trong View

```python
def admin_import_dishes(request, pk):
    if request.method == 'POST':
        form = DishImportForm(request.POST, request.FILES)
        if form.is_valid():
            handler = DishImportHandler(
                request.FILES['excel_file'],
                restaurant
            )
            result = handler.import_dishes()
            
            # Xử lý errors
            if result['errors']:
                for error in result['errors']:
                    messages.error(request, error)
            
            # Xử lý warnings
            if result['warnings']:
                for warning in result['warnings']:
                    messages.warning(request, warning)
            
            # Xử lý success
            if result['success_count'] > 0:
                messages.success(request, result['message'])
                return redirect('admin_menu_list', pk=pk)
```

---

## 🔌 Mở Rộng

### Thêm Cột Mới

Để thêm cột mới, ví dụ "Danh Mục":

1. **Cập nhật Model** (`models.py`):
```python
class Dish(models.Model):
    category = models.CharField(max_length=100, blank=True)
```

2. **Cập nhật Handler** (`import_dishes_from_excel.py`):
```python
class DishImportHandler:
    OPTIONAL_COLUMNS = ['Mô Tả', 'Còn Món', 'Dùng Làm Giá Đại Diện', 'Danh Mục']
    
    def _import_single_dish(self, row, row_number):
        # ... existing code ...
        category = ""
        if 'Danh Mục' in row and not pd.isna(row['Danh Mục']):
            category = str(row['Danh Mục']).strip()
        
        dish, created = Dish.objects.update_or_create(
            restaurant=self.restaurant,
            name=dish_name,
            defaults={
                'category': category,  # Thêm dòng này
                # ... other fields ...
            }
        )
```

3. **Cập nhật Template** (`admin_import_dishes.html`):
```html
<tr>
    <td><strong>Danh Mục</strong></td>
    <td><span class="badge bg-success">Tùy Chọn</span></td>
    <td>Danh mục món ăn: Phở, Cơm, Bánh mì, etc.</td>
</tr>
```

### Thêm Validation Tùy Chỉnh

```python
def _import_single_dish(self, row, row_number):
    # ... existing code ...
    
    # Validation tùy chỉnh
    if price > 1000000:  # Giá không được quá 1 triệu
        raise ValueError("Giá tiền không được quá 1,000,000 VNĐ")
    
    # ... continue ...
```

### Tích Hợp với Background Task

```python
from celery import shared_task

@shared_task
def import_dishes_async(restaurant_id, excel_file_path):
    restaurant = Restaurant.objects.get(pk=restaurant_id)
    with open(excel_file_path, 'rb') as f:
        handler = DishImportHandler(f, restaurant)
        return handler.import_dishes()
```

---

## 📊 Thống Kê & Monitoring

### Log Import Activity

```python
from django.utils import timezone

def log_import(restaurant, result):
    ImportLog.objects.create(
        restaurant=restaurant,
        success_count=result['success_count'],
        failed_count=result['failed_count'],
        errors=json.dumps(result['errors']),
        warnings=json.dumps(result['warnings']),
        timestamp=timezone.now(),
    )
```

### Metrics

- Số lượng import/ngày
- Tỷ lệ thành công
- Loại lỗi phổ biến
- Thời gian import trung bình

---

## 🧪 Testing

### Unit Test Example

```python
from django.test import TestCase
from restaurants.import_dishes_from_excel import DishImportHandler

class DishImportHandlerTestCase(TestCase):
    def setUp(self):
        self.restaurant = Restaurant.objects.create(...)
    
    def test_parse_price(self):
        handler = DishImportHandler(None, self.restaurant)
        self.assertEqual(handler.parse_price("50000"), 50000)
        self.assertEqual(handler.parse_price("50.000"), 50000)
        self.assertIsNone(handler.parse_price("-100"))
    
    def test_parse_boolean(self):
        handler = DishImportHandler(None, self.restaurant)
        self.assertTrue(handler.parse_boolean("Có"))
        self.assertFalse(handler.parse_boolean("Không"))
        self.assertTrue(handler.parse_boolean("Yes"))
```

---

## 📝 Changelog

### v1.0 (April 2026)
- ✅ Initial release
- ✅ Support .xlsx, .xls
- ✅ Auto template generation
- ✅ Error reporting
- ✅ Bilingual UI (Vietnamese)

### Planned Features
- 🔲 Image import from URLs
- 🔲 Bulk category assignment
- 🔲 Price history tracking
- 🔲 Duplicate detection
- 🔲 Preview before import
- 🔲 Undo import

---

## 📞 Support & Contribution

Để báo cáo lỗi hoặc đóng góp tính năng mới:
1. Tạo issue chi tiết
2. Gửi pull request
3. Theo dõi changelog

---

**Tác Giả**: Admin Team  
**Phiên Bản**: 1.0  
**Cập Nhật**: April 2026  
**License**: MIT
