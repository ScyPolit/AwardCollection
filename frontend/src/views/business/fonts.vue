<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox, type UploadFile } from "element-plus";
import RecordDetail from "@/components/RecordDetail.vue";
import {
  importFont,
  manageFonts,
  listFonts,
  currentUser,
  updateFont,
  type CertificateFont
} from "@/api/business";

const rows = ref<CertificateFont[]>([]),
  isSuper = ref(false),
  search = ref(""),
  busy = ref(false);
const dialog = ref(false),
  saving = ref(false),
  file = ref<File>();
const form = reactive({ name: "", confirmed: false });
const selected = ref<CertificateFont>(),
  preview = ref(false),
  previewError = ref("");
const visible = computed(() =>
  rows.value.filter(f =>
    f.name.toLowerCase().includes(search.value.toLowerCase())
  )
);
const details = computed(() =>
  selected.value
    ? {
        名称: selected.value.name,
        来源: selected.value.builtin ? "系统内置" : "授权导入",
        状态: selected.value.active ? "启用" : "停用",
        许可: selected.value.license,
        SHA256: selected.value.sha256
      }
    : {}
);
const sample = ref("荣誉证书 校园竞赛 ABCDEFG abcdefg 0123456789");
async function load() {
  busy.value = true;
  try {
    isSuper.value = (await currentUser()).isSuperuser;
    rows.value = isSuper.value ? await manageFonts() : await listFonts();
  } finally {
    busy.value = false;
  }
}
function openImport() {
  Object.assign(form, { name: "", confirmed: false });
  file.value = undefined;
  dialog.value = true;
}
function choose(upload: UploadFile) {
  file.value = upload.raw;
}
async function upload() {
  if (!file.value || saving.value) return;
  saving.value = true;
  try {
    const data = new FormData();
    data.append("file", file.value);
    data.append("name", form.name);
    data.append("license_confirmed", "true");
    const result = await importFont(data);
    dialog.value = false;
    await load();
    ElMessage.success(
      result.active
        ? "字体已导入，可在模板编辑器选用"
        : "字体已存在且已停用，请由超管重新启用"
    );
  } finally {
    saving.value = false;
  }
}
async function rename(font: CertificateFont) {
  try {
    const { value } = await ElMessageBox.prompt(
      "修改字体的显示名称",
      "重命名字体",
      {
        inputValue: font.name,
        inputValidator: value =>
          (!!value?.trim() && value.trim().length <= 160) ||
          "请输入 1～160 个字符"
      }
    );
    await updateFont(font.id, { name: value.trim() });
    await load();
    ElMessage.success("名称已更新");
  } catch (error) {
    if (error !== "cancel" && error !== "close") console.error(error);
  }
}
async function toggle(font: CertificateFont) {
  try {
    await ElMessageBox.confirm(
      font.active
        ? "停用后不再出现在新字体选项中；历史模板和已签发证书仍保留原字体。"
        : "启用后可在模板编辑器中选用。",
      font.active ? "停用字体" : "启用字体",
      { type: "warning" }
    );
    await updateFont(font.id, { active: !font.active });
    await load();
    ElMessage.success("字体状态已更新");
  } catch (error) {
    if (error !== "cancel" && error !== "close") console.error(error);
  }
}
async function show(font: CertificateFont) {
  selected.value = font;
  previewError.value = "字体加载中…";
  preview.value = true;
  try {
    const face = await new FontFace(
      "AC_preview_" + font.id.replaceAll("-", "_"),
      `url("${font.url}")`
    ).load();
    (document.fonts as FontFaceSet & { add(face: FontFace): void }).add(face);
    if (selected.value?.id === font.id) previewError.value = "";
  } catch {
    if (selected.value?.id === font.id)
      previewError.value = "字体预览加载失败，请重试";
  }
}
onMounted(load);
</script>
<template>
  <div class="page business-page">
    <header>
      <div>
        <h2>字体管理</h2>
        <p>维护学校授权字体；内置字体随系统维护</p>
      </div>
      <div class="toolbar">
        <el-input
          v-model="search"
          placeholder="搜索字体名称"
          clearable
        /><el-button type="primary" @click="openImport">导入字体</el-button>
      </div>
    </header>
    <el-alert
      type="info"
      :closable="false"
      title="支持静态 TTF / TTC，最大 40 MB。请确认具备使用、转换、嵌入和展示授权；停用不会影响历史证书。"
    />
    <el-table v-loading="busy" :data="visible" border class="font-table">
      <el-table-column label="字体名称" min-width="260"
        ><template #default="s"
          ><el-button link type="primary" @click="show(s.row)">{{
            s.row.name
          }}</el-button></template
        ></el-table-column
      >
      <el-table-column label="来源" width="110"
        ><template #default="s"
          ><el-tag :type="s.row.builtin ? 'info' : 'primary'">{{
            s.row.builtin ? "系统内置" : "授权导入"
          }}</el-tag></template
        ></el-table-column
      >
      <el-table-column label="状态" width="90"
        ><template #default="s"
          ><el-tag :type="s.row.active ? 'success' : 'info'">{{
            s.row.active ? "启用" : "停用"
          }}</el-tag></template
        ></el-table-column
      >
      <el-table-column
        prop="license"
        label="许可说明"
        min-width="200"
        show-overflow-tooltip
      />
      <el-table-column label="操作" width="240"
        ><template #default="s"
          ><el-button link @click="show(s.row)">预览与详情</el-button
          ><template v-if="isSuper && !s.row.builtin"
            ><el-button link @click="rename(s.row)">重命名</el-button
            ><el-button
              link
              :type="s.row.active ? 'danger' : 'success'"
              @click="toggle(s.row)"
              >{{ s.row.active ? "停用" : "启用" }}</el-button
            ></template
          ></template
        ></el-table-column
      >
    </el-table>
    <el-dialog
      v-model="dialog"
      title="导入授权字体"
      width="520"
      destroy-on-close
      :show-close="!saving"
      :close-on-click-modal="!saving"
      :close-on-press-escape="!saving"
    >
      <el-form label-position="top"
        ><el-form-item label="显示名称（可选）"
          ><el-input v-model.trim="form.name" maxlength="160" /></el-form-item
        ><el-form-item label="字体文件"
          ><el-upload
            :auto-upload="false"
            :limit="1"
            accept=".ttf,.ttc"
            :on-change="choose"
            :on-remove="() => (file = undefined)"
            ><el-button>选择 TTF / TTC 文件</el-button></el-upload
          ></el-form-item
        ><el-checkbox v-model="form.confirmed" class="license-check"
          >确认具备此字体在本系统中使用、格式转换、嵌入和展示的授权</el-checkbox
        ></el-form
      >
      <template #footer
        ><el-button :disabled="saving" @click="dialog = false">取消</el-button
        ><el-button
          type="primary"
          :loading="saving"
          :disabled="!file || !form.confirmed"
          @click="upload"
          >导入字体</el-button
        ></template
      >
    </el-dialog>
    <RecordDetail v-model="preview" title="字体预览与详情" :data="details"
      ><el-input v-model="sample" placeholder="输入预览文本" />
      <p
        class="font-sample"
        :style="{
          fontFamily: selected
            ? 'AC_preview_' + selected.id.replaceAll('-', '_')
            : 'inherit'
        }"
      >
        {{ sample }}
      </p>
      <p>
        {{
          previewError ||
          "预览中不受此字体支持的字形由浏览器回退显示；证书生成前另有字形覆盖校验。"
        }}
      </p></RecordDetail
    >
  </div>
</template>
<style scoped>
.page {
  padding: 20px;
}
header,
.toolbar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
header {
  margin-bottom: 18px;
}
h2 {
  margin: 0;
  font-size: 20px;
  letter-spacing: 0;
}
p {
  color: var(--el-text-color-secondary);
}
.toolbar .el-input {
  width: 240px;
  max-width: 100%;
}
.font-table {
  margin-top: 18px;
}
.font-sample {
  padding: 24px;
  margin: 16px 0;
  font-size: 28px;
  line-height: 1.8;
  overflow-wrap: anywhere;
  color: var(--el-text-color-primary);
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
}
.license-check {
  height: auto;
  white-space: normal;
}
.license-check :deep(.el-checkbox__label) {
  white-space: normal;
}
</style>
