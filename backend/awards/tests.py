import io
import tempfile
from pathlib import Path
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from pyhanko.pdf_utils.reader import PdfFileReader
from .models import (
    ApprovalDepartment, AwardBatch, BatchVersion, Competition, Department,
    DepartmentMembership, Seal, SealVersion, TeamAward, Template, TemplateVersion,
)
from .renderer import render_certificate
from .services import allocate_number, decide, excel_template, parse_excel, submit_batch


class WorkflowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user("owner", password="Test-Pass-2026")
        self.admin_a = User.objects.create_user("admin_a", password="Test-Pass-2026")
        self.admin_b = User.objects.create_user("admin_b", password="Test-Pass-2026")
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
