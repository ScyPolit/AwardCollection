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
from .permissions import grant_owner, is_owner
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
        grant_owner(self.owner)
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
                    self.assertEqual(list(signature.sig_field["/Rect"]), [0, 0, 0, 0])
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
        self.assertEqual(b"".join(response.streaming_content), b"pdf")

        response = client.get(f"/api/v1/certificates/{certificate.id}/download/image/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'{certificate.number}.png', response["Content-Disposition"])
        self.assertEqual(b"".join(response.streaming_content), b"png")
        response = client.get(f"/api/v1/certificates/batch/{self.batch.id}/archive/")
        self.assertEqual(response.status_code, 200)
        archive_data = b"".join(response.streaming_content)
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
        self.assertEqual(len(response.data), 2)
        self.assertEqual(set(item["department"] for item in response.data), set(d.id for d in self.departments))
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
        self.assertTrue(is_owner(self.owner))
        self.assertFalse(DepartmentMembership.objects.filter(user=self.owner, role="owner").exists())

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

    def test_owner_creation_has_no_department_and_duplicate_is_rejected(self):
        client = APIClient(); client.force_authenticate(self.admin_a)
        payload = {"username": "independent_owner", "name": "独立负责人", "password": "Owner-Strong-2026!", "role": "owner"}
        response = client.post("/api/v1/management/accounts/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        user = get_user_model().objects.get(username=payload['username'])
        self.assertTrue(is_owner(user))
        self.assertFalse(DepartmentMembership.objects.filter(user=user).exists())
        self.assertEqual(response.data['memberships'], [])
        self.assertNotIn(payload['password'], str(response.data))
        self.assertEqual(client.post("/api/v1/management/accounts/", payload, format="json").status_code, 400)
        self.assertEqual(get_user_model().objects.filter(username=payload['username']).count(), 1)

    def test_independent_owner_can_choose_departments_and_create_competition(self):
        client = APIClient(); client.force_authenticate(self.owner)
        self.assertFalse(DepartmentMembership.objects.filter(user=self.owner).exists())
        self.assertEqual(len(client.get('/api/v1/departments/').data), 2)
        response = client.post('/api/v1/competitions/', {'name': '独立负责人测试竞赛', 'departments': [d.id for d in self.departments]}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data['active'])
        client.force_authenticate(self.outsider)
        self.assertEqual(client.post('/api/v1/competitions/', {'name':'无授权竞赛', 'departments':[self.departments[0].id]}, format='json').status_code, 403)

    def test_superuser_can_deactivate_competition_without_revoking_history(self):
        certificate = self.create_published_certificate()
        client = APIClient(); client.force_authenticate(self.superuser)
        response = client.patch(f'/api/v1/competitions/{self.batch.competition_id}/', {'active': False}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        with self.assertRaisesMessage(ValueError, '废止'):
            submit_batch(self.batch.pk, self.owner)
        client.force_authenticate(self.owner)
        response = client.post('/api/v1/batches/', {'name':'应拒绝的新批次', 'competition':self.batch.competition_id}, format='json')
        self.assertEqual(response.status_code, 400)
        certificate.refresh_from_db(); self.assertEqual(certificate.status, 'active')
        client.force_authenticate(self.superuser)
        self.assertEqual(client.patch(f'/api/v1/competitions/{self.batch.competition_id}/', {'active':True}, format='json').status_code, 200)
        self.assertEqual(client.delete(f'/api/v1/competitions/{self.batch.competition_id}/').status_code, 400)

    def test_non_superuser_cannot_change_competition_active_flag(self):
        client = APIClient(); client.force_authenticate(self.owner)
        response = client.patch(f'/api/v1/competitions/{self.batch.competition_id}/', {'active':False}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_superuser_inherits_department_approval_without_memberships(self):
        self.assertFalse(DepartmentMembership.objects.filter(user=self.superuser).exists())
        submit_batch(self.batch.pk, self.owner)
        requirements = list(self.version.required_departments.order_by('id'))
        self.assertIsNone(decide(requirements[0].pk, self.superuser, 'approved'))
        self.assertIsNotNone(decide(requirements[1].pk, self.superuser, 'approved'))
        for requirement in requirements:
            self.assertEqual(requirement.decision.actor_id, self.superuser.pk)

    def test_superuser_still_observes_ordinary_approval_avoidance(self):
        submit_batch(self.batch.pk, self.superuser)
        with self.assertRaises(PermissionError):
            decide(self.version.required_departments.first().pk, self.superuser, 'approved')

    def test_superuser_inherits_revocation_approval(self):
        certificate = self.create_published_certificate()
        request = request_revocation(certificate.pk, self.owner, '测试作废')
        decide_revocation(request.pk, self.departments[0].pk, self.superuser, 'approved')
        certificate.refresh_from_db(); self.assertEqual(certificate.status, 'active')
        decide_revocation(request.pk, self.departments[1].pk, self.superuser, 'approved')
        certificate.refresh_from_db(); self.assertEqual(certificate.status, 'void')

    def test_font_catalog_serves_exact_font_bytes_with_authentication(self):
        from django.core.management import call_command
        call_command('cache_builtin_fonts', verbosity=0)
        from .fonts import font_file
        client = APIClient(); client.force_authenticate(self.owner)
        catalog = client.get('/api/v1/fonts/')
        self.assertEqual(catalog.status_code, 200)
        self.assertTrue({'hei','song','kai','fangsong'}.issubset({f['id'] for f in catalog.data}))
        response = client.get('/api/v1/fonts/fangsong/file/')
        self.assertEqual(b''.join(response.streaming_content), font_file('fangsong').read_bytes())
        self.assertEqual(APIClient().get('/api/v1/fonts/fangsong/file/').status_code, 403)

    def test_shared_layout_falls_back_for_mixed_english_and_chinese(self):
        from .fonts import layout_text
        layer = {'fontFamily':'liberationserif-regular','fontSize':24,'minFontSize':12,'width':500,'height':100,'lineHeight':1.5,'align':'left'}
        layout = layout_text('荣誉证书 AWARD 2026', layer)
        fonts = {r['fontId'] for line in layout['lines'] for r in line['runs']}
        self.assertEqual(fonts, {'hei','liberationserif-regular'})
        self.assertEqual(layout['lines'][0]['baseline'], 36)
        with self.assertRaisesMessage(ValueError, '缺少字形'):
            layout_text(chr(0x10FFFF), layer)

    def test_template_layout_endpoint_and_font_selection(self):
        client = APIClient(); client.force_authenticate(self.admin_a)
        canvas = {'page':{'width':842,'height':595},'layers':[{'id':'title','type':'text','field':'static','text':'荣誉证书 AWARD','x':100,'y':100,'width':600,'height':100,'fontFamily':'fangsong','fontSize':32,'minFontSize':10,'lineHeight':1.4}]}
        response = client.post('/api/v1/templates/layout/', {'canvas':canvas}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['title']['fontSize'], 32)
        self.assertTrue(all(r['fontId']=='fangsong' for line in response.data['title']['lines'] for r in line['runs']))
        canvas['background']='/srv/media/protected/seals/forbidden.png'
        response = client.post('/api/v1/templates/', {'department':self.departments[0].pk,'name':'坏模板','canvas':canvas}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Template.objects.filter(name='坏模板').exists())

    def test_font_import_requires_login_and_license_confirmation(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .fonts import font_file
        self.assertEqual(APIClient().post('/api/v1/fonts/',{},format='multipart').status_code,403)
        client = APIClient(); client.force_authenticate(self.owner)
        self.assertEqual(client.post('/api/v1/fonts/',{},format='multipart').status_code,400)
        file=SimpleUploadedFile('licensed.ttf',font_file('liberationserif-regular').read_bytes())
        response=client.post('/api/v1/fonts/',{'file':file,'name':'授权英文字体测试','license_confirmed':'true'},format='multipart')
        self.assertEqual(response.status_code,201,response.data)
        self.assertEqual(response.data['name'],'授权英文字体测试')
        file_response=client.get(response.data['url'])
        self.assertGreater(len(b''.join(file_response.streaming_content)),1000)
        from .fonts import resolved_font_files, layout_text
        files={response.data['id']:str(font_file(response.data['id'])),'hei':str(font_file('hei'))}
        with self.assertNumQueries(0), resolved_font_files(files):
            layout=layout_text('荣誉证书 AWARD',{'fontFamily':response.data['id'],'fontSize':24,'minFontSize':10,'width':500,'height':100})
            self.assertTrue(layout['lines'])
        for user in (self.admin_a, self.outsider, self.superuser):
            client.force_authenticate(user)
            self.assertEqual(client.post('/api/v1/fonts/',{},format='multipart').status_code,400)
            duplicate=client.post('/api/v1/fonts/',{'file':SimpleUploadedFile('licensed.ttf',font_file('liberationserif-regular').read_bytes()),'license_confirmed':'true'},format='multipart')
            self.assertEqual(duplicate.status_code,200,duplicate.data)
            self.assertEqual(duplicate.data['id'],response.data['id'])
        client.force_authenticate(self.owner)
        self.assertEqual(client.post('/api/v1/fonts/',{'file':SimpleUploadedFile('bad.ttf',b'not a font'),'license_confirmed':'true'},format='multipart').status_code,400)


    def test_only_superuser_can_manage_font_without_changing_historical_bytes(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .fonts import font_file, layout_text
        client = APIClient(); client.force_authenticate(self.superuser)
        content = font_file('liberationserif-regular').read_bytes()
        response = client.post('/api/v1/fonts/', {'file': SimpleUploadedFile('licensed.ttf', content), 'license_confirmed': 'true'}, format='multipart')
        self.assertEqual(response.status_code, 201)
        font_id = response.data['id']; url = f'/api/v1/fonts/{font_id}/'
        for user in (self.owner, self.admin_a):
            client.force_authenticate(user)
            self.assertEqual(client.patch(url, {'active': False}, format='json').status_code, 403)
            self.assertEqual(client.get('/api/v1/fonts/?include_inactive=1').status_code, 403)
        client.force_authenticate(self.superuser)
        self.assertEqual(client.patch(url, {'name': '', 'active': False}, format='json').status_code, 400)
        self.assertEqual(client.patch(url, {'file': 'replacement'}, format='json').status_code, 400)
        response = client.patch(url, {'name': '学校授权字体', 'active': False}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['active'])
        self.assertNotIn(font_id, {f['id'] for f in client.get('/api/v1/fonts/').data})
        self.assertIn(font_id, {f['id'] for f in client.get('/api/v1/fonts/?include_inactive=1').data})
        self.assertEqual(font_file(font_id).read_bytes(), content)
        self.assertTrue(layout_text('历史证书 AWARD', {'fontFamily': font_id})['lines'])
        self.assertEqual(client.patch(url, {'active': True}, format='json').status_code, 200)
        self.assertEqual(client.patch('/api/v1/fonts/hei/', {'active': False}, format='json').status_code, 400)

    def test_styled_text_and_shapes_are_rendered_and_remain_extractable(self):
        import fitz
        from .fonts import validate_canvas
        from .renderer import render_unsigned
        title={'id':'title','type':'text','field':'static','text':'荣誉证书 AWARD','x':80,'y':50,'width':650,'height':100,'fontFamily':'fangsong','fontSize':36,'minFontSize':10,'bold':True,'italic':True,'underline':True}
        shapes=[
            {'id':'box','type':'shape','kind':'rect','x':80,'y':200,'width':120,'height':80,'stroke':'#123456','fill':'#e5edff','strokeWidth':2},
            {'id':'oval','type':'shape','kind':'ellipse','x':300,'y':200,'width':140,'height':90,'stroke':'#cc3333','fill':'none','strokeWidth':3},
            {'id':'line','type':'shape','kind':'line','x':100,'y':400,'width':500,'height':5,'stroke':'#336699','fill':'none','strokeWidth':2,'points':[[0,0],[1,1]]},
            {'id':'pen','type':'shape','kind':'freehand','x':500,'y':200,'width':180,'height':100,'stroke':'#00aa33','fill':'none','strokeWidth':4,'points':[[0,0],[.2,.8],[.5,.3],[1,1]]},
        ]
        template=validate_canvas({'page':{'width':842,'height':595},'layers':[title,*shapes]})
        output=io.BytesIO();render_unsigned(self.award,'TEST-STYLES',output,template=template)
        document=fitz.open(stream=output.getvalue(),filetype='pdf');page=document[0]
        self.assertIn('荣誉证书 AWARD',page.get_text())
        self.assertGreaterEqual(len(page.get_drawings()),5)
        self.assertTrue(any(span['type']==1 for span in page.get_texttrace()),'Bold outlines must be present in the PDF')
        pixel=page.get_pixmap().pixel(120,240)
        self.assertTrue(all(abs(a-b)<=1 for a,b in zip(pixel,(229,237,255))))
        plain=io.BytesIO();render_unsigned(self.award,'TEST-STYLES',plain,template={'page':{'width':842,'height':595},'layers':[{**title,'bold':False,'italic':False,'underline':False}]})
        original=fitz.open(stream=plain.getvalue(),filetype='pdf')
        self.assertNotEqual(page.get_pixmap().samples,original[0].get_pixmap().samples)

    def test_template_rejects_invalid_shapes_and_non_boolean_text_styles(self):
        client=APIClient();client.force_authenticate(self.admin_a)
        shape={'id':'shape','type':'shape','kind':'freehand','x':20,'y':20,'width':200,'height':100,'stroke':'#123456','fill':'none','strokeWidth':2,'points':[[0,0],[1,1]]}
        bad_layers=[{**shape,'points':[[0,0],[2,1]]},{**shape,'points':[[0,0]]},{**shape,'points':[[0,0]]*1001},{**shape,'stroke':None},{**shape,'kind':'script'},{**shape,'strokeWidth':50},
                    {'id':'t','type':'text','field':'static','text':'证书','x':20,'y':20,'width':200,'height':100,'bold':'yes'}]
        bad_layers += [{key:value for key,value in shape.items() if key != missing} for missing in ('x','y','width','height','stroke','fill','strokeWidth')]
        for layer in bad_layers:
            response=client.post('/api/v1/templates/layout/',{'canvas':{'page':{'width':842,'height':595},'layers':[layer]}},format='json')
            self.assertEqual(response.status_code,400,response.data)
        too_many=[{**shape,'id':str(i),'points':[[0,0]]*900} for i in range(6)]
        self.assertEqual(client.post('/api/v1/templates/layout/',{'canvas':{'page':{'width':842,'height':595},'layers':too_many}},format='json').status_code,400)

    def test_audit_details_are_scoped_to_actor_for_department_admin(self):
        from .models import AuditEvent
        first=AuditEvent.objects.create(actor=self.admin_a,action='test.detail',object_type='TEST',object_id='1',detail={'reason':'完整内容'})
        other=AuditEvent.objects.create(actor=self.admin_b,action='test.detail',object_type='TEST',object_id='2',detail={'reason':'他部门内容'})
        client=APIClient();client.force_authenticate(self.admin_a)
        self.assertEqual(client.get(f'/api/v1/logs/{first.pk}/').data['detail']['reason'],'完整内容')
        self.assertEqual(client.get(f'/api/v1/logs/{other.pk}/').status_code,404)
        client.force_authenticate(self.superuser)
        self.assertEqual(client.get(f'/api/v1/logs/{other.pk}/').status_code,200)
        client.force_authenticate(self.owner)
        self.assertEqual(client.get('/api/v1/logs/').status_code,403)

    def test_seal_preview_is_authorized_and_can_choose_version(self):
        seal=Seal.objects.get(department=self.departments[0]);version=seal.versions.first()
        content=io.BytesIO();Image.new('RGBA',(100,100),(255,0,0,100)).save(content,'PNG')
        version.image.save('valid-preview.png',ContentFile(content.getvalue()),save=True)
        client=APIClient();client.force_authenticate(self.superuser)
        response=client.get(f'/api/v1/seals/{seal.pk}/preview/?version={version.pk}')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.content.startswith(b'\x89PNG'))
        client.force_authenticate(self.outsider)
        self.assertEqual(client.get(f'/api/v1/seals/{seal.pk}/preview/').status_code,404)

    def test_template_thumbnail_is_real_png_and_certificate_detail_is_complete(self):
        client=APIClient();client.force_authenticate(self.owner)
        template=self.version.template_version.template
        response=client.get(f'/api/v1/templates/{template.pk}/thumbnail/')
        self.assertEqual(response.status_code,200)
        self.assertTrue(b''.join(response.streaming_content).startswith(b'\x89PNG'))
        certificate=self.create_published_certificate()
        detail=client.get(f'/api/v1/certificates/{certificate.pk}/')
        self.assertEqual(detail.status_code,200)
        self.assertEqual(detail.data['members'],self.award.members)
        self.assertEqual(len(detail.data['departments']),2)

    def test_deactivated_competition_cannot_finish_pending_approval(self):
        submit_batch(self.batch.pk,self.owner)
        competition=self.batch.competition
        competition.active=False;competition.save(update_fields=['active'])
        with self.assertRaisesMessage(ValueError,'废止'):
            decide(self.version.required_departments.first().pk,self.superuser,'approved')
        self.assertFalse(GenerationTask.objects.filter(version=self.version).exists())
