<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from "vue";
import { usePreparedFile } from "@/composables/usePreparedFile";
import SmartImage from "./SmartImage.vue";
const props = defineProps<{ version: number; alt?: string }>();
const root = ref<HTMLElement>(),
  visible = ref(false);
const { file, loading, error, start, stop } = usePreparedFile();
let observer: IntersectionObserver;
function prepare() {
  if (props.version && visible.value)
    start({ kind: "template_thumbnail", template_version: props.version });
}
onMounted(() => {
  observer = new IntersectionObserver(
    entries => {
      if (entries.some(e => e.isIntersecting)) {
        visible.value = true;
        prepare();
        observer.disconnect();
      }
    },
    { rootMargin: "80px" }
  );
  if (root.value) observer.observe(root.value);
});
onBeforeUnmount(() => observer?.disconnect());
watch(
  () => props.version,
  () => {
    stop();
    prepare();
  }
);
</script>
<template>
  <div
    ref="root"
    class="prepared-preview"
    :aria-busy="
      loading || (file && file.status !== 'ready' && file.status !== 'failed')
    "
  >
    <SmartImage
      v-if="file?.status === 'ready'"
      :src="file.download_url"
      :alt="alt || '证书模板预览'"
      fit="contain"
    />
    <div
      v-else-if="error || file?.status === 'failed'"
      class="preview-status"
      role="status"
    >
      <span>{{ error || file?.error }}</span
      ><el-button link @click.stop="prepare">重试</el-button>
    </div>
    <div v-else class="preview-status" role="status">
      <el-skeleton animated
        ><template #template
          ><el-skeleton-item
            variant="image"
            style="width: 100%; height: 140px" /></template></el-skeleton
      ><span>{{
        file?.status === "running" ? "正在生成预览…" : "预览准备中…"
      }}</span>
    </div>
  </div>
</template>
<style scoped>
.prepared-preview {
  width: 100%;
  height: 100%;
  min-height: 160px;
}
.prepared-preview :deep(.el-image) {
  width: 100%;
  height: 100%;
}
.preview-status {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 8px;
  height: 100%;
  padding: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
