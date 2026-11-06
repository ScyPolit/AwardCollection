import uuid
from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Department(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=24, unique=True)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, through="DepartmentMembership")

    def __str__(self):
        return self.name


class DepartmentMembership(TimeStampedModel):
    class Role(models.TextChoices):
        ADMIN = "admin", "部门管理员"
        OWNER = "owner", "竞赛负责人"

    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=16, choices=Role.choices)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["department", "user", "role"], name="uniq_department_member_role")]


class LoginProtection(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="login_protection")
    failed_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)


class Competition(TimeStampedModel):
    name = models.CharField(max_length=240)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_competitions")
    collaborators = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="competitions")
    departments = models.ManyToManyField(Department, related_name="competitions")
    award_presets = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True)


class Template(TimeStampedModel):
    name = models.CharField(max_length=160)
    department = models.ForeignKey(Department, on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    source = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
    published = models.BooleanField(default=False)


class TemplateVersion(TimeStampedModel):
    template = models.ForeignKey(Template, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField()
    canvas = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["template", "number"], name="uniq_template_version")]


class Seal(TimeStampedModel):
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="seals")
    name = models.CharField(max_length=120)
    active = models.BooleanField(default=True)


class SealVersion(TimeStampedModel):
    seal = models.ForeignKey(Seal, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField()
    image = models.FileField(upload_to="protected/seals/%Y/%m")
    sha256 = models.CharField(max_length=64)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["seal", "number"], name="uniq_seal_version")]


class CertificateFont(TimeStampedModel):
    sha256 = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=160)
    file = models.FileField(upload_to="protected/font-library")
    license_note = models.CharField(max_length=240)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)


class AwardBatch(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        REVIEW = "review", "审批中"
        RETURNED = "returned", "已退回"
        QUEUED = "queued", "待生成"
        ISSUED = "issued", "已签发"
        FAILED = "failed", "生成失败"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    competition = models.ForeignKey(Competition, on_delete=models.PROTECT, related_name="batches")
    name = models.CharField(max_length=160)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    current_version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)


class BatchVersion(TimeStampedModel):
    batch = models.ForeignKey(AwardBatch, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField()
    template_version = models.ForeignKey(TemplateVersion, on_delete=models.PROTECT)
    output_formats = models.JSONField(default=list)
    snapshot = models.JSONField(default=dict)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="submitted_batch_versions")
    submitted_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["batch", "number"], name="uniq_batch_version")]


class TeamAward(TimeStampedModel):
    version = models.ForeignKey(BatchVersion, on_delete=models.CASCADE, related_name="awards")
    source_row = models.PositiveIntegerField()
    members = models.JSONField(default=list)
    award_name = models.CharField(max_length=160)
    team_name = models.CharField(max_length=240, blank=True)
    work_name = models.CharField(max_length=500, blank=True)
    category = models.CharField(max_length=160, blank=True)
    teachers = models.JSONField(default=list, blank=True)
    note = models.TextField(blank=True)
    last_edited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["version", "source_row"], name="uniq_award_source_row")]


class ApprovalDepartment(TimeStampedModel):
    version = models.ForeignKey(BatchVersion, on_delete=models.CASCADE, related_name="required_departments")
    department = models.ForeignKey(Department, on_delete=models.PROTECT)
    seal_version = models.ForeignKey(SealVersion, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["version", "department"], name="uniq_required_department")]


class ApprovalDecision(TimeStampedModel):
    class Decision(models.TextChoices):
        APPROVED = "approved", "通过"
        RETURNED = "returned", "退回"

    requirement = models.OneToOneField(ApprovalDepartment, on_delete=models.CASCADE, related_name="decision")
    decision = models.CharField(max_length=16, choices=Decision.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    comment = models.TextField(blank=True)
    issue_rows = models.JSONField(default=list, blank=True)


class GenerationTask(TimeStampedModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "待处理"
        RUNNING = "running", "处理中"
        FAILED = "failed", "失败"
        DONE = "done", "完成"

    version = models.OneToOneField(BatchVersion, on_delete=models.PROTECT, related_name="generation_task")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    lease_token = models.UUIDField(null=True)
    lease_expires_at = models.DateTimeField(null=True)
    attempts = models.PositiveIntegerField(default=0)
    processed = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)


class Certificate(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "有效"
        VOID = "void", "已作废"

    number = models.CharField(max_length=32, unique=True)
    award = models.OneToOneField(TeamAward, on_delete=models.PROTECT, related_name="certificate")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    pdf = models.FileField(upload_to="protected/certificates/%Y", blank=True)
    image = models.FileField(upload_to="protected/certificates/%Y", blank=True)
    pdf_sha256 = models.CharField(max_length=64, blank=True)
    published_at = models.DateTimeField(null=True)


class RevocationRequest(TimeStampedModel):
    class Status(models.TextChoices):
        REVIEW = "review", "审批中"
        REJECTED = "rejected", "已驳回"
        APPROVED = "approved", "已作废"

    certificate = models.ForeignKey(Certificate, on_delete=models.PROTECT, related_name="revocation_requests")
    reason = models.TextField()
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.REVIEW)


class RevocationDecision(TimeStampedModel):
    class Decision(models.TextChoices):
        APPROVED = "approved", "通过"
        REJECTED = "rejected", "驳回"

    request = models.ForeignKey(RevocationRequest, on_delete=models.CASCADE, related_name="decisions")
    department = models.ForeignKey(Department, on_delete=models.PROTECT)
    decision = models.CharField(max_length=16, choices=Decision.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    comment = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["request", "department"], name="uniq_revocation_department")]


class AuditEvent(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=80)
    detail = models.JSONField(default=dict)


class Notification(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=160)
    body = models.TextField()
    read_at = models.DateTimeField(null=True)


class CertificateSequence(models.Model):
    year = models.PositiveIntegerField(unique=True)
    next_value = models.PositiveBigIntegerField(default=1)


class SystemSetting(models.Model):
    key = models.CharField(max_length=80, unique=True)
    value = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)


class VerificationAttempt(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField()
    certificate_number = models.CharField(max_length=32, blank=True)
    successful = models.BooleanField(default=False)
