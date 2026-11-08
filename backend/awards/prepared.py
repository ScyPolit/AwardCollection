"""Leased, deduplicated previews and ZIPs persisted before a download is advertised."""
import hashlib
import io
import json
import multiprocessing
import os
from pathlib import Path
import re
import uuid
import zipfile
from concurrent.futures import ProcessPoolExecutor
from datetime import timedelta
from django.conf import settings
from django.db import models, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from .models import PreparedFile, BatchVersion, TemplateVersion, Certificate, Notification, AuditEvent
from .scopes import accessible_batches, accessible_versions, accessible_templates
from .integrity import file_digest
from .downloads import disk_response

KINDS = {"batch_zip", "batch_preview", "batch_thumbnail", "template_thumbnail"}


def template_versions_for(user):
    return TemplateVersion.objects.filter(template__in=accessible_templates(user))


def publish_submission_previews(version_id, expected_keys, pdf_bytes):
    """Persist the already validated first page; no second browser or worker queue."""
    import pymupdf as fitz
    root = Path(settings.MEDIA_ROOT) / 'protected' / 'prepared'
    root.mkdir(parents=True, exist_ok=True)
    written = []
    try:
        with transaction.atomic():
            for kind, ext in [('batch_preview', 'pdf'), ('batch_thumbnail', 'png')]:
                if key_for(kind, version_id) != expected_keys[kind]:
                    continue
                asset, _ = PreparedFile.objects.get_or_create(key=expected_keys[kind], defaults={'kind': kind, 'version_id': version_id})
                asset = PreparedFile.objects.select_for_update().get(pk=asset.pk)
                if asset.status == 'ready' and asset.file.storage.exists(asset.file.name):
                    continue
                path = root / f'{asset.pk}-{uuid.uuid4()}.{ext}'
                written.append(path)
                if ext == 'pdf':
                    path.write_bytes(pdf_bytes)
                else:
                    with fitz.open(stream=pdf_bytes, filetype='pdf') as document:
                        page = document[0]
                        scale = min(1, 640 / max(page.rect.width, page.rect.height))
                        page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).save(path)
                asset.file.name = path.relative_to(settings.MEDIA_ROOT).as_posix()
                asset.sha256, asset.byte_size = file_digest(path), path.stat().st_size
                asset.status, asset.processed, asset.total = 'ready', 1, 1
                asset.error, asset.lease_token, asset.lease_expires_at = '', None, None
                asset.save()
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise


def archive_stamp(version_id):
    data = Certificate.objects.filter(award__version_id=version_id, deleted_at__isnull=True, published_at__isnull=False).aggregate(count=models.Count("pk"), modified=models.Max("updated_at"))
    return f"{data['count']}:{data['modified']}"


def key_for(kind, version_id=None, template_version_id=None):
    if kind == "batch_zip":
        stamp = archive_stamp(version_id)
    elif kind in ("batch_preview", "batch_thumbnail"):
        version = BatchVersion.objects.only("integrity_hmac", "updated_at").get(pk=version_id)
        stamp = f"{settings.BUILD_VERSION}:{version.updated_at}:{version.integrity_hmac}"
    else:
        stamp = settings.BUILD_VERSION
    return hashlib.sha256(f"{kind}:{version_id}:{template_version_id}:{stamp}".encode()).hexdigest()


def allowed(user, asset):
    if asset.version_id:
        return accessible_versions(user).filter(pk=asset.version_id).exists()
    return template_versions_for(user).filter(pk=asset.template_version_id).exists()


