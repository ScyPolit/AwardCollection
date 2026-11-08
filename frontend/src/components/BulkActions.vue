<script setup lang="ts">
import { ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { bulkAction } from "@/api/business";
const props = withDefaults(
  defineProps<{
    selected: Record<string, any>[];
    resource?: string;
    canDelete?: boolean;
    canToggle?: boolean;
    readonlyReason?: string;
    columns?: { key: string; label: string }[];
  }>(),
  { canDelete: false, canToggle: false }
);
const emit = defineEmits<{ changed: []; clear: [] }>();
const busy = ref(false);
async function run(operation: string) {
  if (!props.resource || !props.selected.length || busy.value) return;
  if (props.selected.length > 200)
    return ElMessage.warning("单次最多处理200条，请分批选择");
  const label =
    operation === "delete"
      ? "删除"
      : operation === "enable"
        ? "启用 / 共享"
        : "停用 / 取消共享";
  try {
    await ElMessageBox.confirm(
      `确认${label}选中的 ${props.selected.length} 条记录？将逐条检查权限与状态，任一记录不符合条件时整批不执行。历史文件与审计记录保留。`,
      `批量${label}`,
      { type: "warning" }
    );
  } catch {
    return;
  }
  busy.value = true;
  try {
    const result = await bulkAction(
      props.resource,
      operation,
      props.selected.map(r => r.id)
    );
    ElMessage.success(`已处理 ${result.count} 条记录`);
    emit("clear");
    emit("changed");
  } catch {
  } finally {
    busy.value = false;
  }
}
function exportCsv() {
  const keys = [
    "id",
    "name",
    "number",
    "username",
    "competition_name",
    "batch_name",
    "department_name",
    "status",
    "award_name",
    "team_name",
    "action",
    "actor",
    "created_at"
  ];
  keys.push(
    "source_row",
    "members",
    "teachers",
    "work_name",
    "category",
    "note",
    "decision",
    "seal_label"
  );
  const labels: Record<string, string> = {
    id: "记录编号",
    name: "名称",
    number: "证书编号",
    username: "账号",
    competition_name: "竞赛",
    batch_name: "批次",
    department_name: "部门",
    status: "状态",
    award_name: "奖项",
    team_name: "团队",
    action: "操作",
    actor: "操作人",
    created_at: "创建时间",
    source_row: "来源行",
    members: "团队成员",
    teachers: "指导教师",
    work_name: "作品名称",
    category: "项目类别",
    note: "备注",
    decision: "审批决定",
    seal_label: "用章状态"
  };
  const columns =
    props.columns ||
    keys
      .filter(key => props.selected.some(row => key in row))
      .map(key => ({ key, label: labels[key] || key }));
  const cell = (value: unknown) => {
    let text =
      value == null
        ? ""
        : typeof value === "object"
          ? JSON.stringify(value)
          : String(value);
    if (/^\s*[=+\-@]|^[\t\r]/.test(text)) text = "'" + text;
    return '"' + text.replace(/"/g, '""') + '"';
  };
  const csv = [
    columns.map(c => cell(c.label)).join(","),
    ...props.selected.map(row => columns.map(c => cell(row[c.key])).join(","))
  ].join("\r\n");
  const url = URL.createObjectURL(
    new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" })
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = `${props.resource || "records"}-selection.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
</script>
<template>
  <div class="bulk-actions" :aria-busy="busy">
    <span
      >已选择 <strong>{{ selected.length }}</strong> 项</span
    >
    <el-button :disabled="!selected.length || busy" @click="exportCsv"
      >导出所选 CSV</el-button
    >
    <el-button
      v-if="canToggle && resource"
      :disabled="!selected.length || busy"
      @click="run('enable')"
      >批量启用 / 共享</el-button
    >
    <el-button
      v-if="canToggle && resource"
      :disabled="!selected.length || busy"
      @click="run('disable')"
      >批量停用 / 取消共享</el-button
    >
    <el-button
      v-if="canDelete && resource"
      type="danger"
      plain
      :disabled="!selected.length || busy"
      :loading="busy"
      @click="run('delete')"
      >批量删除</el-button
    >
    <slot :busy="busy" />
    <el-button
      v-if="selected.length"
      link
      :disabled="busy"
      @click="$emit('clear')"
      >清空选择</el-button
    >
    <small v-if="readonlyReason">{{ readonlyReason }}</small>
  </div>
</template>
<style scoped>
.bulk-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 12px;
  margin: 0 0 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
}
.bulk-actions .el-button {
  margin: 0;
}
small {
  color: var(--el-text-color-secondary);
}
</style>
