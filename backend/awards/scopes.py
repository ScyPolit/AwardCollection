"""One source of truth for object-level visibility, including frozen approvals."""

from django.db.models import Q, F
from .models import Competition, AwardBatch, BatchVersion, Certificate, DepartmentMembership, Notification


def managed_departments(user):
    return DepartmentMembership.objects.filter(
        user=user, role="admin", active=True, department__deleted_at__isnull=True
    ).values_list("department_id", flat=True)


def owned_competitions(user):
    return Competition.objects.filter(Q(created_by=user) | Q(collaborators=user)).distinct()


def accessible_versions(user):
    qs = BatchVersion.objects.all()
    if user.is_superuser:
        return qs
    departments = managed_departments(user)
    if departments.exists():
        return qs.filter(required_departments__department_id__in=departments).distinct()
    return qs.filter(batch__competition__in=owned_competitions(user)).distinct()


def accessible_batches(user):
    qs = AwardBatch.objects.filter(deleted_at__isnull=True, competition__deleted_at__isnull=True)
    if user.is_superuser:
        return qs
    departments = managed_departments(user)
    if departments.exists():
        return qs.filter(versions__number=F("current_version"), versions__required_departments__department_id__in=departments).distinct()
    return qs.filter(competition__in=owned_competitions(user)).distinct()


def accessible_competitions(user):
    qs = Competition.objects.filter(deleted_at__isnull=True)
    if user.is_superuser:
        return qs
    departments = managed_departments(user)
    if departments.exists():
        return qs.filter(Q(departments__in=departments) | Q(batches__versions__required_departments__department_id__in=departments)).distinct()
    return qs.filter(pk__in=owned_competitions(user)).distinct()


def visible_certificates(user):
    return Certificate.objects.filter(
        deleted_at__isnull=True, published_at__isnull=False,
        award__version__in=accessible_versions(user),
    )


def can_access_version(user, version_id):
    return accessible_versions(user).filter(pk=version_id).exists()


def visible_notifications(user):
    qs = Notification.objects.filter(user=user)
    if user.is_superuser:
        return qs
    return qs.filter(Q(batch_id__in=accessible_batches(user)) | (Q(batch__isnull=True) & ~Q(target__contains="batch=")))
