<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { displayValue } from "@/utils/display";
defineOptions({ name: "DetailValue" });
const props = withDefaults(
  defineProps<{ value: unknown; depth?: number; field?: string }>(),
  {
    depth: 0
  }
);
const page = ref(1);
watch(
  () => props.value,
  () => (page.value = 1)
);
const labels: Record<string, string> = {
  id: "编号",
  name: "名称",
  username: "账号",
  department: "部门编号",
  department_name: "部门",
  department__name: "部门",
  active: "启用",
  role: "角色",
  source_row: "来源行",
  team_name: "团队名称",
  members: "团队成员",
  award_name: "奖项",
  work_name: "作品名称",
  category: "项目类别",
  teachers: "指导教师",
  note: "备注",
  notes: "管理备注",
  created_at: "创建时间",
  updated_at: "更新时间",
  actor: "操作人",
  decision: "审批决定",
  comment: "审批意见",
  number: "编号",
  version: "版本",
  batch: "批次",
  batch_id: "批次编号",
  batch_name: "批次名称",
  competition: "竞赛",
  competition_name: "竞赛名称",
  version_number: "版本",
  before: "修改前",
  after: "修改后",
  sha256: "SHA256摘要",
  status: "状态",
  count: "数量",
  total: "总数",
  processed: "已处理",
  format: "格式",
  reason: "原因",
  error: "错误详情",
  attempts: '执行次数', percent: '完成进度', successful:'查验成功',
  submitted_by:'提交人', submitted_at:'提交时间', published_at:'签发时间',
  requirement:'审批记录', department_id:'部门编号', template_version:'模板记录',
  issue_rows:'问题行号', seal_version:'公章版本', seal_versions:'所选公章',
  withdrawn_at:'撤回时间', withdrawn_by:'撤回人编号', withdrawal_reason:'撤回原因',
  original_actor:'原审批人编号', original_approved_at:'原批准时间',
  voided_certificates:'作废证书数量', resolved_revocations:'已处理作废申请数',
  new_version:'修订记录', historical_versions_preserved:'保留历史模板',
  archived_templates:'归档模板', kept_version:'保留模板记录',
  show_team:'公开团队', show_members:'公开成员', mask_members:'成员脱敏',
  show_competition:'公开竞赛', show_award:'公开奖项', show_work:'公开作品',
  show_category:'公开类别', show_teachers:'公开教师', mask_teachers:'教师脱敏',
  show_issue_date:'公开颁发日期', show_departments:'公开盖章部门',
  show_published_at:'公开签发时间', show_batch:'公开批次', show_template:'公开模板',
  watermark_text:'查验水印', kind:'类型', action:'操作', object_type:'对象类型'
};
const isArray = computed(() => Array.isArray(props.value));
const objectArray = computed(
  () =>
    isArray.value &&
    (props.value as any[]).length > 0 &&
    (props.value as any[]).every(
      v => v && typeof v === "object" && !Array.isArray(v)
    )
);
const visible = computed(() =>
  isArray.value
    ? (props.value as any[]).slice((page.value - 1) * 10, page.value * 10)
    : []
);
const columns = computed(() =>
  objectArray.value
    ? [...new Set((props.value as any[]).flatMap(v => Object.keys(v)))].slice(
        0,
        30
      )
    : []
);
const entries = computed(() =>
  props.value && typeof props.value === "object" && !isArray.value
    ? Object.entries(props.value)
    : []
);
function scalar(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  return displayValue(value, props.field);
}
</script>
<template>
  <span v-if="value === null || value === undefined || value === ''">—</span>
  <el-tag
    v-else-if="typeof value === 'boolean'"
    :type="value ? 'success' : 'info'"
    size="small"
    >{{ value ? "是" : "否" }}</el-tag
  >
  <template v-else-if="isArray">
    <span v-if="!(value as any[]).length">暂无记录</span>
    <el-table
      v-else-if="objectArray && depth < 5"
      :data="visible"
      border
      max-height="420"
      size="small"
      ><el-table-column
        v-for="key in columns"
        :key="key"
        :label="labels[key] || key"
        min-width="150"
        ><template #default="s"
          ><DetailValue
            :value="s.row[key]"
            :field="key"
            :depth="depth + 1" /></template></el-table-column
    ></el-table>
    <div v-else class="detail-array">
      <template v-for="(item, index) in visible" :key="index"
        ><DetailValue :value="item" :field="field" :depth="depth + 1" /><span
          v-if="index < visible.length - 1"
          class="separator"
          >、</span
        ></template
      >
    </div>
    <el-pagination
      v-if="(value as any[]).length > 10"
      v-model:current-page="page"
      :total="(value as any[]).length"
      :page-size="10"
      small
      layout="total,prev,pager,next"
    />
  </template>
  <dl v-else-if="entries.length && depth < 6" class="detail-object">
    <template v-for="[key, item] in entries" :key="key"
      ><dt>{{ labels[key] || key }}</dt>
      <dd><DetailValue :value="item" :field="key" :depth="depth + 1" /></dd
    ></template>
  </dl>
  <span v-else-if="typeof value === 'object'">{{
    entries.length ? "内容层级较深，请联系管理员查看导出档案" : "暂无明细"
  }}</span>
  <span v-else class="detail-text">{{ scalar(value) }}</span>
</template>
<style scoped>
.detail-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.detail-object {
  display: grid;
  grid-template-columns: minmax(80px, 130px) minmax(0, 1fr);
  margin: 0;
  border: 1px solid var(--el-border-color-lighter);
}
.detail-object dt,
.detail-object dd {
  padding: 8px;
  margin: 0;
  overflow-wrap: anywhere;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.detail-object dt {
  background: var(--el-fill-color-light);
  color: var(--el-text-color-regular);
}
.detail-array {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.separator {
  color: var(--el-text-color-secondary);
}
</style>
