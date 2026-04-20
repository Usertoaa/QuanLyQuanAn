# Migration tạo UserProfile và PasswordResetToken models
# Đây là một migration tự động được Django tạo ra

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('restaurants', '0015_add_reservation_item_and_updates'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email_verified', models.BooleanField(default=False, verbose_name='Email đã xác thực')),
                ('email_verification_token', models.CharField(blank=True, max_length=100, verbose_name='Token xác thực email')),
                ('email_verification_expires', models.DateTimeField(blank=True, null=True, verbose_name='Thời hạn xác thực email')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Thông tin người dùng',
                'verbose_name_plural': 'Thông tin người dùng',
            },
        ),
        migrations.CreateModel(
            name='PasswordResetToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(max_length=100, unique=True, verbose_name='Token')),
                ('expires_at', models.DateTimeField(verbose_name='Hết hạn lúc')),
                ('is_used', models.BooleanField(default=False, verbose_name='Đã sử dụng')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='password_reset_tokens', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Token reset mật khẩu',
                'verbose_name_plural': 'Token reset mật khẩu',
                'ordering': ['-created_at'],
            },
        ),
    ]
