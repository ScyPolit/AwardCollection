const states: Record<string, string> = {
  draft: "草稿",
  review: "审批中",
  returned: "已退回",
  queued: "排队中",
  running: "处理中",
  done: "已完成",
  failed: "处理失败",
  issued: "已签发",
  ready: "已就绪",
  active: "有效",
  void: "已作废",
  pending: "待审批",
  approved: "已通过",
  rejected: "已驳回",
  cancelled: "已取消",
  withdrawn: "批准已撤回",
  completed: "已完成",
  info: "通知",
  error: "失败",
  success: "成功",
  owner: "竞赛负责人",
  admin: "部门管理员",
  super: "超级管理员"
};
const actions: Record<string, string> = {
  "approval.seal_selected": "确认审批用章",
  "approval.withdrawn": "撤回批准并作废证书",
  "batch.approval": "处理部门审批",
  "batch.submitted": "提交部门会签",
  "batch.revised": "修订获奖名单",
  "archive.queue_failed": "下载包入队失败",
  "archive.ready": "下载包准备完成",
  "generation.completed": "证书生成完成",
  "generation.failed": "证书生成失败",
  "generation.retried": "重新生成证书",
  "font.order_updated": "调整字体顺序",
  "font.imported": "导入字体",
  "verification.settings_updated": "修改查验设置",
  "template.version_saved": "保存证书模板",
  "delivery.template_selected": "设置标准模板",
  "certificate.correction_created": "创建更正批次",
  "certificate.note_updated": "修改证书备注",
  "emergency.issue": "应急签发",
  "emergency.void": "应急作废",
  "revocation.requested": "申请作废证书",
  "revocation.decided": "处理作废审批",
  "file.prepare_failed": "文件准备失败",
  "seal.uploaded": "上传公章版本",
  "management.bulk_delete": "批量归档删除",
  "management.bulk_enable": "批量启用",
  "management.bulk_disable": "批量停用",
  "system.authorized_demo_cleanup": "清理授权演示数据"
};
const objects: Record<string, string> = {
  User: "账号",
  AccountProfile: "账号资料",
  Department: "部门",
  DepartmentMembership: "部门角色",
  Competition: "竞赛",
  AwardBatch: "获奖批次",
  BatchVersion: "名单修订",
  TeamAward: "获奖记录",
  Template: "证书模板",
  TemplateVersion: "模板记录",
  Seal: "公章",
  SealVersion: "公章版本",
  Certificate: "证书",
  CertificateFont: "字体",
  SystemSetting: "系统设置",
  PreparedFile: "下载与预览文件",
  RevocationRequest: "作废申请",
  Notification: "通知"
};
export function objectLabel(value: unknown) {
  return objects[String(value)] || String(value ?? "—");
}
export function actionLabel(value: unknown) {
  const key = String(value ?? "");
  if (actions[key]) return actions[key];
  const [entity, verb] = key.split(".");
  const subject: Record<string, string> = {
    account: "账号",
    competition: "竞赛",
    batch: "批次",
    membership: "部门角色",
    font: "字体",
    department: "部门",
    template: "模板",
    seal: "公章",
    certificate: "证书",
    notification: "通知",
    certificatefont: "字体"
  };
  const verbs: Record<string, string> = {
    created: "创建",
    updated: "修改",
    deleted: "归档删除"
  };
  return subject[entity] && verbs[verb] ? verbs[verb] + subject[entity] : key;
}
export function statusLabel(value: unknown) {
  const key = String(value ?? "");
  return states[key] || key || "—";
}
export function displayValue(value: unknown, field = "") {
  if (field === "操作" || field === "action") return actionLabel(value);
  if (field === "对象类型" || field === "object_type")
    return objectLabel(value);
  if (
    /时间|^(created_at|updated_at|submitted_at|published_at|withdrawn_at)$/.test(
      field
    ) &&
    typeof value === "string" &&
    !Number.isNaN(Date.parse(value))
  )
    return new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      dateStyle: "medium",
      timeStyle: "short"
    }).format(new Date(value));
  return /状态|决定|角色|^(status|decision|roles?|kind)$/.test(field)
    ? statusLabel(value)
    : String(value ?? "");
}
