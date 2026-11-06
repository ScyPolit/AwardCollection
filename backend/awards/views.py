import hashlib
import io
import random
import tempfile
import os
from pathlib import Path
import zipfile
from datetime import timedelta

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from PIL import Image, ImageDraw
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import connection, models, transaction, IntegrityError
from django.http import FileResponse, HttpResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from .models import (
    ApprovalDepartment, AuditEvent, AwardBatch, BatchVersion, Certificate, Competition,
    Department, DepartmentMembership, GenerationTask, LoginProtection, Notification,
    RevocationDecision, RevocationRequest, Seal, SealVersion, SystemSetting,
    TeamAward, Template, TemplateVersion, VerificationAttempt, CertificateFont,
)
from .serializers import (
    ApprovalSerializer, BatchSerializer, CertificateSerializer,
    CompetitionSerializer, DepartmentSerializer, NotificationSerializer,
    RevocationSerializer, SealSerializer, TemplateSerializer,
    UserOptionSerializer,
)
from .services import (
    decide, decide_revocation, emergency_void, excel_template, parse_excel,
    emergency_issue, request_revocation, revise_batch, submit_batch,
)
from .renderer import render_unsigned, _field_value
from .permissions import OWNER_GROUP, grant_owner, is_owner, is_department_admin, user_roles
from .fonts import font_catalog, font_file, import_font, layout_text, validate_canvas


def client_ip(request):
    return request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", "127.0.0.1")).split(",")[0].strip()


def accessible_competitions(user):
    if user.is_superuser:
        return Competition.objects.all()
    department_ids = DepartmentMembership.objects.filter(user=user, role="admin", active=True).values_list("department_id", flat=True)
    return Competition.objects.filter(models.Q(created_by=user) | models.Q(collaborators=user) | models.Q(departments__in=department_ids)).distinct()


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return Response({"status": "ok", "database": "ok", "version": settings.BUILD_VERSION})


@api_view(["GET"])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def csrf(request):
    return Response({"csrfToken": get_token(request)})


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    username = request.data.get("username", "").strip()
    user = get_user_model().objects.filter(username=username).first()
    protection = LoginProtection.objects.filter(user=user).first() if user else None
    if protection and protection.locked_until and protection.locked_until > timezone.now():
        return Response({"detail": "连续登录失败次数过多，请 15 分钟后重试"}, status=429)
    authenticated = authenticate(request, username=username, password=request.data.get("password", ""))
    if authenticated is None or not authenticated.is_active:
        if user:
            protection, _ = LoginProtection.objects.get_or_create(user=user)
            protection.failed_attempts += 1
            if protection.failed_attempts >= 5:
                protection.locked_until = timezone.now() + timedelta(minutes=15)
            protection.save()
        return Response({"detail": "用户名或密码错误"}, status=400)
    protection, _ = LoginProtection.objects.get_or_create(user=authenticated)
    protection.failed_attempts = 0
    protection.locked_until = None
    protection.save()
    login(request, authenticated)
    roles = user_roles(authenticated)
    expires = timezone.now() + timedelta(hours=8)
    return Response({"success": True, "data": {
        "username": authenticated.username,
        "nickname": authenticated.get_full_name() or authenticated.username,
        "avatar": "", "roles": roles or ["user"],
        "permissions": ["*:*:*"] if authenticated.is_superuser else [],
        "accessToken": "session", "refreshToken": "session", "expires": expires.isoformat(),
    }})


@api_view(["POST"])
def logout_view(request):
    logout(request)
    return Response({"success": True})


@api_view(["GET"])
def me(request):
    managed = Department.objects.all().values_list('id', flat=True) if request.user.is_superuser else DepartmentMembership.objects.filter(user=request.user, role='admin', active=True).values_list('department_id', flat=True)
    return Response({"username": request.user.username, "name": request.user.get_full_name() or request.user.username, "isSuperuser": request.user.is_superuser, "roles": user_roles(request.user), "managedDepartmentIds": list(managed)})


@api_view(["GET"])
def dashboard(request):
    competitions = accessible_competitions(request.user)
    batches = AwardBatch.objects.filter(competition__in=competitions).distinct()
    if request.user.is_superuser:
        approvals = ApprovalDepartment.objects.filter(
            version__batch__status=AwardBatch.Status.REVIEW,
            decision__isnull=True,
        )
    else:
        department_ids = DepartmentMembership.objects.filter(
            user=request.user, role=DepartmentMembership.Role.ADMIN, active=True,
        ).values_list("department_id", flat=True)
        approvals = ApprovalDepartment.objects.filter(
            department_id__in=department_ids,
            version__batch__status=AwardBatch.Status.REVIEW,
            decision__isnull=True,
        )
    month_start = timezone.localdate().replace(day=1)
    recent = Notification.objects.filter(user=request.user).order_by("-created_at")[:8]
    return Response({
        "pendingApprovals": approvals.count(),
        "runningTasks": GenerationTask.objects.filter(
            version__batch__in=batches,
            status__in=[GenerationTask.Status.QUEUED, GenerationTask.Status.RUNNING],
        ).count(),
        "issuedThisMonth": Certificate.objects.filter(
            award__version__batch__in=batches,
            published_at__date__gte=month_start,
        ).count(),
        "unreadNotifications": Notification.objects.filter(user=request.user, read_at__isnull=True).count(),
        "recent": NotificationSerializer(recent, many=True).data,
    })


