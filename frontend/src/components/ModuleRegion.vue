<script setup lang="ts">
defineProps<{ loading?: boolean; error?: string; empty?: boolean }>();
defineEmits<{ retry: [] }>();
</script>
<template>
  <section class="module-region" :aria-busy="loading">
    <div v-if="error" role="alert" class="module-error">
      <span>{{ error }}</span
      ><el-button link type="primary" @click="$emit('retry')"
        >重新加载</el-button
      >
    </div>
    <el-skeleton
      v-if="loading && empty"
      :rows="5"
      animated
      class="module-skeleton"
    />
    <div v-else v-loading="loading" element-loading-text="正在加载…">
      <slot />
    </div>
  </section>
</template>
<style scoped>
.module-region {
  min-width: 0;
  position: relative;
}
.module-skeleton {
  padding: 24px;
  min-height: 220px;
  background: var(--el-bg-color);
  border-radius: 6px;
}
.module-error {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 12px;
  color: var(--el-color-danger);
}
</style>
