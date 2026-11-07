"""Authenticated server-sent updates without occupying synchronous API workers."""

import asyncio
import hashlib
import json
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db import close_old_connections, connection
from django.http import JsonResponse, StreamingHttpResponse
from django.utils import timezone
from .models import (
    AuditEvent,
    AwardBatch,
    ApprovalDepartment,
    GenerationTask,
    Notification,
    PreparedFile,
)
from .permissions import is_department_admin


def snapshot_for(user_id, session_key=None, session_auth_hash=None):
    if not connection.in_atomic_block:
        close_old_connections()
    try:
        user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
        if not user or (
            session_key
            and not Session.objects.filter(
                session_key=session_key, expire_date__gt=timezone.now()
            ).exists()
        ):
            return None
        if session_auth_hash and user.get_session_auth_hash() != session_auth_hash:
            return None
        from .scopes import accessible_competitions, accessible_versions, accessible_batches, visible_notifications

        competitions = accessible_competitions(user)
        messages = visible_notifications(user).order_by("-created_at", "-pk")
        notifications = list(
            messages[:40].values(
                "id", "title", "body", "kind", "target", "read_at", "created_at"
            )
        )
        pending = ApprovalDepartment.objects.filter(
            version__batch__competition__in=competitions,
            version__batch__deleted_at__isnull=True,
            version__batch__status="review",
            decision__isnull=True,
        )
        if not user.is_superuser:
            pending = pending.filter(
                department__departmentmembership__user=user,
                department__departmentmembership__role="admin",
                department__departmentmembership__active=True,
            )
        pending = pending.exclude(version__submitted_by=user).exclude(
            version__awards__last_edited_by=user
        )
        tasks = (
            GenerationTask.objects.filter(
                version__in=accessible_versions(user),
                version__batch__deleted_at__isnull=True,
            )
            .select_related("version__batch")
            .defer("version__snapshot")
            .order_by("-updated_at")[:30]
        )
        now = timezone.now()
        jobs = []
        for task in tasks:
            if task.version.number != task.version.batch.current_version:
                continue
            elapsed = (
                max(0, (now - task.started_at).total_seconds())
                if task.started_at
                else 0
            )
            remaining = (
                round(elapsed / task.processed * (task.total - task.processed))
                if task.status == "running"
                and task.processed
                and task.processed < task.total
                else None
            )
            jobs.append(
                {
                    "id": task.pk,
                    "batch_id": task.version.batch_id,
                    "batch_name": task.version.batch.name,
                    "status": task.status,
                    "processed": task.processed,
                    "total": task.total,
                    "percent": (
                        100
                        if task.status == "done"
                        else min(99, round(task.processed / max(1, task.total) * 100))
                    ),
                    "eta_seconds": remaining,
                    "error": task.error,
                    "started_at": task.started_at,
                    "updated_at": task.updated_at,
                }
            )
        return {
            "user": {"id": user.pk, "name": user.get_full_name() or user.username},
            "notifications": notifications,
            "unread": messages.filter(read_at__isnull=True).count(),
            "pending": (
                pending.values("version_id").distinct().count()
                if is_department_admin(user)
                else 0
            ),
            "jobs": jobs,
            "files": [
                {"id": str(a.pk), "batch_id": a.version.batch_id, "status": a.status, "processed": a.processed, "total": a.total,
                 "percent": 100 if a.status == "ready" else min(99, round(a.processed/max(1,a.total)*100)), "error": a.error,
                 "download_url": f"/api/v1/prepared-files/{a.pk}/download/" if a.status == "ready" else None}
                for a in PreparedFile.objects.filter(kind="batch_zip", subscribers=user, version__in=accessible_versions(user)).select_related("version").defer("version__snapshot").order_by("-updated_at")[:20]
            ],
            "revision": str(accessible_batches(user).order_by("-updated_at").values_list("updated_at", flat=True).first() or ""),
        }
    finally:
        if not connection.in_atomic_block:
            close_old_connections()


async def events(request):
    user = await request.auser()
    if not user.is_authenticated or not user.is_active:
        return JsonResponse({"detail": "请先登录"}, status=403)
    user_id = user.pk
    session_key = request.session.session_key
    session_auth_hash = user.get_session_auth_hash()

    async def stream():
        last = None
        ticks = 0
        try:
            while True:
                data = await asyncio.to_thread(
                    snapshot_for, user_id, session_key, session_auth_hash
                )
                if data is None:
                    yield "event: session-expired\ndata: {}\n\n"
                    return
                serialized = json.dumps(
                    data, ensure_ascii=False, default=str, separators=(",", ":")
                )
                digest = hashlib.sha256(serialized.encode()).hexdigest()
                if digest != last:
                    yield f"event: state\nid: {digest}\ndata: {serialized}\n\n"
                    last = digest
                elif ticks % 7 == 0:
                    yield ": heartbeat\n\n"
                ticks += 1
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            return

    return StreamingHttpResponse(
        stream(),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
