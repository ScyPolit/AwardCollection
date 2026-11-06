<script setup lang="ts">
import { ref, reactive } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { http } from "@/utils/http";
export type EditField = {
  key: string;
  label: string;
  type?: "boolean" | "password" | "textarea" | "list" | "select";
  options?: Array<{ label: string; value: any }>;
  required?: boolean;
};
const props = withDefaults(
  defineProps<{
    url: string;
    data: Record<string, any>;
    fields: EditField[];
    canEdit?: boolean;
    canDelete?: boolean;
    name?: string;
  }>(),
  { canEdit: true, canDelete: true, name: "记录" }
);
const emit = defineEmits(["changed"]);
const dialog = ref(false),
  busy = ref(false),
  form = reactive<Record<string, any>>({});
function edit() {
  for (const f of props.fields)
    form[f.key] =
      f.type === "password"
        ? ""
        : structuredClone(props.data[f.key] ?? (f.type === "list" ? [] : ""));
  dialog.value = true;
}
async function save() {
  if (busy.value) return;
  for (const f of props.fields)
    if (f.required && !form[f.key])
      return ElMessage.warning(`请填写${f.label}`);
  busy.value = true;
  try {
    const data = Object.fromEntries(
      props.fields
        .filter(f => f.type !== "password" || form[f.key])
        .map(f => [f.key, form[f.key]])
    );
    await http.request("patch", props.url, { data });
    dialog.value = false;
    emit("changed");
    ElMessage.success("修改已保存");
  } finally {
    busy.value = false;
  }
}
async function remove() {
  await ElMessageBox.confirm(
    `确认删除“${props.name}”？关联历史会保留；审批或生成中的记录需要先处理。`,
    "删除记录",
    { type: "warning" }
  );
  busy.value = true;
  try {
    await http.request("delete", props.url);
    emit("changed");
    ElMessage.success("已删除");
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <span class="management-actions"
    ><el-button
      v-if="canEdit"
      link
      type="primary"
      :disabled="busy"
      @click.stop="edit"
      >修改</el-button
    ><el-button
      v-if="canDelete"
      link
      type="danger"
      :disabled="busy"
      @click.stop="remove"
      >删除</el-button
    ></span
  >
  <el-dialog
    v-model="dialog"
    :title="`修改${name}`"
    width="520px"
    append-to-body
    :close-on-click-modal="!busy"
    ><el-form label-position="top" @submit.prevent="save"
      ><el-form-item
        v-for="field in fields"
        :key="field.key"
        :label="field.label"
        :required="field.required"
        ><el-switch
          v-if="field.type === 'boolean'"
          v-model="form[field.key]" /><el-select
          v-else-if="field.type === 'list' || field.type === 'select'"
          v-model="form[field.key]"
          :multiple="field.type === 'list'"
          filterable
          :allow-create="!field.options"
          style="width: 100%"
          ><el-option
            v-for="o in field.options || []"
            :key="o.value"
            :label="o.label"
            :value="o.value" /></el-select
        ><el-input
          v-else
          v-model="form[field.key]"
          :type="
            field.type === 'password'
              ? 'password'
              : field.type === 'textarea'
                ? 'textarea'
                : 'text'
          "
          :show-password="field.type === 'password'"
          :maxlength="field.type === 'textarea' ? 4000 : 160"
          :placeholder="
            field.type === 'password' ? '留空保持原密码' : ''
          " /></el-form-item></el-form
    ><template #footer
      ><el-button :disabled="busy" @click="dialog = false">取消</el-button
      ><el-button type="primary" :loading="busy" @click="save"
        >保存修改</el-button
      ></template
    ></el-dialog
  >
</template>
<style scoped>
.management-actions {
  display: inline-flex;
  gap: 8px;
  margin-left: 8px;
}
.management-actions .el-button {
  margin: 0;
}
</style>
