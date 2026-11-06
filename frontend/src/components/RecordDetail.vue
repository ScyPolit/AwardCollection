<script setup lang="ts">
defineProps<{
  modelValue: boolean;
  title: string;
  data?: Record<string, unknown> | null;
}>();
defineEmits<{ "update:modelValue": [value: boolean] }>();
function display(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "是" : "否";
  return typeof value === "object"
    ? JSON.stringify(value, null, 2)
    : String(value);
}
</script>
<template>
  <el-drawer
    :model-value="modelValue"
    :title="title"
    size="min(780px, 96vw)"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-descriptions v-if="data" :column="1" border>
      <el-descriptions-item
        v-for="(value, label) in data"
        :key="label"
        :label="String(label)"
      >
        <pre class="value">{{ display(value) }}</pre>
      </el-descriptions-item>
    </el-descriptions>
    <div class="extra"><slot /></div>
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
</style>
