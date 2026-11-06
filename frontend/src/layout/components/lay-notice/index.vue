<script setup lang="ts">
import { onMounted, onBeforeUnmount } from "vue";
import { useRouter } from "vue-router";
import { openNotification, notificationTarget } from "@/utils/notifications";
import { useLiveStore } from "@/store/modules/live";
import { useUserStoreHook } from "@/store/modules/user";
function expireSession() {
  useUserStoreHook().logOut();
}
import BellIcon from "~icons/ep/bell";
const live = useLiveStore(),
  router = useRouter();
function open(notice: any) {
  openNotification(router, notice);
}
function popup(event: Event) {
  open((event as CustomEvent).detail);
}
onMounted(() => {
  live.start();
  window.addEventListener("award-session-expired", expireSession);
  window.addEventListener("award-notification", popup);
});
onBeforeUnmount(() => {
  live.stop();
  window.removeEventListener("award-session-expired", expireSession);
  window.removeEventListener("award-notification", popup);
});
</script>
<template>
  <el-popover trigger="click" placement="bottom-end" :width="370">
    <template #reference
      ><button class="notice-trigger" aria-label="通知中心">
        <el-badge :value="live.unread" :hidden="!live.unread" :max="99"
          ><IconifyIconOffline :icon="BellIcon"
        /></el-badge></button
    ></template>
    <div class="notice-heading">
      <strong>通知中心</strong
      ><el-tag size="small" :type="live.connected ? 'success' : 'warning'">{{
        live.connected ? "实时连接" : "正在重连"
      }}</el-tag
      ><el-button link :loading="live.readingAll" @click="live.readAll"
        >全部已读</el-button
      >
    </div>
    <el-scrollbar max-height="430px"
      ><el-empty
        v-if="!live.notifications.length"
        description="暂无通知"
        :image-size="60"
      /><a
        v-for="n in live.notifications"
        :key="n.id"
        class="notice-item"
        :href="
          notificationTarget(n)
            ? router.resolve(notificationTarget(n)).href
            : '#'
        "
        @click.prevent="open(n)"
      >
        <span class="notice-title"><i v-if="!n.read_at" />{{ n.title }}</span
        ><span>{{ n.body }}</span
        ><small
          >{{ new Date(n.created_at).toLocaleString("zh-CN") }} ·
          {{ n.read_at ? "已读" : "未读" }}</small
        ><el-button
          v-if="!n.read_at"
          link
          size="small"
          @click.stop.prevent="live.read(n.id)"
          >标为已读</el-button
        >
      </a></el-scrollbar
    >
    <div
      v-if="live.jobs.some(j => ['queued', 'running'].includes(j.status))"
      class="live-jobs"
    >
      <div
        v-for="job in live.jobs.filter(j =>
          ['queued', 'running'].includes(j.status)
        )"
        :key="job.id"
        @click="router.push('/business/batches?batch=' + job.batch_id)"
      >
        <span>{{ job.batch_name }} · {{ job.processed }}/{{ job.total }}</span
        ><el-progress :percentage="job.percent" :stroke-width="6" />{{
          job.eta_seconds
            ? `预计剩余 ${Math.ceil(job.eta_seconds / 60)} 分钟`
            : "正在估算剩余时间"
        }}
      </div>
    </div>
  </el-popover>
</template>
<style scoped>
.notice-trigger {
  width: 40px;
  height: 48px;
  border: 0;
  background: transparent;
  color: var(--el-text-color-primary);
  cursor: pointer;
  font-size: 19px;
}
.notice-heading {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 12px;
}
.notice-heading .el-button {
  margin-left: auto;
}
.notice-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  text-align: left;
  border: 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: transparent;
  color: var(--el-text-color-primary);
  padding: 12px 4px;
  cursor: pointer;
}
.notice-item:hover {
  background: var(--el-fill-color-light);
}
.notice-title {
  font-weight: 600;
}
.notice-title i {
  display: inline-block;
  width: 7px;
  height: 7px;
  background: var(--el-color-danger);
  border-radius: 50%;
  margin-right: 7px;
}
.notice-item small {
  color: var(--el-text-color-secondary);
}
.live-jobs {
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color);
}
.live-jobs > div {
  cursor: pointer;
  margin-top: 8px;
}
</style>

<style scoped>
.notice-item span,
.notice-item small {
  overflow-wrap: anywhere;
}
</style>
