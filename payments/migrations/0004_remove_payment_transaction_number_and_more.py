# Generated by Django 5.2.1 on 2025-05-26 18:29

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0003_remove_payment_transaction_photo_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='payment',
            name='transaction_Number',
        ),
        migrations.AddField(
            model_name='payment',
            name='transaction_number',
            field=models.BigIntegerField(blank=True, null=True),
        ),
    ]
