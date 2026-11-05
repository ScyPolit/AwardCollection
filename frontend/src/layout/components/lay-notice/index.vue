<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { http } from "@/utils/http";
import NoticeList from "./components/NoticeList.vue";
import BellIcon from "~icons/ep/bell";

const noticesNum = ref(0);
const notices = ref([
  { key: "1", name: "通知", list: [], emptyText: "暂无通知" },
  { key: "2", name: "消息", list: [], emptyText: "暂无消息" },
  { key: "3", name: "待办", list: [], emptyText: "暂无待办" }
]);
const activeKey = ref("1");

onMounted(async () => {
  try {
    const data = await http.get<any[], never>("/api/v1/notifications/");
    notices.value[0].list = data.map(item => ({
      avatar: "",
      title: item.title,
      description: item.body,
      datetime: new Date(item.created_at).toLocaleString("zh-CN"),
      type: "1"
    }));
    noticesNum.value = notices.value[0].list.length;
  } catch {
    noticesNum.value = 0;
  }
});

const getLabel = computed(
  () => item =>
    item.name + (item.list.length > 0 ? `(${item.list.length})` : "")
);
</script>

<template>
  <el-dropdown trigger="click" placement="bottom-end">
    <span
      :class="[
        'dropdown-badge',
        'navbar-bg-hover',
        'select-none',
        Number(noticesNum) !== 0 && 'mr-[10px]'
      ]"
    >
      <el-badge :value="Number(noticesNum) === 0 ? '' : noticesNum" :max="99">
        <span class="header-notice-icon">
          <IconifyIconOffline :icon="BellIcon" />
        </span>
      </el-badge>
    </span>
    <template #dropdown>
      <el-dropdown-menu>
        <el-tabs
          v-model="activeKey"
          :stretch="true"
          class="dropdown-tabs"
          :style="{ width: notices.length === 0 ? '200px' : '330px' }"
        >
          <el-empty
            v-if="notices.length === 0"
            description="暂无消息"
            :image-size="60"
          />
          <span v-else>
            <template v-for="item in notices" :key="item.key">
              <el-tab-pane :label="getLabel(item)" :name="`${item.key}`">
                <el-scrollbar max-height="330px">
                  <div class="noticeList-container">
                    <NoticeList :list="item.list" :emptyText="item.emptyText" />
                  </div>
                </el-scrollbar>
              </el-tab-pane>
            </template>
          </span>
        </el-tabs>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<style lang="scss" scoped>
.dropdown-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 48px;
  cursor: pointer;

  .header-notice-icon {
    font-size: 18px;
  }
}

.dropdown-tabs {
  .noticeList-container {
    padding: 15px 24px 0;
  }

  :deep(.el-tabs__header) {
    margin: 0;
  }

  :deep(.el-tabs__nav-wrap)::after {
    height: 1px;
  }

  :deep(.el-tabs__nav-wrap) {
    padding: 0 36px;
  }
}
</style>
