from django.db import migrations


def migrate_owners(apps, schema_editor):
    Membership = apps.get_model("awards", "DepartmentMembership")
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("auth", "User")
    group, _ = Group.objects.get_or_create(name="competition_owners")
    user_ids = list(Membership.objects.filter(role="owner", active=True).values_list("user_id", flat=True).distinct())
    through = User.groups.through
    through.objects.bulk_create([through(user_id=pk, group_id=group.pk) for pk in user_ids], ignore_conflicts=True)
    # Old associations are retained only as historical/rollback data. All new
    # authorization uses the global group and admin memberships exclusively.


class Migration(migrations.Migration):
    dependencies = [("awards", "0003_systemsetting_verificationattempt_loginprotection_and_more"), ("auth", "0012_alter_user_first_name_max_length")]
    operations = [migrations.RunPython(migrate_owners, migrations.RunPython.noop)]
