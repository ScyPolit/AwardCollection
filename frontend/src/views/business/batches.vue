<script setup lang="ts">
import ModuleRegion from "@/components/ModuleRegion.vue";
import BulkActions from "@/components/BulkActions.vue";
import { useModuleTask } from "@/composables/useModuleTask";
const listTask = useModuleTask(),
  listLoading = listTask.loading,
  listError = listTask.error;

import BatchWorkflow from "@/components/BatchWorkflow.vue";
import { statusLabel } from "@/utils/display";
import ManagementActions from "@/components/ManagementActions.vue";
import { useLiveStore } from "@/store/modules/live";
import { useBusinessAccess } from "@/utils/businessAccess";
import { http } from "@/utils/http";
const live = useLiveStore(),
  { isAdmin, isSuper, user } = useBusinessAccess();
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import RecordDetail from "@/components/RecordDetail.vue";
import { ElMessage, type UploadFile } from "element-plus";
import {
  batchDetail,
  createBatch,
  importAwards,
  listBatches,
  listCompetitions,
  listSeals,
  listTemplates,
  submitBatch,
  type Batch,
  type Competition,
  type Seal,
  type Template
} from "@/api/business";

const route = useRoute(),
  awardDetail = ref(false),
  awardData = ref<Record<string, unknown>>({});
function showAward(row: any) {
  awardData.value = {
    来源行: row.source_row,
    团队名称: row.team_name,
    团队成员: row.members,
    奖项: row.award_name,
    作品名称: row.work_name,
    项目类别: row.category,
    指导教师: row.teachers,
    备注: row.note
  };
  awardDetail.value = true;
}
const rows = ref<Batch[]>([]),
  table = ref(),
  selection = ref<any[]>([]),
  awardTable = ref(),
  awardSelection = ref<any[]>([]),
  competitions = ref<Competition[]>([]),
  templates = ref<Template[]>([]),
  seals = ref<Seal[]>([]),
  createDialog = ref(false),
  drawer = ref(false),
  selected = ref<any>(null),
  uploading = ref(false),
  actionBusy = ref(false);
const canEditRoster = computed(
  () =>
    !!selected.value?.can_manage &&
    ["draft", "returned"].includes(selected.value.batch.status) &&
    !uploading.value &&
    !actionBusy.value
);
const job = computed(() =>
  selected.value
    ? live.jobs.find(j => j.batch_id === selected.value.batch.id)
    : undefined
);
const rowDialog = ref(false),
  rowSource = ref<number>();
