import io
import uuid
from datetime import timedelta

from django.db import models, transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from openpyxl import Workbook, load_workbook

from .models import (
    ApprovalDecision, ApprovalDepartment, AwardBatch, BatchVersion,
    AuditEvent, Certificate, CertificateSequence, DepartmentMembership,
    GenerationTask, Notification, RevocationDecision, RevocationRequest,
    TeamAward, SealVersion,
)


HEADERS = ["团队成员", "奖项", "团队名称", "作品名称", "项目类别", "指导教师", "备注"]


def excel_template():
    wb = Workbook()
    ws = wb.active
    ws.title = "获奖名单"
    ws.append(HEADERS)
    ws.append(["张三、李四", "一等奖", "示例团队", "示例作品", "创新类", "王老师、赵老师", "填写后请删除示例行"])
    guide = wb.create_sheet("填写说明")
    guide.append(["每支团队一行；团队成员和指导教师使用中文顿号、逗号或换行分隔；奖项可自由填写。"])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def parse_excel(file_obj):
    import zipfile
    content=file_obj.read(16*1024*1024+1)
    if len(content)>16*1024*1024:raise ValueError("Excel文件不能超过16MB")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries=archive.infolist()
            if len(entries)>2000 or sum(e.file_size for e in entries)>64*1024*1024:raise ValueError("Excel文件解压后过大")
    except zipfile.BadZipFile as exc:raise ValueError("请选择有效的XLSX文件") from exc
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb["获奖名单"] if "获奖名单" in wb.sheetnames else wb.active
    rows=[]
    for row in ws.iter_rows(values_only=True):
        rows.append(row)
        if len(rows)>10001:raise ValueError("单批最多10000条，请拆分名单")
        if len(row)>32 or any(len(str(value))>10000 for value in row if value is not None):raise ValueError("单元格内容或列数过多")
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
def submit_batch(batch_id, actor, expected_version=None):
    batch = AwardBatch.objects.select_for_update().get(pk=batch_id)
    if expected_version is not None and expected_version != batch.current_version:
        raise ValueError('名单已被修改，请刷新并核对最新内容后提交')
    if batch.deleted_at or batch.competition.deleted_at or not batch.competition.active:
        raise ValueError("竞赛已废止，不能提交新签发")
    if batch.status not in [AwardBatch.Status.DRAFT, AwardBatch.Status.RETURNED]:
        raise ValueError("当前批次状态不允许提交")
    version = BatchVersion.objects.get(batch=batch, number=batch.current_version)
    if not version.awards.exists():
        raise ValueError("名单为空")
    from .fonts import layout_text
    from .renderer import _field_value
    template = version.snapshot.get("template") or version.template_version.canvas
    for award in (version.awards.iterator() if template.get('engine') != 'pptist' else []):
        for layer in template.get("layers", []):
            if layer.get("type") == "text":
                text = layer.get("text", "") if layer.get("field") == "static" else _field_value(award, layer.get("field"), "2026AC00000000")
                try:
                    layout_text(text, layer)
                except ValueError as exc:
                    raise ValueError(f"第 {award.source_row} 行 {layer.get('field')}：{exc}") from exc
    for requirement in version.required_departments.select_related("seal_version__seal"):
        if requirement.seal_version_id and (not requirement.seal_version.seal.active or requirement.seal_version.seal.deleted_at):
            raise ValueError(f"{requirement.department.name} 的选定公章已停用")
    preview_bytes = None
    if template.get("engine")=="pptist":
        from .ppt_renderer import renderer,award_values
        seals=[{"department_id":r.department_id,"image":r.seal_version.image.path} for r in version.required_departments.select_related("seal_version") if r.seal_version_id]
        awards=list(version.awards.order_by("source_row"))
        for item in awards:
            item.competition_name=version.snapshot.get("competition",{}).get("name",batch.competition.name)
            item.issue_date=version.snapshot.get("issue_date",timezone.localdate().isoformat())
        errors=renderer().preflight(template,seals,[{"source_row":a.source_row,"values":award_values(a,"2026AC00000000")} for a in awards])
        if errors:raise ValueError("；".join(f"第{e['row']}行：{e['error']}" for e in errors))
        buffer = io.BytesIO()
        renderer().render(template, seals, award_values(awards[0], '2026AC00000000'), buffer)
        preview_bytes = buffer.getvalue()
    version.submitted_by = actor
    version.submitted_at = timezone.now()
    version.save(update_fields=["submitted_by", "submitted_at", "updated_at"])
    from .integrity import freeze
    freeze(version)
    batch.status = AwardBatch.Status.REVIEW
    batch.save(update_fields=["status", "updated_at"])
    admin_ids = DepartmentMembership.objects.filter(
        department_id__in=version.required_departments.values_list("department_id", flat=True),
        role=DepartmentMembership.Role.ADMIN,
        active=True,
    ).values_list("user_id", flat=True)
    Notification.objects.bulk_create([
        Notification(user_id=user_id, title="获奖名单待审批", body=f"批次“{batch.name}”已提交部门会签", kind="review", target=f"/business/approvals?batch={batch.pk}")
        for user_id in set(admin_ids) | set(get_user_model().objects.filter(is_superuser=True,is_active=True).values_list('pk',flat=True))
    ])
    AuditEvent.objects.create(actor=actor,action="batch.submitted",object_type="AwardBatch",object_id=str(batch.pk),detail={"version":version.number})
    from .prepared import key_for, publish_submission_previews, request_file
    if preview_bytes:
        expected_keys = {kind: key_for(kind, version.pk) for kind in ('batch_preview', 'batch_thumbnail')}
        transaction.on_commit(lambda: publish_submission_previews(version.pk, expected_keys, preview_bytes), robust=True)
    else:
        transaction.on_commit(lambda: request_file(actor, 'batch_thumbnail', batch_id=batch.pk), robust=True)
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
def withdraw_approval(requirement_id, actor, reason):
    from .permissions import is_department_admin
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 2000:
        raise ValueError('请填写1～2000个字符的撤回原因')
    item = ApprovalDepartment.objects.select_related('version').get(pk=requirement_id)
    batch = AwardBatch.objects.select_for_update().get(pk=item.version.batch_id)
    if batch.deleted_at or not is_department_admin(actor, item.department_id):
        raise PermissionError('只能撤回本部门的审批批准')
    decision = ApprovalDecision.objects.select_for_update().filter(requirement_id=item.pk).first()
    if not decision or decision.decision != 'approved':
        raise ValueError('当前记录不是可撤回的批准状态，请刷新后重试')
    now = timezone.now()
    decision.decision, decision.withdrawn_at, decision.withdrawn_by = 'withdrawn', now, actor
    decision.withdrawal_reason = reason.strip()
    decision.save(update_fields=['decision','withdrawn_at','withdrawn_by','withdrawal_reason','updated_at'])
    task = GenerationTask.objects.select_for_update().filter(version_id=item.version_id).first()
    if task and task.status in ['queued','running']:
        task.status, task.lease_token, task.lease_expires_at = 'cancelled', uuid.uuid4(), None
        task.error = '部门已撤回批准，当前版本停止签发'
        task.save(update_fields=['status','lease_token','lease_expires_at','error','updated_at'])
    certificates = Certificate.objects.filter(award__version_id=item.version_id, status='active', published_at__isnull=False)
    pending_revocations = RevocationRequest.objects.filter(certificate__in=certificates, status='review')
    resolved = pending_revocations.update(status='approved')
    voided = certificates.update(status='void', updated_at=now)
    new_version = None
    if batch.current_version == item.version.number:
        rows = list(item.version.awards.order_by('source_row').values('source_row','members','award_name','team_name','work_name','category','teachers','note'))
        batch.status = AwardBatch.Status.RETURNED
        batch.save(update_fields=['status','updated_at'])
        new_version = revise_batch(batch.pk, actor, rows, batch.current_version)
        AwardBatch.objects.filter(pk=batch.pk).update(status=AwardBatch.Status.RETURNED, updated_at=now)
    AuditEvent.objects.create(actor=actor, action='approval.withdrawn', object_type='AwardBatch', object_id=str(batch.pk), detail={'requirement':item.pk,'version':item.version.number,'department':item.department_id,'original_actor':decision.actor_id,'original_approved_at':decision.created_at.isoformat(),'reason':reason.strip(),'voided_certificates':voided,'resolved_revocations':resolved,'new_version':new_version.number if new_version else None})
    recipients = set(batch.competition.collaborators.values_list('pk',flat=True)) | {batch.created_by_id}
    recipients.update(DepartmentMembership.objects.filter(department_id__in=item.version.required_departments.values('department_id'),role='admin',active=True).values_list('user_id',flat=True))
    recipients.update(get_user_model().objects.filter(is_superuser=True,is_active=True).values_list('pk',flat=True))
    Notification.objects.bulk_create([Notification(user_id=uid,title='会签批准已撤回',body=f'批次“{batch.name}”的批准已撤回，已作废{voided}张证书。原因：{reason.strip()}',kind='returned',batch=batch,target=f'/business/batches?batch={batch.pk}') for uid in recipients])
    return {'withdrawn':True,'voided_certificates':voided,'new_version':new_version.number if new_version else None}