def request_file(user, kind, *, batch_id=None, template_version_id=None):
    if kind not in KINDS:
        raise ValidationError("文件准备类型无效")
    version_id = None
    if kind == "template_thumbnail":
        version = get_object_or_404(template_versions_for(user).only("pk"), pk=template_version_id)
        template_version_id = version.pk
    else:
        batch = get_object_or_404(accessible_batches(user).only("pk", "current_version"), pk=batch_id)
        version = BatchVersion.objects.only("pk").get(batch=batch, number=batch.current_version)
        version_id = version.pk
        template_version_id = None
        if kind == "batch_zip" and not Certificate.objects.filter(award__version_id=version_id, deleted_at__isnull=True, published_at__isnull=False).exists():
            # A withdrawal creates a clean revision. Its published originals still
            # belong in the archive, within the caller's historical approval scope.
            version = accessible_versions(user).filter(
                batch=batch, awards__certificate__deleted_at__isnull=True,
                awards__certificate__published_at__isnull=False,
            ).order_by("-number").only("pk").first()
            if version is None:
                raise ValidationError("证书尚未全部发布，请等待生成完成")
            version_id = version.pk
        if kind in ("batch_preview", "batch_thumbnail") and not version.awards.exists():
            raise ValidationError("请先导入名单")
    key = key_for(kind, version_id, template_version_id)
    with transaction.atomic():
        asset, _ = PreparedFile.objects.get_or_create(key=key, defaults={"kind": kind, "version_id": version_id, "template_version_id": template_version_id})
        asset = PreparedFile.objects.select_for_update().get(pk=asset.pk)
        if asset.status == "failed" or (asset.status == "ready" and not asset.file.storage.exists(asset.file.name)):
            asset.status = "queued"
            asset.error = ""
            asset.attempts = 0
            asset.lease_expires_at = None
            asset.save(update_fields=["status", "error", "attempts", "lease_expires_at", "updated_at"])
        asset.subscribers.add(user)
    return asset


def status_data(asset):
    return {"id": str(asset.pk), "kind": asset.kind, "status": asset.status, "processed": asset.processed, "total": asset.total,
            "percent": 100 if asset.status == "ready" else min(99, round(asset.processed / max(1, asset.total) * 100)),
            "bytes": asset.byte_size, "error": asset.error,
            "status_url": f"/api/v1/prepared-files/{asset.pk}/",
            "download_url": f"/api/v1/prepared-files/{asset.pk}/download/" if asset.status == "ready" else None}


@api_view(["POST"])
def prepare_view(request):
    try:
        asset = request_file(request.user, request.data.get("kind"), batch_id=request.data.get("batch"), template_version_id=request.data.get("template_version"))
    except (TypeError, ValueError):
        raise ValidationError("对象编号无效")
    return Response(status_data(asset), status=200 if asset.status == "ready" else 202)


@api_view(["GET"])
def status_view(request, asset_id):
    asset = get_object_or_404(PreparedFile, pk=asset_id)
    if not allowed(request.user, asset):
        raise PermissionDenied("无权查看此文件")
    return Response(status_data(asset))


@api_view(["GET", "HEAD"])
def download_view(request, asset_id):
    asset = get_object_or_404(PreparedFile, pk=asset_id)
    if not allowed(request.user, asset):
        raise PermissionDenied("无下载权限")
    if asset.kind == "batch_zip" and asset.key != key_for(asset.kind, asset.version_id):
        return Response({"detail": "证书记录已更新，请重新准备下载包"}, status=409)
    if asset.kind in ("batch_preview", "batch_thumbnail") and asset.key != key_for(asset.kind, asset.version_id):
        return Response({"detail": "名单或公章已更新，请重新准备预览"}, status=409)
    if asset.status != "ready":
        return Response(status_data(asset), status=202)
    extension = "zip" if asset.kind == "batch_zip" else "pdf" if asset.kind == "batch_preview" else "png"
    name = f"batch-{asset.version.batch_id}-certificates.zip" if extension == "zip" else f"preview-{asset.pk}.{extension}"
    return disk_response(asset.file.path, digest=asset.sha256, filename=name,
                         content_type={"zip": "application/zip", "pdf": "application/pdf", "png": "image/png"}[extension], inline=extension != "zip")


def waiting_response(asset):
    """Compatibility for bookmarked old download URLs: small polling page, never a Blob."""
    asset_id = str(asset.pk)
    html = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>文件准备中</title><body><main style="max-width:42rem;margin:12vh auto;font:16px system-ui;padding:2rem"><h1>正在准备文件</h1><p id="message" role="status" aria-live="polite">后台正在处理，其他功能可以正常使用。</p><progress id="progress" max="100"></progress><p><a href="/">返回系统</a></p></main><script>
