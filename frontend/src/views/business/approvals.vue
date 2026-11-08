<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import ModuleRegion from "@/components/ModuleRegion.vue";
import BulkActions from "@/components/BulkActions.vue";
import ApprovalWorkspace from "@/components/ApprovalWorkspace.vue";
import RecordDetail from "@/components/RecordDetail.vue";
import { useModuleTask } from "@/composables/useModuleTask";
import { useLiveStore } from "@/store/modules/live";
import {
  batchDetail,
  bulkDecideApprovals,
  bulkDecideRevocations,
  decideRevocation,
  listApprovals,
  listRevocations,
  listSeals,
  type Approval,
  type Seal
} from "@/api/business";
const route = useRoute(),
  live = useLiveStore(),
  listTask = useModuleTask();
const rows = ref<Approval[]>([]),
  revocations = ref<any[]>([]),
  seals = ref<Seal[]>([]),
  tab = ref("issuance");
const table = ref(),
  selection = ref<Approval[]>([]),
  revokeTable = ref(),
  revokeSelection = ref<any[]>([]);
const detail = ref(false),
  batchId = ref<number>(),
  requirementId = ref<number>();
function show(row: { batch_id: number; id?: number }) {
  batchId.value = row.batch_id;
  requirementId.value = row.id;
  detail.value = true;
}
async function load() {
  try {
    await listTask.run(
      () => Promise.all([listApprovals(), listRevocations(), listSeals()]),
      values => {
        [rows.value, revocations.value, seals.value] = values;
      }
    );
  } catch {}
}
const bulkDialog = ref(false),
  bulkBusy = ref(false),
  bulkRows = ref<Approval[]>([]);
const bulkForm = reactive({
  decision: "approved",
  comment: "",
  seals: {} as Record<number, number | undefined>
});
function openBulk() {
  bulkRows.value = selection.value.filter(r => !r.decision);
  if (!bulkRows.value.length) return ElMessage.info("请选择尚未审批的记录");
  if (bulkRows.value.length > 50) return ElMessage.warning("单次最多审批50项");
  bulkForm.decision = "approved";
  bulkForm.comment = "";
  bulkForm.seals = Object.fromEntries(
    bulkRows.value.map(row => [row.id, row.seal_version || undefined])
  );
  bulkDialog.value = true;
}
function sealOptions(department: number) {
  return seals.value
    .filter(s => s.active && s.department === department)
    .flatMap(s =>
      s.versions.map(v => ({ id: v.id, label: `${s.name} · v${v.number}` }))
    );
}
async function submitBulk() {
  if (bulkBusy.value) return;
  if (
    bulkForm.decision === "approved" &&
    bulkRows.value.some(r => !bulkForm.seals[r.id])
  )
    return ElMessage.warning("请为每个审批部门选择公章");
  if (bulkForm.decision === "returned" && !bulkForm.comment.trim())
    return ElMessage.warning("请填写退回原因");
  try {
    await ElMessageBox.confirm(
      "确认处理所选记录？任一项权限或状态发生变化时整批不执行。",
      "确认批量审批"
    );
  } catch {
    return;
  }
  bulkBusy.value = true;
  try {
    const result = await bulkDecideApprovals({
      decision: bulkForm.decision,
      comment: bulkForm.comment,
      items: bulkRows.value.map(r => ({
        id: r.id,
        expected_seal_version: r.seal_version,
        ...(bulkForm.decision === "approved"
          ? { seal_version: bulkForm.seals[r.id] }
          : {})
      }))
    });
    ElMessage.success(`已处理 ${result.count} 项审批`);
    bulkDialog.value = false;
    table.value?.clearSelection();
    await load();
  } catch {
  } finally {
    bulkBusy.value = false;
  }
}
const revokeDialog = ref(false),
  revokeRows = ref<any[]>([]),
  revokeBusy = ref(false);
