"""Scoped changes to mutable business information; historical originals stay immutable."""

from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied, ValidationError, NotFound
from rest_framework.response import Response
from .models import AccountProfile, AuditEvent, DepartmentMembership, AwardBatch
from .permissions import OWNER_GROUP, is_department_admin, is_owner


def account_permissions(actor, target):
    if actor.is_superuser:
        return {"can_edit": True, "can_delete": actor.pk != target.pk}
    own = target.pk == actor.pk
    if own:
        return {"can_edit": True, "can_delete": False}
    created_here = (
        AccountProfile.objects.filter(user=target, created_by=actor).exists()
        or AuditEvent.objects.filter(
            actor=actor, action="account.created", object_id=str(target.pk)
        ).exists()
    )
    allowed = (
        is_department_admin(actor)
        and created_here
        and is_owner(target)
        and not target.is_superuser
        and not DepartmentMembership.objects.filter(
            user=target, role="admin", active=True
        ).exists()
    )
    return {"can_edit": allowed, "can_delete": allowed}


@api_view(["PATCH", "DELETE"])
@transaction.atomic
def account_detail(request, user_id):
    target = get_user_model().objects.select_for_update().filter(pk=user_id).first()
    if (
        not target
        or AccountProfile.objects.filter(user=target, deleted_at__isnull=False).exists()
    ):
        raise NotFound("账号不存在或已删除")
    rights = account_permissions(request.user, target)
    if request.method == "DELETE":
        if not rights["can_delete"]:
            raise PermissionDenied("不能删除当前登录账号或权限范围之外的账号")
        if (
            target.is_superuser
            and get_user_model()
            .objects.filter(is_superuser=True, is_active=True)
            .count()
            <= 1
        ):
            raise ValidationError("至少保留一个可用的超级管理员")
        profile, _ = AccountProfile.objects.get_or_create(user=target)
        profile.deleted_at = timezone.now()
        profile.save(update_fields=["deleted_at", "updated_at"])
        target.is_active = False
        target.save(update_fields=["is_active"])
        AuditEvent.objects.create(
            actor=request.user,
            action="account.deleted",
            object_type="User",
            object_id=str(target.pk),
            detail={
                "username": target.username,
                "historical_authorship_retained": True,
            },
        )
        return Response(status=204)
    if not rights["can_edit"]:
        raise PermissionDenied("只能修改自己或管理范围内的账号")
    data = request.data
    allowed = {"username", "name", "email", "password", "active"}
    if set(data) - allowed:
        raise ValidationError("角色与部门授权请使用授权功能修改")
    before = {
        "username": target.username,
        "name": target.get_full_name(),
        "email": target.email,
        "active": target.is_active,
    }
    if "username" in data:
        username = str(data["username"]).strip()
        try:
            target._meta.get_field("username").run_validators(username)
        except DjangoValidationError as exc:
            raise ValidationError("；".join(exc.messages))
        if (
            not username
            or len(username) > 150
            or get_user_model()
            .objects.filter(username=username)
            .exclude(pk=target.pk)
            .exists()
        ):
            raise ValidationError("账号为空、过长或已被使用")
        target.username = username
    if "name" in data:
        name = str(data["name"]).strip()
        if not name or len(name) > 150:
            raise ValidationError("姓名需要1～150个字符")
        target.first_name = name
        target.last_name = ""
    if "email" in data:
        email = str(data["email"]).strip()
        try:
            target._meta.get_field("email").clean(email, target)
        except DjangoValidationError as exc:
            raise ValidationError("；".join(exc.messages))
        target.email = email
    if "active" in data:
        if not isinstance(data["active"], bool):
            raise ValidationError("启用状态必须为布尔值")
        if target.pk == request.user.pk and not data["active"]:
            raise ValidationError("不能停用当前登录账号")
        if target.is_superuser and not request.user.is_superuser:
            raise PermissionDenied("不能修改超级管理员")
        target.is_active = data["active"]
    changed_password = bool(data.get("password"))
    if changed_password:
        try:
            validate_password(str(data["password"]), target)
        except DjangoValidationError as exc:
            raise ValidationError("；".join(exc.messages))
        target.set_password(str(data["password"]))
    target.save()
    if changed_password and target.pk == request.user.pk:
        update_session_auth_hash(request, target)
    AuditEvent.objects.create(
        actor=request.user,
        action="account.updated",
        object_type="User",
        object_id=str(target.pk),
        detail={
            "before": before,
            "after": {
                "username": target.username,
                "name": target.get_full_name(),
                "email": target.email,
                "active": target.is_active,
            },
            "password_changed": changed_password,
        },
    )
    from .views import account_data

    return Response(
        {**account_data(target), **account_permissions(request.user, target)}
    )


def archive(actor, instance):
    instance.deleted_at = timezone.now()
    fields = ["deleted_at", "updated_at"]
    if hasattr(instance, "active"):
        instance.active = False
        fields.append("active")
    if hasattr(instance, "published"):
        instance.published = False
        fields.append("published")
    instance.save(update_fields=fields)
    AuditEvent.objects.create(
        actor=actor,
        action=f"{instance._meta.model_name}.deleted",
        object_type=type(instance).__name__,
        object_id=str(instance.pk),
        detail={
            "name": getattr(instance, "name", getattr(instance, "number", "")),
            "archived": True,
        },
    )


def can_manage_batch(user, batch):
    return (
        user.is_superuser
        or batch.created_by_id == user.pk
        or batch.competition.collaborators.filter(pk=user.pk).exists()
        or DepartmentMembership.objects.filter(
            user=user,
            role="admin",
            active=True,
            department__competitions=batch.competition,
        ).exists()
    )


def assert_batch_idle(batch):
    if (
        batch.status == AwardBatch.Status.QUEUED
        or batch.versions.filter(generation_task__status="running").exists()
    ):
        raise ValidationError("批次正在生成，请待任务完成后操作")
