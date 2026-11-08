from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('awards', '0013_approval_seal_optional')]
    operations = [
        migrations.CreateModel(
            name='VerificationRateLimit',
            fields=[
                ('ip_address', models.GenericIPAddressField(primary_key=True, serialize=False)),
                ('timestamps', models.JSONField(default=list)),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True)),
            ],
        ),
    ]
