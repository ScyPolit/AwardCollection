from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from awards.models import (
    ApprovalDepartment, AwardBatch, BatchVersion, Competition, Department,
    SealVersion, TeamAward, TemplateVersion,
)
from awards.services import decide, submit_batch


class Command(BaseCommand):
    help = "Create and approve an idempotent TEST ONLY scale batch"

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=5000)

    def handle(self, *args, **options):
        count = options["count"]
        if count < 1 or count > 5000:
            raise ValueError("count must be between 1 and 5000")
        User = get_user_model()
        owner = User.objects.get(username="owner")
        admin_a = User.objects.get(username="dept_a_admin1")
        admin_b = User.objects.get(username="dept_b_admin1")
        departments = list(Department.objects.filter(code__in=["TEST-A", "TEST-B"]).order_by("code"))
        competition, _ = Competition.objects.get_or_create(
            name="测试专用 5000 团队规模竞赛", defaults={"created_by": owner}
        )
        competition.collaborators.add(owner)
        competition.departments.set(departments)
        batch, created = AwardBatch.objects.get_or_create(
            competition=competition, name=f"测试专用 {count} 团队规模批次",
            defaults={"created_by": owner},
        )
        if created:
            template = TemplateVersion.objects.filter(template__published=True).order_by("-created_at").first()
            version = BatchVersion.objects.create(
                batch=batch, number=1, template_version=template,
                output_formats=["pdf", "png"], snapshot={"test_only": True, "scale": count},
            )
            for department in departments:
                seal = SealVersion.objects.filter(seal__department=department, seal__active=True).order_by("-number").first()
                ApprovalDepartment.objects.create(version=version, department=department, seal_version=seal)
            chunk = []
            for index in range(1, count + 1):
                chunk.append(TeamAward(
                    version=version, source_row=index + 1,
                    members=[f"测试成员{index:04d}甲", f"测试成员{index:04d}乙"],
                    award_name=["一等奖", "二等奖", "优秀奖"][index % 3],
                    team_name=f"测试专用规模团队 {index:04d}",
                    work_name=f"测试专用规模作品 {index:04d}",
                    category="规模验收", teachers=["测试教师"],
                    note="5000 团队压力测试专用", last_edited_by=owner,
                ))
                if len(chunk) == 500:
                    TeamAward.objects.bulk_create(chunk)
                    chunk = []
            if chunk:
                TeamAward.objects.bulk_create(chunk)
        version = batch.versions.get(number=batch.current_version)
        if batch.status in [AwardBatch.Status.DRAFT, AwardBatch.Status.RETURNED]:
            submit_batch(batch.id, owner)
            batch.refresh_from_db()
        if batch.status == AwardBatch.Status.REVIEW:
            for requirement in version.required_departments.order_by("department_id"):
                decide(requirement.id, admin_a if requirement.department.code == "TEST-A" else admin_b, "approved", "5000 规模测试自动会签")
        self.stdout.write(self.style.SUCCESS(f"scale batch ready: id={batch.id}, teams={version.awards.count()}"))
