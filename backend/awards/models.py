import uuid
from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ManagedModel(TimeStampedModel):
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True


class AccountProfile(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='management_profile')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='managed_accounts')
    deleted_at = models.DateTimeField(null=True, blank=True)


class Department(ManagedModel):
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


class Competition(ManagedModel):
    name = models.CharField(max_length=240)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_competitions")
    collaborators = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="competitions")
    departments = models.ManyToManyField(Department, related_name="competitions")
    award_presets = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True)


class Template(ManagedModel):
    class Scope(models.TextChoices):
        DEPARTMENT = "department", "部门模板"
        PERSONAL = "personal", "个人模板"

    name = models.CharField(max_length=160)
    department = models.ForeignKey(Department, on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    source = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
    published = models.BooleanField(default=False)
    scope = models.CharField(max_length=16, choices=Scope.choices, default=Scope.DEPARTMENT)


class TemplateVersion(TimeStampedModel):
    template = models.ForeignKey(Template, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField()
    canvas = models.JSONField(default=dict)
    summary = models.JSONField(default=dict, db_default={})

    def save(self, *args, **kwargs):
        fields = kwargs.get("update_fields")
        if fields is None or "canvas" in fields:
            canvas = self.canvas
            native = canvas.get("engine") == "pptist"
            slides = canvas.get("presentation", {}).get("slides", [])
            index = canvas.get("slideIndex", 0)
            elements = slides[index].get("elements", []) if native and 0 <= index < len(slides) else canvas.get("layers", [])
            self.summary = {"engine": "pptist" if native else "legacy", "page": canvas.get("page", {"width": 842, "height": 595}), "element_count": len(elements)}
            if fields is not None:
                kwargs["update_fields"] = set(fields) | {"summary"}
        super().save(*args, **kwargs)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["template", "number"], name="uniq_template_version")]


class Seal(ManagedModel):
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


class CertificateFont(ManagedModel):
    sha256 = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=160)
    active = models.BooleanField(default=True)
    file = models.FileField(upload_to="protected/font-library")
    license_note = models.CharField(max_length=240)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)


class AwardBatch(ManagedModel):
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
    integrity_hmac = models.CharField(max_length=64,blank=True,db_default="")

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
    seal_version = models.ForeignKey(SealVersion, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["version", "department"], name="uniq_required_department")]


class ApprovalDecision(TimeStampedModel):
    class Decision(models.TextChoices):
        APPROVED = "approved", "通过"
        RETURNED = "returned", "退回"
        WITHDRAWN = "withdrawn", "批准已撤回"

    requirement = models.OneToOneField(ApprovalDepartment, on_delete=models.CASCADE, related_name="decision")
    decision = models.CharField(max_length=16, choices=Decision.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    comment = models.TextField(blank=True)
    issue_rows = models.JSONField(default=list, blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    withdrawn_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='withdrawn_approvals')
    withdrawal_reason = models.TextField(blank=True)


class GenerationTask(TimeStampedModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "待处理"
        RUNNING = "running", "处理中"
        FAILED = "failed", "失败"
        DONE = "done", "完成"
        CANCELLED = "cancelled", "已取消"

    version = models.OneToOneField(BatchVersion, on_delete=models.PROTECT, related_name="generation_task")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    lease_token = models.UUIDField(null=True)
    lease_expires_at = models.DateTimeField(null=True)
    attempts = models.PositiveIntegerField(default=0)
    processed = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)


class Certificate(ManagedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "有效"
        VOID = "void", "已作废"

    number = models.CharField(max_length=32, unique=True)
    award = models.OneToOneField(TeamAward, on_delete=models.PROTECT, related_name="certificate")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    pdf = models.FileField(upload_to="protected/certificates/%Y", blank=True)
    image = models.FileField(upload_to="protected/certificates/%Y", blank=True)
    pdf_sha256 = models.CharField(max_length=64, blank=True)
    image_sha256 = models.CharField(max_length=64, blank=True, db_default="")
    published_at = models.DateTimeField(null=True)
    notes = models.TextField(blank=True, db_default="")


class PreparedFile(TimeStampedModel):
    """Deduplicated, leased disk jobs; no browser request performs bulk rendering."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=64, unique=True)
    kind = models.CharField(max_length=24)
    version = models.ForeignKey(BatchVersion, null=True, on_delete=models.CASCADE, related_name="prepared_files")
    template_version = models.ForeignKey(TemplateVersion, null=True, on_delete=models.CASCADE, related_name="prepared_files")
    status = models.CharField(max_length=16, default="queued", db_index=True)
    processed = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    attempts = models.PositiveIntegerField(default=0)
    lease_token = models.UUIDField(null=True)
    lease_expires_at = models.DateTimeField(null=True)
    file = models.FileField(upload_to="protected/prepared", blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    byte_size = models.PositiveBigIntegerField(default=0)
    error = models.TextField(blank=True)
    subscribers = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="prepared_files", blank=True)


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
    target = models.CharField(max_length=240, blank=True, db_default='')
    kind = models.CharField(max_length=24, default='info', db_default='info')
    batch = models.ForeignKey(AwardBatch, null=True, blank=True, on_delete=models.SET_NULL, related_name="notifications")

    def __init__(self, *args, **kwargs):
        if not args and kwargs.get("target") and not kwargs.get("batch") and not kwargs.get("batch_id"):
            import re
            match = re.search(r"[?&]batch=([0-9]+)(?:&|$)", kwargs["target"])
            if match:
                kwargs["batch_id"] = int(match.group(1))
        super().__init__(*args, **kwargs)


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


class VerificationRateLimit(models.Model):
    ip_address = models.GenericIPAddressField(primary_key=True)
    timestamps = models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