UNSET = object()


def approval_context(requirement_id, actor):
    batch_id = ApprovalDepartment.objects.values_list("version__batch_id", flat=True).get(pk=requirement_id)
    batch = AwardBatch.objects.select_for_update(of=("self",)).select_related("competition").get(pk=batch_id)
    requirement = ApprovalDepartment.objects.select_for_update(of=("self",)).select_related("version", "department", "seal_version__seal").get(pk=requirement_id)
    version = requirement.version
    if batch.current_version != version.number or batch.status != AwardBatch.Status.REVIEW:
        raise ValueError("审批版本已失效")
    if batch.deleted_at or batch.competition.deleted_at or not batch.competition.active:
        raise ValueError("竞赛已废止，请先重新启用后再审批")
    from .integrity import verify
    verify(version)
    eligible = actor.is_superuser or DepartmentMembership.objects.filter(department=requirement.department, user=actor, role=DepartmentMembership.Role.ADMIN, active=True).exists()
    if not eligible:
        raise PermissionError("无本部门审批权限")
    return requirement, version, batch


def set_approval_seal(requirement, version, actor, seal_version_id, expected_seal_version=UNSET):
    if expected_seal_version is not UNSET and requirement.seal_version_id != expected_seal_version:
        raise ValueError("本部门用章已被其他管理员修改，请刷新后确认")
    if not isinstance(seal_version_id, int) or isinstance(seal_version_id, bool):
        raise ValueError("请选择本部门有效的公章版本")
    seal = SealVersion.objects.select_related("seal").filter(pk=seal_version_id, seal__department_id=requirement.department_id, seal__active=True, seal__deleted_at__isnull=True).first()
    if not seal:
        raise ValueError("所选公章不属于本部门、已停用或已删除")
    if requirement.seal_version_id == seal.pk:
        return
    if ApprovalDecision.objects.filter(requirement=requirement).exists():
        raise ValueError("本部门已审批，不能修改已确认的公章；请退回并修订新版本")
    before = requirement.seal_version_id
    requirement.seal_version = seal
    requirement.save(update_fields=["seal_version", "updated_at"])
    version.snapshot = {**version.snapshot, "seals": list(version.required_departments.order_by("department_id").values_list("seal_version_id", flat=True))}
    version.save(update_fields=["snapshot", "updated_at"])
    # The server changes only this department's selection. All previously frozen
    # names, template and other departments' selections are verified beforehand.
    from .integrity import freeze
    freeze(version)
    AwardBatch.objects.filter(pk=version.batch_id).update(updated_at=timezone.now())
    AuditEvent.objects.create(actor=actor, action="approval.seal_selected", object_type="ApprovalDepartment", object_id=str(requirement.pk), detail={"batch": version.batch_id, "department": requirement.department_id, "previous_seal_version": before, "seal_version": seal.pk})


