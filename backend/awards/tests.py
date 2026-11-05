import io
import tempfile
from pathlib import Path
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from pyhanko.pdf_utils.reader import PdfFileReader
from .models import (
    ApprovalDepartment, AwardBatch, BatchVersion, Competition, Department,
    Certificate, RevocationRequest, DepartmentMembership, Seal, SealVersion,
    TeamAward, Template, TemplateVersion,
)
from .renderer import fit_text, render_certificate
from .services import (
    allocate_number, decide, decide_revocation, emergency_void, excel_template,
    parse_excel, request_revocation, revise_batch, submit_batch,
)


class WorkflowTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=Path(self.media_directory.name))
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(self.media_directory.cleanup)
        User = get_user_model()
        self.owner = User.objects.create_user("owner", password="Test-Pass-2026")
        self.admin_a = User.objects.create_user("admin_a", password="Test-Pass-2026")
        self.admin_b = User.objects.create_user("admin_b", password="Test-Pass-2026")
        self.outsider = User.objects.create_user("outsider", password="Test-Pass-2026")
        self.superuser = User.objects.create_superuser("super", password="Test-Pass-2026")
        self.departments = [Department.objects.create(name=f"测试部门{x}", code=f"T{x}") for x in ("A", "B")]
        DepartmentMembership.objects.create(department=self.departments[0], user=self.admin_a, role="admin")
        DepartmentMembership.objects.create(department=self.departments[1], user=self.admin_b, role="admin")
        competition = Competition.objects.create(name="测试竞赛", created_by=self.owner)
        competition.collaborators.add(self.owner)
        competition.departments.add(*self.departments)
        template = Template.objects.create(name="测试模板", department=self.departments[0], created_by=self.admin_a, published=True)
        template_version = TemplateVersion.objects.create(template=template, number=1, canvas={})
        self.batch = AwardBatch.objects.create(competition=competition, name="测试批次", created_by=self.owner)
        self.version = BatchVersion.objects.create(batch=self.batch, number=1, template_version=template_version)
        for department in self.departments:
            seal = Seal.objects.create(department=department, name="测试公章")
            seal_version = SealVersion.objects.create(seal=seal, number=1, image=ContentFile(b"test", name="test.png"), sha256="0" * 64)
            ApprovalDepartment.objects.create(version=self.version, department=department, seal_version=seal_version)
        self.award = TeamAward.objects.create(version=self.version, source_row=2, members=["张三", "李四"], award_name="一等奖", team_name="测试专用团队", last_edited_by=self.owner)

    def test_excel_template_roundtrip(self):
        rows, errors = parse_excel(io.BytesIO(excel_template()))
        self.assertFalse(errors)
        self.assertEqual(rows[0]["members"], ["张三", "李四"])

    def test_approval_creates_one_task_and_enforces_avoidance(self):
        submit_batch(self.batch.id, self.owner)
        requirements = list(self.version.required_departments.order_by("department_id"))
        self.assertIsNone(decide(requirements[0].id, self.admin_a, "approved"))
        task = decide(requirements[1].id, self.admin_b, "approved")
        self.assertIsNotNone(task)
        self.assertEqual(self.version.generation_task.pk, task.pk)

    def test_submitter_cannot_approve(self):
        DepartmentMembership.objects.create(department=self.departments[0], user=self.owner, role="admin")
        submit_batch(self.batch.id, self.owner)
        with self.assertRaises(PermissionError):
            decide(self.version.required_departments.first().id, self.owner, "approved")

    def test_numbers_are_unique(self):
        self.assertNotEqual(allocate_number(), allocate_number())

    def test_render_has_two_incremental_signatures(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=Path(directory)):
            number = allocate_number()
            pdf, image, digest = render_certificate(self.award, number)
            self.assertTrue(pdf.exists())
            self.assertTrue(image.exists())
            self.assertEqual(len(digest), 64)
            with open(pdf, "rb") as source:
                self.assertEqual(len(PdfFileReader(source).embedded_signatures), 2)

    def test_return_and_revise_invalidates_old_approval(self):
        submit_batch(self.batch.id, self.owner)
        requirement = self.version.required_departments.order_by("department_id").first()
        decide(requirement.id, self.admin_a, "approved")
        second = self.version.required_departments.order_by("department_id").last()
        decide(second.id, self.admin_b, "returned", "第 2 行作品名需修改")
        rows = [{"source_row": 2, "members": ["张三", "李四"], "award_name": "一等奖", "team_name": "修订团队", "work_name": "修订作品", "category": "创新", "teachers": [], "note": ""}]
        revised = revise_batch(self.batch.id, self.owner, rows, expected_version=1)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.current_version, 2)
        self.assertEqual(revised.required_departments.count(), 2)
        self.assertFalse(revised.required_departments.filter(decision__isnull=False).exists())
        with self.assertRaises(ValueError):
            decide(requirement.id, self.admin_a, "approved")

    def test_revision_conflict_rejected(self):
        rows = [{"source_row": 2, "members": ["张三"], "award_name": "一等奖", "team_name": "团队", "work_name": "作品", "category": "", "teachers": [], "note": ""}]
        revise_batch(self.batch.id, self.owner, rows, expected_version=1)
        with self.assertRaises(ValueError):
            revise_batch(self.batch.id, self.owner, rows, expected_version=1)

    def create_published_certificate(self):
        return Certificate.objects.create(
            award=self.award, number=allocate_number(), published_at=timezone.now(),
            pdf=ContentFile(b"pdf", name="certificate.pdf"),
            image=ContentFile(b"png", name="certificate.png"),
        )

    def test_revocation_partial_approval_keeps_certificate_active(self):
        certificate = self.create_published_certificate()
        item = request_revocation(certificate.id, self.owner, "信息纠错")
        decide_revocation(item.id, self.departments[0].id, self.admin_a, "approved")
        certificate.refresh_from_db(); item.refresh_from_db()
        self.assertEqual(certificate.status, Certificate.Status.ACTIVE)
        self.assertEqual(item.status, RevocationRequest.Status.REVIEW)

    def test_revocation_rejection_keeps_certificate_active(self):
        certificate = self.create_published_certificate()
        item = request_revocation(certificate.id, self.owner, "信息纠错")
        decide_revocation(item.id, self.departments[0].id, self.admin_a, "rejected")
        certificate.refresh_from_db(); item.refresh_from_db()
        self.assertEqual(certificate.status, Certificate.Status.ACTIVE)
        self.assertEqual(item.status, RevocationRequest.Status.REJECTED)

    def test_revocation_all_departments_voids_certificate(self):
        certificate = self.create_published_certificate()
        item = request_revocation(certificate.id, self.owner, "信息纠错")
        decide_revocation(item.id, self.departments[0].id, self.admin_a, "approved")
        decide_revocation(item.id, self.departments[1].id, self.admin_b, "approved")
        certificate.refresh_from_db(); item.refresh_from_db()
        self.assertEqual(certificate.status, Certificate.Status.VOID)
        self.assertEqual(item.status, RevocationRequest.Status.APPROVED)

    def test_emergency_void_requires_superuser_password_and_reason(self):
        certificate = self.create_published_certificate()
        with self.assertRaises(PermissionError):
            emergency_void(certificate.id, self.outsider, "测试", "Test-Pass-2026")
        with self.assertRaises(PermissionError):
            emergency_void(certificate.id, self.superuser, "测试", "wrong")
        with self.assertRaises(ValueError):
            emergency_void(certificate.id, self.superuser, "", "Test-Pass-2026")
        emergency_void(certificate.id, self.superuser, "测试专用应急操作", "Test-Pass-2026")
        certificate.refresh_from_db()
        self.assertEqual(certificate.status, Certificate.Status.VOID)

    def test_protected_download_rejects_outsider(self):
        certificate = self.create_published_certificate()
        client = APIClient(); client.force_authenticate(self.outsider)
        response = client.get(f"/api/v1/certificates/{certificate.id}/download/pdf/")
        self.assertEqual(response.status_code, 403)
        client.force_authenticate(self.owner)
        response = client.get(f"/api/v1/certificates/{certificate.id}/download/pdf/")
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_verification_challenge_is_single_use(self):
        certificate = self.create_published_certificate()
        client = APIClient()
        response = client.get("/api/v1/verification/challenge/")
        left, right = [int(item.strip()) for item in response.data["question"].split("=")[0].split("+")]
        payload = {"number": certificate.number, "answer": left + right}
        first = client.post("/api/v1/verification/query/", payload, format="json")
        second = client.post("/api/v1/verification/query/", payload, format="json")
        self.assertTrue(first.data["found"])
        self.assertEqual(second.status_code, 400)

    def test_login_locks_after_five_failures(self):
        client = APIClient()
        for _ in range(5):
            client.post("/api/v1/auth/login/", {"username": "owner", "password": "wrong"}, format="json")
        response = client.post("/api/v1/auth/login/", {"username": "owner", "password": "Test-Pass-2026"}, format="json")
        self.assertEqual(response.status_code, 429)

    def test_long_text_fits_or_raises_instead_of_truncating(self):
        size, _, lines = fit_text("长作品名" * 30, "Helvetica", 500, 120, 20, 8)
        self.assertGreaterEqual(size, 8)
        self.assertEqual("".join(lines), "长作品名" * 30)
        with self.assertRaises(ValueError):
            fit_text("超长文本" * 500, "Helvetica", 30, 10, 10, 10)
