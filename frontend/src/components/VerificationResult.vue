<script setup lang="ts">
import { displayValue } from "@/utils/display";
defineProps<{ result: any; number?: string }>();
const fields = [
  ["number", "证书编号"],
  ["competition", "竞赛名称"],
  ["award", "奖项"],
  ["team", "团队名称"],
  ["members", "获奖成员"],
  ["work", "作品名称"],
  ["category", "项目类别"],
  ["teachers", "指导教师"],
  ["issue_date", "颁发日期"],
  ["departments", "盖章部门"],
  ["published_at", "签发时间"],
  ["batch", "获奖批次"],
  ["template", "证书模板"]
];
function value(input: unknown, key: string) {
  return Array.isArray(input)
    ? input.join("、") || "—"
    : displayValue(input, key) || "—";
}
</script>
<template>
  <el-watermark
    v-if="result"
    class="verification-result"
    :content="result.watermark_text || '仅供证书信息核验使用'"
    :rotate="-24"
    :gap="[72, 76]"
    :font="{ color: 'rgba(100,130,160,0.18)', fontSize: 15 }"
  >
    <el-result
      :icon="
        result.found
          ? result.status === 'active'
            ? 'success'
            : 'warning'
          : 'info'
      "
      :title="
        result.found
          ? result.status === 'active'
            ? '证书有效'
            : '证书已作废'
          : '未查询到证书记录'
      "
      :sub-title="
        result.found ? '以下为平台登记的证书信息' : '请核对证书编号后重新查验'
      "
    />
    <el-descriptions v-if="result.found" :column="1" border>
      <template v-for="[key, label] in fields" :key="key">
        <el-descriptions-item v-if="key in result" :label="label">{{
          value(result[key], key)
        }}</el-descriptions-item>
      </template>
    </el-descriptions>
    <p v-else class="query-number">查验编号：{{ number || "—" }}</p>
    <p class="result-note">查验结果以平台当前登记状态为准。</p>
  </el-watermark>
</template>
<style scoped>
.verification-result {
  margin-top: 24px;
  padding: 0 20px 18px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
  overflow: hidden;
}
.verification-result :deep(.el-result) {
  padding: 24px 8px;
}
.verification-result :deep(.el-descriptions__label) {
  width: 110px;
}
.verification-result :deep(.el-descriptions__content) {
  overflow-wrap: anywhere;
}
.result-note,
.query-number {
  margin: 16px 0 0;
  color: var(--el-text-color-secondary);
  text-align: center;
  line-height: 1.7;
}
@media (max-width: 600px) {
  .verification-result {
    padding: 0 12px 12px;
  }
}
</style>