@api_view(["GET", "PUT"])
def public_verification_setting(request):
    setting, _ = SystemSetting.objects.get_or_create(
        key="public_verification",
        defaults={"value": {"show_team": True, "show_members": True, "mask_members": True}},
    )
    if request.method == "GET":
        return Response(setting.value)
    if not request.user.is_superuser:
        return Response({"detail": "仅超管可修改全校公开设置"}, status=403)
    allowed = {"show_team", "show_members", "mask_members"}
    setting.value = {key: bool(request.data.get(key, setting.value.get(key, True))) for key in allowed}
    setting.save(update_fields=["value", "updated_at"])
    return Response(setting.value)


def account_data(user):
    return {
        "id": user.id, "username": user.username, "name": user.get_full_name(),
        "active": user.is_active, "superuser": user.is_superuser, "roles": user_roles(user),
        "joined_at": user.date_joined, "last_login": user.last_login,
        "memberships": list(DepartmentMembership.objects.filter(user=user, role="admin").values("id", "department_id", "department__name", "role", "active")),
    }


@api_view(["GET", "POST"])
@transaction.atomic
def account_management(request):
    if not is_department_admin(request.user):
        raise PermissionDenied("需要管理员权限")
    User = get_user_model()
    if request.method == "GET":
        users = User.objects.all()
        if not request.user.is_superuser:
            departments = DepartmentMembership.objects.filter(user=request.user, role="admin", active=True).values_list("department_id", flat=True)
            users = users.filter(models.Q(groups__name=OWNER_GROUP) | models.Q(departmentmembership__department_id__in=departments, departmentmembership__role="admin")).distinct()
        return Response([account_data(user) for user in users.order_by("username")])
    username = str(request.data.get("username", "")).strip()
    password = str(request.data.get("password", ""))
    name = str(request.data.get("name", "")).strip()
    role = request.data.get("role", "owner")
    if role not in ("admin", "owner"):
        raise ValidationError("角色无效")
    if not username or len(username) > 150 or len(name) > 150:
        raise ValidationError("账号或姓名为空或超过长度限制")
    candidate = User(username=username, first_name=name)
    try:
        User._meta.get_field("username").run_validators(username)
        validate_password(password, candidate)
    except DjangoValidationError as exc:
        raise ValidationError("；".join(exc.messages))
    department = None
    if role == "admin":
        if not request.user.is_superuser:
            raise PermissionDenied("只有超管可以创建部门管理员")
        department = Department.objects.filter(pk=request.data.get("department")).first()
        if not department:
            raise ValidationError("部门管理员需要选择管理部门")
    try:
        with transaction.atomic():
            user = User.objects.create_user(username=username, password=password, first_name=name)
            if role == "owner":
                grant_owner(user)
            else:
                DepartmentMembership.objects.create(user=user, department=department, role="admin")
            AuditEvent.objects.create(actor=request.user, action="account.created", object_type="User", object_id=str(user.pk), detail={"username": username, "role": role, "department": department.id if department else None})
    except IntegrityError:
        raise ValidationError("账号已存在，请使用其他账号名")
    return Response(account_data(user), status=201)


@api_view(["POST"])
@transaction.atomic
def membership_management(request):
    if not is_department_admin(request.user):
        raise PermissionDenied("需要管理员权限")
    users = get_user_model().objects
    user = users.filter(pk=request.data["user"]).first() if request.data.get("user") else users.filter(username=str(request.data.get("username", "")).strip()).first()
    role = request.data.get("role")
    if not user or role not in ("admin", "owner"):
        raise ValidationError("账号或角色无效")
    active = request.data.get("active", True)
    if not isinstance(active, bool):
        raise ValidationError("启用状态必须为布尔值")
    if role == "owner":
        if not active and not request.user.is_superuser:
            raise PermissionDenied("只有超管可以撤销全局负责人角色")
        if active:
            grant_owner(user)
        else:
            user.groups.remove(*user.groups.filter(name=OWNER_GROUP))
        object_type, object_id = "User", user.pk
        department = None
    else:
        if not request.user.is_superuser:
            raise PermissionDenied("只有超管可以授予部门管理员权限")
        department = Department.objects.filter(pk=request.data.get("department")).first()
        if not department:
            raise ValidationError("请选择管理部门")
        membership, _ = DepartmentMembership.objects.update_or_create(user=user, department=department, role="admin", defaults={"active": active})
        object_type, object_id = "DepartmentMembership", membership.pk
    AuditEvent.objects.create(actor=request.user, action="membership.updated", object_type=object_type, object_id=str(object_id), detail={"user": user.id, "department": department.id if department else None, "role": role, "active": active})
    return Response({"id": object_id, "active": active})


