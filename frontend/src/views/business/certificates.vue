<script setup lang="ts">
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
async function show(row: Certificate) {
  selected.value = await certificateDetail(row.id);
  const c = selected.value;
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
    盖章部门: c.departments,
    模板: c.template,
    模板版本: c.template_version,
    签发时间: c.published_at,
    PDF摘要: c.pdf_sha256
  };
  drawer.value = true;
}
const rows = ref<Certificate[]>([]),
  total = ref(0),
  page = ref(1),
  pageSize = ref(20),
  search = ref("");
async function load() {
  const data = await listCertificates(page.value, pageSize.value, search.value);
  rows.value = data.results;
  total.value = data.count;
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
    <el-table :data="rows" border @row-dblclick="show"
      ><el-table-column label="证书编号" min-width="180"
        ><template #default="s"
          ><el-button link type="primary" @click="show(s.row)">{{
            s.row.number
          }}</el-button></template
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
      /><el-table-column label="操作" width="260"
        ><template #default="s"
          ><el-button link @click="show(s.row)">查看</el-button
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
            @click="revoke(s.row)"
            >申请作废</el-button
          ></template
        ></el-table-column
      ></el-table
    ><el-pagination
      v-model:current-page="page"
      v-model:page-size="pageSize"
      class="pager"
      :total="total"
      :page-sizes="[20, 50, 100]"
      layout="total, sizes, prev, pager, next"
      @current-change="load"
      @size-change="searchNow"
    /><RecordDetail v-model="drawer" title="证书档案详情" :data="details"
      ><template v-if="selected"
        ><el-image
          v-if="selected.image_url"
          :src="selected.image_url"
          fit="contain"
          style="width: 100%"
          :preview-src-list="[selected.image_url]"
          :preview-teleported="true"
        /><el-button tag="a" target="_blank" :href="selected.pdf_url"
          >预览签名 PDF</el-button
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
