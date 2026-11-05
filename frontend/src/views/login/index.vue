<script setup lang="ts">
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import type { FormInstance, FormRules } from "element-plus";
import { message } from "@/utils/message";
import { useUserStoreHook } from "@/store/modules/user";
import { getTopMenu, initRouter } from "@/router/utils";

defineOptions({ name: "Login" });
const router = useRouter();
const formRef = ref<FormInstance>();
const loading = ref(false);
const form = reactive({ username: "", password: "" });
const rules: FormRules = {
  username: [{ required: true, message: "请输入账号", trigger: "blur" }],
  password: [{ required: true, message: "请输入密码", trigger: "blur" }]
};

async function submit() {
  if (!formRef.value || !(await formRef.value.validate())) return;
  loading.value = true;
  try {
    const result = await useUserStoreHook().loginByUsername(form);
    if (!result.success) throw new Error("login failed");
    await initRouter();
    await router.push(getTopMenu(true).path);
    message("登录成功", { type: "success" });
  } catch {
    message("登录失败，请检查账号和密码", { type: "error" });
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <main class="login-shell">
    <section class="login-panel">
      <div class="brand-mark">证</div>
      <h1>校赛电子证书系统</h1>
      <p>使用学校分配的独立账号登录</p>
      <el-form ref="formRef" :model="form" :rules="rules" size="large" @keyup.enter="submit">
        <el-form-item prop="username"><el-input v-model="form.username" autocomplete="username" placeholder="账号" /></el-form-item>
        <el-form-item prop="password"><el-input v-model="form.password" type="password" show-password autocomplete="current-password" placeholder="密码" /></el-form-item>
        <el-button type="primary" :loading="loading" class="submit" @click="submit">登录</el-button>
        <el-button link class="verify-link" @click="router.push('/verify')">证书编号查验</el-button>
      </el-form>
    </section>
  </main>
</template>

<style scoped>
.login-shell{min-height:100vh;display:grid;place-items:center;background:#f3f5f7;padding:24px}.login-panel{width:min(400px,100%);background:#fff;border:1px solid #dfe3e8;border-radius:8px;padding:36px;box-shadow:0 12px 36px rgb(31 41 55 / 8%)}.brand-mark{width:48px;height:48px;display:grid;place-items:center;background:#1f4b73;color:#fff;border-radius:6px;font-size:24px;font-weight:700}.login-panel h1{margin:22px 0 8px;font-size:24px;letter-spacing:0;color:#1f2937}.login-panel p{margin:0 0 26px;color:#73767a}.submit{width:100%}.verify-link{width:100%;margin:14px 0 0}
</style>