class DepartmentViewSet(ModelViewSet):
    serializer_class = DepartmentSerializer
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def perform_create(self, serializer):
        if not self.request.user.is_superuser:
            raise PermissionDenied("只有超管可以创建部门")
        serializer.save()

    def perform_update(self, serializer):
        if not self.request.user.is_superuser:
            raise PermissionDenied("只有超管可以修改部门")
        serializer.save()

    def get_queryset(self):
        if self.request.user.is_superuser or is_owner(self.request.user):
            return Department.objects.all().order_by("name")
        return Department.objects.filter(departmentmembership__user=self.request.user, departmentmembership__role="admin", departmentmembership__active=True).distinct().order_by("name")


class UserOptionViewSet(ReadOnlyModelViewSet):
    serializer_class = UserOptionSerializer

    def get_queryset(self):
        if self.request.user.is_superuser:
            return get_user_model().objects.filter(is_active=True).order_by("username")
        if is_owner(self.request.user) or is_department_admin(self.request.user):
            return get_user_model().objects.filter(groups__name=OWNER_GROUP, is_active=True).distinct().order_by("username")
        return get_user_model().objects.none()


class CompetitionViewSet(ModelViewSet):
    serializer_class = CompetitionSerializer

    def get_queryset(self):
        return accessible_competitions(self.request.user).prefetch_related("departments", "collaborators").order_by("-created_at")

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user
        if not (is_department_admin(user) or is_owner(user)):
            raise PermissionDenied("需要管理员或负责人权限")
        if not serializer.validated_data.get("departments"):
            raise ValidationError("至少选择一个拟盖章部门")
        competition = serializer.save(created_by=user, active=True)
        competition.collaborators.add(user)
        AuditEvent.objects.create(actor=user, action="competition.created", object_type="Competition", object_id=str(competition.pk), detail={"name": competition.name})

    @transaction.atomic
    def perform_update(self, serializer):
        competition = self.get_object()
        requested = serializer.validated_data
        if 'departments' in requested and not requested['departments']:
            raise ValidationError('至少选择一个拟盖章部门')
        if "active" in requested and not self.request.user.is_superuser:
            raise PermissionDenied("只有超管可以启用或废止竞赛")
        if requested.get("active") is False and competition.batches.filter(status=AwardBatch.Status.QUEUED).exists():
            raise ValidationError("仍有生成中的批次，请待任务完成后废止")
        if not self.request.user.is_superuser and (not competition.active or "departments" in requested):
            raise PermissionDenied("修改废止竞赛或盖章部门需要超管权限")
        previous = competition.active
        saved = serializer.save()
        AuditEvent.objects.create(actor=self.request.user, action="competition.updated", object_type="Competition", object_id=str(saved.pk), detail={"name": saved.name, "previous_active": previous, "active": saved.active})

    def perform_destroy(self, instance):
        raise ValidationError("请使用废止功能，竞赛及历史数据不能删除")


