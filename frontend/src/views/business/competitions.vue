<script setup lang="ts">
import BulkActions from "@/components/BulkActions.vue";
const bulkTable = ref(),
  bulkSelection = ref<any[]>([]);
import ModuleRegion from "@/components/ModuleRegion.vue";
import { useModuleTask } from "@/composables/useModuleTask";
const listTask = useModuleTask(),
  listLoading = listTask.loading,
  listError = listTask.error;

import ManagementActions from "@/components/ManagementActions.vue";
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import RecordDetail from "@/components/RecordDetail.vue";
import { useBusinessAccess } from "@/utils/businessAccess";
import {
  updateCompetition,
  createCompetition,
  listCompetitions,
  listDepartments,
  listUsers,
  type Competition,
  type Option
} from "@/api/business";

const { isSuper, isAdmin, user } = useBusinessAccess();
const competitionRow = ref<Competition>();
const detail = ref(false),
  selected = ref<Record<string, unknown>>({}),
  changing = ref<number>();
function show(row: Competition) {
  competitionRow.value = row;
  selected.value = {
    竞赛名称: row.name,
    状态: row.active ? "启用" : "废止",
    拟盖章部门: row.department_names,
    协作负责人: row.collaborator_names,
    常用奖项: row.award_presets,
    创建人: row.created_by_name,
    创建时间: row.created_at
  };
  detail.value = true;
}
async function toggle(row: Competition) {
  try {
    await ElMessageBox.confirm(
      `确认${row.active ? "废止" : "启用"}“${row.name}”？已签发证书和历史记录将保留。`,
      "竞赛状态"
    );
    changing.value = row.id;
    await updateCompetition(row.id, { active: !row.active });
    ElMessage.success("竞赛状态已更新");
    await load();
  } catch {
  } finally {
    changing.value = undefined;
  }
}
const rows = ref<Competition[]>([]),
  departments = ref<Option[]>([]),
  users = ref<Option[]>([]),
  dialog = ref(false),
  saving = ref(false);
