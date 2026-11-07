<script setup lang="ts">
import ModuleRegion from "@/components/ModuleRegion.vue";
import { useModuleTask } from "@/composables/useModuleTask";
const listTask = useModuleTask(),
  listLoading = listTask.loading,
  listError = listTask.error;

import { onMounted, ref } from "vue";
import RecordDetail from "@/components/RecordDetail.vue";
import { listLogs, logDetail } from "@/api/business";
const rows = ref<any[]>([]),
  total = ref(0),
  page = ref(1),
  search = ref(""),
  drawer = ref(false),
  selected = ref<Record<string, unknown>>({});
async function load() {
  try {
    await listTask.run(
      () => listLogs(page.value, search.value),
      data => {
        rows.value = data.results;
        total.value = data.count;
      }
    );
  } catch {}
}
const detailTask = useModuleTask(),
  detailLoading = detailTask.loading;
async function show(row: any) {
  drawer.value = true;
  try {
    await detailTask.run(
      () => logDetail(row.id),
      log => {
        selected.value = {
          日志编号: log.id,
          时间: log.created_at,
          操作人: log.actor,
          操作: log.action,
          对象类型: log.object_type,
          对象编号: log.object_id,
          详细内容: log.detail
        };
        drawer.value = true;
      }
    );
  } catch {}
}
function query() {
  page.value = 1;
  load();
}
onMounted(load);
</script>
<template>
  <div class="page business-page">
    <header>
      <div>
        <h2>操作日志</h2>
        <p>超管查看全部日志，部门管理员查看本人的操作记录</p>
      </div>
      <div class="search">
        <el-input
          v-model="search"
          placeholder="操作、对象编号或操作人"
          clearable
          @keyup.enter="query"
        /><el-button @click="query">查询</el-button>
      </div>
    </header>
    <ModuleRegion
      :loading="listLoading"
      :error="listError"
      :empty="!rows.length"
      @retry="load"
      ><el-table :data="rows" border @row-dblclick="show"
        ><el-table-column label="日志编号" width="110"
          ><template #default="s"
            ><el-button link type="primary" @click="show(s.row)">{{
              s.row.id
            }}</el-button></template
          ></el-table-column
        ><el-table-column
          prop="created_at"
          label="时间"
          min-width="200"
        /><el-table-column
          min-width="160"
          prop="actor"
          label="操作人"
        /><el-table-column
          prop="action"
          label="操作"
          min-width="180"
        /><el-table-column
          min-width="160"
          prop="object_type"
          label="对象"
        /><el-table-column label="操作" width="90"
          ><template #default="s"
            ><el-button link @click="show(s.row)">查看</el-button></template
          ></el-table-column
        ></el-table
      ></ModuleRegion
    ><el-pagination
      v-model:current-page="page"
      :total="total"
      :page-size="30"
      layout="total,prev,pager,next"
      @current-change="load"
    /><RecordDetail
      :loading="detailLoading"
      :error="detailTask.error.value"
      v-model="drawer"
      title="日志完整内容"
      :data="selected"
      readonly-reason="审计日志记录已发生的操作，为保护追溯记录，日志原文不允许修改或删除。"
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
  margin-bottom: 18px;
}
h2 {
  font-size: 20px;
  letter-spacing: 0;
  margin: 0;
}
p {
  color: var(--el-text-color-secondary);
}
.search {
  display: flex;
  gap: 10px;
  width: 380px;
}
:deep(.el-pagination) {
  margin-top: 20px;
}
@media (max-width: 800px) {
  header {
    flex-direction: column;
  }
  .search {
    width: 100%;
  }
}
</style>
