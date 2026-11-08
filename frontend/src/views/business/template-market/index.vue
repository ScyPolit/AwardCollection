<!-- Product-card grid adapted from Pure Admin's official CardList page (MIT). -->
<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import ListCard from "./ListCard.vue";
import RecordDetail from "@/components/RecordDetail.vue";
import PreparedPreview from "@/components/PreparedPreview.vue";
import ModuleRegion from "@/components/ModuleRegion.vue";
import BulkActions from "@/components/BulkActions.vue";
import { useModuleTask } from "@/composables/useModuleTask";
const listTask = useModuleTask(),
  dataLoading = listTask.loading,
  loadError = listTask.error;
import { useBusinessAccess } from "@/utils/businessAccess";
import {
  copyTemplate,
  listDepartments,
  listTemplates,
  type Template,
  type Option
} from "@/api/business";
const router = useRouter(),
  { user, isAdmin, isSuper } = useBusinessAccess();
const productList = ref<Template[]>([]),
  selectedIds = ref<number[]>([]),
  departments = ref<Option[]>([]),
  searchValue = ref(""),
  library = ref("all"),
  department = ref<number>(),
  pagination = reactive({ current: 1, pageSize: 12 });
const filtered = computed(() =>
  productList.value.filter(
    p =>
      p.name.toLowerCase().includes(searchValue.value.toLowerCase()) &&
      (library.value === "all" ||
        (library.value === "mine" ? p.is_mine : p.published)) &&
      (!department.value || p.department === department.value)
  )
);
const visible = computed(() =>
  filtered.value.slice(
    (pagination.current - 1) * pagination.pageSize,
    pagination.current * pagination.pageSize
  )
);
const filterDepartments = computed(() => [
  ...new Map(
    productList.value.map(item => [
      item.department,
      { id: item.department, name: item.department_name }
    ])
  ).values()
]);
const managed = computed(() =>
  departments.value.filter(
    d =>
      isSuper.value ||
      user.value.roles.includes("owner") ||
      user.value.managedDepartmentIds.includes(d.id)
  )
);
const bulkSelection = computed(() =>
  productList.value.filter(p => selectedIds.value.includes(p.id))
);
const canBulkManage = computed(() =>
  bulkSelection.value.every(p => p.can_manage)
);
function check(product: Template, value: boolean) {
  selectedIds.value = value
    ? [...new Set([...selectedIds.value, product.id])]
    : selectedIds.value.filter(id => id !== product.id);
}
const selected = ref<Template>(),
  preview = ref(false),
  copyDialog = ref(false),
  saving = ref(false),
  form = reactive({ name: "", department: undefined as number | undefined });
