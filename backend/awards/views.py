import hashlib
import io
import random
import tempfile
import os
from pathlib import Path
import zipfile
from datetime import timedelta

from django.contrib.auth import authenticate, get_user_model, login, logout
from PIL import Image, ImageDraw
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import connection, models, transaction, IntegrityError
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_protect
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from .models import (
    ApprovalDepartment, AuditEvent, AwardBatch, BatchVersion, Certificate, Competition,
    Department, DepartmentMembership, GenerationTask, LoginProtection, Notification,
    RevocationDecision, RevocationRequest, Seal, SealVersion, SystemSetting,
    TeamAward, Template, TemplateVersion, VerificationAttempt, CertificateFont, AccountProfile,
)
from .serializers import (
    AccountCreateSerializer, ApprovalSerializer, BatchSerializer, CertificateSerializer,
    CompetitionSerializer, DepartmentSerializer, NotificationSerializer,
    RevocationSerializer, SealSerializer, TemplateSerializer,
    UserOptionSerializer,
)
from .services import (
    decide, decide_revocation, emergency_void, excel_template, parse_excel,
    emergency_issue, request_revocation, revise_batch, submit_batch, choose_approval_seal, UNSET,
)
from .renderer import render_unsigned, _field_value
from .permissions import OWNER_GROUP, grant_owner, is_owner, is_department_admin, user_roles
from .fonts import font_catalog, font_file, import_font, layout_text, validate_canvas
from .management_api import account_permissions, archive, can_manage_batch, assert_batch_idle
from .scopes import accessible_batches, accessible_versions, visible_certificates, managed_departments, visible_notifications
from .downloads import disk_response
from django.db.models.fields.json import KeyTextTransform, KeyTransform


def client_ip(request):
    return request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", "127.0.0.1")).split(",")[0].strip()


def accessible_competitions(user):
    from .scopes import accessible_competitions as scope
    return scope(user)


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
@csrf_protect
def login_view(request):
    username=request.data.get("username", "")
    password=request.data.get("password", "")
    if not isinstance(username,str) or not isinstance(password,str) or len(username)>150 or len(password)>1024:raise ValidationError("登录信息格式无效")
    username=username.strip()
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
    batches = accessible_batches(request.user)
    if request.user.is_superuser:
        approvals = ApprovalDepartment.objects.filter(
            version__batch__status=AwardBatch.Status.REVIEW,
            version__number=models.F("version__batch__current_version"), version__batch__deleted_at__isnull=True,
            decision__isnull=True,
        )
    else:
        department_ids = DepartmentMembership.objects.filter(
            user=request.user, role=DepartmentMembership.Role.ADMIN, active=True,
        ).values_list("department_id", flat=True)
        approvals = ApprovalDepartment.objects.filter(
            department_id__in=department_ids,
            version__batch__status=AwardBatch.Status.REVIEW,
            version__number=models.F("version__batch__current_version"), version__batch__deleted_at__isnull=True,
            decision__isnull=True,
        )
    month_start = timezone.localdate().replace(day=1)
    recent = visible_notifications(request.user).order_by("-created_at")[:8]
    return Response({
        "pendingApprovals": approvals.count(),
        "runningTasks": GenerationTask.objects.filter(
            version__batch__in=batches,
            status__in=[GenerationTask.Status.QUEUED, GenerationTask.Status.RUNNING],
        ).count(),
        "issuedThisMonth": Certificate.objects.filter(
            award__version__in=accessible_versions(request.user), deleted_at__isnull=True,
            published_at__date__gte=month_start,
        ).count(),
        "unreadNotifications": visible_notifications(request.user).filter(read_at__isnull=True).count(),
        "recent": NotificationSerializer(recent, many=True).data,
    })


@api_view(["GET", "PUT"])
def public_verification_setting(request):
    if not request.user.is_superuser:
        raise PermissionDenied('只有超级管理员可以管理查验设置')
    from .verification import configuration, validate_configuration
    if request.method == 'GET':
        return Response(configuration())
    value = validate_configuration(request.data)
    SystemSetting.objects.update_or_create(key='public_verification', defaults={'value': value})
    AuditEvent.objects.create(actor=request.user, action='verification.settings_updated', object_type='SystemSetting', object_id='public_verification', detail=value)
    return Response(value)


