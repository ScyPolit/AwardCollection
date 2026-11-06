<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  emergencyIssue,
  emergencyVoid,
  listBatches,
  listCertificates,
  type Batch,
  type Certificate
} from "@/api/business";
const batches = ref<Batch[]>([]),
  certificates = ref<Certificate[]>([]),
  form = reactive({
    mode: "issue",
    target: undefined as number | undefined,
    reason: "",
    password: ""
  });
async function load() {
  batches.value = await listBatches();
  certificates.value = (await listCertificates(1, 100)).results;
}
async function execute() {
  if (form.mode === "issue")
    await emergencyIssue(form.target!, {
      reason: form.reason,
      password: form.password
    });
  else
    await emergencyVoid(form.target!, {
      reason: form.reason,
      password: form.password
    });
  ElMessage.success(
    form.mode === "issue" ? "批次已进入应急签发队列" : "证书已应急作废"
  );
  form.password = "";
  await load();
}
onMounted(load);
</script>
<template>
  <div class="page business-page">
    <header>
      <h2>超管应急操作</h2>
      <p>每次操作均需密码复核、原因和完整审计记录</p>
    </header>
    <el-alert
      type="warning"
      :closable="false"
      title="仅在普通审批流程无法满足紧急业务时使用"
    /><el-form label-position="top" class="form"
      ><el-form-item label="操作"
        ><el-segmented
          v-model="form.mode"
          :options="[
            { label: '应急签发', value: 'issue' },
            { label: '应急作废', value: 'void' }
          ]" /></el-form-item
      ><el-form-item :label="form.mode === 'issue' ? '目标批次' : '目标证书'"
        ><el-select v-model="form.target" filterable class="full"
          ><el-option
            v-for="item in form.mode === 'issue' ? batches : certificates"
            :key="item.id"
            :label="
              form.mode === 'issue'
                ? (item as Batch).name
                : (item as Certificate).number
            "
            :value="item.id" /></el-select></el-form-item
      ><el-form-item label="应急原因"
        ><el-input
          v-model="form.reason"
          type="textarea"
          :rows="4" /></el-form-item
      ><el-form-item label="超管密码复核"
        ><el-input
          v-model="form.password"
          type="password"
          show-password
          autocomplete="current-password" /></el-form-item
      ><el-button
        type="danger"
        :disabled="!form.target || !form.reason.trim() || !form.password"
        @click="execute"
        >确认执行</el-button
      ></el-form
    >
  </div>
</template>
<style scoped>
.page {
  padding: 20px;
  max-width: 760px;
}
h2 {
  margin: 0;
  font-size: 20px;
  letter-spacing: 0;
}
header p {
  color: var(--el-text-color-secondary);
}
.form {
  margin-top: 22px;
}
.full {
  width: 100%;
}
</style>
