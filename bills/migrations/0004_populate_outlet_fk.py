from django.db import migrations

def forwards(apps, schema_editor):
    Bill   = apps.get_model('bills', 'Bill')
    Route  = apps.get_model('bills', 'Route')
    Outlet = apps.get_model('bills', 'Outlet')

    for bill in Bill.objects.all():
        # Grab the *old* text values from each row
        route_name  = bill.route        # CharField
        outlet_name = bill.outlet_name  # CharField

        # Create or fetch proper objects
        route_obj,  _ = Route.objects.get_or_create(name=route_name)
        outlet_obj, _ = Outlet.objects.get_or_create(
            name=outlet_name,
            route=route_obj
        )

        # Fill the new FK
        bill.outlet = outlet_obj
        bill.save(update_fields=['outlet'])

def backwards(apps, schema_editor):
    # DANGER: if you ever need to roll back, wipe the FK
    Bill = apps.get_model('bills', 'Bill')
    Bill.objects.update(outlet=None)

class Migration(migrations.Migration):

    dependencies = [
        ('bills', '0003_outlet_route_remove_bill_outlet_name_and_more'),  # ← adjust to the actual file number
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