@transaction.atomic
def choose_approval_seal(requirement_id, actor, seal_version_id, expected_seal_version=UNSET):
    requirement, version, _ = approval_context(requirement_id, actor)
    set_approval_seal(requirement, version, actor, seal_version_id, expected_seal_version)
    return requirement


@transaction.atomic
def decide(requirement_id, actor, decision, comment="", *, seal_version_id=UNSET, expected_seal_version=UNSET, issue_rows=None):
    if decision not in ApprovalDecision.Decision.values:
        raise ValueError("审批决定无效")
    if not isinstance(comment, str) or len(comment) > 4000:
        raise ValueError("审批意见最多4000个字符")
    issue_rows = issue_rows or []
    if not isinstance(issue_rows, list) or len(issue_rows) > 200 or any(not isinstance(n, int) or isinstance(n, bool) or n < 2 for n in issue_rows):
        raise ValueError("问题行号无效，最多标注200行")
    requirement, version, batch = approval_context(requirement_id, actor)
    if ApprovalDecision.objects.filter(requirement=requirement).exists():
        raise ValueError("本部门已审批，请刷新查看最新进度")
    if seal_version_id is not UNSET:
        set_approval_seal(requirement, version, actor, seal_version_id, expected_seal_version)
    if decision == ApprovalDecision.Decision.APPROVED:
        if not requirement.seal_version_id:
            raise ValueError("请先选择本部门公章再通过审批")
        if not requirement.seal_version.seal.active or requirement.seal_version.seal.deleted_at:
            raise ValueError("本部门公章已停用或删除，请重新选择")
    if set(issue_rows) - set(version.awards.filter(source_row__in=issue_rows).values_list("source_row", flat=True)):
        raise ValueError("问题行号不在当前名单中")
    ApprovalDecision.objects.create(requirement=requirement, decision=decision, actor=actor, comment=comment, issue_rows=issue_rows)
    batch.save(update_fields=["updated_at"])
    AuditEvent.objects.create(actor=actor, action="batch.approval", object_type="ApprovalDepartment", object_id=str(requirement.pk), detail={"batch": batch.id, "version": version.number, "department": requirement.department_id, "decision": decision, "comment": comment})
    if decision == ApprovalDecision.Decision.RETURNED:
        batch.status = AwardBatch.Status.RETURNED
        batch.save(update_fields=["status", "updated_at"])
        collaborator_ids = set(batch.competition.collaborators.values_list("id", flat=True)) | {batch.created_by_id}
        Notification.objects.bulk_create([
            Notification(user_id=user_id, title="获奖名单已退回", body=f"批次“{batch.name}”被退回：{comment or '请查看审批意见'}", kind="returned", target=f"/business/batches?batch={batch.pk}")
            for user_id in collaborator_ids if user_id != actor.id
        ])
        return None
    required = version.required_departments.count()
    approved = ApprovalDecision.objects.filter(requirement__version=version, decision=ApprovalDecision.Decision.APPROVED).count()
    if decision == 'approved':
        recipients=set(batch.competition.collaborators.values_list('pk',flat=True)) | {batch.created_by_id}
        Notification.objects.bulk_create([Notification(user_id=uid,title='部门会签进度已更新',body=f'批次“{batch.name}”已有 {approved}/{required} 个部门通过',kind='approval',target=f'/business/batches?batch={batch.pk}') for uid in recipients if uid!=actor.pk])
    if required and approved == required:
        if version.required_departments.filter(seal_version__isnull=True).exists():
            raise ValueError("尚有部门未确认用章")
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
    if batch.deleted_at or batch.competition.deleted_at or not batch.competition.active:
        raise ValueError("竞赛已废止，不能签发")
    version = BatchVersion.objects.get(batch=batch, number=batch.current_version)
    if not version.awards.exists():
        raise ValueError("名单为空")
    for requirement in version.required_departments.select_related("seal_version__seal"):
        if not requirement.seal_version_id:
            raise ValueError(f"{requirement.department.name} 尚未选择公章，请先在审批详情中确认用章")
        if not requirement.seal_version.seal.active or requirement.seal_version.seal.deleted_at:
            raise ValueError(f"{requirement.department.name} 的选定公章已停用")
    from .integrity import freeze,verify
    if version.integrity_hmac:verify(version)
    else:freeze(version)
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
        Notification(user_id=user_id, batch=batch, title="超管应急签发", body=f"批次“{batch.name}”已应急进入签发队列：{reason}", target=f"/business/batches?batch={batch.pk}")
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
        Notification(user_id=user_id, batch_id=certificate.award.version.batch_id, title="证书作废审批", body=f"证书 {certificate.number} 申请作废：{reason}",kind="review",target=f"/business/approvals?revocation={request.pk}")
        for user_id in set(admin_ids) | set(get_user_model().objects.filter(is_superuser=True,is_active=True).exclude(pk=actor.pk).values_list('pk',flat=True))
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
    Notification.objects.bulk_create([Notification(user_id=user_id, batch_id=certificate.award.version.batch_id, title="超管应急作废", body=f"证书 {certificate.number} 已应急作废：{reason}", target=f"/business/batches?batch={certificate.award.version.batch_id}") for user_id in related_ids if user_id != actor.id])
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
    task.started_at = now
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
    return f"{year}AC{value:08d}"
