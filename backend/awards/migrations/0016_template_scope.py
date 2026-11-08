from django.db import migrations, models


def mark_personal_templates(apps, schema_editor):
    Template = apps.get_model("awards", "Template")
    Membership = apps.get_model("awards", "DepartmentMembership")
    for template in Template.objects.select_related("created_by").iterator():
        creator = template.created_by
        if not creator.is_superuser and creator.groups.filter(name="competition_owners").exists():
            if not Membership.objects.filter(user_id=creator.pk, department_id=template.department_id, role="admin", active=True).exists():
                Template.objects.filter(pk=template.pk).update(scope="personal")


class Migration(migrations.Migration):
    dependencies = [("awards", "0015_approvaldecision_withdrawal_reason_and_more")]
    operations = [
        migrations.AddField(model_name="template", name="scope", field=models.CharField(choices=[("department", "部门模板"), ("personal", "个人模板")], default="department", max_length=16)),
        migrations.RunPython(mark_personal_templates, migrations.RunPython.noop),
    ]
