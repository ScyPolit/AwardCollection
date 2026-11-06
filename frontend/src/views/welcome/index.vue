<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import RecordDetail from "@/components/RecordDetail.vue";
import { dashboard, markNotificationRead } from "@/api/business";
defineOptions({ name: "Welcome" });
const router = useRouter(),
  detail = ref(false),
  message = ref<Record<string, unknown>>({});
async function showNotification(row: any) {
  message.value = { 事项: row.title, 内容: row.body, 创建时间: row.created_at };
  detail.value = true;
  if (!row.read_at) {
    await markNotificationRead(row.id);
    data.value = await dashboard();
  }
}
const data = ref({
  pendingApprovals: 0,
  runningTasks: 0,
  issuedThisMonth: 0,
  unreadNotifications: 0,
  recent: [] as any[]
});
onMounted(async () => (data.value = await dashboard()));
</script>
<template>
  <div class="dashboard business-page">
    <header>
      <div>
        <h1>证书签发工作台</h1>
        <p>待办、生成任务和近期签发状态</p>
      </div>
      <el-tag type="success">系统运行正常</el-tag>
    </header>
    <div class="stats">
      <div
        role="button"
        tabindex="0"
        @click="router.push('/business/approvals')"
        @keydown.enter="router.push('/business/approvals')"
      >
        <span>待审批批次</span><strong>{{ data.pendingApprovals }}</strong>
      </div>
      <div
        role="button"
        tabindex="0"
        @click="router.push('/business/batches')"
        @keydown.enter="router.push('/business/batches')"
      >
        <span>生成中任务</span><strong>{{ data.runningTasks }}</strong>
      </div>
      <div
        role="button"
        tabindex="0"
        @click="router.push('/business/certificates')"
        @keydown.enter="router.push('/business/certificates')"
      >
        <span>本月签发</span><strong>{{ data.issuedThisMonth }}</strong>
      </div>
      <div>
        <span>未读消息</span><strong>{{ data.unreadNotifications }}</strong>
      </div>
    </div>
    <section>
      <h2>近期动态</h2>
      <el-table
        v-if="data.recent.length"
        :data="data.recent"
        @row-click="showNotification"
        ><el-table-column
          prop="title"
          label="事项"
          width="180" /><el-table-column
          prop="body"
          label="内容" /><el-table-column
          prop="created_at"
          label="时间"
          width="190" /></el-table
      ><el-empty v-else description="尚无业务记录" :image-size="90" />
    </section>
    <RecordDetail v-model="detail" title="消息详情" :data="message" />
  </div>
</template>
<style scoped>
.dashboard {
  padding: 24px;
}
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
h1 {
  margin: 0;
  font-size: 24px;
  letter-spacing: 0;
}
header p {
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
}
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin: 24px 0;
}
.stats div,
section {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  padding: 18px;
  border-radius: 6px;
}
.stats [role="button"] {
  cursor: pointer;
}
.stats span {
  display: block;
  color: var(--el-text-color-secondary);
}
.stats strong {
  display: block;
  margin-top: 10px;
  font-size: 28px;
}
section h2 {
  font-size: 18px;
  letter-spacing: 0;
}
@media (max-width: 800px) {
  .stats {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