class BatchViewSet(ModelViewSet):
    serializer_class = BatchSerializer

    def get_queryset(self):
        return AwardBatch.objects.filter(competition__in=accessible_competitions(self.request.user)).select_related("competition").distinct().order_by("-created_at")

    @transaction.atomic
    def perform_create(self, serializer):
        competition = serializer.validated_data["competition"]
        if not accessible_competitions(self.request.user).filter(pk=competition.pk).exists():
            raise ValidationError("无权访问该竞赛")
        if not competition.active:
            raise ValidationError("竞赛已废止，不能新建批次")
        template = serializer.validated_data.pop("template_version", None)
        output_formats = serializer.validated_data.pop("output_formats", ["pdf", "png"])
        requested_seals = serializer.validated_data.pop("seal_versions", {})
        if template is None:
            template = TemplateVersion.objects.filter(template__published=True).order_by("-created_at").first()
        if template is None:
            raise ValidationError("请先创建并发布证书模板")
        selected = []
        for department in competition.departments.all():
            requested_id = requested_seals.get(str(department.id))
            seals = SealVersion.objects.filter(seal__department=department, seal__active=True)
            seal = seals.filter(pk=requested_id).first() if requested_id else seals.order_by("-number").first()
            if seal is None:
                raise ValidationError(f"{department.name} 没有选中有效的启用公章")
            selected.append((department, seal))
        batch = serializer.save(created_by=self.request.user)
        version = BatchVersion.objects.create(
            batch=batch, number=1, template_version=template,
            output_formats=output_formats,
            snapshot={
                "template": template.canvas,
                "template_version": template.id,
                "departments": [department.id for department, _ in selected],
                "seals": [seal.id for _, seal in selected],
                "output_formats": output_formats,
            },
        )
        for department, seal in selected:
            ApprovalDepartment.objects.create(version=version, department=department, seal_version=seal)

    @action(detail=True, methods=["get"], url_path="detail")
    def overview(self, request, pk=None):
        batch = self.get_object()
        version = BatchVersion.objects.get(batch=batch, number=batch.current_version)
        return Response({
            "batch": BatchSerializer(batch).data,
            "awards": list(version.awards.order_by("source_row").values("source_row", "members", "award_name", "team_name", "work_name", "category", "teachers", "note")),
            "approvals": ApprovalSerializer(version.required_departments.select_related("department", "version__batch__competition"), many=True).data,
            "configuration": {
                "template_version": version.template_version_id,
                "template_name": version.template_version.template.name,
                "output_formats": version.output_formats,
                "seals": {
                    str(item.department_id): item.seal_version_id
                    for item in version.required_departments.all()
                },
            },
        })

    @action(detail=True, methods=["post"], url_path="import")
    def import_awards(self, request, pk=None):
        batch = self.get_object()
        uploaded = request.FILES.get("file")
        if not uploaded:
            return Response({"detail": "请选择 XLSX 文件"}, status=400)
        rows, errors = parse_excel(uploaded)
        if errors:
            return Response({"errors": errors}, status=400)
        expected = int(request.data.get("expected_version", batch.current_version))
        try:
            if batch.versions.get(number=batch.current_version).awards.exists():
                version = revise_batch(batch.id, request.user, rows, expected)
            else:
                version = batch.versions.get(number=batch.current_version)
                TeamAward.objects.bulk_create([TeamAward(version=version, last_edited_by=request.user, **row) for row in rows])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response({"count": len(rows), "version": version.number})

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        try:
            version = submit_batch(self.get_object().id, request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"status": "review", "version": version.number})

    @action(detail=True, methods=["get"])
    def progress(self, request, pk=None):
        batch = self.get_object()
        version = BatchVersion.objects.get(batch=batch, number=batch.current_version)
        task = getattr(version, "generation_task", None)
        return Response(None if task is None else {"status": task.status, "processed": task.processed, "total": task.total, "attempts": task.attempts, "error": task.error})

    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        batch = self.get_object()
        version = BatchVersion.objects.get(batch=batch, number=batch.current_version)
        award = version.awards.order_by("source_row").first()
        if award is None:
            return Response({"detail": "请先导入名单"}, status=400)
        seals = [{
            "department_id": item.department_id,
            "seal_version_id": item.seal_version_id,
            "image": item.seal_version.image.path,
        } for item in version.required_departments.select_related("seal_version")]
        output = io.BytesIO()
        render_unsigned(
            award,
            "PREVIEW-ONLY",
            output,
            template=version.snapshot.get("template") or version.template_version.canvas,
            seals=seals,
        )
        return HttpResponse(output.getvalue(), content_type="application/pdf", headers={
            "Content-Disposition": f'inline; filename="batch-{batch.id}-preview.pdf"',
            "Cache-Control": "no-store",
        })

    @action(detail=True, methods=["post"], url_path="emergency-issue")
    def emergency_issue_action(self, request, pk=None):
        try:
            task = emergency_issue(
                self.get_object().id,
                request.user,
                request.data.get("reason", ""),
                request.data.get("password", ""),
            )
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=403)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"task": task.id, "status": task.status})


class ApprovalViewSet(ReadOnlyModelViewSet):
    serializer_class = ApprovalSerializer

    def get_queryset(self):
        user = self.request.user
        qs = ApprovalDepartment.objects.select_related("department", "version__batch__competition")
        if user.is_superuser:
            return qs.order_by("-created_at")
        departments = DepartmentMembership.objects.filter(user=user, role=DepartmentMembership.Role.ADMIN, active=True).values_list("department_id", flat=True)
        return qs.filter(department_id__in=departments, version__batch__status=AwardBatch.Status.REVIEW).order_by("-created_at")

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        try:
            task = decide(self.get_object().id, request.user, request.data.get("decision"), request.data.get("comment", ""))
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=403)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response({"accepted": True, "taskCreated": task is not None})


