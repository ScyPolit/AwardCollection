<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, type FormInstance } from "element-plus";
import RecordDetail from "@/components/RecordDetail.vue";
import { useBusinessAccess } from "@/utils/businessAccess";
import {
  createDepartment,
  createAccount,
  getPublicSettings,
  listAccounts,
  listDepartments,
  updateMembership,
  updatePublicSettings,
  type Option
} from "@/api/business";
const { isSuper, isAdmin } = useBusinessAccess();
const accounts = ref<any[]>([]),
  departments = ref<Option[]>([]),
  dialog = ref(false),
  saving = ref(false),
  formRef = ref<FormInstance>();
const settings = reactive({
  show_team: true,
  show_members: true,
  mask_members: true
});
const form = reactive({
  username: "",
  name: "",
  password: "",
  department: undefined as number | undefined,
  role: "owner"
});
const departmentDialog = ref(false),
  departmentSaving = ref(false),
  departmentForm = reactive({ name: "", code: "" });
const linkDialog = ref(false),
  linkSaving = ref(false),
  linkForm = reactive({
    username: "",
    department: undefined as number | undefined,
    role: "owner"
  });
const detail = ref(false),
  selected = ref<Record<string, unknown>>({});
const roleOptions = computed(() =>
  isSuper.value
    ? [
        { label: "竞赛负责人", value: "owner" },
        { label: "部门管理员", value: "admin" }
      ]
    : [{ label: "竞赛负责人", value: "owner" }]
);
const roleName = (role: string) =>
  ({ super: "超级管理员", admin: "部门管理员", owner: "竞赛负责人" })[role] ||
  role;
