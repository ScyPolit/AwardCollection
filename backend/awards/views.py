from django.contrib.auth import authenticate, login, logout
from django.db import connection
from django.http import HttpResponse
from django.middleware.csrf import get_token
from datetime import timedelta
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
import random

from .models import ApprovalDepartment, AwardBatch, BatchVersion, Certificate, Competition, Notification, SealVersion, TeamAward, TemplateVersion
from .serializers import BatchSerializer, CompetitionSerializer, NotificationSerializer
from .services import decide, excel_template, parse_excel, submit_batch


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
    user = authenticate(request, username=request.data.get("username", ""), password=request.data.get("password", ""))
    if user is None or not user.is_active:
        return Response({"detail": "用户名或密码错误"}, status=400)
    login(request, user)
    expires = timezone.now() + timedelta(hours=8)
    return Response({"success": True, "data": {
        "username": user.username,
        "nickname": user.get_full_name() or user.username,
        "avatar": "",
        "roles": ["super" if user.is_superuser else "user"],
        "permissions": ["*:*:*"] if user.is_superuser else [],
        "accessToken": "session",
        "refreshToken": "session",
        "expires": expires.isoformat(),
    }})


@api_view(["POST"])
def logout_view(request):
    logout(request)
    return Response({"success": True})


@api_view(["GET"])
def me(request):
    return Response({"username": request.user.username, "name": request.user.get_full_name() or request.user.username, "isSuperuser": request.user.is_superuser})


class CompetitionViewSet(ModelViewSet):
    serializer_class = CompetitionSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Competition.objects.all().order_by("-created_at")
        return Competition.objects.filter(collaborators=user).distinct().order_by("-created_at")

    def perform_create(self, serializer):
        competition = serializer.save(created_by=self.request.user)
        competition.collaborators.add(self.request.user)


class BatchViewSet(ModelViewSet):
    serializer_class = BatchSerializer

    def get_queryset(self):
        user = self.request.user
        qs = AwardBatch.objects.select_related("competition").order_by("-created_at")
        return qs if user.is_superuser else qs.filter(competition__collaborators=user).distinct()

    def perform_create(self, serializer):
        batch = serializer.save(created_by=self.request.user)
        template = TemplateVersion.objects.filter(template__published=True).order_by("-created_at").first()
        if template is None:
            raise ValueError("请先创建并发布证书模板")
        version = BatchVersion.objects.create(batch=batch, number=1, template_version=template, output_formats=["pdf", "png"], snapshot={"template": template.canvas})
        for department in batch.competition.departments.all():
            seal = SealVersion.objects.filter(seal__department=department, seal__active=True).order_by("-number").first()
            if seal is None:
                raise ValueError(f"{department.name} 没有启用的公章")
            ApprovalDepartment.objects.create(version=version, department=department, seal_version=seal)

    @action(detail=True, methods=["post"], url_path="import")
    def import_awards(self, request, pk=None):
        batch = self.get_object()
        uploaded = request.FILES.get("file")
        if not uploaded:
            return Response({"detail": "请选择 XLSX 文件"}, status=400)
        rows, errors = parse_excel(uploaded)
        if errors:
            return Response({"errors": errors}, status=400)
        version = BatchVersion.objects.get(batch=batch, number=batch.current_version)
        TeamAward.objects.filter(version=version).delete()
        TeamAward.objects.bulk_create([TeamAward(version=version, last_edited_by=request.user, **row) for row in rows])
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
        return Response(None if task is None else {"status": task.status, "processed": task.processed, "total": task.total, "error": task.error})


@api_view(["POST"])
def approval_decide(request, requirement_id):
    try:
        task = decide(requirement_id, request.user, request.data.get("decision"), request.data.get("comment", ""))
    except PermissionError as exc:
        return Response({"detail": str(exc)}, status=403)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=409)
    return Response({"accepted": True, "taskCreated": task is not None})


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
    if request.session.get("verification_used", True) or str(request.data.get("answer", "")) != str(request.session.get("verification_answer", "missing")):
        return Response({"detail": "验证码错误或已使用"}, status=400)
    request.session["verification_used"] = True
    certificate = Certificate.objects.select_related("award__version__batch__competition").filter(number=request.data.get("number", "")).first()
    if certificate is None or certificate.published_at is None:
        return Response({"found": False})
    award = certificate.award
    masked = [name[0] + "*" * max(1, len(name) - 1) for name in award.members]
    return Response({"found": True, "number": certificate.number, "status": certificate.status, "competition": award.version.batch.competition.name, "award": award.award_name, "team": award.team_name, "members": masked})


@api_view(["GET"])
def certificate_download(request, certificate_id, kind):
    certificate = Certificate.objects.select_related("award__version__batch__competition").get(pk=certificate_id)
    competition = certificate.award.version.batch.competition
    if not request.user.is_superuser and not competition.collaborators.filter(pk=request.user.pk).exists():
        return Response({"detail": "无下载权限"}, status=403)
    field = certificate.pdf if kind == "pdf" else certificate.image
    if not field:
        return Response({"detail": "文件尚未生成"}, status=404)
    response = HttpResponse(field.open("rb"), content_type="application/pdf" if kind == "pdf" else "image/png")
    response["Content-Disposition"] = f'attachment; filename="{certificate.number}.{kind}"'
    return response
