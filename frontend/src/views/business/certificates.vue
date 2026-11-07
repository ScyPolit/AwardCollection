<script setup lang="ts">
import SmartImage from "@/components/SmartImage.vue";
import ModuleRegion from "@/components/ModuleRegion.vue";
import { useModuleTask } from "@/composables/useModuleTask";
const listTask = useModuleTask(),
  listLoading = listTask.loading,
  listError = listTask.error;

import ManagementActions from "@/components/ManagementActions.vue";
import { useBusinessAccess } from "@/utils/businessAccess";
import { useRouter } from "vue-router";
const router = useRouter();
import { http } from "@/utils/http";
const { isAdmin } = useBusinessAccess();
import { onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import RecordDetail from "@/components/RecordDetail.vue";
import {
  certificateDetail,
  listCertificates,
  revokeCertificate,
  type Certificate
} from "@/api/business";

const drawer = ref(false),
  selected = ref<any>(null),
  details = ref<Record<string, unknown>>({});
const detailTask = useModuleTask(),
  detailLoading = detailTask.loading;
async function show(row: any) {
  drawer.value = true;
  try {
    await detailTask.run(
      () => certificateDetail(row.id),
      c => {
        selected.value = c;
        details.value = {
          证书编号: c.number,
          状态: c.status,
          竞赛: c.competition_name,
          批次: c.batch_name,
          团队: c.team_name,
          成员: c.members,
          奖项: c.award_name,
          作品: c.work_name,
          项目类别: c.category,
          指导教师: c.teachers,
          备注: c.note,
          管理备注: c.notes,
          盖章部门: c.departments,
          模板: c.template,
          模板版本: c.template_version,
          签发时间: c.published_at,
          PDF摘要: c.pdf_sha256
        };
        drawer.value = true;
      }
    );
  } catch {}
}
const rows = ref<Certificate[]>([]),
  total = ref(0),
  page = ref(1),
  pageSize = ref(20),
  search = ref("");
async function load() {
  try {
    await listTask.run(
      () => listCertificates(page.value, pageSize.value, search.value),
      data => {
        rows.value = data.results;
        total.value = data.count;
      }
    );
  } catch {}
}
async function revoke(row: Certificate) {
  const { value } = await ElMessageBox.prompt("填写作废原因", "申请作废", {
    inputType: "textarea",
    inputValidator: v => !!v || "必须填写原因"
  });
  await revokeCertificate(row.id, value);
  ElMessage.success("作废申请已提交，审批期间证书继续有效");
  await load();
}
async function correct(row: Certificate) {
  await ElMessageBox.confirm(
    "将以此证书数据创建新的待审批批次；原证书保持原状。",
    "更正重发"
  );
  const data = await http.post<any, object>(
    `/api/v1/certificates/${row.id}/correction/`,
    { data: {} }
  );
  ElMessage.success("更正批次已创建，请修改后提交审批");
  router.push({ path: "/business/batches", query: { batch: data.batch } });
}
function searchNow() {
  page.value = 1;
  load();
}
onMounted(load);
</script>
<template>
  <div class="page business-page">
    <header>
      <div>
        <h2>证书档案</h2>
        <p>下载签名 PDF、图片或申请作废</p>
      </div>
      <div class="search">
        <el-input
          v-model="search"
          clearable
          placeholder="编号、团队或竞赛"
          @keyup.enter="searchNow"
        /><el-button @click="searchNow">查询</el-button>
      </div>
    </header>
    <ModuleRegion
      :loading="listLoading"
      :error="listError"
      :empty="!rows.length"
      @retry="load"
      ><el-table
        :data="rows"
        border
        @row-dblclick="row => show(row as Certificate)"
        ><el-table-column label="证书编号" min-width="180"
          ><template #default="s"
            ><el-button
              link
              type="primary"
              @click="show(s.row as Certificate)"
              >{{ s.row.number }}</el-button
            ></template
          ></el-table-column
        ><el-table-column
          min-width="240"
          prop="competition_name"
          label="竞赛"
        /><el-table-column
          min-width="180"
          prop="team_name"
          label="团队"
        /><el-table-column
          min-width="140"
          prop="award_name"
          label="奖项"
        /><el-table-column
          prop="status"
          label="状态"
          width="90"
        /><el-table-column label="操作" width="420"
          ><template #default="s"
            ><el-button link @click="show(s.row as Certificate)">查看</el-button
            ><ManagementActions
              :url="`/api/v1/certificates/${s.row.id}/`"
              :data="s.row"
              :name="s.row.number"
              :can-edit="isAdmin"
              :can-delete="isAdmin"
              :fields="[
                {
                  key: 'notes',
                  label: '档案管理备注（不改变证书内容）',
                  type: 'textarea'
                }
              ]"
              @changed="load"
            /><el-button
              v-if="isAdmin"
              link
              @click="correct(s.row as Certificate)"
              >更正重发</el-button
            ><el-button
              link
              tag="a"
              :href="`/api/v1/certificates/${s.row.id}/download/pdf/`"
              >PDF</el-button
            ><el-button
              link
              tag="a"
              :href="`/api/v1/certificates/${s.row.id}/download/image/`"
              >图片</el-button
            ><el-button
              link
              type="danger"
              :disabled="s.row.status !== 'active'"
              @click="revoke(s.row as Certificate)"
              >申请作废</el-button
            ></template
          ></el-table-column
        ></el-table
      ></ModuleRegion
    ><el-pagination
      v-model:current-page="page"
      v-model:page-size="pageSize"
      class="pager"
      :total="total"
      :page-sizes="[20, 50, 100]"
      layout="total, sizes, prev, pager, next"
      @current-change="load"
      @size-change="searchNow"
    /><RecordDetail
      :loading="detailLoading"
      :error="detailTask.error.value"
      v-model="drawer"
      title="证书档案详情"
      :data="details"
      readonly-reason="签名证书原件与签发快照只读；内容更正请新建更正批次，完成会签后重发。"
      ><template v-if="selected"
        ><SmartImage
          v-if="selected.image_url"
          :src="selected.image_url"
          fit="contain"
          style="width: 100%"
          :preview-src-list="[selected.image_url]"
          :preview-teleported="true"
        /><el-button tag="a" target="_blank" :href="selected.pdf_url"
          >预览签名 PDF</el-button
        ></template
      ><template #actions
        ><ManagementActions
          v-if="selected"
          :url="`/api/v1/certificates/${selected.id}/`"
          :data="selected"
          :name="selected.number"
          :can-edit="isAdmin"
          :can-delete="isAdmin"
          :fields="[{ key: 'notes', label: '档案管理备注', type: 'textarea' }]"
          @changed="
            drawer = false;
            load();
          "
        /><el-button
          v-if="isAdmin && selected"
          type="primary"
          @click="correct(selected)"
          >更正重发</el-button
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
  color: var(--el-text-color-secondary);
}
.search {
  display: flex;
  width: 360px;
  gap: 8px;
}
.pager {
  margin-top: 18px;
  justify-content: flex-end;
}
@media (max-width: 700px) {
  header {
    flex-direction: column;
  }
  .search {
    width: 100%;
    margin-top: 12px;
  }
}
</style>
