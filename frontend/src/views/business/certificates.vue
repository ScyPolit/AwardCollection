<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import SmartImage from "@/components/SmartImage.vue";
import ModuleRegion from "@/components/ModuleRegion.vue";
import BulkActions from "@/components/BulkActions.vue";
import BatchDownload from "@/components/BatchDownload.vue";
import ManagementActions from "@/components/ManagementActions.vue";
import RecordDetail from "@/components/RecordDetail.vue";
import { useModuleTask } from "@/composables/useModuleTask";
import { useBusinessAccess } from "@/utils/businessAccess";
import { http } from "@/utils/http";
import {
  certificateDetail,
  listCertificates,
  listCertificateBatches,
  revokeCertificate,
  type Certificate,
  type CertificateBatch
} from "@/api/business";
const router = useRouter(),
  { isAdmin } = useBusinessAccess(),
  listTask = useModuleTask(),
  detailTask = useModuleTask();
type ArchiveNode = Partial<Certificate & CertificateBatch> & {
  id: number;
  nodeKey: string;
  isBatch?: boolean;
  isMore?: boolean;
  isError?: boolean;
  parentId?: number;
  hasChildren?: boolean;
  message?: string;
  busy?: boolean;
};
const table = ref(),
  rows = ref<ArchiveNode[]>([]),
  selection = ref<any[]>([]),
  total = ref(0),
  page = ref(1),
  pageSize = ref(20),
  search = ref(""),
  activeSearch = ref(""),
  treeEpoch = ref(0);
const children = new Map<
  number,
  { rows: ArchiveNode[]; page: number; count: number }
>();
function selectable(row: ArchiveNode) {
  return !row.isBatch && !row.isMore && !row.isError;
}
async function load() {
  try {
    await listTask.run(
      () =>
        listCertificateBatches(page.value, pageSize.value, activeSearch.value),
      data => {
        treeEpoch.value++;
        children.clear();
        selection.value = [];
        rows.value = data.results.map(batch => ({
          ...batch,
          nodeKey: `batch-${batch.id}`,
          isBatch: true,
          hasChildren: true
        }));
        total.value = data.count;
      }
    );
  } catch {}
}
function searchNow() {
  activeSearch.value = search.value;
  page.value = 1;
  load();
}
async function childPage(batchId: number, number: number) {
  const data = await listCertificates(number, 50, activeSearch.value, batchId);
  return {
    rows: data.results.map(
      c => ({ ...c, nodeKey: `certificate-${c.id}` }) as ArchiveNode
    ),
    page: number,
    count: data.count
  };
}
function displayChildren(batchId: number) {
  const state = children.get(batchId);
  if (!state) return [];
  return [
    ...state.rows,
    ...(state.rows.length < state.count
      ? [
          {
            id: batchId,
            parentId: batchId,
            nodeKey: `more-${batchId}`,
            isMore: true,
            name: `继续加载（已显示 ${state.rows.length} / ${state.count}）`
          }
        ]
      : [])
  ];
}
async function expand(
  row: ArchiveNode,
  _node: any,
  resolve: (data: ArchiveNode[]) => void
) {
  const epoch = treeEpoch.value;
  try {
    const result = await childPage(row.id, 1);
    if (epoch !== treeEpoch.value) return resolve([]);
    children.set(row.id, result);
    resolve(displayChildren(row.id));
  } catch {
    resolve([
      {
        id: row.id,
        parentId: row.id,
        nodeKey: `error-${row.id}`,
        isError: true,
        message: "证书加载失败，点击重试"
      }
    ]);
  }
}
async function loadMore(row: ArchiveNode) {
  if (row.busy) return;
  row.busy = true;
  const epoch = treeEpoch.value,
    batchId = row.parentId!;
  try {
    const current = children.get(batchId);
    const result = await childPage(batchId, (current?.page || 0) + 1);
    if (epoch !== treeEpoch.value) return;
    children.set(batchId, {
      ...result,
      rows: [...(current?.rows || []), ...result.rows]
    });
    table.value?.updateKeyChildren(
      `batch-${batchId}`,
      displayChildren(batchId)
    );
  } catch {
    ElMessage.error("证书加载失败，请重试");
  } finally {
    row.busy = false;
  }
}
const drawer = ref(false),
  selected = ref<any>(),
  details = ref<Record<string, unknown>>({});
async function show(row: ArchiveNode) {
  if (row.isBatch) return table.value?.toggleRowExpansion(row);
  if (!selectable(row)) return;
  drawer.value = true;
  selected.value = undefined;
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
      }
    );
  } catch {}
}
async function revoke(row: ArchiveNode) {
  try {
    const { value } = await ElMessageBox.prompt("填写作废原因", "申请作废", {
      inputType: "textarea",
      inputValidator: v => !!v?.trim() || "必须填写原因"
    });
    await revokeCertificate(row.id, value);
    ElMessage.success("作废申请已提交，审批期间证书继续有效");
  } catch {}
}
async function correct(row: any) {
  try {
    await ElMessageBox.confirm(
      "将以此证书数据创建新的待审批批次；原证书保持原状。",
      "更正重发"
    );
  } catch {
    return;
  }
  const data = await http.post<any, object>(
    `/api/v1/certificates/${row.id}/correction/`,
    { data: {} }
  );
  ElMessage.success("更正批次已创建，请修改后提交审批");
  router.push({ path: "/business/batches", query: { batch: data.batch } });
}
const downloadDialog = ref(false),
  downloadBatch = ref<number>();
