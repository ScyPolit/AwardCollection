"""Explicit one-time reset requested by the system owner; never runs during startup."""

import hashlib
import json
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from awards.models import (
    AccountProfile,
    ApprovalDecision,
    ApprovalDepartment,
    AuditEvent,
    AwardBatch,
    BatchVersion,
    Certificate,
    CertificateFont,
    Competition,
    Department,
    DepartmentMembership,
    GenerationTask,
    LoginProtection,
    Notification,
    RevocationDecision,
    RevocationRequest,
    Seal,
    TeamAward,
    Template,
    VerificationAttempt,
)


def canvas_digest(canvas):
    return hashlib.sha256(
        json.dumps(
            canvas, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


class Command(BaseCommand):
    help = "Clear all competition business and non-super accounts after a verified external backup; preserve the selected template and its materials"

    def add_arguments(self, parser):
        parser.add_argument("--template-id", type=int, required=True)
        parser.add_argument("--superuser-id", type=int, required=True)
        parser.add_argument("--expected-template-sha256", required=True)
        parser.add_argument("--verified-backup", required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        with transaction.atomic():
            template = Template.objects.select_for_update().get(
                pk=options["template_id"]
            )
            latest = template.versions.order_by("-number").first()
            if (
                not latest
                or canvas_digest(latest.canvas) != options["expected_template_sha256"]
            ):
                raise CommandError(
                    "Protected template changed. Re-inventory the latest version; never overwrite it."
                )
            root = get_user_model().objects.get(
                pk=options["superuser_id"], is_superuser=True, is_active=True
            )
            if GenerationTask.objects.filter(status__in=["queued", "running"]).exists():
                raise CommandError("Generation tasks must finish before cleanup")
            if not options["verified_backup"].startswith(
                "/opt/awardcollection-v1-test/backups/"
            ):
                raise CommandError(
                    "A verified backup path from this deployment is required"
                )
            # Retain all non-demo materials, including fonts imported by the user.
            seal_ids = set(
                Seal.objects.exclude(department_id__in=[1, 2, 3, 4, 5])
                .exclude(name__startswith="TEST ONLY V4")
                .values_list("pk", flat=True)
            )
            dep_ids = {template.department_id} | set(
                Seal.objects.filter(pk__in=seal_ids).values_list(
                    "department_id", flat=True
                )
            )
            for layer in latest.canvas.get("layers", []):
                if layer.get("type") == "seal" and layer.get("department"):
                    dep_ids.add(int(layer["department"]))
            seal_ids |= set(
                Seal.objects.filter(department_id__in=dep_ids)
                .exclude(name__startswith="TEST ONLY V4")
                .values_list("pk", flat=True)
            )
            # Only these three precisely identified synthetic import duplicates are demo fonts.
            demo_fonts = {
                "29d12439831b7f59194efec85872f24f54eff05738933f9a860220d2abff88ba",
                "8d91388f1d3604b3b8ae0e3ee2d140e50cd6122f9214514f4aca772540a4076d",
                "6b3809450cf6253b36d157198dc15004a5fbade9abad5543c377feb7bb29139c",
            }
            serialized = json.dumps(
                list(template.versions.values_list("canvas", flat=True))
            )
            demo_fonts = {font for font in demo_fonts if font not in serialized}
            users = get_user_model().objects.exclude(pk=root.pk)
            report = {
                "backup": options["verified_backup"],
                "protected_template": template.pk,
                "protected_version": latest.number,
                "canvas_sha256": canvas_digest(latest.canvas),
                "remove": {
                    "accounts": users.count(),
                    "competitions": Competition.objects.count(),
                    "batches": AwardBatch.objects.count(),
                    "certificates": Certificate.objects.count(),
                    "tasks": GenerationTask.objects.count(),
                    "templates": Template.objects.exclude(pk=template.pk).count(),
                },
                "keep": {"departments": sorted(dep_ids), "seals": sorted(seal_ids)},
                "applied": options["apply"],
            }
            if not options["apply"]:
                self.stdout.write(json.dumps(report, ensure_ascii=False))
                return
            paths = list(
                Certificate.objects.exclude(pdf="").values_list("pdf", flat=True)
            ) + list(
                Certificate.objects.exclude(image="").values_list("image", flat=True)
            )
            RevocationDecision.objects.all().delete()
            RevocationRequest.objects.all().delete()
            Certificate.objects.all().delete()
            GenerationTask.objects.all().delete()
            ApprovalDecision.objects.all().delete()
            ApprovalDepartment.objects.all().delete()
            TeamAward.objects.all().delete()
            BatchVersion.objects.all().delete()
            AwardBatch.objects.all().delete()
            Competition.objects.all().delete()
            Template.objects.exclude(pk=template.pk).delete()
            template.name = "标准模板"
            template.created_by = root
            template.deleted_at = None
            template.published = True
            template.save(
                update_fields=[
                    "name",
                    "created_by",
                    "deleted_at",
                    "published",
                    "updated_at",
                ]
            )
            Seal.objects.exclude(pk__in=seal_ids).delete()
            Department.objects.exclude(pk__in=dep_ids).delete()
            CertificateFont.objects.filter(pk__in=demo_fonts).delete()
            CertificateFont.objects.exclude(created_by=root).update(created_by=root)
            DepartmentMembership.objects.exclude(user=root).delete()
            Notification.objects.all().delete()
            VerificationAttempt.objects.all().delete()
            users.delete()
            for session in Session.objects.all():
                if str(session.get_decoded().get("_auth_user_id")) != str(root.pk):
                    session.delete()
            AuditEvent.objects.create(
                actor=root,
                action="system.authorized_demo_cleanup",
                object_type="System",
                object_id="v4",
                detail=report,
            )
            if (
                canvas_digest(template.versions.get(pk=latest.pk).canvas)
                != report["canvas_sha256"]
            ):
                raise CommandError("Protected content changed")
            # Remove only exact certificate paths obtained before deletion. Signing keys/fonts/materials are not touched.
            media = Path(settings.MEDIA_ROOT).resolve()
            safe = []
            for relative in paths:
                path = (media / relative).resolve()
                if not path.is_relative_to(media / "protected" / "certificates"):
                    raise CommandError(
                        "Unexpected certificate path; transaction rolled back"
                    )
                safe.append(path)
            transaction.on_commit(
                lambda: [path.unlink(missing_ok=True) for path in safe]
            )
        self.stdout.write(json.dumps(report, ensure_ascii=False))
