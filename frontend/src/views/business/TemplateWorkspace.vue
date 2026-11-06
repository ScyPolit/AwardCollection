<script setup lang="ts">
import {
  computed,
  onMounted,
  onBeforeUnmount,
  ref,
  reactive,
  watch
} from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { useBusinessAccess } from "@/utils/businessAccess";
import {
  listTemplates,
  listDepartments,
  listFonts,
  createTemplate,
  copyTemplate,
  saveTemplateVersion,
  importFont,
  type Template,
  type Option
} from "@/api/business";
import { http } from "@/utils/http";
const route = useRoute(),
  router = useRouter(),
  { user, isSuper, isAdmin } = useBusinessAccess();
const templates = ref<Template[]>([]),
  departments = ref<Option[]>([]),
  fonts = ref<any[]>([]),
  selectedId = ref<number>(),
  frame = ref<HTMLIFrameElement>();
const selected = computed(() =>
  templates.value.find(t => t.id === selectedId.value)
);
const canManage = computed(
  () =>
    isAdmin.value &&
    (isSuper.value ||
      user.value.managedDepartmentIds.includes(selected.value?.department || 0))
);
const managed = computed(() =>
  departments.value.filter(
    d => isSuper.value || user.value.managedDepartmentIds.includes(d.id)
  )
);
const dirty = ref(false),
  busy = ref(false),
  ready = ref(false),
  dialog = ref(false),
  copy = ref(false),
  fontDialog = ref(false),
  fontFile = ref<File>(),
  fontName = ref(""),
  license = ref(false);
