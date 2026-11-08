from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('awards', '0012_notification_batch')]
    operations = [migrations.AlterField(
        model_name='approvaldepartment', name='seal_version',
        field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='awards.sealversion'),
    )]
