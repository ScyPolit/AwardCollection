from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('awards', '0005_certificatefont')]
    operations = [migrations.AddField(model_name='certificatefont', name='active', field=models.BooleanField(default=True))]
