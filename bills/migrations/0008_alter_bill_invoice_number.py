# Generated by Django 5.2.1 on 2025-05-22 11:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bills', '0007_bill_cleared_at_bill_overdue_days'),
    ]

    operations = [
        migrations.AlterField(
            model_name='bill',
            name='invoice_number',
            field=models.CharField(max_length=255, unique=True),
        ),
    ]