class TemplateViewSet(ModelViewSet):
    serializer_class = TemplateSerializer

    def get_queryset(self):
        queryset = Template.objects.all()
        if not self.request.user.is_superuser:
            departments = DepartmentMembership.objects.filter(
                user=self.request.user,
                role=DepartmentMembership.Role.ADMIN,
                active=True,
            ).values_list("department_id", flat=True)
            queryset = queryset.filter(models.Q(published=True) | models.Q(department_id__in=departments))
        return queryset.select_related("department").prefetch_related("versions").distinct().order_by("-updated_at")

    def can_manage(self, template):
        return self.request.user.is_superuser or DepartmentMembership.objects.filter(
            user=self.request.user,
            department=template.department,
            role=DepartmentMembership.Role.ADMIN,
            active=True,
        ).exists()

    @transaction.atomic
    def perform_create(self, serializer):
        department = serializer.validated_data["department"]
        if not self.request.user.is_superuser and not DepartmentMembership.objects.filter(user=self.request.user, department=department, role=DepartmentMembership.Role.ADMIN, active=True).exists():
            raise ValidationError("只能为本部门创建模板")
        try:
            canvas = validate_canvas(self.request.data.get("canvas", {}))
        except ValueError as exc:
            raise ValidationError(str(exc))
        template = serializer.save(created_by=self.request.user)
        TemplateVersion.objects.create(template=template, number=1, canvas=canvas)

    def perform_update(self, serializer):
        if not self.can_manage(self.get_object()):
            raise PermissionDenied("只能维护本部门的模板")
        serializer.save(department=self.get_object().department, created_by=self.get_object().created_by)

    def perform_destroy(self, instance):
        if not self.can_manage(instance):
            raise PermissionDenied("只能删除本部门的模板")
        if BatchVersion.objects.filter(template_version__template=instance).exists():
            raise ValidationError("模板已有批次使用，不能删除")
        instance.delete()

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def save_version(self, request, pk=None):
        template = self.get_object()
        if not request.user.is_superuser and not DepartmentMembership.objects.filter(user=request.user, department=template.department, role=DepartmentMembership.Role.ADMIN, active=True).exists():
            return Response({"detail": "只能维护本部门发布的模板"}, status=403)
        Template.objects.select_for_update().get(pk=template.pk)
        try:
            canvas = validate_canvas(request.data.get("canvas", {}))
        except ValueError as exc:
            raise ValidationError(str(exc))
        number = (template.versions.aggregate(models.Max("number"))["number__max"] or 0) + 1
        version = TemplateVersion.objects.create(template=template, number=number, canvas=canvas)
        AuditEvent.objects.create(actor=request.user, action="template.version_saved", object_type="Template", object_id=str(template.id), detail={"name": template.name, "version": number})
        return Response({"id": version.id, "number": version.number}, status=201)

    @action(detail=False, methods=["post"])
    def layout(self, request):
        try:
            canvas = validate_canvas(request.data.get("canvas", {}))
            sample = type("Sample", (), {"team_name": "测试专用团队", "members": ["张三", "李四"], "award_name": "一等奖", "work_name": "测试专用作品", "category": "创新类", "teachers": ["王老师"]})()
            result = {}
            for layer in canvas.get("layers", []):
                if layer["type"] == "text":
                    text = layer.get("text", "") if layer.get("field") == "static" else _field_value(sample, layer["field"], "2026-AC-00000001")
                    result[layer["id"]] = layout_text(text, layer)
            return Response(result)
        except (ValueError, KeyError, TypeError) as exc:
            raise ValidationError(str(exc))

    @action(detail=True, methods=["get"])
    def thumbnail(self, request, pk=None):
        import fitz
        from django.conf import settings
        template = self.get_object()
        versions = template.versions.all()
        version = versions.filter(pk=request.query_params['version']).first() if request.query_params.get('version') else versions.order_by('-number').first()
        if not version:
            raise ValidationError('模板没有可预览的版本')
        root = Path(settings.MEDIA_ROOT) / 'temporary' / 'template-thumbnails'
        root.mkdir(parents=True, exist_ok=True)
        target = root / f'{version.pk}-{settings.BUILD_VERSION[:12]}.png'
        if not target.exists():
            sample = type('Sample', (), {'team_name': '示例团队', 'members': ['张三', '李四'], 'award_name': '一等奖', 'work_name': '示例作品', 'category': '创新类', 'teachers': ['王老师']})()
            output = io.BytesIO()
            try:
                render_unsigned(sample, 'PREVIEW-ONLY', output, template=version.canvas)
                with fitz.open(stream=output.getvalue(), filetype='pdf') as document:
                    page = document[0]
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(640 / page.rect.width, 640 / page.rect.width))
                    with tempfile.NamedTemporaryFile(dir=root, suffix='.png', delete=False) as temporary:
                        temporary.write(pixmap.tobytes('png'))
                        temporary_name = temporary.name
                    os.replace(temporary_name, target)
            except ValueError as exc:
                raise ValidationError(str(exc))
        return FileResponse(target.open('rb'), content_type='image/png', headers={'Cache-Control': 'private, max-age=300'})

    @action(detail=True, methods=["post"])
    def copy(self, request, pk=None):
        source = self.get_object()
        department = Department.objects.get(pk=request.data.get("department"))
        if not request.user.is_superuser and not DepartmentMembership.objects.filter(user=request.user, department=department, role=DepartmentMembership.Role.ADMIN, active=True).exists():
            return Response({"detail": "无目标部门权限"}, status=403)
        target = Template.objects.create(name=request.data.get("name") or f"{source.name} - 副本", department=department, created_by=request.user, source=source, published=False)
        latest = source.versions.order_by("-number").first()
        TemplateVersion.objects.create(template=target, number=1, canvas=latest.canvas if latest else {})
        return Response(TemplateSerializer(target).data, status=201)