def account_data(user, actor=None):
    return {
        "id": user.id, "username": user.username, "name": user.get_full_name(), "email": user.email,
        **(account_permissions(actor, user) if actor else {}),
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
        users = User.objects.filter(management_profile__deleted_at__isnull=True)
        if not request.user.is_superuser:
            departments = DepartmentMembership.objects.filter(user=request.user, role="admin", active=True).values_list("department_id", flat=True)
            users = users.filter(models.Q(pk=request.user.pk) | models.Q(management_profile__created_by=request.user) | models.Q(management_profile__created_by__departmentmembership__department_id__in=departments, management_profile__created_by__departmentmembership__role="admin", management_profile__created_by__departmentmembership__active=True) | models.Q(departmentmembership__department_id__in=departments, departmentmembership__role="admin", departmentmembership__active=True)).distinct()
        return Response([account_data(user, request.user) for user in users.order_by("username")])
    serializer = AccountCreateSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    username, password, name, role = (data[key] for key in ("username", "password", "name", "role"))
    department = data.get("department")
    try:
        with transaction.atomic():
            user = User.objects.create_user(username=username, password=password, first_name=name)
            AccountProfile.objects.create(user=user, created_by=request.user)
            if role == "owner":
                grant_owner(user)
            else:
                DepartmentMembership.objects.create(user=user, department=department, role="admin")
            AuditEvent.objects.create(actor=request.user, action="account.created", object_type="User", object_id=str(user.pk), detail={"username": username, "role": role, "department": department.id if department else None})
    except IntegrityError:
        raise ValidationError("账号已存在，请使用其他账号名")
    return Response(account_data(user, request.user), status=201)


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
        if not request.user.is_superuser and (
            not user.is_active or user.is_superuser
            or not AccountProfile.objects.filter(user=user, created_by=request.user, deleted_at__isnull=True).exists()
            or is_department_admin(user)
        ):
            raise PermissionDenied("只能为本人创建的有效普通账号授予负责人角色")
        if active:
            grant_owner(user)
        else:
            user.groups.remove(*user.groups.filter(name=OWNER_GROUP))
        object_type, object_id = "User", user.pk
        department = None
    else:
        if not request.user.is_superuser:
            raise PermissionDenied("只有超管可以授予部门管理员权限")
        department = Department.objects.filter(pk=request.data.get("department"), deleted_at__isnull=True).first()
        if not department:
            raise ValidationError("请选择管理部门")
        membership, _ = DepartmentMembership.objects.update_or_create(user=user, department=department, role="admin", defaults={"active": active})
        object_type, object_id = "DepartmentMembership", membership.pk
    AuditEvent.objects.create(actor=request.user, action="membership.updated", object_type=object_type, object_id=str(object_id), detail={"user": user.id, "department": department.id if department else None, "role": role, "active": active})
    return Response({"id": object_id, "active": active})


class DepartmentViewSet(ModelViewSet):
    lookup_value_regex = r"[0-9]+"
    serializer_class = DepartmentSerializer
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

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
            return Department.objects.filter(deleted_at__isnull=True).order_by("name")
        return Department.objects.filter(deleted_at__isnull=True, departmentmembership__user=self.request.user, departmentmembership__role="admin", departmentmembership__active=True).distinct().order_by("name")


    def perform_destroy(self, instance):
        if not self.request.user.is_superuser: raise PermissionDenied("只有超管可以删除部门")
        if instance.competitions.filter(active=True, deleted_at__isnull=True).exists(): raise ValidationError("部门仍参与启用竞赛，请先调整竞赛盖章部门")
        archive(self.request.user, instance)


class UserOptionViewSet(ReadOnlyModelViewSet):
    lookup_value_regex = r"[0-9]+"
    serializer_class = UserOptionSerializer

    def get_queryset(self):
        from .scopes import collaborator_options
        return collaborator_options(self.request.user).order_by("username")


class CompetitionViewSet(ModelViewSet):
    lookup_value_regex = r"[0-9]+"
    serializer_class = CompetitionSerializer

    def get_queryset(self):
        return accessible_competitions(self.request.user).filter(deleted_at__isnull=True).prefetch_related("departments", "collaborators").order_by("-created_at")

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user
        if not (is_department_admin(user) or is_owner(user)):
            raise PermissionDenied("需要管理员或负责人权限")
        if not serializer.validated_data.get("departments"):
            raise ValidationError("至少选择一个拟盖章部门")
        if not user.is_superuser and is_department_admin(user):
            selected = {d.pk for d in serializer.validated_data["departments"]}
            if not selected.intersection(managed_departments(user)):
                raise PermissionDenied("新建竞赛必须包含本部门")
        competition = serializer.save(created_by=user, active=True)
        competition.collaborators.add(user)
        AuditEvent.objects.create(actor=user, action="competition.created", object_type="Competition", object_id=str(competition.pk), detail={"name": competition.name})

    @transaction.atomic
    def perform_update(self, serializer):
        competition = self.get_object()
        self.assert_current_department(competition)
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
        self.assert_current_department(instance)
        if instance.batches.filter(status=AwardBatch.Status.QUEUED).exists(): raise ValidationError("仍有生成中的批次")
        archive(self.request.user, instance)

    def assert_current_department(self, competition):
        user = self.request.user
        if not user.is_superuser and is_department_admin(user) and not competition.departments.filter(pk__in=managed_departments(user)).exists():
            raise PermissionDenied("历史会签仅授予历史记录查看权限，不能修改当前不属于本部门的竞赛")


class BatchViewSet(ModelViewSet):
    lookup_value_regex = r"[0-9]+"
    serializer_class = BatchSerializer

    def get_queryset(self):
        qs = accessible_batches(self.request.user).select_related("competition").order_by("-created_at")
        versions = BatchVersion.objects.filter(batch_id=models.OuterRef("pk"), number=models.OuterRef("current_version"))
        return qs.annotate(
            current_version_id=models.Subquery(versions.values("pk")[:1]),
            team_count_value=models.Count("versions__awards", filter=models.Q(versions__number=models.F("current_version")), distinct=True),
            required_count_value=models.Count("versions__required_departments", filter=models.Q(versions__number=models.F("current_version")), distinct=True),
            approved_count_value=models.Count("versions__required_departments", filter=models.Q(versions__number=models.F("current_version"), versions__required_departments__decision__decision="approved"), distinct=True),
        )

    @transaction.atomic
    def perform_create(self, serializer):
        competition = serializer.validated_data["competition"]
        if not accessible_competitions(self.request.user).filter(pk=competition.pk).exists():
            raise ValidationError("无权访问该竞赛")
        if not competition.active or competition.deleted_at:
            raise ValidationError("竞赛已废止或删除，不能新建批次")
        if not self.request.user.is_superuser and is_department_admin(self.request.user) and not competition.departments.filter(pk__in=managed_departments(self.request.user)).exists():
            raise PermissionDenied("只能为本部门参与的竞赛新建批次")
        template = serializer.validated_data.pop("template_version", None)
        output_formats = serializer.validated_data.pop("output_formats", ["pdf", "png"])
        requested_seals = serializer.validated_data.pop("seal_versions", {})
        if requested_seals and not is_department_admin(self.request.user):
            raise PermissionDenied("负责人不能选择公章版本，请交由各部门管理员审批时确认")
        allowed_ids = set(competition.departments.values_list("pk", flat=True))
        if not self.request.user.is_superuser:
            allowed_ids.intersection_update(managed_departments(self.request.user))
        if set(requested_seals) - {str(pk) for pk in allowed_ids}:
            raise PermissionDenied("只能选择本人管理部门的公章")
        if template is None:
            from .prepared import template_versions_for
            template = template_versions_for(self.request.user).order_by("-created_at").first()
        if template is None:
            raise ValidationError("请先创建自己的模板或选择共享模板")
        selected = []
        for department in competition.departments.all():
            requested_id = requested_seals.get(str(department.id))
            seals = SealVersion.objects.filter(seal__department=department, seal__active=True, seal__deleted_at__isnull=True)
            seal = seals.filter(pk=requested_id).first() if requested_id else None
            if requested_id and seal is None:
                raise ValidationError(f"{department.name} 所选公章无效或已停用")
            selected.append((department, seal))
        batch = serializer.save(created_by=self.request.user)
        version = BatchVersion.objects.create(
            batch=batch, number=1, template_version=template,
            output_formats=output_formats,
            snapshot={
                "template": template.canvas,
                "competition": {"id": competition.id, "name": competition.name},
                "issue_date": timezone.localdate().isoformat(),
                "template_version": template.id,
                "departments": [department.id for department, _ in selected],
                "department_details": [{"id":department.id,"name":department.name} for department,_ in selected],
                "seals": [seal.id if seal else None for _, seal in selected],
                "output_formats": output_formats,
            },
        )
        for department, seal in selected:
            ApprovalDepartment.objects.create(version=version, department=department, seal_version=seal)

    def perform_update(self, serializer):
        batch = self.get_object()
        if not can_manage_batch(self.request.user, batch): raise PermissionDenied("无权修改批次")
        if set(serializer.validated_data) - {'name'}: raise ValidationError("此处只能修改批次名称，名单请在批次详情修订")
        saved=serializer.save()
        AuditEvent.objects.create(actor=self.request.user, action='batch.updated', object_type='AwardBatch', object_id=str(saved.pk), detail={'name':saved.name})

    def perform_destroy(self, instance):
        if not can_manage_batch(self.request.user, instance): raise PermissionDenied("无权删除批次")
        assert_batch_idle(instance)
        archive(self.request.user, instance)

    @action(detail=True, methods=['post'])
    def rows(self, request, pk=None):
        batch=self.get_object()
        if not can_manage_batch(request.user,batch): raise PermissionDenied('无权修订名单')
        if batch.status not in ('draft','returned'): raise ValidationError('只能编辑草稿或已退回批次的名单')
        version=batch.versions.get(number=batch.current_version)
        from .serializers import AwardSerializer
        rows=list(AwardSerializer(version.awards.order_by('source_row'),many=True).data)
        operation=request.data.get('operation'); source=request.data.get('source_row')
        if operation not in ('create','update','delete','bulk_delete'): raise ValidationError('名单操作无效')
        if operation == 'bulk_delete':
            sources = request.data.get('source_rows')
            if not isinstance(sources, list) or not 1 <= len(sources) <= 200 or any(not isinstance(n, int) or isinstance(n, bool) for n in sources):
                raise ValidationError('请选择1～200行名单')
            sources = set(sources)
            if sources - {r['source_row'] for r in rows}:
                raise ValidationError('名单行已变化，请刷新后重选')
            rows = [r for r in rows if r['source_row'] not in sources]
        elif operation=='create':
            row=dict(request.data.get('row',{}));row['source_row']=max([r['source_row'] for r in rows]+[1])+1
            parsed=AwardSerializer(data=row);parsed.is_valid(raise_exception=True);rows.append(dict(parsed.validated_data))
        else:
            index=next((i for i,r in enumerate(rows) if r['source_row']==source),None)
            if index is None: raise ValidationError('名单行不存在')
            if operation=='delete': rows.pop(index)
            else:
                row={**rows[index],**request.data.get('row',{}),'source_row':source}
                parsed=AwardSerializer(data=row);parsed.is_valid(raise_exception=True);rows[index]=dict(parsed.validated_data)
        for row in rows:
            if not row['members'] or not row['award_name'].strip():raise ValidationError('成员和奖项不能为空')
        try: updated=revise_batch(batch.pk,request.user,rows,int(request.data.get('expected_version',-1)))
        except ValueError as exc: raise ValidationError(str(exc))
        return Response({'version':updated.number,'count':len(rows)})

    @action(detail=True, methods=["get"], url_path="detail")
    def overview(self, request, pk=None):
        batch = self.get_object()
        version = BatchVersion.objects.only("pk", "number", "template_version_id", "output_formats", "updated_at").get(batch=batch, number=batch.current_version)
        try:
            page = max(1, int(request.query_params.get("page", 1)))
            size = min(100, max(1, int(request.query_params.get("page_size", 50))))
        except ValueError:
            raise ValidationError("分页参数无效")
        awards = version.awards.order_by("source_row")
        requirements = version.required_departments.select_related("department", "version__batch__competition", "seal_version__seal", "decision__actor").defer("version__snapshot").order_by("department_id")
        metadata = TemplateVersion.objects.values("template__name").get(pk=version.template_version_id)
        return Response({
            "batch": BatchSerializer(batch).data,
            "can_manage": can_manage_batch(request.user, batch),
            "awards": list(awards.values("source_row", "members", "award_name", "team_name", "work_name", "category", "teachers", "note")[(page-1)*size:page*size]),
            "award_count": awards.count(), "page": page, "page_size": size,
            "approvals": ApprovalSerializer(requirements, many=True, context={"request": request}).data,
            "configuration": {"template_version": version.template_version_id, "template_name": metadata["template__name"], "output_formats": version.output_formats, "preview_revision": version.updated_at.isoformat(),
                              "seals": {str(item.department_id): item.seal_version_id for item in requirements if request.user.is_superuser or item.department_id in managed_departments(request.user)}}})

    @action(detail=True, methods=["post"], url_path="import")
    @transaction.atomic
    def import_awards(self, request, pk=None):
        batch = self.get_object()
        if not can_manage_batch(request.user,batch): raise PermissionDenied("无权修订名单")
        if batch.status not in ("draft","returned"): raise ValidationError("只能编辑草稿或已退回批次的名单")
        uploaded = request.FILES.get("file")
        if not uploaded:
            return Response({"detail": "请选择 XLSX 文件"}, status=400)
        rows, errors = parse_excel(uploaded)
        if errors:
            return Response({"errors": errors}, status=400)
        try:expected = int(request.data.get("expected_version", batch.current_version))
        except (ValueError,TypeError):raise ValidationError("名单版本无效")
        try:
            if batch.versions.get(number=batch.current_version).awards.exists():
                version = revise_batch(batch.id, request.user, rows, expected)
            else:
                locked=AwardBatch.objects.select_for_update().get(pk=batch.pk)
                if locked.current_version!=expected or locked.status not in ("draft","returned"):raise ValueError("版本或状态已变化，请重新载入")
                version = locked.versions.get(number=locked.current_version)
                TeamAward.objects.bulk_create([TeamAward(version=version, last_edited_by=request.user, **row) for row in rows])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response({"count": len(rows), "version": version.number})

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        batch=self.get_object()
        if not can_manage_batch(request.user,batch):raise PermissionDenied("无权提交该批次")
        try:
            expected = request.data.get('expected_version')
            if expected is not None and (not isinstance(expected, int) or isinstance(expected, bool)):
                raise ValueError('名单版本无效，请刷新后重试')
            version = submit_batch(batch.id, request.user, expected_version=expected)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"status": "review", "version": version.number})

    @action(detail=True,methods=['post'])
    @transaction.atomic
    def retry_generation(self,request,pk=None):
        batch=self.get_object()
        if not can_manage_batch(request.user,batch):raise PermissionDenied('无权重试此批次')
        version=batch.versions.get(number=batch.current_version)
        task=GenerationTask.objects.select_for_update().filter(version=version,status='failed').first()
        if not task:raise ValidationError('只有失败的生成任务可以重试')
        from .integrity import verify
        try:verify(version)
        except ValueError as exc:raise ValidationError(str(exc))
        if version.required_departments.exclude(decision__decision='approved').exists():raise ValidationError('缺少完整部门会签')
        task.status='queued';task.error='';task.lease_token=None;task.lease_expires_at=None;task.save()
        batch.status='queued';batch.save(update_fields=['status','updated_at'])
        AuditEvent.objects.create(actor=request.user,action='generation.retried',object_type='AwardBatch',object_id=str(batch.pk))
        return Response({'status':'queued'})

    @action(detail=True, methods=["get"])
    def progress(self, request, pk=None):
        batch = self.get_object()
        version = BatchVersion.objects.get(batch=batch, number=batch.current_version)
        task = getattr(version, "generation_task", None)
        return Response(None if task is None else {"status": task.status, "processed": task.processed, "total": task.total, "attempts": task.attempts, "error": task.error})

    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        from .prepared import request_file, download_view, waiting_response
        batch = self.get_object()
        asset = request_file(request.user, "batch_preview", batch_id=batch.pk)
        if asset.status == "ready":
            from django.http import HttpResponseRedirect
            return HttpResponseRedirect(f"/api/v1/prepared-files/{asset.pk}/download/")
        return waiting_response(asset)

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
    lookup_value_regex = r"[0-9]+"
    serializer_class = ApprovalSerializer

    def get_queryset(self):
        qs = ApprovalDepartment.objects.filter(version__batch__deleted_at__isnull=True).select_related("department", "version__batch__competition", "seal_version__seal", "decision__actor").defer("version__snapshot")
        if self.action == 'list' and self.request.query_params.get('scope') == 'approved':
            qs = qs.filter(decision__decision='approved', version__number=models.F('version__batch__current_version'))
        elif self.action != 'withdraw':
            qs = qs.filter(version__batch__status=AwardBatch.Status.REVIEW, version__number=models.F('version__batch__current_version'))
        if not self.request.user.is_superuser:
            if is_department_admin(self.request.user):
                qs = qs.filter(department_id__in=managed_departments(self.request.user))
            else:
                qs = qs.filter(version__in=accessible_versions(self.request.user))
        return qs.order_by("-created_at")

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        try:
            task = decide(self.get_object().id, request.user, request.data.get("decision"), request.data.get("comment", ""),
                          seal_version_id=request.data.get("seal_version", UNSET), expected_seal_version=request.data.get("expected_seal_version", UNSET), issue_rows=request.data.get("issue_rows"))
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=403)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response({"accepted": True, "taskCreated": task is not None})

    @action(detail=True, methods=['post'])
    def withdraw(self, request, pk=None):
        from .services import withdraw_approval
        try:
            return Response(withdraw_approval(self.get_object().pk, request.user, request.data.get('reason', '')))
        except PermissionError as exc:
            raise PermissionDenied(str(exc))
        except ValueError as exc:
            return Response({'detail':str(exc)},status=409)

    @action(detail=True, methods=["post"], url_path="seal")
    def select_seal(self, request, pk=None):
        try:
            requirement = choose_approval_seal(self.get_object().pk, request.user, request.data.get("seal_version"), request.data.get("expected_seal_version", UNSET))
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=403)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response(ApprovalSerializer(requirement, context={"request": request}).data)

    @action(detail=False, methods=["post"], url_path="bulk-decide")
    @transaction.atomic
    def bulk_decide(self, request):
        items = request.data.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 50 or any(not isinstance(item, dict) or not isinstance(item.get("id"), int) or isinstance(item.get("id"), bool) for item in items):
            raise ValidationError("请选择1～50项待审批记录")
        ids = [item['id'] for item in items]
        if len(set(ids)) != len(ids):
            raise ValidationError("不能重复选择审批记录")
        visible = dict(self.get_queryset().filter(pk__in=ids).values_list('pk', 'version__batch_id'))
        if set(visible) != set(ids):
            raise PermissionDenied("所选审批已结束或无权处理，请刷新后重选")
        seen, count = set(), 0
        try:
            for item in sorted(items, key=lambda r: (visible[r['id']], r['id'])):
                if request.data.get('decision') == 'returned' and visible[item['id']] in seen:
                    continue
                decide(item['id'], request.user, request.data.get('decision'), request.data.get('comment', ''),
                       seal_version_id=item.get('seal_version', UNSET), expected_seal_version=item.get('expected_seal_version', UNSET))
                seen.add(visible[item['id']]); count += 1
        except PermissionError as exc:
            raise PermissionDenied(str(exc))
        except ValueError as exc:
            raise ValidationError(str(exc))
        return Response({'count': count})


