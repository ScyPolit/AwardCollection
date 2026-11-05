import hashlib
import io
import random
import zipfile
from datetime import timedelta

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.core.files.base import ContentFile
from django.db import connection, models, transaction
from django.http import FileResponse, HttpResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from .models import (
    ApprovalDepartment, AwardBatch, BatchVersion, Certificate, Competition,
    Department, DepartmentMembership, LoginProtection, Notification,
    RevocationDecision, RevocationRequest, Seal, SealVersion, SystemSetting,
    TeamAward, Template, TemplateVersion, VerificationAttempt,
)
from .serializers import (
    ApprovalSerializer, BatchSerializer, CertificateSerializer,
    CompetitionSerializer, DepartmentSerializer, NotificationSerializer,
    RevocationSerializer, SealSerializer, TemplateSerializer,
    UserOptionSerializer,
)
from .services import (
    decide, decide_revocation, emergency_void, excel_template, parse_excel,
    request_revocation, revise_batch, submit_batch,
)


def client_ip(request):
    return request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", "127.0.0.1")).split(",")[0].strip()


def accessible_competitions(user):
    if user.is_superuser:
        return Competition.objects.all()
    department_ids = DepartmentMembership.objects.filter(user=user, active=True).values_list("department_id", flat=True)
    return Competition.objects.filter(models.Q(collaborators=user) | models.Q(departments__in=department_ids)).distinct()


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return Response({"status": "ok", "database": "ok"})


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
    roles = list(DepartmentMembership.objects.filter(user=authenticated, active=True).values_list("role", flat=True).distinct())
    if authenticated.is_superuser:
        roles.append("super")
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
    return Response({"username": request.user.username, "name": request.user.get_full_name() or request.user.username, "isSuperuser": request.user.is_superuser})


class DepartmentViewSet(ReadOnlyModelViewSet):
    serializer_class = DepartmentSerializer

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Department.objects.all().order_by("name")
        return Department.objects.filter(departmentmembership__user=self.request.user, departmentmembership__active=True).distinct().order_by("name")


class UserOptionViewSet(ReadOnlyModelViewSet):
    serializer_class = UserOptionSerializer

    def get_queryset(self):
        if self.request.user.is_superuser:
            return get_user_model().objects.filter(is_active=True).order_by("username")
        departments = DepartmentMembership.objects.filter(user=self.request.user, active=True).values_list("department_id", flat=True)
        return get_user_model().objects.filter(departmentmembership__department_id__in=departments, is_active=True).distinct().order_by("username")


class CompetitionViewSet(ModelViewSet):
    serializer_class = CompetitionSerializer

    def get_queryset(self):
        return accessible_competitions(self.request.user).prefetch_related("departments", "collaborators").order_by("-created_at")

    def perform_create(self, serializer):
        departments = serializer.validated_data.get("departments", [])
        if not departments:
            raise ValidationError({"departments": "至少选择一个拟盖章部门"})
        user = self.request.user
        if not user.is_superuser:
            allowed = set(DepartmentMembership.objects.filter(user=user, active=True).values_list("department_id", flat=True))
            if not set(item.id for item in departments).issubset(allowed):
                raise ValidationError({"departments": "包含未授权部门"})
        competition = serializer.save(created_by=user)
        competition.collaborators.add(user)


class BatchViewSet(ModelViewSet):
    serializer_class = BatchSerializer

    def get_queryset(self):
        return AwardBatch.objects.filter(competition__in=accessible_competitions(self.request.user)).select_related("competition").distinct().order_by("-created_at")

    @transaction.atomic
    def perform_create(self, serializer):
        competition = serializer.validated_data["competition"]
        if not accessible_competitions(self.request.user).filter(pk=competition.pk).exists():
            raise ValidationError("无权访问该竞赛")
        template = TemplateVersion.objects.filter(template__published=True).order_by("-created_at").first()
        if template is None:
            raise ValidationError("请先创建并发布证书模板")
        selected = []
        for department in competition.departments.all():
            seal = SealVersion.objects.filter(seal__department=department, seal__active=True).order_by("-number").first()
            if seal is None:
                raise ValidationError(f"{department.name} 没有启用的公章")
            selected.append((department, seal))
        batch = serializer.save(created_by=self.request.user)
        version = BatchVersion.objects.create(
            batch=batch, number=1, template_version=template,
            output_formats=["pdf", "png"],
            snapshot={"template": template.canvas, "departments": [department.id for department, _ in selected], "seals": [seal.id for _, seal in selected]},
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
        return Template.objects.filter(published=True).select_related("department").prefetch_related("versions").order_by("-updated_at")

    def perform_create(self, serializer):
        department = serializer.validated_data["department"]
        if not self.request.user.is_superuser and not DepartmentMembership.objects.filter(user=self.request.user, department=department, role=DepartmentMembership.Role.ADMIN, active=True).exists():
            raise ValidationError("只能为本部门创建模板")
        template = serializer.save(created_by=self.request.user)
        TemplateVersion.objects.create(template=template, number=1, canvas=self.request.data.get("canvas", {}))

    @action(detail=True, methods=["post"])
    def save_version(self, request, pk=None):
        template = self.get_object()
        if not request.user.is_superuser and not DepartmentMembership.objects.filter(user=request.user, department=template.department, role=DepartmentMembership.Role.ADMIN, active=True).exists():
            return Response({"detail": "只能维护本部门发布的模板"}, status=403)
        number = (template.versions.aggregate(models.Max("number"))["number__max"] or 0) + 1
        version = TemplateVersion.objects.create(template=template, number=number, canvas=request.data.get("canvas", {}))
        return Response({"id": version.id, "number": version.number}, status=201)

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
        departments = DepartmentMembership.objects.filter(user=self.request.user, role=DepartmentMembership.Role.ADMIN, active=True).values_list("department_id", flat=True)
        return Seal.objects.filter(department_id__in=departments).select_related("department").prefetch_related("versions")

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
        return Response({"id": version.id, "number": number}, status=201)


class CertificateViewSet(ReadOnlyModelViewSet):
    serializer_class = CertificateSerializer

    def get_queryset(self):
        return Certificate.objects.filter(award__version__batch__competition__in=accessible_competitions(self.request.user)).select_related("award__version__batch__competition").distinct().order_by("-created_at")

    @action(detail=False, methods=["get"], url_path="batch/(?P<batch_id>[^/.]+)/archive")
    def archive(self, request, batch_id=None):
        certificates = self.get_queryset().filter(award__version__batch_id=batch_id, published_at__isnull=False)
        if not certificates.exists():
            return Response({"detail": "没有可归档文件"}, status=404)
        output = io.BytesIO()
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
    certificate = Certificate.objects.select_related("award__version__batch__competition").filter(pk=certificate_id).first()
    if not certificate or not accessible_competitions(request.user).filter(pk=certificate.award.version.batch.competition_id).exists():
        return Response({"detail": "无下载权限"}, status=403)
    field = certificate.pdf if kind == "pdf" else certificate.image
    if not field:
        return Response({"detail": "文件尚未生成"}, status=404)
    return FileResponse(field.open("rb"), as_attachment=True, filename=f"{certificate.number}.{kind}", content_type="application/pdf" if kind == "pdf" else "image/png")
