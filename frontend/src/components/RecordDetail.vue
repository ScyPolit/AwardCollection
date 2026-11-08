<script setup lang="ts">
import DetailValue from "./DetailValue.vue";
defineProps<{
  modelValue: boolean;
  title: string;
  data?: Record<string, unknown> | null;
  readonlyReason?: string;
  loading?: boolean;
  error?: string;
}>();
defineEmits<{ "update:modelValue": [value: boolean] }>();
</script>
<template>
  <el-drawer
    :model-value="modelValue"
    :title="title"
    size="min(780px, 96vw)"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-skeleton v-if="loading" :rows="7" animated />
    <el-alert v-else-if="error" :title="error" type="error" :closable="false" />
    <el-descriptions v-else-if="data" :column="1" border>
      <el-descriptions-item
        v-for="(value, label) in data"
        :key="label"
        :label="String(label)"
      >
        <div class="value">
          <DetailValue :value="value" :field="String(label)" />
        </div>
      </el-descriptions-item>
    </el-descriptions>
    <el-alert
      v-if="readonlyReason"
      :title="readonlyReason"
      :closable="false"
      type="info"
      class="extra"
    />
    <div v-if="!loading && !error" class="extra"><slot /></div>
    <template v-if="$slots.actions && !loading && !error" #footer
      ><div class="detail-actions"><slot name="actions" /></div
    ></template>
  </el-drawer>
</template>
<style scoped>
.value {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font: inherit;
  max-height: 420px;
  overflow: auto;
}
.extra {
  margin-top: 20px;
}
.detail-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}
.detail-actions :deep(.el-button) {
  margin: 0;
}
.extra :deep(.el-space) {
  flex-wrap: wrap;
}
:deep(.el-descriptions__label) {
  width: 120px;
}
:deep(.el-descriptions__content) {
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