const info = computed(() => ({
  模板名称: selected.value?.name,
  维护部门: selected.value?.department_name,
  共享: selected.value?.published
}));
watch([searchValue, department, library], () => (pagination.current = 1));
async function load() {
  try {
    await listTask.run(
      () => Promise.all([listTemplates(), listDepartments()]),
      values => {
        [productList.value, departments.value] = values;
        selectedIds.value = [];
      }
    );
  } catch {}
}
function show(product: Template) {
  selected.value = product;
  preview.value = true;
}
function select(product: Template) {
  router.push({
    path: "/business/batches",
    query: { template: product.latest_version?.id }
  });
}
function edit(product: Template) {
  router.push({ path: "/business/templates", query: { template: product.id } });
}
function openCopy(product: Template) {
  selected.value = product;
  Object.assign(form, {
    name: product.name + " 副本",
    department:
      managed.value.find(d => d.id === product.department)?.id ||
      managed.value[0]?.id
  });
  copyDialog.value = true;
}
async function copy() {
  if (!selected.value || saving.value) return;
  saving.value = true;
  try {
    const target = await copyTemplate(selected.value.id, { ...form });
    copyDialog.value = false;
    ElMessage.success("已复制到我的模板库，默认不共享，可在编辑器中调整");
    edit(target);
  } catch {
  } finally {
    saving.value = false;
  }
}
onMounted(load);
</script>
<template>
  <div class="market-page business-page">
    <div class="w-full flex justify-between mb-4 toolbar">
      <div>
        <el-button
          v-if="isAdmin || user.roles.includes('owner')"
          @click="router.push('/business/templates')"
          >新建与编辑模板</el-button
        ><el-select
          v-model="library"
          aria-label="模板范围"
          style="width: 140px"
        >
          <el-option label="全部可用模板" value="all" />
          <el-option label="我的模板" value="mine" />
          <el-option label="共享模板" value="shared" /> </el-select
        ><el-select
          :loading="dataLoading"
          v-model="department"
          clearable
          placeholder="全部维护部门"
          style="width: 200px"
          ><el-option
            v-for="d in filterDepartments"
            :key="d.id"
            :label="d.name"
            :value="d.id"
        /></el-select>
      </div>
      <el-input
        v-model="searchValue"
        style="width: 300px"
        placeholder="搜索证书模板"
        clearable
      />
    </div>
    <BulkActions
      :selected="bulkSelection"
      resource="templates"
      :can-delete="canBulkManage"
      :can-toggle="canBulkManage"
      readonly-reason="只能修改或删除自己的模板和有管理权限的部门模板。"
      @clear="selectedIds = []"
      @changed="load"
    />
    <ModuleRegion
      :loading="dataLoading"
      :error="loadError"
      :empty="!productList.length"
      @retry="load"
    >
      <el-empty
        v-if="!dataLoading && !filtered.length"
        description="未找到模板，可新建或复制共享模板"
      /><el-row :gutter="16" class="template-grid"
        ><el-col
          v-for="product in visible"
          :key="product.id"
          :xs="24"
          :sm="12"
          :md="12"
          :lg="8"
          :xl="6"
          ><ListCard
            :product="product"
            :can-copy="isAdmin || user.roles.includes('owner')"
            :checked="selectedIds.includes(product.id)"
            @check="check"
            @preview="show"
            @select="select"
            @copy="openCopy"
            @edit="edit" /></el-col></el-row
      ><el-pagination
        v-model:current-page="pagination.current"
        v-model:page-size="pagination.pageSize"
        class="float-right"
        :total="filtered.length"
        :page-sizes="[12, 24, 36]"
        background
        layout="total,sizes,prev,pager,next,jumper"
      />
    </ModuleRegion>
    <RecordDetail v-model="preview" title="证书模板预览" :data="info"
      ><PreparedPreview
        v-if="selected?.latest_version"
        :version="selected.latest_version.id"
        style="height: 450px"
      /><el-space
        ><el-button type="primary" @click="selected && select(selected)"
          >选用模板</el-button
        ><el-button
          v-if="isAdmin || user.roles.includes('owner')"
          @click="selected && openCopy(selected)"
          >复制到我的模板库</el-button
        ></el-space
      ></RecordDetail
    >
    <el-dialog
      v-model="copyDialog"
      title="复制到我的模板库"
      width="480"
      :show-close="!saving"
      :close-on-click-modal="!saving"
      ><el-form label-position="top"
        ><el-form-item label="模板名称"
          ><el-input v-model.trim="form.name" /></el-form-item
        ><el-form-item label="维护部门"
          ><el-select
            :loading="dataLoading"
            v-model="form.department"
            style="width: 100%"
            ><el-option
              v-for="d in managed"
              :key="d.id"
              :label="d.name"
              :value="d.id" /></el-select></el-form-item></el-form
      ><template #footer
        ><el-button :disabled="saving" @click="copyDialog = false"
          >取消</el-button
        ><el-button
          type="primary"
          :loading="saving"
          :disabled="!form.name || !form.department"
          @click="copy"
          >复制并编辑</el-button
        ></template
      ></el-dialog
    >
  </div>
</template>
<style scoped>
.market-page {
  padding: 20px;
}
.toolbar {
  gap: 12px;
  flex-wrap: wrap;
}
.toolbar > div {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.template-grid > .el-col {
  display: flex;
  min-width: 0;
}
.toolbar :deep(.el-input) {
  max-width: 100%;
}
:deep(.el-pagination) {
  float: none;
}
:deep(.el-pagination) {
  margin: 20px 0;
}
</style>