class TemplateViewSet(ModelViewSet):
    lookup_value_regex = r"[0-9]+"
    serializer_class = TemplateSerializer

    def get_queryset(self):
        from .scopes import accessible_templates
        qs = accessible_templates(self.request.user)
        qs = qs.select_related("department").order_by("-updated_at")
        if self.action == "list":
            qs = qs.prefetch_related(models.Prefetch("versions", queryset=TemplateVersion.objects.only("id", "template_id", "number", "created_at", "summary").order_by("-number"), to_attr="light_versions"))
        return qs

    def can_manage(self, template):
        from .permissions import can_manage_template
        return can_manage_template(self.request.user, template)

    def can_edit(self, template):
        return self.can_manage(template)

    def target_scope(self, department):
        return Template.Scope.DEPARTMENT if is_department_admin(self.request.user, department) else Template.Scope.PERSONAL

    @transaction.atomic
    def perform_create(self, serializer):
        department = serializer.validated_data["department"]
        if not is_owner(self.request.user) and not self.request.user.is_superuser and not DepartmentMembership.objects.filter(user=self.request.user, department=department, role=DepartmentMembership.Role.ADMIN, active=True).exists():
            raise ValidationError("只能为本部门创建模板")
        try:
            canvas = validate_canvas(self.request.data.get("canvas", {}))
        except ValueError as exc:
            raise ValidationError(str(exc))
        template = serializer.save(created_by=self.request.user, scope=self.target_scope(department))
        TemplateVersion.objects.create(template=template, number=1, canvas=canvas)

    def perform_update(self, serializer):
        if not self.can_manage(self.get_object()):
            raise PermissionDenied("只能维护自己的模板或有管理权限的部门模板；共享模板请先复制")
        serializer.save(department=self.get_object().department, created_by=self.get_object().created_by)

    def perform_destroy(self, instance):
        if not self.can_manage(instance): raise PermissionDenied("只能删除管理范围内的模板")
        if BatchVersion.objects.filter(template_version__template=instance, batch__status__in=['review','queued'], batch__deleted_at__isnull=True).exists():
            raise ValidationError("模板仍被审批或生成中的批次使用")
        archive(self.request.user, instance)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def save_version(self, request, pk=None):
        template = self.get_object()
        if not self.can_edit(template):
            raise PermissionDenied('无此模板的编辑权限')
        Template.objects.select_for_update().get(pk=template.pk)
        try:
            canvas = validate_canvas(request.data.get("canvas", {}))
        except ValueError as exc:
            raise ValidationError(str(exc))
        latest_number = template.versions.aggregate(models.Max("number"))["number__max"] or 0
        if request.data.get("expected_version") is not None and request.data["expected_version"] != latest_number:
            return Response({"detail":"模板已被其他人修改，请重新载入后编辑"},status=409)
        number = latest_number + 1
        version = TemplateVersion.objects.create(template=template, number=number, canvas=canvas)
        Template.objects.filter(pk=template.pk).update(updated_at=timezone.now())
        AuditEvent.objects.create(actor=request.user, action="template.version_saved", object_type="Template", object_id=str(template.id), detail={"name": template.name, "version": number})
        return Response({"id": version.id, "number": version.number}, status=201)

    @action(detail=False, methods=["post"])
    def import_file(self, request):
        from .permissions import can_edit_templates
        if not can_edit_templates(request.user):raise PermissionDenied("需要模板编辑权限")
        uploaded=request.FILES.get('file')
        if not uploaded:raise ValidationError('请选择模板文件')
        from .template_import import import_file
        try:return Response(import_file(uploaded))
        except ValueError as exc:raise ValidationError(str(exc))

    @action(detail=False, methods=["post"])
    def layout(self, request):
        try:
            canvas = validate_canvas(request.data.get("canvas", {}))
            sample = type("Sample", (), {"team_name": "示例团队", "members": ["张三", "李四"], "award_name": "一等奖", "work_name": "示例作品", "category": "创新类", "teachers": ["王老师"]})()
            result = {}
            for layer in canvas.get("layers", []):
                if layer["type"] == "text":
                    text = layer.get("text", "") if layer.get("field") == "static" else _field_value(sample, layer["field"], "2026AC00000001")
                    result[layer["id"]] = layout_text(text, layer)
            return Response(result)
        except (ValueError, KeyError, TypeError) as exc:
            raise ValidationError(str(exc))

    @action(detail=True, methods=["get"])
    def thumbnail(self, request, pk=None):
        from .prepared import request_file, waiting_response
        from django.http import HttpResponseRedirect
        template = self.get_object()
        versions = template.versions.only("pk", "number")
        version = versions.filter(pk=request.query_params["version"]).first() if request.query_params.get("version") else versions.order_by("-number").first()
        if not version:
            raise ValidationError("模板没有可预览版本")
        asset = request_file(request.user, "template_thumbnail", template_version_id=version.pk)
        if asset.status == "ready":
            return HttpResponseRedirect(f"/api/v1/prepared-files/{asset.pk}/download/")
        return waiting_response(asset)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def copy(self, request, pk=None):
        from .permissions import can_edit_templates
        if not can_edit_templates(request.user):
            raise PermissionDenied("需要模板编辑权限")
        source = self.get_object()
        department = get_object_or_404(Department,pk=request.data.get("department"),deleted_at__isnull=True)
        if not is_owner(request.user) and not request.user.is_superuser and not DepartmentMembership.objects.filter(user=request.user, department=department, role=DepartmentMembership.Role.ADMIN, active=True).exists():
            return Response({"detail": "无目标部门权限"}, status=403)
        name = str(request.data.get("name") or f"{source.name} 副本").strip()
        if not name or len(name) > 160:
            raise ValidationError("模板名称应为 1 至 160 个字符")
        target = Template.objects.create(name=name, department=department, created_by=request.user, source=source, published=False, scope=self.target_scope(department))
        latest = source.versions.order_by("-number").first()
        TemplateVersion.objects.create(template=target, number=1, canvas=latest.canvas if latest else {})
        return Response(self.get_serializer(target).data, status=201)