const rowForm = reactive({
  members: "",
  teachers: "",
  award_name: "",
  team_name: "",
  work_name: "",
  category: "",
  note: ""
});
function editRow(row?: any) {
  if (!canEditRoster.value) return;
  rowSource.value = row?.source_row;
  Object.assign(rowForm, {
    members: row?.members?.join("、") || "",
    teachers: row?.teachers?.join("、") || "",
    award_name: row?.award_name || "",
    team_name: row?.team_name || "",
    work_name: row?.work_name || "",
    category: row?.category || "",
    note: row?.note || ""
  });
  rowDialog.value = true;
}
async function saveRow() {
  if (!canEditRoster.value) return;
  actionBusy.value = true;
  try {
    await http.post(`/api/v1/batches/${selected.value.batch.id}/rows/`, {
      data: {
        operation: rowSource.value ? "update" : "create",
        source_row: rowSource.value,
        expected_version: selected.value.batch.current_version,
        row: {
          ...rowForm,
          members: rowForm.members
            .split(/[、，,\n]/)
            .map(s => s.trim())
            .filter(Boolean),
          teachers: rowForm.teachers
            .split(/[、，,\n]/)
            .map(s => s.trim())
            .filter(Boolean)
        }
      }
    });
    rowDialog.value = false;
    await open(selected.value.batch);
    await load();
  } finally {
    actionBusy.value = false;
  }
}
async function deleteRow(row: any) {
  if (!canEditRoster.value) return;
  const { ElMessageBox } = await import("element-plus");
  try {
    await ElMessageBox.confirm("确认删除此获奖记录？", "删除名单行");
  } catch {
    return;
  }
  if (!canEditRoster.value) return;
  actionBusy.value = true;
  try {
    await http.post(`/api/v1/batches/${selected.value.batch.id}/rows/`, {
      data: {
        operation: "delete",
        source_row: row.source_row,
        expected_version: selected.value.batch.current_version
      }
    });
    await open(selected.value.batch);
    await load();
  } finally {
    actionBusy.value = false;
  }
}
async function deleteAwardSelection() {
  const { ElMessageBox } = await import("element-plus");
  try {
    await ElMessageBox.confirm(
      `确认删除所选 ${awardSelection.value.length} 行？名单会创建新版本。`,
      "批量删除名单"
    );
  } catch {
    return;
  }
  actionBusy.value = true;
  try {
    await http.post(`/api/v1/batches/${selected.value.batch.id}/rows/`, {
      data: {
        operation: "bulk_delete",
        source_rows: awardSelection.value.map(r => r.source_row),
        expected_version: selected.value.batch.current_version
      }
    });
    awardTable.value?.clearSelection();
    await open(selected.value.batch);
    await load();
  } finally {
    actionBusy.value = false;
  }
}
watch(
  () => live.revision,
  async () => {
    await load();
    if (drawer.value && selected.value && !detailLoading.value)
      await changeAwardPage(awardPage.value);
  }
);
watch(
  () => [route.query.batch, route.query.notice],
  async () => {
    const id = route.query.batch;
    if (id) {
      await load();
      const row = rows.value.find(r => r.id === Number(id));
      if (row) await open(row);
      else ElMessage.info("该批次已删除或当前账号无权查看");
    }
  }
);
const form = reactive({
  name: "",
  competition: undefined as number | undefined,
  template_version: undefined as number | undefined,
  output_formats: ["pdf", "png"],
  seal_versions: {} as Record<string, number>
});
const competition = computed(() =>
  competitions.value.find(item => item.id === form.competition)
);
const managedSealDepartments = computed(() =>
  (competition.value?.departments || []).filter(
    id => isSuper.value || user.value.managedDepartmentIds.includes(id)
  )
);
async function load() {
  try {
    await listTask.run(
      () =>
        Promise.all([
          listBatches(),
          listCompetitions(),
          listTemplates(),
          isAdmin.value ? listSeals() : Promise.resolve([])
        ]),
      values => {
        [rows.value, competitions.value, templates.value, seals.value] = values;
      }
    );
  } catch {}
}
watch(
  () => form.competition,
  () => {
    form.seal_versions = {};
  }
);
async function create() {
  actionBusy.value = true;
  try {
    await createBatch({
      ...form,
      seal_versions: isAdmin.value
        ? Object.fromEntries(
            Object.entries(form.seal_versions).filter(
              ([, id]) => Number.isInteger(id) && id > 0
            )
          )
        : undefined
    });
    createDialog.value = false;
    ElMessage.success("批次已创建，各部门管理员将在审批时确认用章");
    await load();
  } finally {
    actionBusy.value = false;
  }
}
const detailTask = useModuleTask(),
  detailLoading = detailTask.loading,
  awardPage = ref(1);
