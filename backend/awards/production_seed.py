"""Explicit, offline production initialization. No startup hook calls this module."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import zipfile

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core import serializers
from django.core.management.base import CommandError
from django.core.management.color import no_style
from django.db import connection, transaction
from django.db.models import Q
from . import models as m

VERSION = 1
BASE_MODELS = (m.Department, m.Template, m.TemplateVersion, m.Seal, m.SealVersion, m.CertificateFont, m.SystemSetting)
BUSINESS_MODELS = (m.RevocationDecision, m.RevocationRequest, m.Certificate, m.GenerationTask,
                   m.ApprovalDecision, m.ApprovalDepartment, m.TeamAward, m.PreparedFile,
                   m.BatchVersion, m.AwardBatch, m.Competition, m.Notification,
                   m.VerificationAttempt, m.VerificationRateLimit, m.CertificateSequence,
                   m.AuditEvent, m.AccountProfile, m.DepartmentMembership, m.LoginProtection)
ALLOWED_MODELS = {model._meta.label_lower for model in BASE_MODELS} | {get_user_model()._meta.label_lower}
ALLOWED_MEDIA = ("protected/font-library/", "protected/seals/", "fonts/")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def digest_file(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def media_path(name):
    value = PurePosixPath(name)
    if not name or "\\" in name or value.is_absolute() or ".." in value.parts or not name.startswith(ALLOWED_MEDIA):
        raise CommandError("初始化包包含不允许的素材路径")
    root = Path(settings.MEDIA_ROOT).resolve()
    path = root.joinpath(*value.parts).resolve()
    if not path.is_relative_to(root) or path.is_symlink():
        raise CommandError("素材路径超出媒体目录")
    return path


def seed_records(root_id):
    root = get_user_model().objects.get(pk=root_id, is_superuser=True, is_active=True)
    templates = list(m.Template.objects.filter(deleted_at__isnull=True).order_by("pk"))
    template_ids = {obj.pk for obj in templates}
    versions = [obj.versions.order_by("-number").first() for obj in templates]
    if any(obj is None for obj in versions):
        raise CommandError("存在没有版本的模板，请补全后再导出")
    seals = list(m.Seal.objects.filter(deleted_at__isnull=True).order_by("pk"))
    seal_versions = list(m.SealVersion.objects.filter(seal__in=seals).order_by("pk"))
    fonts = list(m.CertificateFont.objects.filter(deleted_at__isnull=True).order_by("pk"))
    dep_ids = {obj.department_id for obj in templates + seals}
    departments = m.Department.objects.filter(Q(deleted_at__isnull=True) | Q(pk__in=dep_ids)).order_by("pk")
    records = json.loads(serializers.serialize("json", [root, *departments, *templates, *versions, *seals, *seal_versions, *fonts, *m.SystemSetting.objects.order_by("pk")]))
    for record in records:
        fields = record["fields"]
        if record["model"] == root._meta.label_lower:
            fields.update(groups=[], user_permissions=[], last_login=None)
        if record["model"] in {"awards.template", "awards.certificatefont"}:
            fields["created_by"] = root.pk
        if record["model"] == "awards.template":
            fields["scope"] = "department"
            if fields["source"] not in template_ids:
                fields["source"] = None
    files = {obj.image.name for obj in seal_versions} | {obj.file.name for obj in fonts}
    for directory in ("fonts", "protected/font-library/builtin"):
        path = Path(settings.MEDIA_ROOT) / directory
        if path.exists():
            files.update(p.relative_to(settings.MEDIA_ROOT).as_posix() for p in path.rglob("*") if p.is_file())
    for obj in [*seal_versions, *fonts]:
        field = obj.image if isinstance(obj, m.SealVersion) else obj.file
        if digest_file(media_path(field.name)) != obj.sha256:
            raise CommandError("字体或公章素材完整性检查失败")
    return records, sorted(files)


def export_seed(output, root_id):
    records, files = seed_records(root_id)
    payload = canonical(records)
    manifest = {"format": "awardcollection-production-seed", "version": VERSION, "private": True,
                "root_id": root_id, "data_sha256": hashlib.sha256(payload).hexdigest(),
                "files": {name: {"sha256": digest_file(media_path(name)), "size": media_path(name).stat().st_size} for name in files},
                "contents": "Only superuser, latest template layouts, fonts, departments, seals and settings; no competition business or signing keys."}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Never truncate an existing migration bundle; permissions are restrictive at creation.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream, zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("data.json", payload)
            archive.writestr("manifest.json", canonical(manifest))
            for record in records:
                if record["model"] == "awards.templateversion":
                    archive.writestr(f"templates/template-{record['fields']['template']}.json", canonical(record["fields"]["canvas"]))
            for name in files:
                archive.write(media_path(name), "media/" + name)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return {"file": str(output), "sha256": digest_file(output), "templates": sum(r["model"] == "awards.template" for r in records), "fonts": sum(r["model"] == "awards.certificatefont" for r in records), "media_files": len(files), "private": True}


def read_seed(bundle, expected_sha256):
    if digest_file(bundle) != expected_sha256:
        raise CommandError("初始化包 SHA256 不匹配")
    with zipfile.ZipFile(bundle) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)) or len(names) > 10000 or sum(e.file_size for e in entries) > 512 * 1024 * 1024:
            raise CommandError("初始化包内容重复或过大")
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if entry.flag_bits & 1 or path.is_absolute() or ".." in path.parts or "\\" in entry.filename or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise CommandError("初始化包路径或文件类型无效")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != "awardcollection-production-seed" or manifest.get("version") != VERSION:
            raise CommandError("不支持的初始化包格式")
        payload = archive.read("data.json")
        if hashlib.sha256(payload).hexdigest() != manifest["data_sha256"]:
            raise CommandError("初始化记录校验失败")
        records = json.loads(payload)
        roots = [r for r in records if r["model"] == get_user_model()._meta.label_lower]
        if len(roots) != 1 or not roots[0]["fields"].get("is_superuser") or not roots[0]["fields"].get("is_active") or roots[0]["pk"] != manifest["root_id"]:
            raise CommandError("初始化包必须只包含一个有效超管")
        if any(r["model"] not in ALLOWED_MODELS for r in records):
            raise CommandError("初始化包包含非基础业务模型")
        expected_names = {"data.json", "manifest.json"} | {"media/" + name for name in manifest["files"]} | {f"templates/template-{r['fields']['template']}.json" for r in records if r["model"] == "awards.templateversion"}
        if set(names) != expected_names:
            raise CommandError("初始化包文件清单不一致")
        for name, info in manifest["files"].items():
            media_path(name)
            entry = archive.getinfo("media/" + name)
            with archive.open(entry) as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if entry.file_size != info["size"] or actual != info["sha256"]:
                raise CommandError("初始化素材校验失败")
    return manifest, records


def verify_backup(path):
    path = Path(path)
    required = {"database.dump", "media.tar.gz", "deployment-config.tar.gz.enc"}
    if not (path / "COMPLETE").is_file():
        raise CommandError("必须提供已完成的完整备份")
    listed = set()
    for line in (path / "SHA256SUMS").read_text().splitlines():
        checksum, name = line.split(maxsplit=1)
        name = name.strip().lstrip("*")
        if Path(name).name != name or digest_file(path / name) != checksum:
            raise CommandError("备份文件校验失败")
        listed.add(name)
    if not required.issubset(listed):
        raise CommandError("备份缺少数据库、素材或配置")


def reset_business(bundle, checksum, *, backup=None, apply=False):
    manifest, records = read_seed(bundle, checksum)
    # Lock and compare original layouts/materials before deleting any business row.
    with transaction.atomic():
        list(m.Template.objects.select_for_update().all())
        current, _ = seed_records(manifest["root_id"])
        if canonical(current) != canonical(records):
            raise CommandError("原始数据已发生变化，请重新导出初始化包")
        if m.GenerationTask.objects.filter(status__in=["queued", "running"]).exists() or m.PreparedFile.objects.filter(status="running").exists():
            raise CommandError("请等待后台任务结束并停止 Worker 后再初始化")
        root_id = manifest["root_id"]
        report = {"applied": apply, "remove": {"accounts": get_user_model().objects.exclude(pk=root_id).count(), "competitions": m.Competition.objects.count(), "batches": m.AwardBatch.objects.count(), "certificates": m.Certificate.objects.count()}, "keep": {"accounts": 1, **{model._meta.model_name: sum(r["model"] == model._meta.label_lower for r in records) for model in BASE_MODELS}}}
        if not apply:
            return report
        if not backup:
            raise CommandError("执行初始化必须指定经过校验的完整备份")
        verify_backup(backup)
        for model in BUSINESS_MODELS:
            model.objects.all().delete()
        Session.objects.all().delete()
        m.Template.objects.all().update(source=None)
        m.Template.objects.all().update(created_by_id=root_id, scope="department")
        m.CertificateFont.objects.all().update(created_by_id=root_id)
        for model in (m.TemplateVersion, m.Template, m.SealVersion, m.Seal, m.CertificateFont, m.Department):
            ids = [r["pk"] for r in records if r["model"] == model._meta.label_lower]
            model.objects.exclude(pk__in=ids).delete()
        for record in records:
            if record["model"] == "awards.template":
                m.Template.objects.filter(pk=record["pk"]).update(source_id=record["fields"]["source"])
        get_user_model().objects.exclude(pk=root_id).delete()
        # Keep a single initialization audit entry; business history remains in the private backup.
        m.AuditEvent.objects.create(actor_id=root_id, action="system.production_initialized", object_type="System", object_id="production", detail={"seed_sha256": checksum, "removed": report["remove"]})
    # The complete backup remains outside MEDIA_ROOT. Old downloadable artifacts
    # must disappear from the live volume as well as from the database.
    root = Path(settings.MEDIA_ROOT).resolve()
    removed = 0
    for name in ("protected/certificates", "protected/prepared", "protected/snapshots", "temporary"):
        path = root / name
        if not path.exists():
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise CommandError("拒绝清理媒体目录之外的路径")
        removed += sum(1 for item in path.rglob("*") if item.is_file())
        shutil.rmtree(path)
    report["removed_media_files"] = removed
    return report


def import_seed(bundle, checksum):
    manifest, records = read_seed(bundle, checksum)
    created_files = []
    try:
        with transaction.atomic():
            # Only a fresh database can receive account hashes and explicit primary keys.
            if get_user_model().objects.exists() or any(model.objects.exists() for model in (*BASE_MODELS, *BUSINESS_MODELS)):
                raise CommandError("只能导入到已迁移且没有账号、素材或业务的全新数据库")
            with zipfile.ZipFile(bundle) as archive:
                for name, info in manifest["files"].items():
                    path = media_path(name)
                    if path.exists():
                        if digest_file(path) != info["sha256"]:
                            raise CommandError("目标素材已存在且内容不同")
                        continue
                    path.parent.mkdir(parents=True, exist_ok=True)
                    # Exclusive creation prevents overwriting a concurrent or unrelated file.
                    with path.open("xb") as output, archive.open("media/" + name) as source:
                        created_files.append(path)
                        shutil.copyfileobj(source, output)
            with connection.constraint_checks_disabled():
                for record in serializers.deserialize("json", json.dumps(records)):
                    record.save()
            connection.check_constraints()
            for sql in connection.ops.sequence_reset_sql(no_style(), [get_user_model(), *BASE_MODELS]):
                with connection.cursor() as cursor:
                    cursor.execute(sql)
            m.AuditEvent.objects.create(actor_id=manifest["root_id"], action="system.production_seed_imported", object_type="System", object_id="production", detail={"seed_sha256": checksum})
    except Exception:
        for path in created_files:
            path.unlink(missing_ok=True)
        raise
    return {"imported": True, "accounts": 1, "templates": sum(r["model"] == "awards.template" for r in records), "business_records": 0}