class SealViewSet(ModelViewSet):
    lookup_value_regex = r"[0-9]+"
    serializer_class = SealSerializer

    def get_queryset(self):
        if not is_department_admin(self.request.user):
            raise PermissionDenied("负责人无公章管理权限")
        qs = Seal.objects.filter(deleted_at__isnull=True)
        if not self.request.user.is_superuser:
            qs = qs.filter(department_id__in=managed_departments(self.request.user))
        return qs.select_related("department").prefetch_related("versions")

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
        if not is_department_admin(self.request.user, instance.department): raise PermissionDenied("只能删除本部门公章")
        if ApprovalDepartment.objects.filter(seal_version__seal=instance, version__batch__status__in=['review','queued'], version__batch__deleted_at__isnull=True).exists():
            raise ValidationError("公章仍被审批或生成中的批次使用")
        archive(self.request.user, instance)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def upload_version(self, request, pk=None):
        seal = self.get_object()
        uploaded = request.FILES.get("file")
        if not uploaded or not uploaded.content_type.startswith("image/"):
            return Response({"detail": "请选择图片文件"}, status=400)
        content = uploaded.read(5*1024*1024+1)
        if len(content) > 5 * 1024 * 1024:
            return Response({"detail": "图片不能超过 5MB"}, status=400)
        try:
            with Image.open(io.BytesIO(content)) as source:
                if source.width*source.height>16_000_000:raise ValueError('公章图片像素过大')
                source.load();output=io.BytesIO();source.convert('RGBA').save(output,'PNG');content=output.getvalue()
        except (OSError,ValueError,Image.DecompressionBombError):raise ValidationError('请选择有效的PNG/JPG公章图片，最大1600万像素')
        Seal.objects.select_for_update().get(pk=seal.pk)
        number = (seal.versions.aggregate(models.Max("number"))["number__max"] or 0) + 1
        version = SealVersion(seal=seal, number=number, sha256=hashlib.sha256(content).hexdigest())
        version.image.save(f'seal-{seal.pk}-v{number}.png', ContentFile(content), save=True)
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


