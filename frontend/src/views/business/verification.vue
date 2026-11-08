<script setup lang="ts">
import { ref } from "vue";
import CertificateIcon from "~icons/ep/document-checked";
import { adminVerify, publicVerify } from "@/api/business";
import { useRoute } from "vue-router";
import { useBusinessAccess } from "@/utils/businessAccess";
import VerificationResult from "@/components/VerificationResult.vue";
import VerificationSettings from "@/components/VerificationSettings.vue";
const isPublic = useRoute().name === "PublicVerification";
const access = isPublic ? undefined : useBusinessAccess();
const number = ref(""),
  queriedNumber = ref(""),
  result = ref<any>(),
  loading = ref(false);
async function query() {
  if (loading.value || !number.value.trim()) return;
  loading.value = true;
  result.value = undefined;
  queriedNumber.value = number.value.trim();
  try {
    result.value = isPublic
      ? await publicVerify({ number: queriedNumber.value })
      : await adminVerify(queriedNumber.value);
  } finally {
    loading.value = false;
  }
}
</script>
<template>
  <div class="verify" :class="{ public: isPublic }">
    <section class="query-panel">
      <div class="heading">
        <span class="heading-icon"
          ><IconifyIconOffline :icon="CertificateIcon"
        /></span>
        <div>
          <h2>证书编号查验</h2>
          <p>输入证书编号，核对获奖信息与证书状态。</p>
        </div>
      </div>
      <el-form label-position="top" @submit.prevent="query">
        <el-form-item label="证书编号"
          ><el-input
            v-model="number"
            maxlength="40"
            clearable
            placeholder="例如 2026AC00000001"
            size="large"
        /></el-form-item>
        <el-button
          type="primary"
          native-type="submit"
          :loading="loading"
          :disabled="!number.trim()"
          size="large"
          >查验证书</el-button
        >
        <span class="limit-note">每分钟最多查验60次，历史编号可直接输入。</span>
      </el-form>
      <el-skeleton v-if="loading" :rows="5" animated class="result-loading" />
      <VerificationResult
        v-else-if="result"
        :result="result"
        :number="queriedNumber"
      />
    </section>
    <VerificationSettings
      v-if="!isPublic && access?.isSuper.value"
      class="settings-panel"
    />
  </div>
</template>
<style scoped>
.verify {
  min-height: calc(100vh - 130px);
  padding: 24px;
  display: grid;
  grid-template-columns: minmax(0, 760px);
  justify-content: center;
  align-content: start;
  gap: 24px;
}
.query-panel {
  padding: 28px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
}
.heading {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 24px;
}
.heading-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 26px;
  flex-shrink: 0;
}
h2 {
  margin: 0;
  font-size: 22px;
}
p {
  color: var(--el-text-color-secondary);
  line-height: 1.7;
  margin: 6px 0 0;
}
.limit-note {
  display: inline-block;
  margin: 10px 0 0 14px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.result-loading {
  margin-top: 24px;
}
.verify.public {
  min-height: 100vh;
  background: var(--el-fill-color-light);
  padding-top: clamp(24px, 8vh, 80px);
}
@media (min-width: 1300px) {
  .verify:has(.settings-panel) {
    grid-template-columns: minmax(0, 1fr) minmax(360px, 0.85fr);
  }
  .query-panel,
  .settings-panel {
    align-self: start;
  }
}
@media (max-width: 700px) {
  .verify {
    padding: 12px;
    gap: 16px;
  }
  .query-panel {
    padding: 20px;
  }
  .limit-note {
    display: block;
    margin: 10px 0 0;
  }
  .heading {
    align-items: flex-start;
  }
}
</style>
