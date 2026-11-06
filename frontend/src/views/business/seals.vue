<script setup lang="ts">
import ManagementActions from "@/components/ManagementActions.vue";
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox, type UploadFile } from "element-plus";
import RecordDetail from "@/components/RecordDetail.vue";
import { useBusinessAccess } from "@/utils/businessAccess";
import {
  createSeal,
  listDepartments,
  listSeals,
  updateSeal,
  uploadSeal,
  type Option,
  type Seal
} from "@/api/business";
const { user, isSuper, isAdmin } = useBusinessAccess();
const rows = ref<Seal[]>([]),
  departments = ref<Option[]>([]),
  dialog = ref(false),
  saving = ref(false),
  busy = ref<number>(),
  drawer = ref(false),
  selected = ref<Seal>(),
  versionId = ref<number>();
const form = reactive({
  name: "",
  department: undefined as number | undefined,
  active: true
});
const managed = computed(() =>
  departments.value.filter(
    d => isSuper.value || user.value.managedDepartmentIds.includes(d.id)
  )
);
const canManage = (row: Seal) =>
  isSuper.value || user.value.managedDepartmentIds.includes(row.department);
const version = computed(() =>
  selected.value?.versions.find(v => v.id === versionId.value)
);
const previewUrl = computed(() =>
  selected.value && versionId.value
    ? `/api/v1/seals/${selected.value.id}/preview/?version=${versionId.value}`
    : ""
);
const info = computed(() => ({
  公章名称: selected.value?.name,
  所属部门: selected.value?.department_name,
  状态: selected.value?.active ? "启用" : "停用",
  版本数量: selected.value?.versions.length,
  创建时间: (selected.value as any)?.created_at,
  当前版本: version.value?.number,
  版本摘要: version.value?.sha256
}));
async function load() {
  [rows.value, departments.value] = await Promise.all([
    listSeals(),
    listDepartments()
  ]);
}
function openCreate() {
  Object.assign(form, {
    name: "",
    department: managed.value[0]?.id,
    active: true
  });
  dialog.value = true;
}
function show(row: Seal) {
  selected.value = row;
  versionId.value = row.versions.at(-1)?.id;
  drawer.value = true;
}
async function create() {
  if (saving.value) return;
  saving.value = true;
  try {
    await createSeal({ ...form });
    dialog.value = false;
    ElMessage.success("公章已创建");
    await load();
  } catch {
  } finally {
    saving.value = false;
  }
}
async function toggle(row: Seal) {
  try {
    await ElMessageBox.confirm(
      `确认${row.active ? "停用" : "启用"}“${row.name}”？`,
      "公章状态"
    );
    busy.value = row.id;
    await updateSeal(row.id, { active: !row.active });
    await load();
  } catch {
  } finally {
    busy.value = undefined;
  }
}
async function upload(row: Seal, file: UploadFile) {
  if (!file.raw) return;
  busy.value = row.id;
  try {
    await uploadSeal(row.id, file.raw);
    ElMessage.success("新版本已上传");
    await load();
    if (selected.value?.id === row.id)
      show(rows.value.find(r => r.id === row.id)!);
  } catch {
  } finally {
    busy.value = undefined;
  }
}
onMounted(load);
</script>
<template>
  <div class="page business-page">
    <header>
      <div>
        <h2>公章管理</h2>
        <p>点击公章名称查看图片和历史版本；管理员维护本部门公章</p>
      </div>
      <el-button v-if="isAdmin" type="primary" @click="openCreate"
        >新增公章</el-button
      >
    </header>
    <el-table :data="rows" border @row-dblclick="row => show(row as Seal)"
      ><el-table-column min-width="220" label="公章名称"
        ><template #default="s"
          ><el-button link type="primary" @click="show(s.row as Seal)">{{
            s.row.name
          }}</el-button></template
        ></el-table-column
      ><el-table-column
        min-width="220"
        prop="department_name"
        label="部门"
      /><el-table-column label="版本" width="90"
        ><template #default="s">{{
          s.row.versions.length
        }}</template></el-table-column
      ><el-table-column label="状态" width="90"
        ><template #default="s"
          ><el-tag :type="s.row.active ? 'success' : 'info'">{{
            s.row.active ? "启用" : "停用"
          }}</el-tag></template
        ></el-table-column
      ><el-table-column label="操作" width="350"
        ><template #default="s"
          ><el-button link @click="show(s.row as Seal)">查看</el-button
          ><ManagementActions
            :url="`/api/v1/seals/${s.row.id}/`"
            :data="s.row"
            :name="s.row.name"
            :can-edit="canManage(s.row as Seal)"
            :can-delete="canManage(s.row as Seal)"
            :fields="[{ key: 'name', label: '公章名称', required: true }]"
            @changed="load"
          /><template v-if="canManage(s.row as Seal)"
            ><el-upload
              :auto-upload="false"
              :show-file-list="false"
              accept="image/*"
              :disabled="busy === s.row.id"
              :on-change="f => upload(s.row as Seal, f)"
              ><el-button link type="primary" :loading="busy === s.row.id"
                >上传新版本</el-button
              ></el-upload
            ><el-button
              link
              :disabled="busy === s.row.id"
              @click="toggle(s.row as Seal)"
              >{{ s.row.active ? "停用" : "启用" }}</el-button
            ></template
          ></template
        ></el-table-column
      ></el-table
    >
    <el-dialog
      v-model="dialog"
      title="新增公章"
      width="480"
      :show-close="!saving"
      :close-on-click-modal="!saving"
      ><el-form label-position="top"
        ><el-form-item label="名称"
          ><el-input v-model.trim="form.name" /></el-form-item
        ><el-form-item label="所属部门"
          ><el-select v-model="form.department" class="full"
            ><el-option
              v-for="d in managed"
              :key="d.id"
              :label="d.name"
              :value="d.id" /></el-select></el-form-item></el-form
      ><template #footer
        ><el-button :disabled="saving" @click="dialog = false">取消</el-button
        ><el-button
          type="primary"
          :loading="saving"
          :disabled="!form.name || !form.department"
          @click="create"
          >创建</el-button
        ></template
      ></el-dialog
    >
    <RecordDetail v-model="drawer" title="公章详情与预览" :data="info"
      ><el-select v-model="versionId" placeholder="选择历史版本" class="full"
        ><el-option
          v-for="v in selected?.versions || []"
          :key="v.id"
          :value="v.id"
          :label="`v${v.number} · ${v.created_at}`" /></el-select
      ><el-empty v-if="!previewUrl" description="尚未上传公章图片" />
      <div v-else class="seal-preview">
        <el-image
          :src="previewUrl"
          fit="contain"
          :preview-src-list="[previewUrl]"
          :preview-teleported="true"
          ><template #error
            >图片无法预览，请刷新或联系维护部门。</template
          ></el-image
        >
      </div>
      <p v-if="selected && !canManage(selected)">
        此处为用印信息核对预览，负责人不能修改公章。
      </p>
      <template #actions
        ><ManagementActions
          v-if="selected"
          :url="`/api/v1/seals/${selected.id}/`"
          :data="selected"
          :name="selected.name"
          :can-edit="canManage(selected)"
          :can-delete="canManage(selected)"
          :fields="[{ key: 'name', label: '公章名称', required: true }]"
          @changed="
            drawer = false;
            load();
          "
        /><el-upload
          v-if="selected && canManage(selected)"
          :auto-upload="false"
          :show-file-list="false"
          accept="image/png,image/jpeg"
          :on-change="f => upload(selected!, f)"
          ><el-button>上传公章新版本</el-button></el-upload
        ></template
      ></RecordDetail
    >
  </div>
</template>
<style scoped>
.page {
  padding: 20px;
}
header {
  display: flex;
  justify-content: space-between;
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
.full {
  width: 100%;
  margin-bottom: 16px;
}
:deep(.el-upload) {
  display: inline-block;
  margin: 0 10px;
}
.seal-preview {
  display: grid;
  place-items: center;
  min-height: 320px;
  padding: 20px;
  border: 1px solid #e5e7eb;
  background: repeating-conic-gradient(#f3f4f6 0 25%, white 0 50%) 0/20px 20px;
}
.seal-preview :deep(.el-image) {
  width: 360px;
  height: 360px;
  max-width: 100%;
}
</style>
