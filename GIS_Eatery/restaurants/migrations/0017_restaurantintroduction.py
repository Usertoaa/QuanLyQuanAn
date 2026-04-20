# Generated migration for RestaurantIntroduction model

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('restaurants', '0016_userprofile_passwordresettoken'),
    ]

    operations = [
        migrations.CreateModel(
            name='RestaurantIntroduction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200, verbose_name='Tiêu đề')),
                ('description', models.TextField(verbose_name='Nội dung giới thiệu')),
                ('featured', models.BooleanField(default=False, verbose_name='Nổi bật')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Tạo lúc')),
                ('restaurant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='introductions', to='restaurants.restaurant', verbose_name='Quán ăn')),
            ],
            options={
                'verbose_name': 'Bài giới thiệu quán ăn',
                'verbose_name_plural': 'Bài giới thiệu quán ăn',
                'ordering': ['-featured', '-created_at'],
            },
        ),
    ]
