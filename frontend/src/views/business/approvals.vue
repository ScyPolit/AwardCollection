<script setup lang="ts">
import ModuleRegion from "@/components/ModuleRegion.vue";
import { useModuleTask } from "@/composables/useModuleTask";
const listTask = useModuleTask(),
  listLoading = listTask.loading,
  listError = listTask.error;

import { useLiveStore } from "@/store/modules/live";
import { watch } from "vue";
import { useRoute } from "vue-router";
const route = useRoute();
const live = useLiveStore();
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
const detailTask = useModuleTask(),
  detailLoading = detailTask.loading;
async function show(row: any) {
  detail.value = true;
  try {
    await detailTask.run(
      () => batchDetail(row.batch_id),
      data => {
        detailData.value = {
          批次: data.batch.name,
          竞赛: data.batch.competition_name,
          状态: data.batch.status,
          名单总数: data.award_count,
          当前显示: "前50条；完整名单请进入名单与批次分页查看",
          版本: data.batch.current_version,
          模板: data.configuration.template_name,
          输出格式: data.configuration.output_formats,
          获奖名单: data.awards,
          部门会签: data.approvals
        };
        previewBatch.value = row.batch_id;
        detail.value = true;
      }
    );
  } catch {}
}
function showRevocation(row: any) {
  detailLoading.value = false;
  detailTask.error.value = "";
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
  try {
    await listTask.run(async () => {
      [rows.value, revocations.value, departments.value] = await Promise.all([
        listApprovals(),
        listRevocations(),
        listDepartments()
      ]);
    });
  } catch {}
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
async function openLinked() {
  if (route.query.revocation) {
    tab.value = "revocation";
    const row = revocations.value.find(
      r => r.id === Number(route.query.revocation)
    );
    if (row) showRevocation(row);
    else ElMessage.info("该作废申请已处理或记录已删除");
    return;
  }
  if (route.query.batch) {
    const row = rows.value.find(r => r.batch_id === Number(route.query.batch));
    if (row) await show(row);
    else {
      try {
        const data = await batchDetail(Number(route.query.batch));
        await show({ batch_id: data.batch.id } as Approval);
        ElMessage.info("该批次已离开待审批阶段，已打开批次记录");
      } catch {
        ElMessage.info("记录已删除或当前账号无权查看");
      }
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
        <p>处理签发与作废的部门会签</p>
      </div>
      <el-button @click="load">刷新</el-button>
    </header>
    <el-tabs v-model="tab"
      ><el-tab-pane label="签发审批" name="issuance"
        ><ModuleRegion
          :loading="listLoading"
          :error="listError"
          :empty="!rows.length"
          @retry="load"
          ><el-table :data="rows" border
            ><el-table-column
              min-width="240"
              prop="competition_name"
              label="竞赛"
            /><el-table-column min-width="240" label="批次"
              ><template #default="s"
                ><el-button
                  link
                  type="primary"
                  @click="show(s.row as Approval)"
                  >{{ s.row.batch_name }}</el-button
                ></template
              ></el-table-column
            ><el-table-column
              prop="version_number"
              label="版本"
              width="80"
            /><el-table-column
              min-width="240"
              prop="department_name"
              label="审批部门"
            /><el-table-column label="决定" width="180"
              ><template #default="s"
                ><el-button link @click="show(s.row as Approval)"
                  >查看</el-button
                ><template v-if="!s.row.decision"
                  ><el-button
                    link
                    type="success"
                    @click="act(s.row as Approval, 'approved')"
                    >通过</el-button
                  ><el-button
                    link
                    type="danger"
                    @click="act(s.row as Approval, 'returned')"
                    >整批退回</el-button
                  ></template
                ><el-tag v-else>{{
                  s.row.decision === "approved" ? "已通过" : "已退回"
                }}</el-tag></template
              ></el-table-column
            ></el-table
          ></ModuleRegion
        ></el-tab-pane
      ><el-tab-pane label="作废审批" name="revocation"
        ><ModuleRegion
          :loading="listLoading"
          :error="listError"
          :empty="!rows.length"
          @retry="load"
          ><el-table :data="revocations" border
            ><el-table-column min-width="180" label="证书编号"
              ><template #default="s"
                ><el-button
                  link
                  type="primary"
                  @click="showRevocation(s.row)"
                  >{{ s.row.certificate_number }}</el-button
                ></template
              ></el-table-column
            ><el-table-column
              min-width="240"
              prop="reason"
              label="原因"
            /><el-table-column label="进度" width="100"
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
                ><el-button
                  link
                  type="success"
                  @click="revoke(s.row, 'approved')"
                  >同意</el-button
                ><el-button
                  link
                  type="danger"
                  @click="revoke(s.row, 'rejected')"
                  >驳回</el-button
                ></template
              ></el-table-column
            ></el-table
          ></ModuleRegion
        ></el-tab-pane
      ></el-tabs
    ><RecordDetail
      :loading="detailLoading"
      :error="detailTask.error.value"
      v-model="detail"
      title="审批信息详情"
      :data="detailData"
      readonly-reason="已提交名单和审批记录只读；发现问题请整批退回，由负责人修订后重新提交。"
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
