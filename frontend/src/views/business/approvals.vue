<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import RecordDetail from "@/components/RecordDetail.vue";
import {
  batchDetail,
  decideApproval,
  decideRevocation,
  listApprovals,
  listDepartments,
  listRevocations,
  type Approval,
  type Option
} from "@/api/business";
const detail = ref(false),
  detailData = ref<Record<string, unknown>>({}),
  previewBatch = ref<number>();
async function show(row: Approval) {
  const data = await batchDetail(row.batch_id);
  detailData.value = {
    批次: data.batch.name,
    竞赛: data.batch.competition_name,
    状态: data.batch.status,
    版本: data.batch.current_version,
    模板: data.configuration.template_name,
    输出格式: data.configuration.output_formats,
    获奖名单: data.awards,
    部门会签: data.approvals
  };
  previewBatch.value = row.batch_id;
  detail.value = true;
}
function showRevocation(row: any) {
  detailData.value = {
    证书编号: row.certificate_number,
    作废原因: row.reason,
    状态: row.status,
    已批准部门: row.approved_departments,
    全部部门: row.total_departments,
    创建时间: row.created_at
  };
  previewBatch.value = undefined;
  detail.value = true;
}
const rows = ref<Approval[]>([]),
  revocations = ref<any[]>([]),
  departments = ref<Option[]>([]),
  tab = ref("issuance");
async function load() {
  [rows.value, revocations.value, departments.value] = await Promise.all([
    listApprovals(),
    listRevocations(),
    listDepartments()
  ]);
}
async function act(row: Approval, decision: string) {
  const { value } = await ElMessageBox.prompt(
    decision === "approved" ? "填写审批意见（可选）" : "填写退回原因",
    "审批决定",
    { inputType: "textarea", inputValue: "" }
  );
  await decideApproval(row.id, decision, value);
  ElMessage.success(decision === "approved" ? "已通过" : "已退回整批名单");
  await load();
}
async function revoke(row: any, decision: string) {
  if (!departments.value.length) return ElMessage.error("当前账号没有部门权限");
  const department =
    departments.value.length === 1
      ? departments.value[0].id
      : Number(
          (
            await ElMessageBox.prompt(
              `请选择本部门：${departments.value.map(d => `${d.name}(${d.id})`).join("、")}`,
              "作废审批",
              { inputValue: String(departments.value[0].id) }
            )
          ).value
        );
  await decideRevocation(row.id, department, decision);
  ElMessage.success(
    decision === "approved" ? "本部门已同意作废" : "作废申请已驳回"
  );
  await load();
}
onMounted(load);
</script>
<template>
  <div class="page business-page">
    <header>
      <div>
        <h2>会签待办</h2>
        <p>处理签发与作废的部门会签</p>
      </div>
      <el-button @click="load">刷新</el-button>
    </header>
    <el-tabs v-model="tab"
      ><el-tab-pane label="签发审批" name="issuance"
        ><el-table :data="rows" border
          ><el-table-column
            prop="competition_name"
            label="竞赛"
          /><el-table-column label="批次"
            ><template #default="s"
              ><el-button link type="primary" @click="show(s.row)">{{
                s.row.batch_name
              }}</el-button></template
            ></el-table-column
          ><el-table-column
            prop="version_number"
            label="版本"
            width="80"
          /><el-table-column
            prop="department_name"
            label="审批部门"
          /><el-table-column label="决定" width="180"
            ><template #default="s"
              ><el-button link @click="show(s.row)">查看</el-button
              ><template v-if="!s.row.decision"
                ><el-button link type="success" @click="act(s.row, 'approved')"
                  >通过</el-button
                ><el-button link type="danger" @click="act(s.row, 'returned')"
                  >整批退回</el-button
                ></template
              ><el-tag v-else>{{
                s.row.decision === "approved" ? "已通过" : "已退回"
              }}</el-tag></template
            ></el-table-column
          ></el-table
        ></el-tab-pane
      ><el-tab-pane label="作废审批" name="revocation"
        ><el-table :data="revocations" border
          ><el-table-column label="证书编号"
            ><template #default="s"
              ><el-button link type="primary" @click="showRevocation(s.row)">{{
                s.row.certificate_number
              }}</el-button></template
            ></el-table-column
          ><el-table-column prop="reason" label="原因" /><el-table-column
            label="进度"
            width="100"
            ><template #default="s"
              >{{ s.row.approved_departments }} /
              {{ s.row.total_departments }}</template
            ></el-table-column
          ><el-table-column
            prop="status"
            label="状态"
            width="100"
          /><el-table-column label="决定" width="160"
            ><template #default="s"
              ><el-button link type="success" @click="revoke(s.row, 'approved')"
                >同意</el-button
              ><el-button link type="danger" @click="revoke(s.row, 'rejected')"
                >驳回</el-button
              ></template
            ></el-table-column
          ></el-table
        ></el-tab-pane
      ></el-tabs
    ><RecordDetail v-model="detail" title="审批信息详情" :data="detailData"
      ><el-button
        v-if="previewBatch"
        tag="a"
        target="_blank"
        :href="`/api/v1/batches/${previewBatch}/preview/`"
        >查看证书样张</el-button
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
</style>