const id="ASSET";async function poll(){try{const r=await fetch('/api/v1/prepared-files/'+id+'/');if(!r.ok)throw Error('登录已失效或无权访问，请返回系统重新登录');const d=await r.json();document.getElementById('message').textContent=d.status==='failed'?d.error:(d.status==='queued'?'排队中':'正在处理 '+d.processed+' / '+d.total);document.getElementById('progress').value=d.percent;if(d.status==='ready'){location.replace(d.download_url);return}if(d.status==='failed')return;setTimeout(poll,2000)}catch(e){document.getElementById('message').textContent=e.message}}poll();
</script></body></html>'''.replace("ASSET", asset_id)
    return HttpResponse(html, headers={"Cache-Control": "no-store"})


@transaction.atomic
def claim_file():
    now = timezone.now()
    PreparedFile.objects.filter(status="running", attempts__gte=3, lease_expires_at__lt=now).update(status="failed", error="处理多次中断，请手动重试", lease_expires_at=None)
    asset = PreparedFile.objects.select_for_update(skip_locked=True).filter(status__in=["queued", "running"], attempts__lt=3).filter(models.Q(lease_expires_at__lt=now) | models.Q(lease_expires_at=None)).annotate(priority=models.Case(models.When(kind="batch_zip", then=0), default=1)).order_by("priority", "created_at").first()
    if asset:
        asset.status = "running"
        asset.lease_token = uuid.uuid4()
        asset.lease_expires_at = now + timedelta(minutes=5)
        asset.attempts += 1
        asset.error = ""
        asset.save()
    return asset


def progress(asset, processed, total):
    updated = PreparedFile.objects.filter(pk=asset.pk, lease_token=asset.lease_token, status="running").update(processed=processed, total=total, lease_expires_at=timezone.now()+timedelta(minutes=5), updated_at=timezone.now())
    if not updated:
        raise ValueError("文件任务租约已失效")


def build_zip(asset, target):
    version = BatchVersion.objects.only("pk", "output_formats").get(pk=asset.version_id)
    fields = version.output_formats or ["pdf", "png"]
    rows = Certificate.objects.filter(award__version_id=asset.version_id, published_at__isnull=False, deleted_at__isnull=True).order_by("pk")
    total = rows.count()
    if not total:
        raise ValueError("没有可打包证书")
    progress(asset, 0, total)
    # PDF and PNG are compressed already. Stored ZIP avoids recompression and CPU spikes.
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as bundle:
        for index, row in enumerate(rows.values("number", "pdf", "image", "pdf_sha256", "image_sha256").iterator(chunk_size=16), 1):
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", row["number"]):
                raise ValueError("证书编号无效")
            for fmt, field, digest_field in [("pdf", "pdf", "pdf_sha256"), ("png", "image", "image_sha256")]:
                if fmt not in fields:
                    continue
                path = (Path(settings.MEDIA_ROOT) / row[field]).resolve()
                if not row[field] or not path.is_relative_to((Path(settings.MEDIA_ROOT)/"protected"/"certificates").resolve()):
                    raise ValueError("证书文件路径无效")
                digest = hashlib.sha256()
                with path.open("rb") as source, bundle.open(f"{row['number']}.{fmt}", "w", force_zip64=True) as output:
                    while chunk := source.read(256 * 1024):
                        digest.update(chunk)
                        output.write(chunk)
                if not row[digest_field] or digest.hexdigest() != row[digest_field]:
                    raise ValueError("证书文件完整性校验失败，未发布下载包")
            if index % 10 == 0 or index == total:
                progress(asset, index, total)
    if asset.key != key_for("batch_zip", asset.version_id):
        raise ValueError("打包期间证书记录已变化，请重新准备")


def render_preview_job(kind, canvas, values, seals, fonts, target):
    from .renderer import render_unsigned
    from .fonts import resolved_font_files
    from .ppt_renderer import release_renderer
    from types import SimpleNamespace
    import pymupdf as fitz
    try:
        with resolved_font_files(fonts):
            buffer = io.BytesIO()
            render_unsigned(SimpleNamespace(**values), "2026AC00000000", buffer, template=canvas, seals=seals)
            if kind == "batch_preview":
                Path(target).write_bytes(buffer.getbuffer())
            else:
                with fitz.open(stream=buffer.getbuffer(), filetype="pdf") as document:
                    page = document[0]
                    scale = min(1, 640 / max(page.rect.width, page.rect.height))
                    page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).save(target)
    finally:
        release_renderer()


def build_preview(asset, target):
    from .fonts import font_file
    from .presentation import presentation_fonts
    if asset.kind in ("batch_preview", "batch_thumbnail"):
        version = BatchVersion.objects.select_related("batch__competition", "template_version").get(pk=asset.version_id)
        award = version.awards.order_by("source_row").values("members", "team_name", "award_name", "work_name", "category", "teachers").first()
        if not award:
            raise ValueError("名单为空")
        award.update(competition_name=version.snapshot.get("competition", {}).get("name", version.batch.competition.name), issue_date=version.snapshot.get("issue_date", ""))
        canvas = version.snapshot.get("template") or version.template_version.canvas
        seals = [{"department_id": r.department_id, "image": r.seal_version.image.path} for r in version.required_departments.select_related("seal_version") if r.seal_version_id]
    else:
        canvas = TemplateVersion.objects.get(pk=asset.template_version_id).canvas
        award = {"team_name": "示例团队", "members": ["张三", "李四"], "award_name": "一等奖", "work_name": "示例作品", "category": "创新类", "teachers": ["王老师"], "competition_name": "校园创新竞赛", "issue_date": "2026年"}
        seals = []
    font_ids = {"hei"} | ({layer.get("fontFamily", "hei") for layer in canvas.get("layers", []) if layer.get("type") == "text"})
    if canvas.get("engine") == "pptist":
        font_ids |= presentation_fonts(canvas)
    fonts = {key: str(font_file(key)) for key in font_ids}
    from .render_jobs import setup_django
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"), initializer=setup_django) as pool:
        pool.submit(render_preview_job, asset.kind, canvas, award, seals, fonts, str(target)).result(timeout=150)


def process_file(asset):
    root = Path(settings.MEDIA_ROOT) / "protected" / "prepared"
    root.mkdir(parents=True, exist_ok=True)
    ext = "zip" if asset.kind == "batch_zip" else "pdf" if asset.kind == "batch_preview" else "png"
    target = root / f"{asset.pk}-{asset.lease_token}.{ext}"
    try:
        if asset.kind == "batch_zip":
            build_zip(asset, target)
        else:
            progress(asset, 0, 1)
            build_preview(asset, target)
        digest, size = file_digest(target), target.stat().st_size
        with transaction.atomic():
            current = PreparedFile.objects.select_for_update().get(pk=asset.pk)
            if current.lease_token != asset.lease_token or current.status != "running":
                raise ValueError("文件任务租约已失效")
            current.file.name = target.relative_to(settings.MEDIA_ROOT).as_posix()
            current.sha256, current.byte_size = digest, size
            current.status, current.processed, current.total = "ready", current.total or 1, current.total or 1
            current.lease_expires_at = None
            current.save()
            if asset.kind == "batch_zip":
                batch_id = BatchVersion.objects.values_list("batch_id", flat=True).get(pk=asset.version_id)
                users = [u for u in current.subscribers.filter(is_active=True) if allowed(u, current)]
                Notification.objects.bulk_create([Notification(user=u, title="整批 ZIP 已就绪", body="下载包已保存到服务器，点击进入批次直接下载。", kind="completed", target=f"/business/batches?batch={batch_id}&download={current.pk}") for u in users])
                AuditEvent.objects.create(action="archive.ready", object_type="AwardBatch", object_id=str(batch_id), detail={"bytes": size, "archive": str(current.pk)})
    except Exception as exc:
        target.unlink(missing_ok=True)
        detail = "原件文件缺失，请联系管理员恢复后重试" if isinstance(exc, FileNotFoundError) else "服务器文件处理失败，请联系管理员检查存储空间和服务日志" if isinstance(exc, OSError) else str(exc)[:500]
        changed = PreparedFile.objects.filter(pk=asset.pk, lease_token=asset.lease_token).update(status="failed", error=detail, lease_expires_at=None, updated_at=timezone.now())
        if changed:
            AuditEvent.objects.create(action="file.prepare_failed", object_type="PreparedFile", object_id=str(asset.pk), detail={"error": str(exc)[:1000], "kind": asset.kind})
    return PreparedFile.objects.get(pk=asset.pk)
