<script setup lang="ts">
import { computed, watch } from "vue";
import { usePreparedFile } from "@/composables/usePreparedFile";
import { statusLabel } from "@/utils/display";
const props = defineProps<{
  batch: { id: number; status: string };
  job?: any;
  approvals?: any[];
  submitting?: boolean;
}>();
const archive = usePreparedFile();
watch(
  () => [props.batch.id, props.batch.status],
  () => {
    archive.stop();
    archive.file.value = undefined;
    archive.error.value = "";
    archive.loading.value = false;
    if (props.batch.status === "issued")
      archive.start({ kind: "batch_zip", batch: props.batch.id });
  },
  { immediate: true }
);
const active = computed(() =>
  props.batch.status === "issued"
    ? archive.file.value?.status === "ready"
      ? 5
      : 3
    : props.batch.status === "queued" || props.batch.status === "failed"
      ? 2
      : props.batch.status === "review"
        ? 1
        : 0
);
const problem = computed(
  () =>
    props.batch.status === "returned" ||
    props.batch.status === "failed" ||
    archive.file.value?.status === "failed"
);
const titles = ["名单提交", "部门会签", "证书生成", "文件打包", "可下载"];
const descriptions = computed(() => [
  props.submitting
    ? "正在校验名单并准备首张样张"
    : props.batch.status === "returned"
      ? "已退回，请核对后重新提交"
      : active.value > 0
        ? "名单校验完成"
        : "导入并核对获奖名单",
  `${props.approvals?.filter(item => item.decision === "approved").length || 0} / ${props.approvals?.length || 0} 个部门已通过`,
  props.job
    ? `${statusLabel(props.job.status)} · ${props.job.processed} / ${props.job.total} 份`
    : "全部部门通过后开始",
  archive.file.value?.status === "ready"
    ? "整批文件已保存"
    : archive.file.value
      ? `${statusLabel(archive.file.value.status)} · ${archive.file.value.processed} / ${archive.file.value.total} 份`
      : "签发完成后自动准备",
  archive.file.value?.status === "ready"
    ? "点击下方链接下载整批证书"
    : "准备完成后通知"
]);
</script>
<template>
  <section class="batch-workflow" aria-label="批次任务流程">
    <div class="flow-heading">
      <h3>任务流程</h3>
      <el-tag
        :type="problem ? 'warning' : active === 5 ? 'success' : 'primary'"
        >{{ submitting ? "正在提交" : statusLabel(batch.status) }}</el-tag
      >
    </div>
    <div class="flow-scroll">
      <el-steps
        :active="active"
        finish-status="success"
        :process-status="problem ? 'error' : 'process'"
        align-center
        ><el-step
          v-for="(title, index) in titles"
          :key="title"
          :title="title"
          :description="descriptions[index]"
      /></el-steps>
    </div>
    <div v-if="approvals?.length" class="approval-tags">
      <el-tag
        v-for="item in approvals"
        :key="item.id"
        :type="
          item.decision === 'approved'
            ? 'success'
            : item.decision === 'returned' || item.decision === 'withdrawn'
              ? 'danger'
              : 'info'
        "
        >{{ item.department_name }} ·
        {{ statusLabel(item.decision || "pending") }}</el-tag
      >
    </div>
    <el-progress
      v-if="job && ['queued', 'running'].includes(job.status)"
      :percentage="
        job.percent ||
        Math.round((job.processed / Math.max(job.total, 1)) * 100)
      "
      :indeterminate="!job.total"
    />
    <el-alert
      v-if="job?.error || archive.error.value || archive.file.value?.error"
      :title="job?.error || archive.error.value || archive.file.value?.error"
      type="warning"
      :closable="false"
    />
    <el-skeleton v-if="archive.loading.value" :rows="1" animated />
    <el-button
      v-if="archive.error.value || archive.file.value?.status === 'failed'"
      @click="archive.start({ kind: 'batch_zip', batch: batch.id })"
      >重新准备下载包</el-button
    >
    <el-button
      v-if="archive.file.value?.status === 'ready'"
      type="primary"
      tag="a"
      :href="archive.file.value.download_url"
      >下载整批 ZIP</el-button
    >
  </section>
</template>
<style scoped>
.batch-workflow {
  margin-top: 20px;
  padding: 20px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
}
.flow-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 24px;
}
h3 {
  margin: 0;
  font-size: 16px;
}
.flow-scroll {
  overflow-x: auto;
  padding-bottom: 8px;
}
.flow-scroll :deep(.el-steps) {
  min-width: 620px;
}
.flow-scroll :deep(.el-step__description) {
  padding-top: 8px;
  line-height: 1.7;
}
.approval-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 18px 0;
}
.batch-workflow > .el-button,
.batch-workflow > .el-alert {
  margin-top: 16px;
}
.batch-workflow :deep(.el-step__title) {
  font-size: 14px;
}
@media (max-width: 600px) {
  .batch-workflow {
    padding: 16px 12px;
  }
}
</style>
