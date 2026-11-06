import io
import uuid
from datetime import timedelta

from django.db import models, transaction
from django.utils import timezone
from openpyxl import Workbook, load_workbook

from .models import (
    ApprovalDecision, ApprovalDepartment, AwardBatch, BatchVersion,
    AuditEvent, Certificate, CertificateSequence, DepartmentMembership,
    GenerationTask, Notification, RevocationDecision, RevocationRequest,
    TeamAward,
)


HEADERS = ["团队成员", "奖项", "团队名称", "作品名称", "项目类别", "指导教师", "备注"]


def excel_template():
    wb = Workbook()
    ws = wb.active
    ws.title = "获奖名单"
    ws.append(HEADERS)
    ws.append(["张三、李四", "一等奖", "测试专用团队", "测试专用作品", "创新类", "王老师、赵老师", "测试数据"])
    guide = wb.create_sheet("填写说明")
    guide.append(["每支团队一行；团队成员和指导教师使用中文顿号、逗号或换行分隔；奖项可自由填写。"])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def parse_excel(file_obj):
    wb = load_workbook(file_obj, read_only=True, data_only=True)
    ws = wb["获奖名单"] if "获奖名单" in wb.sheetnames else wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows or list(rows[0])[:7] != HEADERS:
        raise ValueError("表头必须与统一模板一致")
    parsed, errors = [], []
    for row_number, row in enumerate(rows[1:], 2):
        values = [(str(v).strip() if v is not None else "") for v in list(row)[:7]]
        if not any(values):
            continue
        if not values[0]: errors.append({"row": row_number, "field": "团队成员", "message": "不能为空"})
        if not values[1]: errors.append({"row": row_number, "field": "奖项", "message": "不能为空"})
        split = lambda text: [x.strip() for x in text.replace("，", "、").replace(",", "、").replace("\n", "、").split("、") if x.strip()]
        parsed.append({"source_row": row_number, "members": split(values[0]), "award_name": values[1], "team_name": values[2], "work_name": values[3], "category": values[4], "teachers": split(values[5]), "note": values[6]})
    return parsed, errors


@transaction.atomic
def submit_batch(batch_id, actor):
    batch = AwardBatch.objects.select_for_update().get(pk=batch_id)
    if not batch.competition.active:
        raise ValueError("竞赛已废止，不能提交新签发")
    if batch.status not in [AwardBatch.Status.DRAFT, AwardBatch.Status.RETURNED]:
        raise ValueError("当前批次状态不允许提交")
    version = BatchVersion.objects.get(batch=batch, number=batch.current_version)
    if not version.awards.exists():
        raise ValueError("名单为空")
    from .fonts import layout_text
    from .renderer import _field_value
    template = version.snapshot.get("template") or version.template_version.canvas
    for award in version.awards.iterator():
        for layer in template.get("layers", []):
            if layer.get("type") == "text":
                text = layer.get("text", "") if layer.get("field") == "static" else _field_value(award, layer.get("field"), "2026-AC-00000000")
                try:
                    layout_text(text, layer)
                except ValueError as exc:
                    raise ValueError(f"第 {award.source_row} 行 {layer.get('field')}：{exc}") from exc
    for requirement in version.required_departments.select_related("seal_version__seal"):
        if not requirement.seal_version.seal.active:
            raise ValueError(f"{requirement.department.name} 的选定公章已停用")
    version.submitted_by = actor
    version.submitted_at = timezone.now()
    version.save(update_fields=["submitted_by", "submitted_at", "updated_at"])
    batch.status = AwardBatch.Status.REVIEW
    batch.save(update_fields=["status", "updated_at"])
    admin_ids = DepartmentMembership.objects.filter(
        department_id__in=version.required_departments.values_list("department_id", flat=True),
        role=DepartmentMembership.Role.ADMIN,
        active=True,
    ).exclude(user=actor).values_list("user_id", flat=True)
    Notification.objects.bulk_create([
        Notification(user_id=user_id, title="获奖名单待审批", body=f"批次“{batch.name}”已提交部门会签")
        for user_id in set(admin_ids)
    ])
    return version


@transaction.atomic
def revise_batch(batch_id, actor, rows, expected_version):
    batch = AwardBatch.objects.select_for_update().get(pk=batch_id)
    if batch.current_version != expected_version:
        raise ValueError("批次已被其他人修改，请刷新后重试")
    if batch.status not in [AwardBatch.Status.DRAFT, AwardBatch.Status.RETURNED, AwardBatch.Status.REVIEW]:
        raise ValueError("当前批次状态不允许修改")
    previous = BatchVersion.objects.select_related("template_version").get(batch=batch, number=expected_version)
    number = expected_version + 1
    version = BatchVersion.objects.create(
        batch=batch,
        number=number,
        template_version=previous.template_version,
        output_formats=previous.output_formats,
        snapshot=previous.snapshot,
    )
    for requirement in previous.required_departments.all():
        ApprovalDepartment.objects.create(
            version=version,
            department=requirement.department,
            seal_version=requirement.seal_version,
        )
    TeamAward.objects.bulk_create([
        TeamAward(version=version, last_edited_by=actor, **row) for row in rows
    ])
    batch.current_version = number
    batch.status = AwardBatch.Status.DRAFT
    batch.save(update_fields=["current_version", "status", "updated_at"])
    AuditEvent.objects.create(
        actor=actor, action="batch.revised", object_type="AwardBatch",
        object_id=str(batch.id), detail={"from": expected_version, "to": number},
    )
    return version