const revokeForm = reactive({
  department: undefined as number | undefined,
  decision: "approved",
  comment: ""
});
const revokeDepartments = computed(() =>
  (revokeRows.value[0]?.approval_departments || []).filter((d: any) =>
    revokeRows.value.every(r =>
      r.approval_departments?.some((own: any) => own.id === d.id)
    )
  )
);
function showRevocation(row?: any) {
  revokeRows.value = row ? [row] : [...revokeSelection.value];
  if (!revokeRows.value.length) return;
  if (revokeRows.value.length > 50)
    return ElMessage.warning("单次最多处理50项作废审批");
  revokeForm.department = revokeDepartments.value[0]?.id;
  revokeForm.decision = "approved";
  revokeForm.comment = "";
  revokeDialog.value = true;
}
async function revoke() {
  if (revokeBusy.value || !revokeForm.department)
    return ElMessage.warning("请选择所选记录共有的本部门");
  if (revokeForm.decision === "rejected" && !revokeForm.comment.trim())
    return ElMessage.warning("请填写驳回原因");
  try {
    await ElMessageBox.confirm(
      "确认提交本部门的作废审批决定？",
      "确认作废审批"
    );
  } catch {
    return;
  }
  revokeBusy.value = true;
  try {
    if (revokeRows.value.length === 1)
      await decideRevocation(
        revokeRows.value[0].id,
        revokeForm.department,
        revokeForm.decision,
        revokeForm.comment
      );
    else
      await bulkDecideRevocations({
        ids: revokeRows.value.map(r => r.id),
        ...revokeForm
      });
    ElMessage.success("作废审批已保存");
    revokeDialog.value = false;
    revokeTable.value?.clearSelection();
    await load();
  } catch {
  } finally {
    revokeBusy.value = false;
  }
}
async function openLinked() {
  if (route.query.revocation) {
    tab.value = "revocation";
    const row = revocations.value.find(
      r => r.id === Number(route.query.revocation)
    );
    if (row) showRevocation(row);
    else ElMessage.info("该作废申请已处理或记录已删除");
  } else if (route.query.batch) {
    const row = rows.value.find(r => r.batch_id === Number(route.query.batch));
    if (row) show(row);
    else
      try {
        const data = await batchDetail(Number(route.query.batch));
        show({ batch_id: data.batch.id });
      } catch {
        ElMessage.info("记录不存在或无权查看");
      }
  }
}
watch(
  () => [route.query.batch, route.query.revocation, route.query.notice],
  async () => {
    await load();
    await openLinked();
  }
);
watch(() => live.revision, load);
onMounted(async () => {
  await load();
  await openLinked();
});
</script>
<template>
  <div class="page business-page">
    <header>
      <div>
        <h2>会签待办</h2>
        <p>在审批详情中确认用章、预览证书并填写审批表单</p>
      </div>
      <el-button @click="load">刷新</el-button>
    </header>
    <el-tabs v-model="tab">
      <el-tab-pane label="签发审批" name="issuance">
        <BulkActions
          :selected="selection"
          readonly-reason="审批记录保留，不提供删除；可批量填写审批决定。"
          @clear="table?.clearSelection()"
          ><el-button
            type="primary"
            :disabled="!selection.length"
            @click="openBulk"
            >批量审批</el-button
          ></BulkActions
        >
        <ModuleRegion
          :loading="listTask.loading.value"
          :error="listTask.error.value"
          :empty="!rows.length"
          @retry="load"
        >
          <el-table
            ref="table"
            :data="rows"
            row-key="id"
            border
            @selection-change="selection = $event"
            @row-dblclick="show"
          >
            <el-table-column
              type="selection"
              width="48"
              :selectable="row => !row.decision"
            />
            <el-table-column
              min-width="200"
              prop="competition_name"
              label="竞赛"
            />
            <el-table-column min-width="220" label="批次"
              ><template #default="s"
                ><el-button
                  link
                  type="primary"
                  @click="show(s.row as Approval)"
                  >{{ s.row.batch_name }}</el-button
                ></template
              ></el-table-column
            >
            <el-table-column prop="version_number" label="版本" width="75" />
            <el-table-column
              min-width="180"
              prop="department_name"
              label="审批部门"
            />
            <el-table-column
              min-width="160"
              prop="seal_label"
              label="用章状态"
            />
            <el-table-column label="操作" width="150"
              ><template #default="s"
                ><el-button
                  link
                  type="primary"
                  @click="show(s.row as Approval)"
                  >{{ s.row.decision ? "查看记录" : "查看并审批" }}</el-button
                ><el-tag v-if="s.row.decision" size="small"
                  >已处理</el-tag
                ></template
              ></el-table-column
            >
          </el-table>
        </ModuleRegion>
      </el-tab-pane>
      <el-tab-pane label="作废审批" name="revocation">
        <BulkActions
          :selected="revokeSelection"
          readonly-reason="作废申请保留审批历史，不提供删除。"
          @clear="revokeTable?.clearSelection()"
          ><el-button
            type="primary"
            :disabled="!revokeSelection.length"
            @click="showRevocation()"
            >批量作废审批</el-button
          ></BulkActions
        >
        <ModuleRegion
          :loading="listTask.loading.value"
          :error="listTask.error.value"
          :empty="!revocations.length"
          @retry="load"
        >
          <el-table
            ref="revokeTable"
            :data="revocations"
            row-key="id"
            border
            @selection-change="revokeSelection = $event"
            @row-dblclick="showRevocation"
          >
            <el-table-column
              type="selection"
              width="48"
              :selectable="row => row.status === 'review'"
            />
            <el-table-column min-width="190" label="证书编号"
              ><template #default="s"
                ><el-button
                  link
                  type="primary"
                  @click="showRevocation(s.row)"
                  >{{ s.row.certificate_number }}</el-button
                ></template
              ></el-table-column
            >
            <el-table-column
              prop="reason"
              label="原因"
              min-width="250"
            /><el-table-column label="进度" width="100"
              ><template #default="s"
                >{{ s.row.approved_departments }} /
                {{ s.row.total_departments }}</template
              ></el-table-column
            ><el-table-column prop="status" label="状态" width="100" />
            <el-table-column label="操作" width="130"
              ><template #default="s"
                ><el-button link type="primary" @click="showRevocation(s.row)"
                  >查看并审批</el-button
                ></template
              ></el-table-column
            >
          </el-table>
        </ModuleRegion>
      </el-tab-pane>
    </el-tabs>
    <ApprovalWorkspace
      v-model="detail"
      :batch-id="batchId"
      :requirement-id="requirementId"
      @changed="load"
    />
    <el-dialog
      v-model="bulkDialog"
      title="批量签发审批"
      width="min(800px, 96vw)"
      :close-on-click-modal="!bulkBusy"
    >
      <el-alert
        title="每个部门单独确认本部门公章；退回操作对同一批次只执行一次。任一项失败时本次批量操作全部撤回。"
        :closable="false"
      />
      <el-form label-position="top"
        ><el-form-item label="决定"
          ><el-radio-group v-model="bulkForm.decision"
            ><el-radio value="approved">通过</el-radio
            ><el-radio value="returned">整批退回</el-radio></el-radio-group
          ></el-form-item
        >
        <el-table :data="bulkRows" border
          ><el-table-column
            prop="batch_name"
            label="批次"
            min-width="180"
          /><el-table-column
            prop="department_name"
            label="部门"
            min-width="150"
          /><el-table-column label="公章版本" min-width="240"
            ><template #default="s"
              ><el-select
                v-if="bulkForm.decision === 'approved'"
                v-model="bulkForm.seals[s.row.id]"
                filterable
                placeholder="选择本部门公章"
                ><el-option
                  v-for="v in sealOptions(s.row.department)"
                  :key="v.id"
                  :label="v.label"
                  :value="v.id" /></el-select
              ><span v-else>退回不需要选择公章</span></template
            ></el-table-column
          ></el-table
        >
        <el-form-item
          label="统一审批意见 / 退回原因"
          :required="bulkForm.decision === 'returned'"
          ><el-input
            v-model="bulkForm.comment"
            type="textarea"
            :rows="4"
            maxlength="4000"
            show-word-limit /></el-form-item
      ></el-form>
      <template #footer
        ><el-button :disabled="bulkBusy" @click="bulkDialog = false"
          >取消</el-button
        ><el-button type="primary" :loading="bulkBusy" @click="submitBulk"
          >确认批量审批</el-button
        ></template
      >
    </el-dialog>
    <el-dialog
      v-model="revokeDialog"
      title="作废审批详情"
      width="min(800px, 96vw)"
      :close-on-click-modal="!revokeBusy"
    >
      <el-table :data="revokeRows" border
        ><el-table-column
          prop="certificate_number"
          label="证书编号"
          min-width="200" /><el-table-column
          prop="reason"
          label="申请原因"
          min-width="240"
      /></el-table>
      <el-form label-position="top"
        ><el-form-item label="代表部门" required
          ><el-select
            v-model="revokeForm.department"
            placeholder="选择所选记录共有的本部门"
            ><el-option
              v-for="d in revokeDepartments"
              :key="d.id"
              :label="d.name"
              :value="d.id" /></el-select></el-form-item
        ><el-form-item label="审批决定"
          ><el-radio-group v-model="revokeForm.decision"
            ><el-radio value="approved">同意作废</el-radio
            ><el-radio value="rejected">驳回申请</el-radio></el-radio-group
          ></el-form-item
        ><el-form-item
          label="审批意见"
          :required="revokeForm.decision === 'rejected'"
          ><el-input
            v-model="revokeForm.comment"
            type="textarea"
            maxlength="4000"
            :rows="4" /></el-form-item
      ></el-form>
      <template #footer
        ><el-button :disabled="revokeBusy" @click="revokeDialog = false"
          >关闭</el-button
        ><el-button
          type="primary"
          :loading="revokeBusy"
          :disabled="
            !revokeForm.department ||
            revokeRows.some(r => r.status !== 'review')
          "
          @click="revoke"
          >提交审批</el-button
        ></template
      >
    </el-dialog>
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
  gap: 14px;
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
.el-form {
  margin-top: 18px;
}
.el-select {
  width: 100%;
}
@media (max-width: 700px) {
  header {
    flex-direction: column;
  }
}
</style>