function download(row: ArchiveNode) {
  downloadBatch.value = row.id;
  downloadDialog.value = true;
}
onMounted(load);
</script>
<template>
  <div class="page business-page">
    <header>
      <div>
        <h2>证书档案</h2>
        <p>按批次展开证书，每次加载50份；可选择证书批量操作或下载整批 ZIP。</p>
      </div>
      <div class="search">
        <el-input
          v-model="search"
          clearable
          placeholder="编号、团队、竞赛或批次"
          @keyup.enter="searchNow"
        /><el-button @click="searchNow">查询</el-button>
      </div>
    </header>
    <BulkActions
      :selected="selection"
      resource="certificates"
      :can-delete="isAdmin"
      :readonly-reason="
        isAdmin
          ? '删除为档案归档，签名原件和审计保留；单次最多200份。'
          : '负责人可选择和导出证书信息，档案删除由管理员执行。'
      "
      @clear="table?.clearSelection()"
      @changed="load"
    />
    <ModuleRegion
      :loading="listTask.loading.value"
      :error="listTask.error.value"
      :empty="!rows.length"
      @retry="load"
    >
      <el-table
        :key="treeEpoch"
        ref="table"
        :data="rows"
        row-key="nodeKey"
        border
        lazy
        :load="expand"
        :tree-props="{ children: 'children', hasChildren: 'hasChildren' }"
        @selection-change="selection = $event.filter(selectable)"
        @row-dblclick="show"
      >
        <el-table-column
          type="selection"
          width="48"
          :selectable="selectable"
          reserve-selection
        />
        <el-table-column label="批次 / 证书编号" min-width="350"
          ><template #default="s">
            <template v-if="s.row.isBatch"
              ><el-button
                link
                type="primary"
                class="batch-label"
                @click="show(s.row as ArchiveNode)"
                >{{ s.row.name }}</el-button
              ><el-tag size="small" class="count-tag"
                >{{ s.row.certificate_count }} 份</el-tag
              ></template
            >
            <el-button
              v-else-if="s.row.isMore || s.row.isError"
              link
              :type="s.row.isError ? 'danger' : 'primary'"
              :loading="s.row.busy"
              @click="loadMore(s.row as ArchiveNode)"
              >{{ s.row.message || s.row.name }}</el-button
            >
            <el-button
              v-else
              link
              type="primary"
              @click="show(s.row as ArchiveNode)"
              >{{ s.row.number }}</el-button
            >
          </template></el-table-column
        >
        <el-table-column
          prop="competition_name"
          label="竞赛"
          min-width="190"
          show-overflow-tooltip
        />
        <el-table-column
          prop="team_name"
          label="团队"
          min-width="150"
          show-overflow-tooltip
        /><el-table-column prop="award_name" label="奖项" min-width="120" />
        <el-table-column label="状态" width="140"
          ><template #default="s"
            ><span v-if="s.row.isBatch">有效 {{ s.row.active_count }} 份</span
            ><el-tag
              v-else-if="s.row.status"
              :type="s.row.status === 'active' ? 'success' : 'info'"
              >{{ s.row.status === "active" ? "有效" : "已作废" }}</el-tag
            ></template
          ></el-table-column
        >
        <el-table-column label="操作" min-width="270"
          ><template #default="s">
            <template v-if="s.row.isBatch"
              ><el-button
                link
                type="primary"
                @click="show(s.row as ArchiveNode)"
                >展开 / 收起</el-button
              ><el-button
                link
                type="primary"
                @click="download(s.row as ArchiveNode)"
                >下载整批 ZIP</el-button
              ></template
            >
            <template v-else-if="selectable(s.row as ArchiveNode)"
              ><el-button link @click="show(s.row as ArchiveNode)"
                >查看</el-button
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
                @click="revoke(s.row as ArchiveNode)"
                >申请作废</el-button
              ></template
            >
          </template></el-table-column
        >
      </el-table>
    </ModuleRegion>
    <el-pagination
      v-model:current-page="page"
      v-model:page-size="pageSize"
      class="pager"
      :total="total"
      :page-sizes="[10, 20, 50]"
      layout="total, sizes, prev, pager, next"
      @current-change="load"
      @size-change="
        () => {
          page = 1;
          load();
        }
      "
    />
    <RecordDetail
      v-model="drawer"
      title="证书档案详情"
      :loading="detailTask.loading.value"
      :error="detailTask.error.value"
      :data="details"
      readonly-reason="签名证书原件与签发快照只读；更正需重新会签。"
    >
      <template v-if="selected"
        ><SmartImage
          v-if="selected.image_url"
          :src="selected.image_url"
          fit="contain"
          style="width: 100%"
          :preview-src-list="[selected.image_url]"
          preview-teleported
        /><el-button tag="a" target="_blank" :href="selected.pdf_url"
          >预览签名 PDF</el-button
        ></template
      >
      <template #actions
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
      >
    </RecordDetail>
    <el-dialog
      v-model="downloadDialog"
      title="整批文件下载"
      width="min(600px,96vw)"
      ><BatchDownload
        v-if="downloadDialog && downloadBatch"
        :batch-id="downloadBatch"
    /></el-dialog>
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
  gap: 16px;
  margin-bottom: 18px;
}
h2 {
  margin: 0;
  font-size: 20px;
  letter-spacing: 0;
}
p {
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
.search {
  display: flex;
  width: 360px;
  flex-shrink: 0;
  gap: 8px;
}
.pager {
  margin-top: 18px;
  justify-content: flex-end;
}
.count-tag {
  margin-left: 8px;
}
.batch-label {
  max-width: 250px;
  white-space: normal;
  text-align: left;
  line-height: 1.5;
}
@media (max-width: 700px) {
  header {
    flex-direction: column;
  }
  .search {
    width: 100%;
  }
}
</style>