class CertificateViewSet(ModelViewSet):
    lookup_value_regex = r"[0-9]+"
    http_method_names=["get","post","patch","delete","head","options"]
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
        return visible_certificates(self.request.user).select_related("award__version__batch__competition").defer("award__version__snapshot").annotate(
            frozen_competition_name=KeyTextTransform("name", KeyTransform("competition", "award__version__snapshot"))
        ).order_by("-created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.filtered_certificates(request)
        page, page_size = self.page_parameters(request)
        count = queryset.count()
        start = (page - 1) * page_size
        return Response({"count": count, "page": page, "page_size": page_size,
                         "results": CertificateSerializer(queryset[start:start + page_size], many=True).data})

    def filtered_certificates(self, request):
        queryset = self.get_queryset()
        keyword = request.query_params.get("search", "").strip()
        if keyword:
            queryset = queryset.filter(
                models.Q(number__icontains=keyword)
                | models.Q(award__team_name__icontains=keyword)
                | models.Q(award__version__batch__competition__name__icontains=keyword)
                | models.Q(award__version__batch__name__icontains=keyword)
            )
        if request.query_params.get("batch"):
            try:
                batch_id = int(request.query_params["batch"])
            except (ValueError, TypeError):
                raise ValidationError("批次编号无效")
            queryset = queryset.filter(award__version__batch_id=batch_id)
        return queryset

    def page_parameters(self, request):
        try:
            page = max(1, int(request.query_params.get("page", 1)))
            page_size = min(100, max(1, int(request.query_params.get("page_size", 20))))
        except ValueError:
            raise ValidationError("分页参数无效")
        return page, page_size

    @action(detail=False, methods=["get"], url_path="batches")
    def batch_tree(self, request):
        queryset = self.filtered_certificates(request).order_by().values(
            "award__version__batch_id", "award__version__batch__name", "award__version__batch__competition__name"
        ).annotate(certificate_count=models.Count("pk"), active_count=models.Count("pk", filter=models.Q(status="active")), last_issued=models.Max("published_at")).order_by("-last_issued", "-award__version__batch_id")
        page, size = self.page_parameters(request)
        return Response({"count": queryset.count(), "page": page, "page_size": size,
                         "results": [{"id": r["award__version__batch_id"], "name": r["award__version__batch__name"], "competition_name": r["award__version__batch__competition__name"],
                                      "certificate_count": r["certificate_count"], "active_count": r["active_count"], "last_issued": r["last_issued"]} for r in queryset[(page-1)*size:page*size]]})

    def create(self, request, *args, **kwargs):
        raise PermissionDenied('证书只能由审批通过的生成任务签发')

    def perform_update(self, serializer):
        certificate=self.get_object()
        if not is_department_admin(self.request.user): raise PermissionDenied('需要管理员权限')
        if set(self.request.data)-{'notes'}:raise ValidationError('签发正文不可覆盖，请创建更正批次重新会签')
        serializer.save()
        AuditEvent.objects.create(actor=self.request.user,action='certificate.note_updated',object_type='Certificate',object_id=str(certificate.pk),detail={'notes':serializer.validated_data.get('notes','')})

    def perform_destroy(self, instance):
        if not is_department_admin(self.request.user):raise PermissionDenied('需要管理员权限')
        if instance.revocation_requests.filter(status='review').exists():raise ValidationError('请先完成作废审批')
        archive(self.request.user,instance)

    @action(detail=True,methods=['post'])
    @transaction.atomic
    def correction(self, request, pk=None):
        original=self.get_object();source=original.award;previous=source.version
        if not can_manage_batch(request.user, previous.batch):raise PermissionDenied('无权更正此证书')
        from .serializers import AwardSerializer
        row={**AwardSerializer(source).data,**request.data.get('row',{}),'source_row':2}
        parsed=AwardSerializer(data=row);parsed.is_valid(raise_exception=True)
        batch=AwardBatch.objects.create(name=f'更正 {original.number}',competition=previous.batch.competition,created_by=request.user)
        version=BatchVersion.objects.create(batch=batch,number=1,template_version=previous.template_version,output_formats=previous.output_formats,snapshot={**previous.snapshot,'correction_of':original.pk})
        for requirement in previous.required_departments.all():ApprovalDepartment.objects.create(version=version,department=requirement.department,seal_version=requirement.seal_version)
        TeamAward.objects.create(version=version,last_edited_by=request.user,**parsed.validated_data)
        AuditEvent.objects.create(actor=request.user,action='certificate.correction_created',object_type='Certificate',object_id=str(original.pk),detail={'batch':batch.pk})
        return Response({'batch':batch.pk,'name':batch.name},status=201)

    @action(detail=False, methods=["get"], url_path="batch/(?P<batch_id>[^/.]+)/archive")
    def archive(self, request, batch_id=None):
        from .prepared import request_file, waiting_response
        from django.http import HttpResponseRedirect
        asset = request_file(request.user, "batch_zip", batch_id=batch_id)
        if asset.status == "ready":
            return HttpResponseRedirect(f"/api/v1/prepared-files/{asset.pk}/download/")
        return waiting_response(asset)

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
    lookup_value_regex = r"[0-9]+"
    serializer_class = RevocationSerializer

    def get_queryset(self):
        return RevocationRequest.objects.filter(certificate__in=visible_certificates(self.request.user)).select_related("certificate__award__version").defer("certificate__award__version__snapshot").distinct().order_by("-created_at")

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        try:
            item = decide_revocation(self.get_object().id, int(request.data.get("department")), request.user, request.data.get("decision"), request.data.get("comment", ""))
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=403)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response(RevocationSerializer(item).data)

    @action(detail=False, methods=['post'], url_path='bulk-decide')
    @transaction.atomic
    def bulk_decide(self, request):
        ids = request.data.get('ids')
        if not isinstance(ids, list) or not 1 <= len(ids) <= 50 or any(not isinstance(pk, int) or isinstance(pk, bool) for pk in ids):
            raise ValidationError('请选择1～50条作废申请')
        ids = sorted(set(ids))
        if self.get_queryset().filter(pk__in=ids).count() != len(ids):
            raise PermissionDenied('所选记录不存在或无权操作')
        try:
            department = int(request.data.get('department'))
            for pk in ids:
                decide_revocation(pk, department, request.user, request.data.get('decision'), request.data.get('comment', ''))
        except (ValueError, TypeError) as exc:
            raise ValidationError(str(exc))
        except PermissionError as exc:
            raise PermissionDenied(str(exc))
        return Response({'count': len(ids)})