async function load() {
  [accounts.value, departments.value] = await Promise.all([
    listAccounts(),
    listDepartments()
  ]);
  Object.assign(settings, await getPublicSettings());
}
function openCreate() {
  Object.assign(form, {
    username: "",
    name: "",
    password: "",
    department: undefined,
    role: "owner"
  });
  formRef.value?.clearValidate();
  dialog.value = true;
}
function showAccount(row: any) {
  selected.value = {
    账号: row.username,
    姓名: row.name,
    角色: row.roles.map(roleName),
    状态: row.active ? "启用" : "停用",
    管理部门: row.memberships.map((m: any) => ({
      部门: m.department__name,
      启用: m.active
    })),
    创建时间: row.joined_at,
    最近登录: row.last_login
  };
  detail.value = true;
}
async function create() {
  if (saving.value) return;
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;
  if (form.role === "admin" && !form.department)
    return ElMessage.warning("请选择管理部门");
  saving.value = true;
  try {
    const payload = {
      ...form,
      department: form.role === "admin" ? form.department : undefined
    };
    await createAccount(payload);
    dialog.value = false;
    form.password = "";
    ElMessage.success("账号创建成功");
    await load();
  } catch {
  } finally {
    saving.value = false;
  }
}
async function addDepartment() {
  if (departmentSaving.value) return;
  departmentSaving.value = true;
  try {
    await createDepartment({ ...departmentForm });
    departmentDialog.value = false;
    Object.assign(departmentForm, { name: "", code: "" });
    ElMessage.success("部门已创建");
    await load();
  } catch {
  } finally {
    departmentSaving.value = false;
  }
}
async function linkAccount() {
  if (linkSaving.value) return;
  linkSaving.value = true;
  try {
    await updateMembership({
      ...linkForm,
      department: linkForm.role === "admin" ? linkForm.department : undefined,
      active: true
    });
    linkDialog.value = false;
    ElMessage.success("角色授权已保存，原登录密码保持不变");
    await load();
  } catch {
  } finally {
    linkSaving.value = false;
  }
}
async function toggle(item: any) {
  try {
    await updateMembership({
      user: item.user,
      department: item.department_id,
      role: "admin",
      active: !item.active
    });
    await load();
  } catch {}
}
async function saveSettings() {
  try {
    await updatePublicSettings({ ...settings });
    ElMessage.success("全校公开设置已保存");
  } catch {}
}
onMounted(load);
</script>
<template>
  <div class="page business-page">
    <header>
      <div>
        <h2>账号与公开设置</h2>
        <p>竞赛负责人独立建档；部门管理员按部门授权</p>
      </div>
      <div class="toolbar">
        <el-button v-if="isSuper" @click="departmentDialog = true"
          >新增部门</el-button
        ><el-button v-if="isAdmin" @click="linkDialog = true"
          >关联已有账号</el-button
        ><el-button v-if="isAdmin" type="primary" @click="openCreate"
          >新增账号</el-button
        >
      </div>
    </header>
    <section>
      <h3>账号与角色</h3>
      <el-table :data="accounts" border @row-dblclick="showAccount">
        <el-table-column label="账号"
          ><template #default="s"
            ><el-button link type="primary" @click="showAccount(s.row)">{{
              s.row.username
            }}</el-button></template
          ></el-table-column
        >
        <el-table-column prop="name" label="姓名" /><el-table-column
          label="角色"
          ><template #default="s"
            ><el-tag v-for="role in s.row.roles" :key="role" class="tag">{{
              roleName(role)
            }}</el-tag></template
          ></el-table-column
        >
        <el-table-column label="管理部门"
          ><template #default="s"
            ><span v-if="!s.row.memberships.length">{{
              s.row.superuser ? "全部部门" : "—"
            }}</span>
            <div v-for="m in s.row.memberships" :key="m.id" class="membership">
              <span>{{ m.department__name }}</span
              ><el-switch
                v-if="isSuper"
                :model-value="m.active"
                @change="toggle({ ...m, user: s.row.id })"
              /><el-tag v-else>{{ m.active ? "启用" : "停用" }}</el-tag>
            </div></template
          ></el-table-column
        >
        <el-table-column label="操作" width="90"
          ><template #default="s"
            ><el-button link @click="showAccount(s.row)"
              >查看</el-button
            ></template
          ></el-table-column
        >
      </el-table>
    </section>
    <section v-if="isSuper">
      <h3>公开查验字段</h3>
      <el-checkbox v-model="settings.show_team">显示团队名称</el-checkbox
      ><el-checkbox v-model="settings.show_members">显示成员姓名</el-checkbox
      ><el-checkbox
        v-model="settings.mask_members"
        :disabled="!settings.show_members"
        >成员姓名脱敏</el-checkbox
      ><el-button type="primary" @click="saveSettings">保存设置</el-button>
    </section>
    <el-dialog
      v-model="dialog"
      title="新增账号"
      width="520"
      :close-on-click-modal="!saving"
      :close-on-press-escape="!saving"
      :show-close="!saving"
    >
      <el-form
        ref="formRef"
        :model="form"
        label-position="top"
        @submit.prevent="create"
      >
        <el-form-item
          label="账号"
          prop="username"
          :rules="[{ required: true, message: '请填写账号', trigger: 'blur' }]"
          ><el-input
            v-model.trim="form.username"
            maxlength="150"
            autocomplete="off"
        /></el-form-item>
        <el-form-item
          label="姓名"
          prop="name"
          :rules="[{ required: true, message: '请填写姓名', trigger: 'blur' }]"
          ><el-input v-model.trim="form.name" maxlength="150"
        /></el-form-item>
        <el-form-item
          label="初始密码"
          prop="password"
          :rules="[
            { required: true, message: '请填写初始密码', trigger: 'blur' },
            { min: 10, message: '密码至少 10 位', trigger: 'blur' }
          ]"
          ><el-input
            v-model="form.password"
            type="password"
            show-password
            autocomplete="new-password"
        /></el-form-item>
        <el-form-item label="角色"
          ><el-segmented v-model="form.role" :options="roleOptions"
        /></el-form-item>
        <el-form-item v-if="form.role === 'admin'" label="管理部门" required
          ><el-select v-model="form.department" class="full"
            ><el-option
              v-for="d in departments"
              :key="d.id"
              :label="d.name"
              :value="d.id" /></el-select
        ></el-form-item>
        <el-alert
          v-else
          title="竞赛负责人不绑定部门；在竞赛中选择拟盖章部门和协作人。"
          type="info"
          :closable="false"
        /> </el-form
      ><template #footer
        ><el-button :disabled="saving" @click="dialog = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="create"
          >创建</el-button
        ></template
      >
    </el-dialog>
    <el-dialog
      v-model="departmentDialog"
      title="新增部门"
      width="480"
      :close-on-click-modal="!departmentSaving"
      :show-close="!departmentSaving"
      ><el-form label-position="top"
        ><el-form-item label="部门名称"
          ><el-input v-model.trim="departmentForm.name" /></el-form-item
        ><el-form-item label="部门编码"
          ><el-input
            v-model.trim="departmentForm.code" /></el-form-item></el-form
      ><template #footer
        ><el-button
          :disabled="departmentSaving"
          @click="departmentDialog = false"
          >取消</el-button
        ><el-button
          type="primary"
          :loading="departmentSaving"
          :disabled="!departmentForm.name || !departmentForm.code"
          @click="addDepartment"
          >创建部门</el-button
        ></template
      ></el-dialog
    >
    <el-dialog
      v-model="linkDialog"
      title="关联已有账号"
      width="480"
      :close-on-click-modal="!linkSaving"
      :show-close="!linkSaving"
      ><el-form label-position="top"
        ><el-form-item label="已有登录账号"
          ><el-input v-model.trim="linkForm.username" /></el-form-item
        ><el-form-item label="授权角色"
          ><el-segmented
            v-model="linkForm.role"
            :options="roleOptions" /></el-form-item
        ><el-form-item v-if="linkForm.role === 'admin'" label="管理部门"
          ><el-select v-model="linkForm.department" class="full"
            ><el-option
              v-for="d in departments"
              :key="d.id"
              :label="d.name"
              :value="d.id" /></el-select></el-form-item
        ><el-alert
          v-else
          title="授予独立的竞赛负责人角色，无需部门绑定。"
          type="info"
          :closable="false" /></el-form
      ><template #footer
        ><el-button :disabled="linkSaving" @click="linkDialog = false"
          >取消</el-button
        ><el-button
          type="primary"
          :loading="linkSaving"
          :disabled="
            !linkForm.username ||
            (linkForm.role === 'admin' && !linkForm.department)
          "
          @click="linkAccount"
          >保存授权</el-button
        ></template
      ></el-dialog
    >
    <RecordDetail v-model="detail" title="账号详情" :data="selected" />
  </div>
</template>
<style scoped>
.page {
  padding: 20px;
}
header,
.toolbar {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}
header {
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
section {
  padding: 18px 0;
  border-top: 1px solid #ebeef5;
}
h3 {
  font-size: 16px;
  letter-spacing: 0;
}
.membership {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 3px 0;
}
.tag {
  margin: 2px;
}
.full {
  width: 100%;
}
@media (max-width: 800px) {
  header {
    flex-direction: column;
  }
  .toolbar {
    flex-wrap: wrap;
  }
}
</style>
