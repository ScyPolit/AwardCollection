<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { getPublicSettings, updatePublicSettings } from "@/api/business";
import ModuleRegion from "./ModuleRegion.vue";
import { useModuleTask } from "@/composables/useModuleTask";
const task = useModuleTask(),
  saving = ref(false),
  config = reactive<Record<string, any>>({});
const fields = [
  ["show_competition", "竞赛名称"],
  ["show_award", "奖项"],
  ["show_team", "团队名称"],
  ["show_members", "获奖成员"],
  ["show_work", "作品名称"],
  ["show_category", "项目类别"],
  ["show_teachers", "指导教师"],
  ["show_issue_date", "颁发日期"],
  ["show_departments", "盖章部门"],
  ["show_published_at", "签发时间"],
  ["show_batch", "获奖批次"],
  ["show_template", "证书模板"]
];
async function load() {
  try {
    await task.run(
      () => getPublicSettings(),
      value => Object.assign(config, value)
    );
  } catch {}
}
async function save() {
  if (saving.value) return;
  saving.value = true;
  try {
    await updatePublicSettings({ ...config });
    ElMessage.success("查验设置已保存");
  } finally {
    saving.value = false;
  }
}
onMounted(load);
</script>
<template>
  <section class="verification-settings">
    <h3>公开查验设置</h3>
    <p>
      统一配置访客可查看的信息和所有查验结果的水印。系统内查验仍遵循账号的数据权限。
    </p>
    <ModuleRegion
      :loading="task.loading.value"
      :error="task.error.value"
      :empty="!Object.keys(config).length"
      @retry="load"
    >
      <el-form label-position="top" @submit.prevent="save">
        <el-form-item label="公开显示字段"
          ><div class="field-grid">
            <el-checkbox
              v-for="[key, label] in fields"
              :key="key"
              v-model="config[key]"
              >{{ label }}</el-checkbox
            >
          </div></el-form-item
        >
        <el-form-item label="姓名保护"
          ><el-checkbox
            v-model="config.mask_members"
            :disabled="!config.show_members"
            >获奖成员姓名脱敏</el-checkbox
          ><el-checkbox
            v-model="config.mask_teachers"
            :disabled="!config.show_teachers"
            >指导教师姓名脱敏</el-checkbox
          ></el-form-item
        >
        <el-form-item label="查验结果水印"
          ><el-input
            v-model="config.watermark_text"
            maxlength="160"
            show-word-limit
            placeholder="请输入水印内容"
          /><span class="help"
            >用于公开查验及系统内查验的全部结果页面。</span
          ></el-form-item
        >
        <el-button
          type="primary"
          native-type="submit"
          :loading="saving"
          :disabled="
            task.loading.value ||
            !!task.error.value ||
            !config.watermark_text?.trim()
          "
          >保存查验设置</el-button
        >
      </el-form>
    </ModuleRegion>
  </section>
</template>
<style scoped>
.verification-settings {
  padding: 24px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
}
h3 {
  margin: 0 0 8px;
  font-size: 18px;
}
p,
.help {
  color: var(--el-text-color-secondary);
  line-height: 1.7;
}
p {
  margin: 0 0 20px;
}
.field-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(120px, 1fr));
  width: 100%;
  gap: 8px 16px;
}
.help {
  display: block;
  margin-top: 6px;
  font-size: 12px;
}
@media (max-width: 700px) {
  .field-grid {
    grid-template-columns: repeat(2, minmax(110px, 1fr));
  }
  .verification-settings {
    padding: 18px;
  }
}
</style>
