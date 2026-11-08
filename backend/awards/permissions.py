from django.contrib.auth.models import Group
from .models import DepartmentMembership

OWNER_GROUP = "competition_owners"


def is_department_admin(user, department=None):
    if user.is_superuser:
        return True
    qs = DepartmentMembership.objects.filter(user=user, role="admin", active=True, department__deleted_at__isnull=True)
    return qs.filter(department=department).exists() if department is not None else qs.exists()


def is_owner(user):
    return user.groups.filter(name=OWNER_GROUP).exists()


def can_edit_templates(user):
    return is_department_admin(user) or is_owner(user)


def can_manage_template(user, template):
    if user.is_superuser:
        return True
    if template.scope == "personal":
        return template.created_by_id == user.pk and can_edit_templates(user)
    return is_department_admin(user, template.department_id)


def grant_owner(user):
    user.groups.add(Group.objects.get_or_create(name=OWNER_GROUP)[0])


def user_roles(user):
    if user.is_superuser:
        return ["super", "admin", "owner"]
    return (["admin"] if is_department_admin(user) else []) + (["owner"] if is_owner(user) else [])