async function open(row: Batch) {
  drawer.value = true;
  selected.value = null;
  awardPage.value = 1;
  try {
    await detailTask.run(
      () => batchDetail(row.id),
      value => (selected.value = value)
    );
  } catch {}
}
async function changeAwardPage(page: number) {
  if (!selected.value) return;
  const id = selected.value.batch.id;
  try {
    await detailTask.run(
      () => batchDetail(id, page),
      value => (selected.value = value)
    );
  } catch {}
}
async function upload(file: UploadFile) {
  if (!selected.value || !file.raw || !canEditRoster.value) return;
  uploading.value = true;
  try {
    await importAwards(
      selected.value.batch.id,
      file.raw,
      selected.value.batch.current_version
    );
    ElMessage.success("名单导入成功");
    selected.value = await batchDetail(
      selected.value.batch.id,
      awardPage.value
    );
    await load();
  } finally {
    uploading.value = false;
  }
}
async function submit() {
  if (!canEditRoster.value) return;
  actionBusy.value = true;
  try {
    await submitBatch(
      selected.value.batch.id,
      selected.value.batch.current_version
    );
    selected.value.batch.status = "review";
    ElMessage.success("已提交全部部门并行会签");
    selected.value = await batchDetail(
      selected.value.batch.id,
      awardPage.value
    );
    await load();
  } finally {
    actionBusy.value = false;
  }
}
async function retryGeneration() {
  await http.post(
    `/api/v1/batches/${selected.value.batch.id}/retry_generation/`,
    { data: {} }
  );
  ElMessage.success("已重新加入生成队列");
}
async function progress() {
  selected.value = await batchDetail(selected.value.batch.id, awardPage.value);
  await load();
}

