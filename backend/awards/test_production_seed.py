import hashlib
import json
from pathlib import Path
import zipfile
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.test import TransactionTestCase, override_settings
from . import tests as fixtures
from . import models as m
from .production_seed import BASE_MODELS, BUSINESS_MODELS, digest_file, export_seed, import_seed, read_seed, reset_business


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ProductionSeedTests(TransactionTestCase):
    setUp = fixtures.WorkflowTests.setUp

    def bundle(self):
        path = Path(self.media_directory.name).parent / (Path(self.media_directory.name).name + "-seed.zip")
        self.addCleanup(path.unlink, missing_ok=True)
        report = export_seed(path, self.superuser.pk)
        return path, report["sha256"]

    def backup(self):
        directory = Path(self.media_directory.name) / "unit-test-backup"
        directory.mkdir()
        lines = []
        for name in ("database.dump", "media.tar.gz", "deployment-config.tar.gz.enc"):
            path = directory / name
            path.write_bytes(b"fake isolated unit-test backup")
            lines.append(digest_file(path) + "  " + name)
        (directory / "SHA256SUMS").write_text("\n".join(lines))
        (directory / "COMPLETE").touch()
        return directory

    def test_export_contains_only_latest_layouts_and_private_base_materials(self):
        template = self.version.template_version.template
        m.TemplateVersion.objects.create(template=template, number=2, canvas={"title": "最新标准模板"})
        path, checksum = self.bundle()
        manifest, records = read_seed(path, checksum)
        self.assertTrue(manifest["private"])
        self.assertEqual(sum(r["model"] == "auth.user" for r in records), 1)
        self.assertEqual(sum(r["model"] == "awards.templateversion" for r in records), 1)
        self.assertFalse(any(r["model"] in {"awards.certificate", "awards.competition", "awards.notification"} for r in records))
        self.assertEqual(next(r["fields"]["canvas"]["title"] for r in records if r["model"] == "awards.templateversion"), "最新标准模板")

    def test_reset_dry_run_and_backup_guard_never_delete_business(self):
        path, checksum = self.bundle()
        report = reset_business(path, checksum)
        self.assertFalse(report["applied"])
        self.assertEqual(report["remove"]["batches"], 1)
        with self.assertRaises(CommandError):
            reset_business(path, checksum, apply=True)
        self.assertEqual(m.AwardBatch.objects.count(), 1)

    def test_reset_preserves_base_assets_and_root_but_removes_business_and_live_files(self):
        from django.conf import settings
        path, checksum = self.bundle()
        old = Path(settings.MEDIA_ROOT) / "protected/certificates/2026/sample.pdf"
        old.parent.mkdir(parents=True)
        old.write_bytes(b"test certificate")
        root_password = self.superuser.password
        seal_files = list(m.SealVersion.objects.values_list("image", flat=True))
        report = reset_business(path, checksum, backup=self.backup(), apply=True)
        self.assertTrue(report["applied"])
        self.assertFalse(old.exists())
        self.assertEqual(list(get_user_model().objects.values_list("pk", flat=True)), [self.superuser.pk])
        self.assertEqual(get_user_model().objects.get().password, root_password)
        self.assertFalse(m.AwardBatch.objects.exists())
        self.assertFalse(m.Competition.objects.exists())
        self.assertFalse(m.DepartmentMembership.objects.exists())
        self.assertEqual(m.Template.objects.get().created_by_id, self.superuser.pk)
        self.assertTrue(all((Path(settings.MEDIA_ROOT) / name).exists() for name in seal_files))
        self.assertEqual(m.AuditEvent.objects.get().action, "system.production_initialized")

    def test_seed_rejects_stale_templates_and_modified_archive(self):
        path, checksum = self.bundle()
        with self.assertRaises(CommandError):
            read_seed(path, "0" * 64)
        template = self.version.template_version.template
        template.name = "导出后发生修改"
        template.save()
        with self.assertRaises(CommandError):
            reset_business(path, checksum, apply=True, backup=self.backup())
        self.assertTrue(m.Competition.objects.exists())

    def test_import_only_into_empty_database_and_roundtrips_root_layouts_and_media(self):
        path, checksum = self.bundle()
        with self.assertRaises(CommandError):
            import_seed(path, checksum)
        original_canvas = self.version.template_version.canvas
        root_password = self.superuser.password
        for model in BUSINESS_MODELS:
            model.objects.all().delete()
        for model in (m.TemplateVersion, m.Template, m.SealVersion, m.Seal, m.CertificateFont, m.Department, m.SystemSetting):
            model.objects.all().delete()
        get_user_model().objects.all().delete()
        result = import_seed(path, checksum)
        self.assertTrue(result["imported"])
        self.assertEqual(get_user_model().objects.get().password, root_password)
        self.assertEqual(m.TemplateVersion.objects.get().canvas, original_canvas)
        self.assertFalse(m.Competition.objects.exists())
        # Explicit PK imports must advance PostgreSQL sequences for the next real record.
        new = m.Department.objects.create(name="正式新部门", code="REAL")
        self.assertNotIn(new.pk, [dep.pk for dep in self.departments])

    def test_import_rejects_traversal_even_with_recomputed_outer_checksum(self):
        path, _ = self.bundle()
        with zipfile.ZipFile(path, "a") as archive:
            archive.writestr("../outside", b"blocked")
        with self.assertRaises(CommandError):
            read_seed(path, digest_file(path))