@transaction.atomic
def decide(requirement_id, actor, decision, comment=""):
    if decision not in ApprovalDecision.Decision.values:
        raise ValueError("审批决定无效")
    requirement = ApprovalDepartment.objects.select_for_update().select_related("version__batch").get(pk=requirement_id)
    version = requirement.version
    batch = AwardBatch.objects.select_for_update().get(pk=version.batch_id)
    if batch.current_version != version.number or batch.status != AwardBatch.Status.REVIEW:
        raise ValueError("审批版本已失效")
    if not batch.competition.active:
        raise ValueError("竞赛已废止，请先重新启用后再审批")
    eligible = actor.is_superuser or DepartmentMembership.objects.filter(department=requirement.department, user=actor, role=DepartmentMembership.Role.ADMIN, active=True).exists()
    if not eligible:
        raise PermissionError("无本部门审批权限")
    editors = set(version.awards.exclude(last_edited_by=None).values_list("last_edited_by_id", flat=True))
    if version.submitted_by_id == actor.id or actor.id in editors:
        raise PermissionError("提交或修改人员必须回避")
    ApprovalDecision.objects.update_or_create(requirement=requirement, defaults={"decision": decision, "actor": actor, "comment": comment})
    AuditEvent.objects.create(actor=actor, action="batch.approval", object_type="ApprovalDepartment", object_id=str(requirement.pk), detail={"batch": batch.id, "version": version.number, "department": requirement.department_id, "decision": decision, "comment": comment})
    if decision == ApprovalDecision.Decision.RETURNED:
        batch.status = AwardBatch.Status.RETURNED
        batch.save(update_fields=["status", "updated_at"])
        collaborator_ids = set(batch.competition.collaborators.values_list("id", flat=True))
        Notification.objects.bulk_create([
            Notification(user_id=user_id, title="获奖名单已退回", body=f"批次“{batch.name}”被退回：{comment or '请查看审批意见'}")
            for user_id in collaborator_ids if user_id != actor.id
        ])
        return None
    required = version.required_departments.count()
    approved = ApprovalDecision.objects.filter(requirement__version=version, decision=ApprovalDecision.Decision.APPROVED).count()
    if required and approved == required:
        task, _ = GenerationTask.objects.get_or_create(version=version, defaults={"total": version.awards.count()})
        batch.status = AwardBatch.Status.QUEUED
        batch.save(update_fields=["status", "updated_at"])
        return task
    return None


@transaction.atomic
def emergency_issue(batch_id, actor, reason, password):
    if not actor.is_superuser or not actor.check_password(password):
        raise PermissionError("超管身份或密码复核失败")
    if not reason.strip():
        raise ValueError("必须填写应急原因")
    batch = AwardBatch.objects.select_for_update().get(pk=batch_id)
    if batch.status not in [AwardBatch.Status.DRAFT, AwardBatch.Status.RETURNED, AwardBatch.Status.REVIEW, AwardBatch.Status.FAILED]:
        raise ValueError("当前批次状态不允许应急签发")
    if not batch.competition.active:
        raise ValueError("竞赛已废止，不能签发")
    version = BatchVersion.objects.get(batch=batch, number=batch.current_version)
    if not version.awards.exists():
        raise ValueError("名单为空")
    for requirement in version.required_departments.select_related("seal_version__seal"):
        if not requirement.seal_version.seal.active:
            raise ValueError(f"{requirement.department.name} 的选定公章已停用")
    task, _ = GenerationTask.objects.get_or_create(version=version, defaults={"total": version.awards.count()})
    if task.status == GenerationTask.Status.DONE:
        raise ValueError("该版本已经签发")
    if task.status == GenerationTask.Status.RUNNING and task.lease_expires_at and task.lease_expires_at >= timezone.now():
        raise ValueError("该版本正在生成，不能重复应急签发")
    task.status = GenerationTask.Status.QUEUED
    task.error = ""
    task.lease_token = None
    task.lease_expires_at = None
    task.total = version.awards.count()
    task.save(update_fields=["status", "error", "lease_token", "lease_expires_at", "total", "updated_at"])
    batch.status = AwardBatch.Status.QUEUED
    batch.save(update_fields=["status", "updated_at"])
    AuditEvent.objects.create(
        actor=actor, action="emergency.issue", object_type="AwardBatch",
        object_id=str(batch.id), detail={"reason": reason, "version": version.number},
    )
    related_ids = set(batch.competition.collaborators.values_list("id", flat=True))
    related_ids.update(DepartmentMembership.objects.filter(
        department__competitions=batch.competition, role=DepartmentMembership.Role.ADMIN, active=True,
    ).values_list("user_id", flat=True))
    Notification.objects.bulk_create([
        Notification(user_id=user_id, title="超管应急签发", body=f"批次“{batch.name}”已应急进入签发队列：{reason}")
        for user_id in related_ids if user_id != actor.id
    ])
    return task


