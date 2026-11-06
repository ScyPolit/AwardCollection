import io
import base64
import tempfile
import zipfile
from pathlib import Path
from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import validate_pdf_signature
from .models import (
    ApprovalDepartment, AwardBatch, BatchVersion, Competition, Department,
    Certificate, GenerationTask, RevocationRequest, DepartmentMembership,
    Seal, SealVersion, SystemSetting, TeamAward, Template, TemplateVersion,
)
from .renderer import fit_text, render_certificate
from .services import (
    allocate_number, decide, decide_revocation, emergency_void, excel_template,
    emergency_issue, parse_excel, request_revocation, revise_batch, submit_batch,
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
                signatures = PdfFileReader(source).embedded_signatures
                self.assertEqual(len(signatures), 2)
                for signature in signatures:
                    status = validate_pdf_signature(signature)
                    self.assertTrue(status.intact)
                    self.assertTrue(status.valid)

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

        response = client.get(f"/api/v1/certificates/{certificate.id}/download/image/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'{certificate.number}.png', response["Content-Disposition"])
        response.close()
        response = client.get(f"/api/v1/certificates/batch/{self.batch.id}/archive/")
        self.assertEqual(response.status_code, 200)
        archive_data = b"".join(response.streaming_content)
        response.close()
        with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
            self.assertEqual(set(archive.namelist()), {f"{certificate.number}.pdf", f"{certificate.number}.png"})
        client.force_authenticate(self.outsider)
        response = client.get(f"/api/v1/certificates/batch/{self.batch.id}/archive/")
        self.assertEqual(response.status_code, 404)

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

    def test_batch_detail_action_returns_awards_and_approvals(self):
        client = APIClient(); client.force_authenticate(self.owner)
        response = client.get(f"/api/v1/batches/{self.batch.id}/detail/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["awards"]), 1)
        self.assertEqual(len(response.data["approvals"]), 2)

    def test_certificate_archive_is_paginated_and_searchable(self):
        certificate = self.create_published_certificate()
        client = APIClient(); client.force_authenticate(self.owner)
        response = client.get("/api/v1/certificates/?page=1&page_size=20")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["number"], certificate.number)
        response = client.get(f"/api/v1/certificates/?search={certificate.number}")
        self.assertEqual(response.data["count"], 1)
        Certificate.objects.create(award=TeamAward.objects.create(version=self.version, source_row=99, members=["待生成"], award_name="测试"), number=allocate_number())
        response = client.get("/api/v1/certificates/")
        self.assertEqual(response.data["count"], 1)

    def test_long_text_fits_or_raises_instead_of_truncating(self):
        size, _, lines = fit_text("长作品名" * 30, "Helvetica", 500, 120, 20, 8)
        self.assertGreaterEqual(size, 8)
        self.assertEqual("".join(lines), "长作品名" * 30)
        with self.assertRaises(ValueError):
            fit_text("超长文本" * 500, "Helvetica", 30, 10, 10, 10)

    def test_issued_batch_cannot_be_submitted_again(self):
        self.batch.status = AwardBatch.Status.ISSUED
        self.batch.save(update_fields=["status"])
        with self.assertRaisesRegex(ValueError, "不允许提交"):
            submit_batch(self.batch.id, self.owner)

    def test_outsider_cannot_create_or_change_department_resources(self):
        client = APIClient(); client.force_authenticate(self.outsider)
        response = client.post("/api/v1/seals/", {
            "name": "越权公章", "department": self.departments[0].id, "active": True,
        }, format="json")
        self.assertEqual(response.status_code, 400)
        template = self.version.template_version.template
        response = client.patch(f"/api/v1/templates/{template.id}/", {"name": "越权修改"}, format="json")
        self.assertIn(response.status_code, [403, 404])
        template.refresh_from_db()
        self.assertEqual(template.name, "测试模板")

    def test_batch_creation_freezes_selected_template_seals_and_formats(self):
        client = APIClient(); client.force_authenticate(self.owner)
        seals = {
            str(item.department_id): item.seal_version_id
            for item in self.version.required_departments.all()
        }
        response = client.post("/api/v1/batches/", {
            "competition": self.batch.competition_id,
            "name": "显式配置批次",
            "template_version": self.version.template_version_id,
            "output_formats": ["pdf"],
            "seal_versions": seals,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        created = AwardBatch.objects.get(pk=response.data["id"])
        version = created.versions.get(number=1)
        self.assertEqual(version.output_formats, ["pdf"])
        self.assertEqual(version.template_version_id, self.version.template_version_id)
        self.assertEqual(
            {str(item.department_id): item.seal_version_id for item in version.required_departments.all()},
            seals,
        )

    def test_template_background_and_seal_change_rendered_output(self):
        def data_image(color):
            output = io.BytesIO()
            Image.new("RGB", (20, 20), color).save(output, format="PNG")
            return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()

        seal_image = Path(self.media_directory.name) / "seal.png"
        Image.new("RGBA", (40, 40), (220, 20, 30, 255)).save(seal_image)
        template = {
            "page": {"width": 842, "height": 595},
            "background": data_image((230, 245, 255)),
            "layers": [
                {"type": "text", "field": "team_name", "x": 100, "y": 160, "width": 640, "height": 80, "fontSize": 28},
                {"type": "seal", "department": self.departments[0].id, "x": 620, "y": 410, "size": 100},
            ],
            "watermark": True,
        }
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=Path(directory)):
            pdf, image, digest = render_certificate(
                self.award,
                allocate_number(),
                template=template,
                seals=[{"department_id": self.departments[0].id, "image": str(seal_image)}],
            )
            self.assertTrue(pdf.exists())
            self.assertTrue(image.exists())
            self.assertEqual(len(digest), 64)

    def test_unpublished_certificate_cannot_be_downloaded_directly(self):
        certificate = Certificate.objects.create(
            award=self.award, number=allocate_number(),
            pdf=ContentFile(b"pdf", name="unpublished.pdf"),
        )
        client = APIClient(); client.force_authenticate(self.owner)
        response = client.get(f"/api/v1/certificates/{certificate.id}/download/pdf/")
        self.assertEqual(response.status_code, 403)

    def test_emergency_issue_requires_superuser_password_and_reason(self):
        with self.assertRaises(PermissionError):
            emergency_issue(self.batch.id, self.outsider, "紧急", "Test-Pass-2026")
        with self.assertRaises(PermissionError):
            emergency_issue(self.batch.id, self.superuser, "紧急", "wrong")
        with self.assertRaises(ValueError):
            emergency_issue(self.batch.id, self.superuser, "", "Test-Pass-2026")
        task = emergency_issue(self.batch.id, self.superuser, "测试专用紧急签发", "Test-Pass-2026")
        self.batch.refresh_from_db()
        self.assertEqual(task.status, GenerationTask.Status.QUEUED)
        self.assertEqual(self.batch.status, AwardBatch.Status.QUEUED)

    def test_public_settings_are_superuser_managed(self):
        client = APIClient(); client.force_authenticate(self.owner)
        response = client.put("/api/v1/settings/public-verification/", {"show_team": False}, format="json")
        self.assertEqual(response.status_code, 403)
        client.force_authenticate(self.superuser)
        response = client.put("/api/v1/settings/public-verification/", {
            "show_team": False, "show_members": True, "mask_members": False,
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SystemSetting.objects.get(key="public_verification").value["show_team"])

    def test_department_admin_can_create_owner_but_not_admin(self):
        client = APIClient(); client.force_authenticate(self.admin_a)
        payload = {"username": "new_owner", "name": "新负责人", "password": "Owner-Pass-2026", "department": self.departments[0].id, "role": "owner"}
        response = client.post("/api/v1/management/accounts/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        payload.update(username="new_admin", role="admin")
        response = client.post("/api/v1/management/accounts/", payload, format="json")
        self.assertEqual(response.status_code, 403)

    def test_batch_preview_uses_frozen_configuration_without_issuing(self):
        client = APIClient(); client.force_authenticate(self.owner)
        response = client.get(f"/api/v1/batches/{self.batch.id}/preview/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertFalse(Certificate.objects.filter(award=self.award).exists())

    def test_owner_can_choose_active_seal_metadata_without_accessing_originals(self):
        DepartmentMembership.objects.create(
            department=self.departments[0], user=self.owner, role="owner",
        )
        client = APIClient()
        client.force_authenticate(self.owner)
        response = client.get("/api/v1/seals/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["department"], self.departments[0].id)
        self.assertNotIn("image", response.data[0]["versions"][0])

    def test_owner_metadata_access_does_not_allow_seal_changes(self):
        DepartmentMembership.objects.create(
            department=self.departments[0], user=self.owner, role="owner",
        )
        seal = Seal.objects.get(department=self.departments[0])
        client = APIClient()
        client.force_authenticate(self.owner)
        response = client.patch(f"/api/v1/seals/{seal.id}/", {"active": False}, format="json")
        self.assertEqual(response.status_code, 404)
        seal.refresh_from_db()
        self.assertTrue(seal.active)
        response = client.post("/api/v1/seals/", {
            "name": "负责人不得创建", "department": self.departments[0].id,
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Seal.objects.filter(name="负责人不得创建").exists())

    def test_superuser_can_create_department(self):
        client = APIClient()
        client.force_authenticate(self.superuser)
        response = client.post("/api/v1/departments/", {
            "name": "新建测试部门", "code": "NEW-TEST",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Department.objects.filter(code="NEW-TEST").exists())

    def test_department_admin_cannot_create_or_modify_department(self):
        client = APIClient()
        client.force_authenticate(self.admin_a)
        response = client.post("/api/v1/departments/", {
            "name": "未授权部门", "code": "FORBIDDEN",
        }, format="json")
        self.assertEqual(response.status_code, 403)
        response = client.patch(f"/api/v1/departments/{self.departments[0].id}/", {
            "name": "未授权改名",
        }, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Department.objects.filter(code="FORBIDDEN").exists())

    def test_admin_can_link_existing_owner_without_resetting_password(self):
        client = APIClient()
        client.force_authenticate(self.admin_a)
        response = client.post("/api/v1/management/memberships/", {
            "username": self.owner.username, "department": self.departments[0].id,
            "role": "owner", "active": True,
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password("Test-Pass-2026"))
        self.assertTrue(DepartmentMembership.objects.filter(
            user=self.owner, department=self.departments[0], role="owner", active=True,
        ).exists())

    def test_department_admin_cannot_grant_an_existing_account_admin_role(self):
        client = APIClient()
        client.force_authenticate(self.admin_a)
        response = client.post("/api/v1/management/memberships/", {
            "username": self.owner.username, "department": self.departments[0].id,
            "role": "admin", "active": True,
        }, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(DepartmentMembership.objects.filter(
            user=self.owner, department=self.departments[0], role="admin",
        ).exists())
