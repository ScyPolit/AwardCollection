import hashlib
from io import BytesIO
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw
from awards.models import Department, DepartmentMembership, Seal, SealVersion, Template, TemplateVersion


USERS = [
    ("superadmin", "系统超管", True),
    ("owner", "测试负责人", False),
    ("dept_a_admin1", "甲部门管理员一", False),
    ("dept_a_admin2", "甲部门管理员二", False),
    ("dept_b_admin1", "乙部门管理员一", False),
    ("dept_b_admin2", "乙部门管理员二", False),
    ("outsider", "无关部门账号", False),
]


class Command(BaseCommand):
    help = "Create idempotent TEST ONLY demo departments, users, seals and template"

    def add_arguments(self, parser):
        parser.add_argument("--password", required=True)

    def handle(self, *args, **options):
        password = options["password"]
        User = get_user_model()
        users = {}
        for username, full_name, superuser in USERS:
            user, _ = User.objects.get_or_create(username=username, defaults={"is_staff": superuser, "is_superuser": superuser})
            user.first_name = full_name
            user.is_staff = superuser
            user.is_superuser = superuser
            user.set_password(password)
            user.save()
            users[username] = user
        departments = []
        for code, name in [("TEST-A", "测试专用甲部门"), ("TEST-B", "测试专用乙部门"), ("TEST-X", "测试专用无关部门")]:
            department, _ = Department.objects.get_or_create(code=code, defaults={"name": name})
            departments.append(department)
        for index, department in enumerate(departments[:2]):
            DepartmentMembership.objects.get_or_create(department=department, user=users["owner"], role=DepartmentMembership.Role.OWNER)
            for suffix in (1, 2):
                DepartmentMembership.objects.get_or_create(department=department, user=users[f"dept_{'a' if index == 0 else 'b'}_admin{suffix}"], role=DepartmentMembership.Role.ADMIN)
            seal, _ = Seal.objects.get_or_create(department=department, name="测试专用公章")
            if not seal.versions.exists():
                image = Image.new("RGBA", (400, 400), (255, 255, 255, 0))
                draw = ImageDraw.Draw(image)
                draw.ellipse((15, 15, 385, 385), outline=(205, 35, 45, 255), width=18)
                draw.text((115, 180), "TEST ONLY", fill=(205, 35, 45, 255))
                out = BytesIO(); image.save(out, "PNG"); content = out.getvalue()
                version = SealVersion(seal=seal, number=1, sha256=hashlib.sha256(content).hexdigest())
                version.image.save(f"test-only-{department.code}.png", ContentFile(content), save=True)
        template, _ = Template.objects.get_or_create(name="测试专用 A4 横版模板", department=departments[0], defaults={"created_by": users["superadmin"], "published": True})
        template.published = True; template.save(update_fields=["published"])
        TemplateVersion.objects.get_or_create(template=template, number=1, defaults={"canvas": {"page": {"width": 842, "height": 595}, "showNumber": True, "showWatermark": True}})
        self.stdout.write(self.style.SUCCESS("TEST ONLY demo data ready"))
