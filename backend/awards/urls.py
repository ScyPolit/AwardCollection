from django.urls import include, path
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("competitions", views.CompetitionViewSet, basename="competition")
router.register("batches", views.BatchViewSet, basename="batch")
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
    path("", include(router.urls)),
]
