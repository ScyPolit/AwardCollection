from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views


router = DefaultRouter()
router.register("departments", views.DepartmentViewSet, basename="department")
router.register("users", views.UserOptionViewSet, basename="user-option")
router.register("competitions", views.CompetitionViewSet, basename="competition")
router.register("batches", views.BatchViewSet, basename="batch")
router.register("approvals", views.ApprovalViewSet, basename="approval")
router.register("templates", views.TemplateViewSet, basename="template")
router.register("seals", views.SealViewSet, basename="seal")
router.register("certificates", views.CertificateViewSet, basename="certificate")
router.register("revocations", views.RevocationViewSet, basename="revocation")
router.register("notifications", views.NotificationViewSet, basename="notification")

urlpatterns = [
    path("health/", views.health),
    path("auth/csrf/", views.csrf),
    path("auth/login/", views.login_view),
    path("auth/logout/", views.logout_view),
    path("auth/me/", views.me),
    path("routes/", views.public_routes),
    path("excel/template/", views.excel_template_view),
    path("excel/validate/", views.excel_validate_view),
    path("verification/challenge/", views.verification_challenge),
    path("verification/query/", views.public_verify),
    path("verification/admin/", views.admin_verify),
    path("certificates/<int:certificate_id>/download/<str:kind>/", views.certificate_download),
    path("", include(router.urls)),
]