@transaction.atomic
def request_revocation(certificate_id, actor, reason):
    certificate = Certificate.objects.select_for_update().select_related("award__version").get(pk=certificate_id)
    if certificate.status != Certificate.Status.ACTIVE:
        raise ValueError("证书当前不是有效状态")
    if certificate.revocation_requests.filter(status=RevocationRequest.Status.REVIEW).exists():
        raise ValueError("已有待审批的作废申请")
    request = RevocationRequest.objects.create(certificate=certificate, reason=reason, requested_by=actor)
    departments = certificate.award.version.required_departments.values_list("department_id", flat=True)
    admin_ids = DepartmentMembership.objects.filter(
        department_id__in=departments, role=DepartmentMembership.Role.ADMIN, active=True,
    ).values_list("user_id", flat=True)
    Notification.objects.bulk_create([
        Notification(user_id=user_id, title="证书作废审批", body=f"证书 {certificate.number} 申请作废：{reason}")
        for user_id in set(admin_ids)
    ])
    AuditEvent.objects.create(actor=actor, action="revocation.requested", object_type="Certificate", object_id=str(certificate.id), detail={"reason": reason})
    return request


@transaction.atomic
def decide_revocation(request_id, department_id, actor, decision, comment=""):
    if decision not in RevocationDecision.Decision.values:
        raise ValueError("作废审批决定无效")
    request = RevocationRequest.objects.select_for_update().select_related("certificate__award__version").get(pk=request_id)
    if request.status != RevocationRequest.Status.REVIEW:
        raise ValueError("作废申请已结束")
    required_ids = set(request.certificate.award.version.required_departments.values_list("department_id", flat=True))
    if department_id not in required_ids:
        raise PermissionError("该部门不在原盖章部门中")
    if not actor.is_superuser and not DepartmentMembership.objects.filter(department_id=department_id, user=actor, role=DepartmentMembership.Role.ADMIN, active=True).exists():
        raise PermissionError("无本部门作废审批权限")
    RevocationDecision.objects.update_or_create(
        request=request, department_id=department_id,
        defaults={"decision": decision, "actor": actor, "comment": comment},
    )
    if decision == RevocationDecision.Decision.REJECTED:
        request.status = RevocationRequest.Status.REJECTED
        request.save(update_fields=["status", "updated_at"])
    else:
        approved_ids = set(request.decisions.filter(decision=RevocationDecision.Decision.APPROVED).values_list("department_id", flat=True))
        if approved_ids == required_ids:
            request.status = RevocationRequest.Status.APPROVED
            request.certificate.status = Certificate.Status.VOID
            request.certificate.save(update_fields=["status", "updated_at"])
            request.save(update_fields=["status", "updated_at"])
    AuditEvent.objects.create(actor=actor, action="revocation.decided", object_type="RevocationRequest", object_id=str(request.id), detail={"department": department_id, "decision": decision})
    return request


@transaction.atomic
def emergency_void(certificate_id, actor, reason, password):
    if not actor.is_superuser or not actor.check_password(password):
        raise PermissionError("超管身份或密码复核失败")
    if not reason.strip():
        raise ValueError("必须填写应急原因")
    certificate = Certificate.objects.select_for_update().get(pk=certificate_id)
    certificate.status = Certificate.Status.VOID
    certificate.save(update_fields=["status", "updated_at"])
    AuditEvent.objects.create(actor=actor, action="emergency.void", object_type="Certificate", object_id=str(certificate.id), detail={"reason": reason})
    related_ids = set(certificate.award.version.batch.competition.collaborators.values_list("id", flat=True))
    related_ids.update(DepartmentMembership.objects.filter(department__competitions=certificate.award.version.batch.competition, role=DepartmentMembership.Role.ADMIN).values_list("user_id", flat=True))
    Notification.objects.bulk_create([Notification(user_id=user_id, title="超管应急作废", body=f"证书 {certificate.number} 已应急作废：{reason}") for user_id in related_ids if user_id != actor.id])
    return certificate


@transaction.atomic
def claim_task():
    now = timezone.now()
    task = GenerationTask.objects.select_for_update(skip_locked=True).filter(status__in=[GenerationTask.Status.QUEUED, GenerationTask.Status.RUNNING]).filter(models.Q(lease_expires_at__lt=now) | models.Q(lease_expires_at=None)).first()
    if not task:
        return None
    task.status = GenerationTask.Status.RUNNING
    task.lease_token = uuid.uuid4()
    task.lease_expires_at = now + timedelta(minutes=10)
    task.attempts += 1
    task.save()
    return task


def allocate_number():
    year = timezone.localdate().year
    with transaction.atomic():
        seq, _ = CertificateSequence.objects.select_for_update().get_or_create(year=year)
        value = seq.next_value
        seq.next_value += 1
        seq.save(update_fields=["next_value"])
    return f"{year}-AC-{value:08d}"
