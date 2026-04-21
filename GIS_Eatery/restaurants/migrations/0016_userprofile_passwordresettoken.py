# Generated migration for UserProfile and PasswordResetToken models

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('restaurants', '0016_update_models'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email_verified', models.BooleanField(default=False, verbose_name='Email đã xác thực')),
                ('email_verification_token', models.CharField(blank=True, max_length=255, verbose_name='Token xác thực email')),
                ('email_verification_expires', models.DateTimeField(blank=True, null=True, verbose_name='Thời hạn xác thực email')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Hồ sơ người dùng',
                'verbose_name_plural': 'Hồ sơ người dùng',
            },
        ),
        migrations.CreateModel(
            name='PasswordResetToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(max_length=255, unique=True, verbose_name='Token')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Tạo lúc')),
                ('expires_at', models.DateTimeField(verbose_name='Hết hạn lúc')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Token đặt lại mật khẩu',
                'verbose_name_plural': 'Token đặt lại mật khẩu',
            },
        ),
    ]