class NotificationViewSet(ModelViewSet):
    lookup_value_regex = r"[0-9]+"
    serializer_class = NotificationSerializer
    http_method_names = ["get", "patch", "delete", "post", "head", "options"]

    def create(self, request):
        raise PermissionDenied("通知由系统业务流程生成")

    def get_queryset(self):
        return visible_notifications(self.request.user).order_by("-created_at")

    def partial_update(self,request,*args,**kwargs):
        notification=self.get_object()
        if set(request.data)-{'read_at'}:raise ValidationError('只能更新已读状态')
        self.get_queryset().filter(pk=notification.pk,read_at__isnull=True).update(read_at=timezone.now())
        notification.refresh_from_db()
        return Response({**NotificationSerializer(notification).data,'unreadCount':self.get_queryset().filter(read_at__isnull=True).count()})

    @action(detail=False,methods=['post'])
    def read_all(self,request):
        count=self.get_queryset().filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response({'count':count,'unreadCount':self.get_queryset().filter(read_at__isnull=True).count()})


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
    return Response({'required': False, 'limit_per_minute': 60})


@api_view(["POST"])
@permission_classes([AllowAny])
def public_verify(request):
    from .verification import reserve_query, find_certificate, result
    ip = client_ip(request)
    retry = reserve_query(ip)
    if retry:
        return Response({'detail': '每分钟最多查验60次，请稍后重试', 'retry_after': retry}, status=429, headers={'Retry-After': str(retry)})
    number = request.data.get('number', '')
    certificate = find_certificate(number)
    VerificationAttempt.objects.create(ip_address=ip, certificate_number=number.strip()[:32], successful=certificate is not None)
    return Response(result(certificate))


