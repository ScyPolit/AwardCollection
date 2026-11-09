"""One source of truth for object-level visibility, including frozen approvals."""

from django.contrib.auth import get_user_model
from django.db.models import Q, F, Value, CharField
from django.db.models.functions import Cast, Concat
from .models import Competition, AwardBatch, BatchVersion, Certificate, DepartmentMembership, Notification, RevocationRequest, Template


def managed_departments(user):
    return DepartmentMembership.objects.filter(
        user=user, role="admin", active=True, department__deleted_at__isnull=True
    ).values_list("department_id", flat=True)


def accessible_templates(user):
    qs = Template.objects.filter(deleted_at__isnull=True)
    if user.is_superuser:
        return qs
    return qs.filter(
        Q(published=True) | Q(scope=Template.Scope.PERSONAL, created_by=user)
        | Q(scope=Template.Scope.DEPARTMENT, department_id__in=managed_departments(user))
    )


def owned_competitions(user):
    from .permissions import is_owner
    if not is_owner(user):
        return Competition.objects.none()
    return Competition.objects.filter(Q(created_by=user) | Q(collaborators=user)).distinct()


def collaborator_options(user):
    """Use the same role and relationship boundary for options and writes."""
    from .permissions import OWNER_GROUP
    users = get_user_model().objects.filter(
        is_active=True, management_profile__deleted_at__isnull=True,
    )
    if user.is_superuser:
        return users.filter(Q(groups__name=OWNER_GROUP) | Q(is_superuser=True)).distinct()
    related = accessible_competitions(user)
    return users.filter(is_superuser=False, groups__name=OWNER_GROUP).filter(
        Q(pk=user.pk) | Q(management_profile__created_by=user)
        | Q(competitions__in=related) | Q(created_competitions__in=related)
    ).distinct()


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
    # Older revocation messages predate the batch FK. Resolve their target in SQL,
    # so removing a department role also removes obsolete certificate notices.
    revocation_targets = RevocationRequest.objects.filter(certificate__in=visible_certificates(user)).annotate(
        path=Concat(Value("/business/approvals?revocation="), Cast("pk", CharField()))
    ).values("path")
    unscoped = Q(batch__isnull=True) & ~Q(target__contains="batch=") & ~Q(target__contains="revocation=") & ~Q(title__in=["超管应急签发", "超管应急作废"])
    return qs.filter(Q(batch_id__in=accessible_batches(user)) | Q(batch__isnull=True, target__in=revocation_targets) | unscoped)
