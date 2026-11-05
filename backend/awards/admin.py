from django.contrib import admin
from . import models

for model in (
    models.Department, models.DepartmentMembership, models.Competition, models.Template,
    models.TemplateVersion, models.Seal, models.SealVersion, models.AwardBatch,
    models.BatchVersion, models.TeamAward, models.ApprovalDepartment,
    models.ApprovalDecision, models.GenerationTask, models.Certificate,
    models.RevocationRequest, models.AuditEvent, models.Notification,
    models.CertificateSequence,
):
    admin.site.register(model)