@api_view(["POST"])
def admin_verify(request):
    from .verification import reserve_query, find_certificate, result
    retry = reserve_query(client_ip(request))
    if retry:
        return Response({'detail': '每分钟最多查验60次，请稍后重试', 'retry_after': retry}, status=429, headers={'Retry-After': str(retry)})
    certificate = find_certificate(request.data.get('number', ''))
    if certificate and not visible_certificates(request.user).filter(pk=certificate.pk).exists():
        certificate = None
    return Response(result(certificate, internal=True))


@api_view(["GET", "HEAD"])
def certificate_download(request, certificate_id, kind):
    if kind not in {"pdf", "image"}:
        raise ValidationError("下载类型无效")
    certificate = visible_certificates(request.user).only("pk", "number", "pdf", "image", "pdf_sha256", "image_sha256").filter(pk=certificate_id).first()
    if not certificate:
        return Response({"detail": "无下载权限"}, status=403)
    field = certificate.pdf if kind == "pdf" else certificate.image
    if not field:
        return Response({"detail": "文件尚未生成"}, status=404)
    return disk_response(field.path, digest=certificate.pdf_sha256 if kind=="pdf" else certificate.image_sha256,
                         filename=f"{certificate.number}.{'pdf' if kind=='pdf' else 'png'}",
                         content_type="application/pdf" if kind=="pdf" else "image/png", inline=request.query_params.get("inline")=="1")