onMounted(async () => {
  await load();
  if (route.query.batch) {
    const row = rows.value.find(r => r.id === Number(route.query.batch));
    if (row) await open(row);
  }
  if (route.query.template) {
    form.template_version = Number(route.query.template);
    createDialog.value = true;
  }
});
</script>
<template>
  <div class="page business-page">
    <header>
      <div>
        <h2>名单与批次</h2>
        <p>导入获奖名单、核对版本并提交会签</p>
      </div>
      <div>
        <el-button tag="a" href="/api/v1/excel/template/"
          >下载 Excel 模板</el-button
        ><el-button type="primary" @click="createDialog = true"
          >新建批次</el-button
        >
      </div>
    </header>
    <BulkActions
      :selected="selection"
      resource="batches"
      can-delete
      @clear="table?.clearSelection()"
      @changed="load"
    />
    <ModuleRegion
      :loading="listLoading"
      :error="listError"
      :empty="!rows.length"
      @retry="load"
      ><el-table
        ref="table"
        row-key="id"
        :data="rows"
        border
        @selection-change="selection = $event"
        @row-dblclick="row => open(row as Batch)"
        ><el-table-column type="selection" width="48" /><el-table-column
          min-width="240"
          label="批次"
          ><template #default="s"
            ><el-button link type="primary" @click="open(s.row as Batch)">{{
              s.row.name
            }}</el-button></template
          ></el-table-column
        ><el-table-column
          min-width="240"
          prop="competition_name"
          label="竞赛" /><el-table-column
          prop="team_count"
          label="团队"
          width="80" /><el-table-column
          prop="current_version"
          label="版本"
          width="80" /><el-table-column label="审批" width="100"
          ><template #default="s"
            >{{ s.row.approval_summary.approved }} /
            {{ s.row.approval_summary.total }}</template
          ></el-table-column
        ><el-table-column prop="status" label="状态" width="110"
          ><template #default="s">{{
            statusLabel(s.row.status)
          }}</template></el-table-column
        ><el-table-column label="操作" width="230"
          ><template #default="s"
            ><el-button link type="primary" @click="open(s.row as Batch)"
              >查看</el-button
            ><ManagementActions
              :url="`/api/v1/batches/${s.row.id}/`"
              :data="s.row"
              :name="s.row.name"
              :fields="[{ key: 'name', label: '批次名称', required: true }]"
              @changed="
                load
              " /></template></el-table-column></el-table></ModuleRegion
    ><el-dialog v-model="createDialog" title="新建批次" width="600"
      ><el-form label-position="top"
        ><el-form-item label="批次名称"
          ><el-input v-model="form.name" /></el-form-item
        ><el-form-item label="竞赛"
          ><el-select
            :loading="listLoading"
            v-model="form.competition"
            class="full"
            ><el-option
              v-for="c in competitions"
              :key="c.id"
              :label="c.name + (c.active ? '' : '（已废止）')"
              :value="c.id"
              :disabled="!c.active" /></el-select></el-form-item
        ><el-form-item label="证书模板"
          ><el-select
            :loading="listLoading"
            v-model="form.template_version"
            class="full"
            ><el-option
              v-for="t in templates"
              :key="t.latest_version?.id"
              :label="t.name"
              :value="t.latest_version?.id"
              :disabled="!t.latest_version" /></el-select></el-form-item
        ><el-form-item label="输出格式"
          ><el-checkbox-group v-model="form.output_formats"
            ><el-checkbox value="pdf">PDF</el-checkbox
            ><el-checkbox value="png">图片</el-checkbox></el-checkbox-group
          ></el-form-item
        ><el-alert
          title="各盖章部门由本部门管理员在审批详情中选择并确认公章。负责人提交名单即可。"
          :closable="false" />
        <el-form-item
          v-for="departmentId in isAdmin ? managedSealDepartments : []"
          :key="departmentId"
          :label="`${competition!.department_names[competition!.departments.indexOf(departmentId)]}公章（可在审批时选择）`"
          ><el-select
            :loading="listLoading"
            v-model="form.seal_versions[String(departmentId)]"
            class="full"
            clearable
            placeholder="暂不选择，审批时由管理员确认"
            ><template v-for="seal in seals" :key="seal.id"
              ><el-option
                v-for="version in seal.versions"
                v-if="seal.department === departmentId && seal.active"
                :key="version.id"
                :label="`${seal.name} · v${version.number}`"
                :value="
                  version.id
                " /></template></el-select></el-form-item></el-form
      ><template #footer
        ><el-button @click="createDialog = false">取消</el-button
        ><el-button
          type="primary"
          :disabled="
            !form.name ||
            !form.competition ||
            !form.template_version ||
            !form.output_formats.length
          "
          @click="create"
          :loading="actionBusy"
          >创建</el-button
        ></template
      ></el-dialog
    ><el-drawer
      v-model="drawer"
      title="批次详情"
      size="min(1100px, 96vw)"
      class="batch-detail"
      ><el-alert
        v-if="detailTask.error.value"
        :title="detailTask.error.value"
        type="error"
        :closable="false" /><el-skeleton
        v-if="detailLoading && !selected"
        :rows="8"
        animated /><template v-if="selected"
        ><el-descriptions border :column="3"
          ><el-descriptions-item label="批次">{{
            selected.batch.name
          }}</el-descriptions-item
          ><el-descriptions-item label="状态">{{
            statusLabel(selected.batch.status)
          }}</el-descriptions-item
          ><el-descriptions-item label="版本"
            >v{{ selected.batch.current_version }}</el-descriptions-item
          ><el-descriptions-item label="模板">{{
            selected.configuration.template_name
          }}</el-descriptions-item
          ><el-descriptions-item label="输出">{{
            selected.configuration.output_formats.join(" + ").toUpperCase()
          }}</el-descriptions-item></el-descriptions
        >
        <BatchWorkflow
          :batch="selected.batch"
          :job="job"
          :approvals="selected.approvals"
          :submitting="actionBusy" />
        <div class="actions">
          <el-button
            v-if="job?.status === 'failed'"
            type="warning"
            @click="retryGeneration"
            >重试生成</el-button
          >
          <el-button
            v-if="selected.can_manage"
            :disabled="!canEditRoster"
            @click="editRow()"
            >新增获奖记录</el-button
          >
          <el-upload
            :disabled="!canEditRoster"
            :auto-upload="false"
            :show-file-list="false"
            accept=".xlsx"
            :on-change="upload"
            ><el-button :disabled="!canEditRoster" :loading="uploading"
              >导入 / 修订 Excel</el-button
            ></el-upload
          ><el-button
            tag="a"
            target="_blank"
            :href="`/api/v1/batches/${selected.batch.id}/preview/`"
            :disabled="!selected.awards.length"
            >预览首条名单</el-button
          ><el-button
            type="primary"
            :disabled="!selected.awards.length || !canEditRoster"
            @click="submit"
            :loading="actionBusy"
            >提交会签</el-button
          ><el-button @click="progress">刷新进度</el-button>
        </div>

        <p>共 {{ selected.award_count }} 条，点击名单行可查看完整信息</p>
        <BulkActions
          :selected="awardSelection"
          readonly-reason="已提交和签发的名单保留历史，退回或草稿可批量删除。"
          @clear="awardTable?.clearSelection()"
        >
          <el-button
            v-if="
              selected.can_manage &&
              ['draft', 'returned'].includes(selected.batch.status)
            "
            type="danger"
            plain
            :disabled="
              !canEditRoster ||
              !awardSelection.length ||
              awardSelection.length > 200
            "
            :loading="actionBusy"
            @click="deleteAwardSelection"
            >批量删除名单</el-button
          >
        </BulkActions>
        <ModuleRegion :loading="detailLoading"
          ><el-table
            ref="awardTable"
            row-key="source_row"
            :data="selected.awards"
            border
            @selection-change="awardSelection = $event"
            @row-dblclick="showAward"
            ><el-table-column type="selection" width="48" /><el-table-column
              prop="source_row"
              label="行"
              width="60"
            /><el-table-column label="团队成员" min-width="180"
              ><template #default="s">{{
                s.row.members.join("、")
              }}</template></el-table-column
            ><el-table-column
              min-width="140"
              prop="award_name"
              label="奖项"
            /><el-table-column
              min-width="180"
              prop="team_name"
              label="团队"
            /><el-table-column
              prop="work_name"
              label="作品"
              min-width="200"
            /><el-table-column
              v-if="['draft', 'returned'].includes(selected.batch.status)"
              label="操作"
              width="150"
              ><template #default="s"
                ><el-button
                  link
                  type="primary"
                  :disabled="!canEditRoster"
                  @click.stop="editRow(s.row)"
                  >修改</el-button
                ><el-button
                  link
                  type="danger"
                  :disabled="!canEditRoster"
                  @click.stop="deleteRow(s.row)"
                  >删除</el-button
                ></template
              ></el-table-column
            ></el-table
          ></ModuleRegion
        ><el-pagination
          v-model:current-page="awardPage"
          :total="selected.award_count"
          :page-size="50"
          layout="total,prev,pager,next"
          @current-change="changeAwardPage" /></template></el-drawer
    ><el-dialog
      v-model="rowDialog"
      :title="rowSource ? '修改获奖记录' : '新增获奖记录'"
      width="540px"
      append-to-body
      ><el-form label-position="top"
        ><el-form-item
          v-for="field in [
            { key: 'members', label: '团队成员（用顿号分隔）' },
            { key: 'award_name', label: '奖项' },
            { key: 'team_name', label: '团队名称' },
            { key: 'work_name', label: '作品名称' },
            { key: 'category', label: '项目类别' },
            { key: 'teachers', label: '指导教师（用顿号分隔）' },
            { key: 'note', label: '备注' }
          ]"
          :key="field.key"
          :label="field.label"
          ><el-input v-model="rowForm[field.key]" /></el-form-item></el-form
      ><template #footer
        ><el-button @click="rowDialog = false">取消</el-button
        ><el-button type="primary" :disabled="!canEditRoster" @click="saveRow"
          >保存</el-button
        ></template
      ></el-dialog
    ><RecordDetail
      v-model="awardDetail"
      title="记录与任务详情"
      :data="awardData"
    />
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
.generation-status {
  margin-top: 18px;
  padding: 16px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}
.actions {
  flex-wrap: wrap;
  display: flex;
  gap: 10px;
  margin: 18px 0;
}
</style>
