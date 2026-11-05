from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand

from awards.models import (
    ApprovalDepartment, AwardBatch, BatchVersion, Competition, Department,
    SealVersion, TeamAward, TemplateVersion,
)
from awards.services import decide, submit_batch


class Command(BaseCommand):
    help = "Create an idempotent, fully approved TEST ONLY sample batch"

    def add_arguments(self, parser):
        parser.add_argument("--password", required=True)

    def handle(self, *args, **options):
        password = options["password"]
        call_command("seed_demo", password=password)
        User = get_user_model()
        owner = User.objects.get(username="owner")
        admin_a = User.objects.get(username="dept_a_admin1")
        admin_b = User.objects.get(username="dept_b_admin1")
        departments = list(Department.objects.filter(code__in=["TEST-A", "TEST-B"]).order_by("code"))
        competition, _ = Competition.objects.get_or_create(
            name="2026 测试专用双部门创新竞赛",
            defaults={"created_by": owner, "award_presets": ["一等奖", "二等奖", "优秀奖"]},
        )
        competition.collaborators.add(owner)
        competition.departments.set(departments)
        batch, created = AwardBatch.objects.get_or_create(
            competition=competition, name="测试专用首版体验批次",
            defaults={"created_by": owner},
        )
        if created or not batch.versions.exists():
            template = TemplateVersion.objects.filter(template__published=True).order_by("-created_at").first()
            version = BatchVersion.objects.create(
                batch=batch, number=1, template_version=template,
                output_formats=["pdf", "png"],
                snapshot={"test_only": True, "template": template.canvas},
            )
            for department in departments:
                seal = SealVersion.objects.filter(seal__department=department, seal__active=True).order_by("-number").first()
                ApprovalDepartment.objects.create(version=version, department=department, seal_version=seal)
            TeamAward.objects.bulk_create([
                TeamAward(version=version, source_row=2, members=["张三", "李四", "王五"], award_name="一等奖", team_name="星火测试团队", work_name="校园竞赛电子证书可信签发平台", category="数字校园", teachers=["赵老师"], note="测试专用", last_edited_by=owner),
                TeamAward(version=version, source_row=3, members=["陈晨", "林晓", "周明", "吴知夏", "孙景行", "何书瑶"], award_name="特别创新奖", team_name="长文本排版测试团队", work_name="面向多部门协同治理场景的校园竞赛电子证书可信签发、长文本自动适配与可追溯验证关键技术研究及示范应用", category="创新实践", teachers=["钱老师", "郑老师"], note="测试专用长文本", last_edited_by=owner),
            ])
        version = batch.versions.get(number=batch.current_version)
        if batch.status in [AwardBatch.Status.DRAFT, AwardBatch.Status.RETURNED]:
            submit_batch(batch.id, owner)
            batch.refresh_from_db()
        if batch.status == AwardBatch.Status.REVIEW:
            for requirement in version.required_departments.order_by("department_id"):
                actor = admin_a if requirement.department.code == "TEST-A" else admin_b
                decide(requirement.id, actor, "approved", "测试专用自动会签")
            batch.refresh_from_db()
        self.stdout.write(self.style.SUCCESS(f"sample ready: batch={batch.id}, status={batch.status}"))