@api_view(["GET", "POST"])
def fonts_view(request):
    from .permissions import can_edit_templates
    if not can_edit_templates(request.user):
        raise PermissionDenied("需要模板编辑权限")
    if request.method == 'GET':
        include_inactive = request.query_params.get('include_inactive') == '1'
        if include_inactive and not request.user.is_superuser:
            raise PermissionDenied('只有超级管理员可以管理完整字体库')
        return Response(font_catalog(include_inactive=include_inactive))
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
            'license_note': str(request.data.get('license_note', '上传者确认具备系统使用、格式转换、嵌入和展示授权'))[:240], 'created_by': request.user,
        })
        if created:
            AuditEvent.objects.create(actor=request.user, action='font.imported', object_type='CertificateFont', object_id=digest, detail={'name': name, 'sha256': digest})
    return Response(next(item for item in font_catalog(include_inactive=True) if item['id'] == font.pk), status=201 if created else 200)


@api_view(["PATCH", "DELETE"])
@transaction.atomic
def font_management(request, font_id):
    if not request.user.is_superuser:
        raise PermissionDenied('只有超级管理员可以管理字体')
    font = CertificateFont.objects.select_for_update().filter(pk=font_id).first()
    if not font:
        raise ValidationError('内置字体随系统维护，不可修改；或字体不存在')
    if request.method == 'DELETE':
        archive(request.user,font)
        return Response(status=204)
    if set(request.data) - {'name', 'active'}:
        raise ValidationError('只能修改显示名称和启用状态，字体文件不可替换')
    before = {'name': font.name, 'active': font.active}
    if 'name' in request.data:
        name = str(request.data['name']).strip()
        if not name or len(name) > 160:
            raise ValidationError('字体名称需要 1～160 个字符')
        font.name = name
    if 'active' in request.data:
        if not isinstance(request.data['active'], bool):
            raise ValidationError('启用状态必须为布尔值')
        font.active = request.data['active']
    font.save(update_fields=['name', 'active', 'updated_at'])
    AuditEvent.objects.create(actor=request.user, action='font.updated', object_type='CertificateFont', object_id=font.pk,
                              detail={'before': before, 'after': {'name': font.name, 'active': font.active}})
    return Response(next(item for item in font_catalog(include_inactive=True) if item['id'] == font.pk))


@api_view(['POST'])
@transaction.atomic
def font_order(request):
    if not request.user.is_superuser:
        raise PermissionDenied('只有超级管理员可以调整字体顺序')
    ids = request.data.get('ids')
    available = {item['id'] for item in font_catalog(include_inactive=True)}
    if not isinstance(ids, list) or len(ids) > 300 or any(not isinstance(key, str) for key in ids) or len(set(ids)) != len(ids) or set(ids) - available:
        raise ValidationError('字体顺序无效，请刷新字体列表后重试')
    SystemSetting.objects.update_or_create(key='font_order', defaults={'value': {'ids': ids}})
    AuditEvent.objects.create(actor=request.user, action='font.order_updated', object_type='SystemSetting', object_id='font_order', detail={'ids': ids})
    return Response(font_catalog(include_inactive=True))


@api_view(["GET"])
def font_download(request, font_id):
    from .permissions import can_edit_templates
    if not can_edit_templates(request.user):
        raise PermissionDenied("需要模板编辑权限")
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
