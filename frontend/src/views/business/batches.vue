<script setup lang="ts">
import ManagementActions from "@/components/ManagementActions.vue";
import { useLiveStore } from "@/store/modules/live";
import { useBusinessAccess } from "@/utils/businessAccess";
import { http } from "@/utils/http";
const live = useLiveStore(),
  { isAdmin } = useBusinessAccess();
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import RecordDetail from "@/components/RecordDetail.vue";
import { ElMessage, type UploadFile } from "element-plus";
import {
  batchDetail,
  batchProgress,
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
  competitions = ref<Competition[]>([]),
  templates = ref<Template[]>([]),
  seals = ref<Seal[]>([]),
  createDialog = ref(false),
  drawer = ref(false),
  selected = ref<any>(null),
  uploading = ref(false);
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
}
async function deleteRow(row: any) {
  const { ElMessageBox } = await import("element-plus");
  await ElMessageBox.confirm("确认删除此获奖记录？", "删除名单行");
  await http.post(`/api/v1/batches/${selected.value.batch.id}/rows/`, {
    data: {
      operation: "delete",
      source_row: row.source_row,
      expected_version: selected.value.batch.current_version
    }
  });
  await open(selected.value.batch);
  await load();
}
watch(
  () => live.revision,
  async () => {
    await load();
    if (drawer.value && selected.value)
      selected.value = await batchDetail(selected.value.batch.id);
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
async function load() {
  [rows.value, competitions.value, templates.value, seals.value] =
    await Promise.all([
      listBatches(),
      listCompetitions(),
      listTemplates(),
      listSeals()
    ]);
}
watch(
  () => form.competition,
  () => {
    form.seal_versions = {};
    for (const id of competition.value?.departments || []) {
      const seal = seals.value.find(
        item => item.department === id && item.active && item.versions.length
      );
      if (seal) form.seal_versions[String(id)] = seal.versions.at(-1)!.id;
    }
  }
);
async function create() {
  await createBatch(form);
  createDialog.value = false;
  ElMessage.success("批次已按选定模板、公章和输出格式创建");
  await load();
}
async function open(row: Batch) {
  selected.value = await batchDetail(row.id);
  drawer.value = true;
}
async function upload(file: UploadFile) {
  if (!selected.value || !file.raw) return;
  uploading.value = true;
  try {
    await importAwards(
      selected.value.batch.id,
      file.raw,
      selected.value.batch.current_version
    );
    ElMessage.success("名单导入成功");
    selected.value = await batchDetail(selected.value.batch.id);
    await load();
  } finally {
    uploading.value = false;
  }
}
async function submit() {
  await submitBatch(selected.value.batch.id);
  ElMessage.success("已提交全部部门并行会签");
  selected.value = await batchDetail(selected.value.batch.id);
  await load();
}
async function retryGeneration(){await http.post(`/api/v1/batches/${selected.value.batch.id}/retry_generation/`,{data:{}});ElMessage.success("已重新加入生成队列")}
async function progress() {
  selected.value = await batchDetail(selected.value.batch.id);
  await load();
  const task = await batchProgress(selected.value.batch.id);
  if (!task) return ElMessage.info("尚未创建生成任务");
  awardData.value = {
    任务状态: task.status,
    已处理: task.processed,
    总数: task.total,
    尝试次数: task.attempts,
    错误详情: task.error || "无"
  };
  awardDetail.value = true;
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
    <el-table :data="rows" border @row-dblclick="row => open(row as Batch)"
      ><el-table-column min-width="240" label="批次"
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
      ><el-table-column
        prop="status"
        label="状态"
        width="110" /><el-table-column label="操作" width="230"
        ><template #default="s"
          ><el-button link type="primary" @click="open(s.row as Batch)"
            >查看</el-button
          ><ManagementActions
            :url="`/api/v1/batches/${s.row.id}/`"
            :data="s.row"
            :name="s.row.name"
            :fields="[{ key: 'name', label: '批次名称', required: true }]"
            @changed="load" /></template></el-table-column></el-table
    ><el-dialog v-model="createDialog" title="新建批次" width="600"
      ><el-form label-position="top"
        ><el-form-item label="批次名称"
          ><el-input v-model="form.name" /></el-form-item
        ><el-form-item label="竞赛"
          ><el-select v-model="form.competition" class="full"
            ><el-option
              v-for="c in competitions"
              :key="c.id"
              :label="c.name + (c.active ? '' : '（已废止）')"
              :value="c.id"
              :disabled="!c.active" /></el-select></el-form-item
        ><el-form-item label="证书模板"
          ><el-select v-model="form.template_version" class="full"
            ><el-option
              v-for="t in templates"
              :key="t.latest_version?.id"
              :label="`${t.name} · v${t.latest_version?.number}`"
              :value="t.latest_version?.id"
              :disabled="!t.latest_version" /></el-select></el-form-item
        ><el-form-item label="输出格式"
          ><el-checkbox-group v-model="form.output_formats"
            ><el-checkbox value="pdf">PDF</el-checkbox
            ><el-checkbox value="png">图片</el-checkbox></el-checkbox-group
          ></el-form-item
        ><el-form-item
          v-for="(name, index) in competition?.department_names || []"
          :key="competition!.departments[index]"
          :label="`${name}公章`"
          ><el-select
            v-model="
              form.seal_versions[String(competition!.departments[index])]
            "
            class="full"
            ><template v-for="seal in seals" :key="seal.id"
              ><el-option
                v-for="version in seal.versions"
                v-if="
                  seal.department === competition!.departments[index] &&
                  seal.active
                "
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
          >创建</el-button
        ></template
      ></el-dialog
    ><el-drawer
      v-model="drawer"
      title="批次详情"
      size="min(1100px, 96vw)"
      class="batch-detail"
      ><template v-if="selected"
        ><el-descriptions border :column="3"
          ><el-descriptions-item label="批次">{{
            selected.batch.name
          }}</el-descriptions-item
          ><el-descriptions-item label="状态">{{
            selected.batch.status
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
        <div v-if="job" class="generation-status">
          <strong
            >证书生成：{{
              job.status === "done"
                ? "已完成，可下载"
                : job.status === "failed"
                  ? "失败，请查看原因"
                  : job.status === "queued"
                    ? "排队中"
                    : "正在生成"
            }}</strong
          ><el-progress
            :percentage="job.percent"
            :status="
              job.status === 'done'
                ? 'success'
                : job.status === 'failed'
                  ? 'exception'
                  : undefined
            "
          /><span
            >{{ job.processed }} / {{ job.total }} 份 ·
            {{
              job.status === "done"
                ? "全部文件已发布"
                : job.eta_seconds
                  ? `预计还需 ${Math.ceil(job.eta_seconds / 60)} 分钟`
                  : "剩余时间估算中"
            }}（估算会随进度更新）</span
          ><el-alert
            v-if="job.error"
            :title="job.error"
            type="error"
            :closable="false"
          />
        </div>
        <div class="actions"><el-button v-if="job?.status==='failed'" type="warning" @click="retryGeneration">重试生成</el-button>
          <el-button
            v-if="['draft', 'returned'].includes(selected.batch.status)"
            @click="editRow()"
            >新增获奖记录</el-button
          >
          <el-upload
            :disabled="!['draft', 'returned'].includes(selected.batch.status)"
            :auto-upload="false"
            :show-file-list="false"
            accept=".xlsx"
            :on-change="upload"
            ><el-button :loading="uploading"
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
            :disabled="
              !selected.awards.length ||
              !['draft', 'returned'].includes(selected.batch.status)
            "
            @click="submit"
            >提交会签</el-button
          ><el-button @click="progress">任务进度</el-button
          ><el-button
            v-if="selected.batch.status === 'issued'"
            tag="a"
            :href="`/api/v1/certificates/batch/${selected.batch.id}/archive/`"
            type="success"
            >下载整批 ZIP</el-button
          >
        </div>
        <p>点击名单行可查看成员、作品与备注等完整信息</p>
        <el-table :data="selected.awards" border @row-click="showAward"
          ><el-table-column
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
              ><el-button link type="primary" @click.stop="editRow(s.row)"
                >修改</el-button
              ><el-button link type="danger" @click.stop="deleteRow(s.row)"
                >删除</el-button
              ></template
            ></el-table-column
          ></el-table
        ></template
      ></el-drawer
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
        ><el-button type="primary" @click="saveRow">保存</el-button></template
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
