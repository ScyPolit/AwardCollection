<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { adminVerify, getChallenge, publicVerify } from "@/api/business";
import { useRoute } from "vue-router";

const isPublic = useRoute().name === "PublicVerification";
const form = reactive({ number: "", answer: "" });
const question = ref("");
const result = ref<any>(null);
const loading = ref(false);

async function challenge() {
  question.value = (await getChallenge()).question;
  form.answer = "";
}
async function query() {
  loading.value = true;
  try { result.value = await publicVerify(form); }
  finally { loading.value = false; await challenge(); }
}
async function admin() {
  loading.value = true;
  try { result.value = await adminVerify(form.number); }
  finally { loading.value = false; }
}
onMounted(challenge);
</script>

<template>
  <div class="verify"><section>
    <h2>证书编号查验</h2><p>访客每次查询都需要新的服务端验证码</p>
    <el-form label-position="top">
      <el-form-item label="证书编号"><el-input v-model="form.number" placeholder="例如 2026-AC-00000001" /></el-form-item>
      <el-form-item :label="question"><el-input v-model="form.answer" /></el-form-item>
      <el-button type="primary" :loading="loading" @click="query">访客查验</el-button>
      <el-button v-if="!isPublic" :loading="loading" @click="admin">管理员免验证码核验</el-button>
    </el-form>
    <el-result v-if="result" :icon="result.found ? (result.status === 'active' ? 'success' : 'warning') : 'error'" :title="result.found ? `证书${result.status === 'active' ? '有效' : '已作废'}` : '未找到记录'">
      <template #sub-title><div v-if="result.found">{{ result.competition }} · {{ result.award }}<br />{{ result.team }}<br />{{ result.members?.join('、') }}</div></template>
    </el-result>
  </section></div>
</template>
<style scoped>.verify{min-height:100vh;padding:24px;display:flex;justify-content:center;align-items:flex-start;background:#f3f5f7}.verify section{width:min(680px,100%);background:#fff;border:1px solid #ebeef5;border-radius:6px;padding:28px}h2{font-size:22px;letter-spacing:0;margin:0}p{color:#73767a;margin-bottom:22px}</style>
