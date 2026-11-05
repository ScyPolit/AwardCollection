from django.contrib.auth import authenticate, login, logout
from django.db import connection
from django.http import HttpResponse
from django.middleware.csrf import get_token
from datetime import timedelta
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from .models import AwardBatch, Competition, Notification
from .serializers import BatchSerializer, CompetitionSerializer, NotificationSerializer
from .services import excel_template, parse_excel


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
        serializer.save(created_by=self.request.user)


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
