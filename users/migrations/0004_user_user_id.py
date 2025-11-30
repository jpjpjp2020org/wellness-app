from django.db import migrations, models
import random
import string
import time


def assign_unique_user_ids(apps, schema_editor):
    User = apps.get_model('users', 'User')

    used_ids = set(User.objects.exclude(user_id__isnull=True).values_list('user_id', flat=True))

    def generate_unique_id():
        for _ in range(100):
            prefix = random.choice(string.ascii_lowercase)
            epoch = int(time.time())
            suffix = random.randint(1000, 9999)
            uid = f"{prefix}{epoch}{suffix}"
            if uid not in used_ids:
                used_ids.add(uid)
                return uid
        raise Exception("Could not generate unique user ID")

    for user in User.objects.all():
        user.user_id = generate_unique_id()
        user.save()


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_rename_is_verified_user_email_verified'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='user_id',
            field=models.CharField(max_length=32, null=True),
        ),
        migrations.RunPython(assign_unique_user_ids),
    ]
