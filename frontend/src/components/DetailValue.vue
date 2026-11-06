<script setup lang="ts">
import { computed, ref, watch } from "vue";
defineOptions({ name: "DetailValue" });
const props = withDefaults(defineProps<{ value: unknown; depth?: number }>(), {
  depth: 0
});
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
  error: "错误详情"
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
  return String(value);
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
            :depth="depth + 1" /></template></el-table-column
    ></el-table>
    <div v-else class="detail-array">
      <template v-for="(item, index) in visible" :key="index"
        ><DetailValue :value="item" :depth="depth + 1" /><span
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
      <dd><DetailValue :value="item" :depth="depth + 1" /></dd
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