const form = reactive({
  name: "",
  award_presets: [] as string[],
  departments: [] as number[],
  collaborators: [] as number[]
});
async function load() {
  try {
    await listTask.run(async () => {
      [rows.value, departments.value, users.value] = await Promise.all([
        listCompetitions(),
        listDepartments(),
        listUsers()
      ]);
    });
  } catch {}
}
function openCreate() {
  Object.assign(form, {
    name: "",
    award_presets: [],
    departments: [],
    collaborators: []
  });
  dialog.value = true;
}
async function submit() {
  saving.value = true;
  try {
    await createCompetition(form);
    dialog.value = false;
    ElMessage.success("竞赛已创建并立即生效");
    await load();
  } catch {
  } finally {
    saving.value = false;
  }
}
onMounted(load);
</script>
<template>
  <div class="page business-page">
    <header>
      <div>
        <h2>竞赛管理</h2>
        <p>创建竞赛并配置协作负责人及拟盖章部门</p>
      </div>
      <el-button type="primary" @click="openCreate">新建竞赛</el-button>
    </header>
    <BulkActions
      :selected="bulkSelection"
      :can-delete="
        isSuper ||
        !isAdmin ||
        bulkSelection.every(r =>
          r.departments?.some(id => user.managedDepartmentIds.includes(id))
        )
      "
      :can-toggle="isSuper"
      resource="competitions"
      @clear="bulkTable?.clearSelection()"
      @changed="load"
    />
    <ModuleRegion
      :loading="listLoading"
      :error="listError"
      :empty="!rows.length"
      @retry="load"
      ><el-table
        ref="bulkTable"
        row-key="id"
        @selection-change="bulkSelection = $event"
        :data="rows"
        border
        @row-dblclick="row => show(row as Competition)"
        ><el-table-column type="selection" width="48" /><el-table-column
          label="竞赛名称"
          min-width="220"
          ><template #default="s"
            ><el-button
              link
              type="primary"
              @click="show(s.row as Competition)"
              >{{ s.row.name }}</el-button
            ></template
          ></el-table-column
        ><el-table-column label="拟盖章部门" min-width="220"
          ><template #default="s">{{
            s.row.department_names.join("、")
          }}</template></el-table-column
        ><el-table-column label="协作负责人" min-width="200"
          ><template #default="s">{{
            s.row.collaborator_names.join("、")
          }}</template></el-table-column
        ><el-table-column label="状态" width="90"
          ><template #default="s"
            ><el-tag :type="s.row.active ? 'success' : 'info'">{{
              s.row.active ? "启用" : "废止"
            }}</el-tag></template
          ></el-table-column
        ><el-table-column label="操作" width="290"
          ><template #default="s"
            ><el-button link @click="show(s.row as Competition)">查看</el-button
            ><ManagementActions
              :url="`/api/v1/competitions/${s.row.id}/`"
              :data="s.row"
              :name="s.row.name"
              :fields="[
                { key: 'name', label: '竞赛名称', required: true },
                { key: 'award_presets', label: '常用奖项', type: 'list' },
                {
                  key: 'collaborators',
                  label: '协作负责人',
                  type: 'list',
                  options: users.map(u => ({
                    label: u.label || u.username || '',
                    value: u.id
                  }))
                }
              ]"
              @changed="load"
            />
            ><el-button
              v-if="isSuper"
              link
              :type="s.row.active ? 'danger' : 'success'"
              :loading="changing === s.row.id"
              @click="toggle(s.row as Competition)"
              >{{ s.row.active ? "废止" : "启用" }}</el-button
            ></template
          ></el-table-column
        ></el-table
      ></ModuleRegion
    ><el-dialog
      v-model="dialog"
      title="新建竞赛"
      width="560"
      :close-on-click-modal="!saving"
      :show-close="!saving"
      ><el-form label-position="top"
        ><el-form-item label="竞赛名称" required
          ><el-input v-model="form.name" /></el-form-item
        ><el-form-item label="拟盖章部门" required
          ><el-select
            :loading="listLoading"
            v-model="form.departments"
            multiple
            class="full"
            ><el-option
              v-for="item in departments"
              :key="item.id"
              :label="item.name"
              :value="item.id" /></el-select></el-form-item
        ><el-form-item label="协作负责人"
          ><el-select
            :loading="listLoading"
            v-model="form.collaborators"
            multiple
            class="full"
            ><el-option
              v-for="item in users"
              :key="item.id"
              :label="item.label"
              :value="item.id" /></el-select></el-form-item
        ><el-form-item label="常用奖项"
          ><el-select
            :loading="listLoading"
            v-model="form.award_presets"
            multiple
            filterable
            allow-create
            class="full" /></el-form-item></el-form
      ><template #footer
        ><el-button :disabled="saving" @click="dialog = false">取消</el-button
        ><el-button
          type="primary"
          :loading="saving"
          :disabled="!form.name || !form.departments.length"
          @click="submit"
          >创建</el-button
        ></template
      ></el-dialog
    ><RecordDetail v-model="detail" title="竞赛详情" :data="selected"
      ><template #actions
        ><ManagementActions
          v-if="competitionRow"
          :url="`/api/v1/competitions/${competitionRow.id}/`"
          :data="competitionRow"
          :name="competitionRow.name"
          :fields="[
            { key: 'name', label: '竞赛名称', required: true },
            { key: 'award_presets', label: '常用奖项', type: 'list' },
            {
              key: 'collaborators',
              label: '协作负责人',
              type: 'list',
              options: users.map(u => ({
                label: u.label || u.username || '',
                value: u.id
              }))
            }
          ]"
          @changed="
            detail = false;
            load();
          "
        /><el-button
          v-if="isSuper && competitionRow"
          @click="toggle(competitionRow)"
          >{{ competitionRow.active ? "废止竞赛" : "启用竞赛" }}</el-button
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
  align-items: flex-start;
  margin-bottom: 18px;
}
h2 {
  margin: 0;
  font-size: 20px;
  letter-spacing: 0;
}
p {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
}
.full {
  width: 100%;
}
</style>