const form = reactive({
  name: "",
  department: undefined as number | undefined
});
const importer = ref<HTMLInputElement>();
let observer: MutationObserver;
function send(type: string, data?: any) {
  frame.value?.contentWindow?.postMessage(
    {
      type,
      data:
        data instanceof File
          ? data
          : data === undefined
            ? undefined
            : JSON.parse(JSON.stringify(data))
    },
    location.origin
  );
}
function init() {
  if (!ready.value || !selected.value) return;
  send("award-init", {
    canvas: selected.value.latest_version?.canvas || {},
    title: selected.value.name,
    readonly: !canManage.value,
    dark: document.documentElement.classList.contains("dark"),
    context: { departments: departments.value, fonts: fonts.value }
  });
  dirty.value = false;
}
async function load() {
  [templates.value, departments.value, fonts.value] = await Promise.all([
    listTemplates(),
    listDepartments(),
    listFonts()
  ]);
  if (!templates.value.some(t => t.id === selectedId.value))
    selectedId.value =
      templates.value.find(t => t.id === Number(route.query.template))?.id ||
      templates.value[0]?.id;
  init();
  send("award-handshake");
}
async function switchTemplate(id: number) {
  if (dirty.value)
    try {
      await ElMessageBox.confirm(
        "当前更改尚未保存，切换会丢失更改。",
        "切换模板"
      );
    } catch {
      return;
    }
  selectedId.value = id;
  router.replace({ query: { template: id } });
  init();
}
async function receive(event: MessageEvent) {
  if (
    event.origin !== location.origin ||
    event.source !== frame.value?.contentWindow
  )
    return;
  const { type, data } = event.data || {};
  if (type === "award-ready") {
    ready.value = true;
    init();
  }
  if (type === "award-dirty") dirty.value = true;
  if (type === "award-clean") dirty.value = false;
  if (type === "award-imported") {
    dirty.value = true;
    ElMessage.success("模板导入完成，请核对排版后保存");
  }
  if (type === "award-error") ElMessage.error(data);
  if (type === "award-preview") preview();
  if (
    type === "award-save" &&
    canManage.value &&
    selected.value &&
    !busy.value
  ) {
    busy.value = true;
    try {
      await saveTemplateVersion(
        selectedId.value!,
        data,
        selected.value.latest_version?.number || 0
      );
      await load();
      ElMessage.success("已保存新版本，当前页面将用于签发");
    } finally {
      busy.value = false;
    }
  }
}
function open(copying = false) {
  copy.value = copying;
  Object.assign(form, {
    name: copying ? `${selected.value?.name} 副本` : "新证书模板",
    department: managed.value[0]?.id
  });
  dialog.value = true;
}
async function create() {
  if (!form.name.trim() || !form.department || busy.value) return;
  busy.value = true;
  try {
    const t = copy.value
      ? await copyTemplate(selectedId.value!, form)
      : await createTemplate({
          ...form,
          published: true,
          canvas: { title: "获 奖 证 书", page: { width: 842, height: 595 } }
        });
    selectedId.value = t.id;
    dialog.value = false;
    await load();
  } finally {
    busy.value = false;
  }
}
async function rename() {
  const { value } = await ElMessageBox.prompt("模板名称", "修改模板信息", {
    inputValue: selected.value?.name,
    inputValidator: v => !!v.trim() && v.length <= 160
  });
  await http.request("patch", `/api/v1/templates/${selectedId.value}/`, {
    data: { name: value.trim() }
  });
  await load();
}
async function togglePublished(value:boolean){if(!selectedId.value)return;await http.request('patch',`/api/v1/templates/${selectedId.value}/`,{data:{published:value}});await load()}
async function remove() {
  await ElMessageBox.confirm(
    "删除后模板不再出现在模板库；已签发档案仍会保留。",
    "删除模板",
    { type: "warning" }
  );
  await http.request("delete", `/api/v1/templates/${selectedId.value}/`);
  selectedId.value = undefined;
  await load();
}
function preview() {
  if (dirty.value) ElMessage.info("此处预览已保存版本；请先保存当前更改");
  window.open(
    `/api/v1/templates/${selectedId.value}/thumbnail/`,
    "_blank",
    "noopener"
  );
}
async function importFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  if (file.size > 16 * 1024 * 1024) {
    ElMessage.error("导入文件不能超过16MB");
    return;
  }
  busy.value = true;
  try {
    const data = new FormData();
    data.append("file", file);
    const result = await http.post<any, FormData>(
      "/api/v1/templates/import_file/",
      {
        data,
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 90000
      }
    );
    if (result.canvas) {
      send("award-init", {
        canvas: result.canvas,
        title: selected.value?.name,
        readonly: false,
        dark: document.documentElement.classList.contains("dark"),
        context: { fonts: fonts.value, departments: departments.value }
      });
    } else {
      const bytes = Uint8Array.from(atob(result.content), c => c.charCodeAt(0));
      send("award-import", new File([bytes], result.filename));
    }
    dirty.value = true;
    ElMessage.success("已导入编辑器，请预览排版、插入证书字段后保存");
  } finally {
    busy.value = false;
    (event.target as HTMLInputElement).value = "";
  }
}
async function uploadFont() {
  if (!fontFile.value || !license.value) return;
  busy.value = true;
  try {
    const data = new FormData();
    data.append("file", fontFile.value);
    data.append("name", fontName.value);
    data.append("license_confirmed", "true");
    await importFont(data);
    fonts.value = await listFonts();
    send("award-fonts", fonts.value);
    fontDialog.value = false;
    ElMessage.success("字体已导入");
  } finally {
    busy.value = false;
  }
}
function unload(event: BeforeUnloadEvent) {
  if (dirty.value) {
    event.preventDefault();
    event.returnValue = "";
  }
}
onMounted(async () => {
  window.addEventListener("message", receive);
  window.addEventListener("beforeunload", unload);
  observer = new MutationObserver(() =>
    send("award-theme", document.documentElement.classList.contains("dark"))
  );
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class"]
  });
  await load();
});
watch(canManage, init);
onBeforeUnmount(() => {
  window.removeEventListener("message", receive);
  window.removeEventListener("beforeunload", unload);
  observer?.disconnect();
});
</script>
<template>
  <section class="template-workspace">
    <div class="workspace-tools"><el-switch v-if="canManage&&selected" :model-value="selected.published" inline-prompt active-text="已共享" inactive-text="未共享" @change="togglePublished" />
      <el-select
        :model-value="selectedId"
        placeholder="选择证书模板"
        filterable
        style="width: 250px"
        @change="switchTemplate"
        ><el-option
          v-for="t in templates"
          :key="t.id"
          :value="t.id"
          :label="t.name"
      /></el-select>
      <el-button @click="router.push('/business/template-library')"
        >可视化模板库</el-button
      >
      <el-button v-if="isAdmin" @click="open()">新建</el-button
      ><el-button v-if="isAdmin && selected" @click="open(true)"
        >复制</el-button
      >
      <el-button v-if="canManage" @click="rename">修改信息</el-button
      ><el-button v-if="canManage" type="danger" plain @click="remove"
        >删除</el-button
      >
      <el-button v-if="canManage" :loading="busy" @click="importer?.click()"
        >导入模板</el-button
      ><input
        ref="importer"
        hidden
        type="file"
        accept=".ppt,.pptx,.odp,.pdf,.png,.jpg,.jpeg,.json,.pptist"
        @change="importFile"
      />
      <el-button @click="fontDialog = true">导入字体</el-button
      ><el-button v-if="selected" @click="preview">签发预览</el-button>
      <el-button
        v-if="canManage"
        type="primary"
        :loading="busy"
        @click="send('award-save-request')"
        >保存当前页为签发模板</el-button
      >
      <el-tag v-if="dirty" type="warning">未保存</el-tag
      ><el-tag v-else-if="selected"
        >版本 {{ selected.latest_version?.number }}</el-tag
      >
    </div>
    <el-alert
      title="PPTX、PPT、ODP 可编辑导入；PDF、图片作为页面背景。请检查字体与排版，使用“证书字段”绑定获奖数据，并选择要签发的一页后保存。"
      type="info"
      :closable="false"
    />
    <iframe
      v-show="selected"
      ref="frame"
      class="ppt-frame"
      src="/ppt-editor/"
      title="证书 PPT 模板编辑器"
      @load="send('award-handshake')"
      sandbox="allow-scripts allow-same-origin allow-downloads allow-modals allow-popups"
    />
    <el-empty v-if="!selected" description="请新建或选择模板" />
    <el-dialog
      v-model="dialog"
      :title="copy ? '复制模板' : '新建模板'"
      width="460px"
      ><el-form label-width="90px"
        ><el-form-item label="模板名称"
          ><el-input v-model="form.name" maxlength="160" /></el-form-item
        ><el-form-item label="所属部门"
          ><el-select v-model="form.department"
            ><el-option
              v-for="d in managed"
              :key="d.id"
              :value="d.id"
              :label="d.name" /></el-select></el-form-item></el-form
      ><template #footer
        ><el-button @click="dialog = false">取消</el-button
        ><el-button type="primary" :loading="busy" @click="create"
          >创建</el-button
        ></template
      ></el-dialog
    >
    <el-dialog v-model="fontDialog" title="导入授权字体" width="480px"
      ><el-input v-model="fontName" placeholder="字体显示名称（可选）" /><input
        type="file"
        accept=".ttf,.ttc"
        @change="fontFile = ($event.target as HTMLInputElement).files?.[0]"
      /><el-checkbox v-model="license">确认具有使用、嵌入及转换授权</el-checkbox
      ><template #footer
        ><el-button @click="fontDialog = false">取消</el-button
        ><el-button
          type="primary"
          :disabled="!fontFile || !license"
          :loading="busy"
          @click="uploadFont"
          >导入</el-button
        ></template
      ></el-dialog
    >
  </section>
</template>
<style scoped>
.template-workspace {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}
.workspace-tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: var(--el-bg-color);
  border-radius: 6px;
}
.workspace-tools .el-button {
  margin: 0;
}
.ppt-frame {
  width: 100%;
  height: calc(100vh - 265px);
  min-height: 650px;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  background: var(--el-bg-color);
}
@media (max-width: 900px) {
  .ppt-frame {
    min-width: 1000px;
  }
  .template-workspace {
    overflow: auto;
  }
}
</style>