class SealViewSet(ModelViewSet):
    serializer_class = SealSerializer

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Seal.objects.all().select_related("department").prefetch_related("versions")
        memberships = DepartmentMembership.objects.filter(user=self.request.user, active=True)
        administered = memberships.filter(role=DepartmentMembership.Role.ADMIN).values_list("department_id", flat=True)
        allowed = models.Q(department_id__in=administered)
        if self.action in {"list", "retrieve", "preview"} and is_owner(self.request.user):
            allowed |= models.Q(active=True)
        return Seal.objects.filter(allowed).select_related("department").prefetch_related("versions")

    def perform_create(self, serializer):
        department = serializer.validated_data["department"]
        if not self.request.user.is_superuser and not DepartmentMembership.objects.filter(
            user=self.request.user,
            department=department,
            role=DepartmentMembership.Role.ADMIN,
            active=True,
        ).exists():
            raise ValidationError("只能为本部门创建公章")
        serializer.save()

    def perform_update(self, serializer):
        seal = self.get_object()
        serializer.save(department=seal.department)

    def perform_destroy(self, instance):
        if ApprovalDepartment.objects.filter(seal_version__seal=instance).exists():
            raise ValidationError("公章已有批次冻结使用，不能删除；可以停用")
        instance.delete()

    @action(detail=True, methods=["post"])
    def upload_version(self, request, pk=None):
        seal = self.get_object()
        uploaded = request.FILES.get("file")
        if not uploaded or not uploaded.content_type.startswith("image/"):
            return Response({"detail": "请选择图片文件"}, status=400)
        content = uploaded.read()
        if len(content) > 5 * 1024 * 1024:
            return Response({"detail": "图片不能超过 5MB"}, status=400)
        number = (seal.versions.aggregate(models.Max("number"))["number__max"] or 0) + 1
        version = SealVersion(seal=seal, number=number, sha256=hashlib.sha256(content).hexdigest())
        version.image.save(uploaded.name, ContentFile(content), save=True)
        AuditEvent.objects.create(actor=request.user, action="seal.uploaded", object_type="Seal", object_id=str(seal.id), detail={"name": seal.name, "version": number, "sha256": version.sha256})
        return Response({"id": version.id, "number": number}, status=201)

    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        seal = self.get_object()
        versions = seal.versions.all()
        version = versions.filter(pk=request.query_params['version']).first() if request.query_params.get('version') else versions.order_by('-number').first()
        if not version:
            raise ValidationError("没有可预览的公章版本")
        with version.image.open('rb') as source:
            try:
                image = Image.open(source).convert('RGBA')
                image.thumbnail((480, 480))
            except Exception:
                raise ValidationError("该版本不是可预览的图片")
        if not is_department_admin(request.user, seal.department):
            draw = ImageDraw.Draw(image)
            draw.text((12, max(12, image.height // 2)), 'PREVIEW ONLY', fill=(110, 110, 110, 210), stroke_width=1)
        output = io.BytesIO(); image.save(output, 'PNG')
        return HttpResponse(output.getvalue(), content_type='image/png', headers={'Cache-Control': 'private, no-store'})


class CertificateViewSet(ReadOnlyModelViewSet):
    serializer_class = CertificateSerializer

    def retrieve(self, request, *args, **kwargs):
        certificate = self.get_object()
        award = certificate.award
        data = CertificateSerializer(certificate).data
        data.update({"members": award.members, "work_name": award.work_name, "category": award.category,
                     "teachers": award.teachers, "note": award.note, "pdf_sha256": certificate.pdf_sha256,
                     "template": award.version.template_version.template.name,
                     "template_version": award.version.template_version.number,
                     "departments": list(award.version.required_departments.values_list("department__name", flat=True)),
                     "pdf_url": f"/api/v1/certificates/{certificate.pk}/download/pdf/?inline=1",
                     "image_url": f"/api/v1/certificates/{certificate.pk}/download/image/?inline=1" if certificate.image else None})
        return Response(data)

    def get_queryset(self):
        return Certificate.objects.filter(
            award__version__batch__competition__in=accessible_competitions(self.request.user),
            published_at__isnull=False,
        ).select_related("award__version__batch__competition").distinct().order_by("-created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        keyword = request.query_params.get("search", "").strip()
        if keyword:
            queryset = queryset.filter(
                models.Q(number__icontains=keyword)
                | models.Q(award__team_name__icontains=keyword)
                | models.Q(award__version__batch__competition__name__icontains=keyword)
            )
        try:
            page = max(1, int(request.query_params.get("page", 1)))
            page_size = min(100, max(1, int(request.query_params.get("page_size", 20))))
        except ValueError:
            return Response({"detail": "分页参数无效"}, status=400)
        count = queryset.count()
        start = (page - 1) * page_size
        return Response({
            "count": count,
            "page": page,
            "page_size": page_size,
            "results": CertificateSerializer(queryset[start:start + page_size], many=True).data,
        })

    @action(detail=False, methods=["get"], url_path="batch/(?P<batch_id>[^/.]+)/archive")
    def archive(self, request, batch_id=None):
        certificates = self.get_queryset().filter(award__version__batch_id=batch_id, published_at__isnull=False)
        if not certificates.exists():
            return Response({"detail": "没有可归档文件"}, status=404)
        output = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for certificate in certificates:
                if certificate.pdf:
                    archive.write(certificate.pdf.path, f"{certificate.number}.pdf")
                if certificate.image:
                    archive.write(certificate.image.path, f"{certificate.number}.png")
        output.seek(0)
        return FileResponse(output, as_attachment=True, filename=f"batch-{batch_id}-certificates.zip", content_type="application/zip")

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        try:
            item = request_revocation(self.get_object().id, request.user, request.data.get("reason", ""))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(RevocationSerializer(item).data, status=201)

    @action(detail=True, methods=["post"])
    def emergency_void(self, request, pk=None):
        try:
            certificate = emergency_void(self.get_object().id, request.user, request.data.get("reason", ""), request.data.get("password", ""))
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=403)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(CertificateSerializer(certificate).data)


class RevocationViewSet(ReadOnlyModelViewSet):
    serializer_class = RevocationSerializer

    def get_queryset(self):
        return RevocationRequest.objects.filter(certificate__award__version__batch__competition__in=accessible_competitions(self.request.user)).select_related("certificate__award__version").distinct().order_by("-created_at")

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        try:
            item = decide_revocation(self.get_object().id, int(request.data.get("department")), request.user, request.data.get("decision"), request.data.get("comment", ""))
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=403)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response(RevocationSerializer(item).data)


class NotificationViewSet(ModelViewSet):
    serializer_class = NotificationSerializer
    http_method_names = ["get", "patch"]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by("-created_at")


@api_view(["GET"])
def excel_template_view(request):
    response = HttpResponse(excel_template(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="award-import-template.xlsx"'
    return response


@api_view(["POST"])
def excel_validate_view(request):
    uploaded = request.FILES.get("file")
    if not uploaded:
        return Response({"detail": "请选择 XLSX 文件"}, status=400)
    try:
        rows, errors = parse_excel(uploaded)
    except (ValueError, KeyError) as exc:
        return Response({"detail": str(exc)}, status=400)
    return Response({"rows": rows, "errors": errors, "count": len(rows), "valid": not errors})


@api_view(["GET"])
@permission_classes([AllowAny])
def public_routes(request):
    return Response({"success": True, "data": []})


@api_view(["GET"])
@permission_classes([AllowAny])
def verification_challenge(request):
    left, right = random.randint(1, 9), random.randint(1, 9)
    request.session["verification_answer"] = left + right
    request.session["verification_used"] = False
    return Response({"question": f"{left} + {right} = ?"})


@api_view(["POST"])
@permission_classes([AllowAny])
def public_verify(request):
    ip = client_ip(request)
    cutoff = timezone.now() - timedelta(minutes=1)
    if VerificationAttempt.objects.filter(ip_address=ip, created_at__gte=cutoff).count() >= 10:
        return Response({"detail": "查询过于频繁，请稍后重试"}, status=429)
    number = request.data.get("number", "").strip()
    if request.session.get("verification_used", True) or str(request.data.get("answer", "")) != str(request.session.get("verification_answer", "missing")):
        VerificationAttempt.objects.create(ip_address=ip, certificate_number=number, successful=False)
        return Response({"detail": "验证码错误或已使用"}, status=400)
    request.session["verification_used"] = True
    certificate = Certificate.objects.select_related("award__version__batch__competition").filter(number=number, published_at__isnull=False).first()
    VerificationAttempt.objects.create(ip_address=ip, certificate_number=number, successful=certificate is not None)
    if certificate is None:
        return Response({"found": False})
    setting = SystemSetting.objects.filter(key="public_verification").first()
    config = setting.value if setting else {"show_team": True, "show_members": True, "mask_members": True}
    award = certificate.award
    result = {"found": True, "number": certificate.number, "status": certificate.status, "competition": award.version.batch.competition.name, "award": award.award_name}
    if config.get("show_team", True):
        result["team"] = award.team_name
    if config.get("show_members", True):
        result["members"] = [name[0] + "*" * max(1, len(name) - 1) for name in award.members] if config.get("mask_members", True) else award.members
    return Response(result)


@api_view(["POST"])
def admin_verify(request):
    certificate = Certificate.objects.select_related("award__version__batch__competition").filter(number=request.data.get("number", ""), published_at__isnull=False).first()
    if not certificate or not accessible_competitions(request.user).filter(pk=certificate.award.version.batch.competition_id).exists():
        return Response({"found": False})
    return Response({"found": True, "number": certificate.number, "status": certificate.status, "team": certificate.award.team_name, "members": certificate.award.members, "competition": certificate.award.version.batch.competition.name, "award": certificate.award.award_name})


@api_view(["GET"])
def certificate_download(request, certificate_id, kind):
    certificate = Certificate.objects.select_related("award__version__batch__competition").filter(
        pk=certificate_id, published_at__isnull=False,
    ).first()
    if not certificate or not accessible_competitions(request.user).filter(pk=certificate.award.version.batch.competition_id).exists():
        return Response({"detail": "无下载权限"}, status=403)
    field = certificate.pdf if kind == "pdf" else certificate.image
    if not field:
        return Response({"detail": "文件尚未生成"}, status=404)
    extension = "pdf" if kind == "pdf" else "png"
    return FileResponse(field.open("rb"), as_attachment=request.query_params.get("inline") != "1", filename=f"{certificate.number}.{extension}", content_type="application/pdf" if kind == "pdf" else "image/png")


@api_view(["GET", "POST"])
def fonts_view(request):
    if request.method == 'GET':
        return Response(font_catalog())
    if not is_department_admin(request.user):
        raise PermissionDenied('只有管理员可以导入字体')
    if request.data.get('license_confirmed') not in (True, 'true', '1'):
        raise ValidationError('请确认字体具备本系统使用、格式转换、嵌入和展示授权')
    uploaded = request.FILES.get('file')
    if not uploaded:
        raise ValidationError('请选择 TTF/TTC 字体文件')
    try:
        content, detected_name, digest = import_font(uploaded.read(40 * 1024 * 1024 + 1))
    except ValueError as exc:
        raise ValidationError(str(exc))
    name = str(request.data.get('name', '')).strip() or detected_name
    if len(name) > 160:
        raise ValidationError('字体名称过长')
    with transaction.atomic():
        font, created = CertificateFont.objects.get_or_create(sha256=digest, defaults={
            'name': name, 'file': ContentFile(content, name=digest + '.ttf'),
            'license_note': str(request.data.get('license_note', '管理员确认具备系统使用授权'))[:240], 'created_by': request.user,
        })
        if created:
            AuditEvent.objects.create(actor=request.user, action='font.imported', object_type='CertificateFont', object_id=digest, detail={'name': name, 'sha256': digest})
    return Response(next(item for item in font_catalog() if item['id'] == font.pk), status=201 if created else 200)


@api_view(["GET"])
def font_download(request, font_id):
    try:
        path = font_file(font_id)
    except ValueError as exc:
        raise ValidationError(str(exc))
    return FileResponse(path.open('rb'), content_type='font/ttf', headers={'Cache-Control': 'private, max-age=31536000, immutable'})


@api_view(["GET"])
def audit_logs(request, event_id=None):
    if not is_department_admin(request.user):
        raise PermissionDenied('需要管理员权限')
    events = AuditEvent.objects.select_related('actor').order_by('-created_at')
    if not request.user.is_superuser:
        events = events.filter(actor=request.user)
    def serialize(event):
        return {'id': event.id, 'created_at': event.created_at, 'actor': event.actor.username if event.actor else '系统/主机管理员',
                'action': event.action, 'object_type': event.object_type, 'object_id': event.object_id, 'detail': event.detail}
    if event_id is not None:
        event = events.filter(pk=event_id).first()
        if not event:
            return Response({'detail': '无此日志或无权限'}, status=404)
        return Response(serialize(event))
    try:
        page = max(1, int(request.query_params.get('page', 1)))
    except ValueError:
        raise ValidationError('页码无效')
    keyword = request.query_params.get('search', '').strip()
    if keyword:
        events = events.filter(models.Q(action__icontains=keyword) | models.Q(object_id__icontains=keyword) | models.Q(actor__username__icontains=keyword))
    return Response({'count': events.count(), 'results': [serialize(event) for event in events[(page - 1) * 30:page * 30]]})
