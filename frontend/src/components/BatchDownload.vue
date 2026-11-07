<script setup lang="ts">
import { watch } from "vue";
import { usePreparedFile } from "@/composables/usePreparedFile";
const props = defineProps<{ batchId: number }>();
const { file, loading, error, start } = usePreparedFile();
function prepare() {
  start({ kind: "batch_zip", batch: props.batchId });
}
watch(() => props.batchId, prepare, { immediate: true });
</script>
<template>
  <section class="batch-download" aria-label="整批文件下载">
    <strong>整批 ZIP</strong>
    <template v-if="file?.status === 'ready'"
      ><p>
        文件已保存到服务器 · {{ (file.bytes / 1024 / 1024).toFixed(1) }} MB
      </p>
      <el-button type="primary" tag="a" :href="file.download_url"
        >下载整批 ZIP</el-button
      ><small>支持断点续传，下载期间可继续使用其他功能。</small></template
    >
    <template v-else-if="error || file?.status === 'failed'"
      ><el-alert
        :title="error || file?.error"
        type="error"
        :closable="false"
      /><el-button @click="prepare">重新准备下载包</el-button></template
    >
    <template v-else
      ><p role="status">
        {{
          loading
            ? "正在查询下载文件…"
            : file?.status === "running"
              ? `服务器正在打包 ${file.processed} / ${file.total} 份`
              : "后台排队中，完成后会实时通知"
        }}
      </p>
      <el-progress
        :percentage="file?.percent || 0"
        :indeterminate="!file?.total"
      /><small
        >后台处理，不影响其他页面。准备完成后点击下载即可。</small
      ></template
    >
  </section>
</template>
<style scoped>
.batch-download {
  padding: 16px;
  margin: 14px 0;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
}
p {
  margin: 10px 0;
}
small {
  display: block;
  margin-top: 10px;
  color: var(--el-text-color-secondary);
}
.el-button {
  margin-top: 8px;
}
</style>
