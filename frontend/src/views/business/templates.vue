<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch
} from "vue";
import { useRoute, useRouter } from "vue-router";
import { useResizeObserver } from "@vueuse/core";
import { ElMessage, type UploadFile } from "element-plus";
import RecordDetail from "@/components/RecordDetail.vue";
import { useBusinessAccess } from "@/utils/businessAccess";
import {
  copyTemplate,
  createTemplate,
  importFont,
  layoutTemplate,
  listDepartments,
  listFonts,
  listTemplates,
  publishTemplate,
  saveTemplateVersion,
  type CertificateFont,
  type Option,
  type Template
} from "@/api/business";
type TextLayer = {
  id: string;
  type: "text";
  field: string;
  text?: string;
  x: number;
  y: number;
  width: number;
  height: number;
  fontSize: number;
  minFontSize: number;
  fontFamily: string;
  lineHeight: number;
  color: string;
  align: string;
};
type SealLayer = {
  id: string;
  type: "seal";
  department?: number;
  x: number;
  y: number;
  size: number;
};
type Layer = TextLayer | SealLayer;
type CanvasModel = {
  page: { width: number; height: number };
  background: string;
  layers: Layer[];
  watermark: boolean;
};
const { user, isSuper, isAdmin } = useBusinessAccess();
const route = useRoute(),
  router = useRouter();
const rows = ref<Template[]>([]),
  departments = ref<Option[]>([]),
  fonts = ref<CertificateFont[]>([]),
  selectedId = ref<number>(Number(route.query.template) || undefined),
  selectedLayerId = ref("");
const canvas = ref<CanvasModel>({
  page: { width: 842, height: 595 },
  background: "",
  layers: [],
  watermark: true
});
const selectedTemplate = computed(() =>
  rows.value.find(t => t.id === selectedId.value)
);
const selectedLayer = computed(() =>
  canvas.value.layers.find(l => l.id === selectedLayerId.value)
);
const managedDepartments = computed(() =>
  departments.value.filter(
    d => isSuper.value || user.value.managedDepartmentIds.includes(d.id)
  )
);
const canManage = computed(
  () =>
    isAdmin.value &&
    (isSuper.value ||
      user.value.managedDepartmentIds.includes(
        selectedTemplate.value?.department || 0
      ))
);
const previewHost = ref<HTMLElement>(),
  previewWidth = ref(760),
  scale = computed(() =>
    Math.min(1, Math.max(100, previewWidth.value) / canvas.value.page.width)
  );
useResizeObserver(
  previewHost,
  entries => (previewWidth.value = entries[0].contentRect.width)
);
const templateDialog = ref(false),
  templateSaving = ref(false),
  saving = ref(false),
  templateForm = reactive({
    name: "",
    department: undefined as number | undefined,
    copy: false
  });
const fontDialog = ref(false),
  fontSaving = ref(false),
  fontUpload = ref<File>(),
  fontForm = reactive({ name: "", license_confirmed: false });
const info = ref(false),
  infoData = ref<Record<string, unknown>>({});
const layouts = ref<Record<string, any>>({}),
  layoutBusy = ref(false),
  layoutError = ref("");
const fieldLabels: Record<string, string> = {
  static: "固定文本",
  team_name: "团队名称",
  members: "团队成员",
  award_name: "奖项",
  work_name: "作品名称",
  category: "项目类别",
  teachers: "指导教师",
  number: "证书编号"
};
let sequence = 0,
  timer: ReturnType<typeof setTimeout>,
  requestId = 0;
const fontPromises = new Map<string, Promise<FontFace>>();
function layerId() {
  return (
    globalThis.crypto?.randomUUID?.() ||
    `layer-${Date.now().toString(36)}-${++sequence}`
  );
}
function newText(field = "static", text = "新文本", y = 130): TextLayer {
  return {
    id: layerId(),
    type: "text",
    field,
    text,
    x: 110,
    y,
    width: 622,
    height: 55,
    fontSize: 24,
    minFontSize: 10,
    fontFamily: "hei",
    lineHeight: 1.35,
    color: "#1f2937",
    align: "center"
  };
}
function normalize(raw: any): CanvasModel {
  const value = JSON.parse(JSON.stringify(raw || {}));
  const layers: Layer[] = value.layers || [
    {
      ...newText("static", value.title || "获 奖 证 书", 90),
      fontSize: value.size || 34,
      height: 60
    },
    { ...newText("team_name", "", 190), fontSize: 22, height: 65 },
    { ...newText("award_name", "", 280), fontSize: 18, height: 50 },
    ...(value.number === false || value.showNumber === false
      ? []
      : [
          {
            ...newText("number", "", 500),
            x: 72,
            width: 320,
            height: 24,
            fontSize: 11,
            minFontSize: 9,
            color: "#4b5563",
            align: "left"
          }
        ])
  ];
  for (const layer of layers)
    if (layer.type === "text") {
      layer.fontFamily ||= "hei";
      layer.lineHeight ??= 1.35;
    }
  return {
    page: value.page || { width: 842, height: 595 },
    background: value.background || "",
    watermark: value.watermark ?? value.showWatermark ?? true,
    layers
  };
}
async function load() {
  [rows.value, departments.value, fonts.value] = await Promise.all([
    listTemplates(),
    listDepartments(),
    listFonts()
  ]);
  if (!selectedId.value && rows.value.length)
    selectedId.value = rows.value[0].id;
}
watch(
  () => route.query.template,
  value => {
    if (value) selectedId.value = Number(value);
  }
);
watch(selectedTemplate, item => {
  canvas.value = normalize(item?.latest_version?.canvas);
  selectedLayerId.value = canvas.value.layers[0]?.id || "";
});
async function ensureFont(id: string) {
  if (fontPromises.has(id)) return fontPromises.get(id)!;
  const font = fonts.value.find(f => f.id === id);
  if (!font) throw Error("所选字体已不存在，请刷新字体库");
  const face = new FontFace(
    "AC_" + id.replaceAll("-", "_"),
    `url("${font.url}")`
  );
  const promise = face.load().then(loaded => {
    (document.fonts as FontFaceSet & { add(face: FontFace): void }).add(loaded);
    return loaded;
  });
  fontPromises.set(id, promise);
  try {
    return await promise;
  } catch (error) {
    fontPromises.delete(id);
    throw error;
  }
}
function scheduleLayout() {
  clearTimeout(timer);
  const id = ++requestId;
  layoutBusy.value = true;
  timer = setTimeout(() => refreshLayout(id), 250);
}
async function refreshLayout(id: number) {
  try {
    const result = await layoutTemplate(
      JSON.parse(JSON.stringify(canvas.value))
    );
    const ids = new Set<string>();
    for (const layer of Object.values(result) as any[])
      for (const line of layer.lines)
        for (const run of line.runs) ids.add(run.fontId);
    if (canvas.value.watermark) ids.add("hei");
    await Promise.all([...ids].map(ensureFont));
    if (id === requestId) {
      layouts.value = result;
      layoutError.value = "";
    }
  } catch (error: any) {
    if (id === requestId)
      layoutError.value =
        typeof error.response?.data?.detail === "string"
          ? error.response.data.detail
          : Array.isArray(error.response?.data)
            ? error.response.data.join("；")
            : error.message || "字体或排版加载失败";
  } finally {
    if (id === requestId) layoutBusy.value = false;
  }
}
watch(canvas, scheduleLayout, { deep: true });
onBeforeUnmount(() => {
  clearTimeout(timer);
  requestId++;
});
function openTemplateDialog(copy: boolean) {
  Object.assign(templateForm, {
    copy,
    name: copy
      ? `${selectedTemplate.value?.name || "模板"} 副本`
      : "新证书模板",
    department: managedDepartments.value[0]?.id
  });
  templateDialog.value = true;
}
async function createOrCopy() {
  if (!templateForm.department || templateSaving.value) return;
  templateSaving.value = true;
  try {
    const payload = {
      name: templateForm.name.trim(),
      department: templateForm.department
    };
    const target =
      templateForm.copy && selectedId.value
        ? await copyTemplate(selectedId.value, payload)
        : await createTemplate({
            ...payload,
            published: true,
            canvas: normalize({})
          });
    if (!target.published) await publishTemplate(target.id);
    await load();
    selectedId.value = target.id;
    templateDialog.value = false;
    ElMessage.success("模板已保存到共享模板库");
  } catch {
  } finally {
    templateSaving.value = false;
  }
}
function addText() {
  const layer = newText();
  canvas.value.layers.push(layer);
  selectedLayerId.value = layer.id;
}
function addSeal() {
  const layer: SealLayer = {
    id: layerId(),
    type: "seal",
    department: managedDepartments.value[0]?.id,
    x: 620,
    y: 410,
    size: 100
  };
  canvas.value.layers.push(layer);
  selectedLayerId.value = layer.id;
}
function remove() {
  canvas.value.layers = canvas.value.layers.filter(
    l => l.id !== selectedLayerId.value
  );
  selectedLayerId.value = canvas.value.layers[0]?.id || "";
}
function upload(file: UploadFile) {
  if (!file.raw) return;
  const reader = new FileReader();
  reader.onload = () => (canvas.value.background = String(reader.result));
  reader.readAsDataURL(file.raw);
}
async function save() {
  if (!selectedId.value || saving.value) return;
  saving.value = true;
  try {
    const result = await saveTemplateVersion(
      selectedId.value,
      JSON.parse(JSON.stringify(canvas.value))
    );
    await load();
    ElMessage.success(`已保存模板版本 v${result.number}`);
  } catch {
  } finally {
    saving.value = false;
  }
}
async function uploadFont() {
  if (!fontUpload.value || fontSaving.value) return;
  fontSaving.value = true;
  try {
    const data = new FormData();
    data.append("file", fontUpload.value);
    data.append("name", fontForm.name);
    data.append("license_confirmed", String(fontForm.license_confirmed));
    const font = await importFont(data);
    fonts.value = await listFonts();
    if (selectedLayer.value?.type === "text")
      selectedLayer.value.fontFamily = font.id;
    fontDialog.value = false;
    ElMessage.success("字体已导入，可用于模板和 PDF");
  } catch {
  } finally {
    fontSaving.value = false;
  }
}
function showInfo() {
  const item = selectedTemplate.value;
  infoData.value = {
    名称: item?.name,
    维护部门: item?.department_name,
    模板版本: item?.latest_version?.number,
    共享: item?.published,
    页面: canvas.value.page,
    图层: canvas.value.layers.map(l =>
      l.type === "text"
        ? {
            类型: fieldLabels[l.field],
            字体: fonts.value.find(f => f.id === l.fontFamily)?.name,
            字号: l.fontSize,
            位置: [l.x, l.y],
            尺寸: [l.width, l.height]
          }
        : {
            类型: "公章",
            部门: departments.value.find(d => d.id === l.department)?.name,
            位置: [l.x, l.y],
            尺寸: l.size
          }
    )
  };
  info.value = true;
}
let drag: {
  layer: Layer;
  x: number;
  y: number;
  clientX: number;
  clientY: number;
  pointer: number;
  target: HTMLElement;
} | null = null;
function moveLayer(layer: Layer, x: number, y: number) {
  const w = layer.type === "seal" ? layer.size : layer.width,
    h = layer.type === "seal" ? layer.size : layer.height;
  layer.x = Math.round(Math.max(0, Math.min(canvas.value.page.width - w, x)));
  layer.y = Math.round(Math.max(0, Math.min(canvas.value.page.height - h, y)));
}
function startDrag(layer: Layer, event: PointerEvent) {
  selectedLayerId.value = layer.id;
  if (!canManage.value || event.button !== 0) return;
  const target = event.currentTarget as HTMLElement;
  target.setPointerCapture(event.pointerId);
  drag = {
    layer,
    x: layer.x,
    y: layer.y,
    clientX: event.clientX,
    clientY: event.clientY,
    pointer: event.pointerId,
    target
  };
}
function moveDrag(event: PointerEvent) {
  if (drag?.pointer === event.pointerId)
    moveLayer(
      drag.layer,
      drag.x + (event.clientX - drag.clientX) / scale.value,
      drag.y + (event.clientY - drag.clientY) / scale.value
    );
}
function endDrag(event: PointerEvent) {
  if (drag?.pointer !== event.pointerId) return;
  if (drag.target.hasPointerCapture(event.pointerId))
    drag.target.releasePointerCapture(event.pointerId);
  drag = null;
}
function moveByKey(layer: Layer, event: KeyboardEvent) {
  if (!canManage.value) return;
  const delta: Record<string, [number, number]> = {
    ArrowLeft: [-1, 0],
    ArrowRight: [1, 0],
    ArrowUp: [0, -1],
    ArrowDown: [0, 1]
  };
  if (!delta[event.key]) return;
  event.preventDefault();
  const [x, y] = delta[event.key],
    step = event.shiftKey ? 10 : 1;
  moveLayer(layer, layer.x + x * step, layer.y + y * step);
}
onMounted(load);
</script>
<template>
  <div class="editor">
    <aside>
      <h3>模板库</h3>
      <div class="stack">
        <el-button @click="router.push('/business/template-library')"
          >可视化选用模板</el-button
        ><el-button v-if="isAdmin" @click="openTemplateDialog(false)"
          >新建模板</el-button
        ><el-button
          v-if="isAdmin"
          :disabled="!selectedId"
          @click="openTemplateDialog(true)"
          >复制当前模板</el-button
        ><el-select v-model="selectedId" aria-label="选择证书模板"
          ><el-option
            v-for="t in rows"
            :key="t.id"
            :label="`${t.name} · ${t.department_name}`"
            :value="t.id" /></el-select
        ><el-button :disabled="!selectedId" @click="showInfo"
          >模板信息</el-button
        >
      </div>
      <el-divider />
      <h3>图层</h3>
      <div class="stack">
        <el-button :disabled="!canManage" @click="addText">添加文本</el-button
        ><el-upload
          :auto-upload="false"
          :show-file-list="false"
          accept="image/png,image/jpeg,image/webp"
          :on-change="upload"
          :disabled="!canManage"
          ><el-button :disabled="!canManage">上传背景</el-button></el-upload
        ><el-button :disabled="!canManage" @click="addSeal"
          >添加公章位</el-button
        >
      </div>
      <div class="layers">
        <button
          v-for="layer in canvas.layers"
          :key="layer.id"
          :class="{ active: selectedLayerId === layer.id }"
          @click="selectedLayerId = layer.id"
        >
          {{ layer.type === "seal" ? "公章位" : fieldLabels[layer.field] }}
        </button>
      </div>
    </aside>
    <main ref="previewHost">
      <div class="preview-status">
        <span v-if="layoutBusy">加载字体与排版…</span
        ><span v-else>与 PDF 共用字体和排版坐标</span
        ><el-alert
          v-if="layoutError"
          :title="layoutError"
          type="error"
          :closable="false"
        />
      </div>
      <div
        class="canvas-wrap"
        :style="{
          width: canvas.page.width * scale + 'px',
          height: canvas.page.height * scale + 'px'
        }"
      >
        <div
          class="canvas"
          :style="{
            width: canvas.page.width + 'px',
            height: canvas.page.height + 'px',
            transform: `scale(${scale})`,
            backgroundImage: canvas.background
              ? `url(${canvas.background})`
              : ''
          }"
        >
          <div
            v-for="layer in canvas.layers"
            :key="layer.id"
            class="layer"
            :class="{
              selected: selectedLayerId === layer.id,
              seal: layer.type === 'seal'
            }"
            :style="
              layer.type === 'text'
                ? {
                    left: layer.x + 'px',
                    top: layer.y + 'px',
                    width: layer.width + 'px',
                    height: layer.height + 'px'
                  }
                : {
                    left: layer.x + 'px',
                    top: layer.y + 'px',
                    width: layer.size + 'px',
                    height: layer.size + 'px'
                  }
            "
            @pointerdown.stop.prevent="startDrag(layer, $event)"
            @pointermove.stop="moveDrag"
            @pointerup="endDrag"
            @pointercancel="endDrag"
            @keydown="moveByKey(layer, $event)"
            tabindex="0"
            role="button"
            :aria-label="
              layer.type === 'seal'
                ? '公章图层'
                : fieldLabels[layer.field] + '图层'
            "
          >
            <svg v-if="layer.type === 'text'" width="100%" height="100%">
              <g
                v-for="(line, index) in layouts[layer.id]?.lines || []"
                :key="index"
              >
                <text
                  v-for="(run, j) in line.runs"
                  :key="j"
                  :x="run.x"
                  :y="line.baseline"
                  :font-size="layouts[layer.id].fontSize"
                  :font-family="run.fontName"
                  :fill="layer.color"
                  style="font-kerning: none; font-variant-ligatures: none"
                >
                  {{ run.text }}
                </text>
              </g></svg
            ><span v-else>公章</span>
          </div>
          <svg
            v-if="canvas.watermark"
            class="watermark"
            :width="canvas.page.width"
            :height="canvas.page.height"
          >
            <text
              :x="canvas.page.width - 60"
              :y="canvas.page.height - 35"
              text-anchor="end"
              font-family="AC_hei"
              font-size="9"
              fill="#bfbfbf"
            >
              2026-AC-00000001
            </text>
          </svg>
        </div>
      </div>
    </main>
    <aside class="properties">
      <h3>属性</h3>
      <el-alert
        v-if="!canManage"
        title="共享模板可查看；请复制到自己的部门后编辑。"
        type="info"
        :closable="false"
      /><el-form
        v-if="selectedLayer"
        label-position="top"
        :disabled="!canManage"
      >
        <template v-if="selectedLayer.type === 'text'"
          ><el-form-item label="内容类型"
            ><el-select v-model="selectedLayer.field"
              ><el-option
                v-for="(label, key) in fieldLabels"
                :key="key"
                :label="label"
                :value="key" /></el-select></el-form-item
          ><el-form-item
            v-if="selectedLayer.field === 'static'"
            label="固定文本"
            ><el-input v-model="selectedLayer.text"
          /></el-form-item>
          <el-form-item label="字体"
            ><el-select v-model="selectedLayer.fontFamily" filterable
              ><el-option
                v-for="font in fonts"
                :key="font.id"
                :label="font.name"
                :value="font.id" /></el-select></el-form-item
          ><el-button v-if="isAdmin" class="full" @click="fontDialog = true"
            >导入授权字体</el-button
          >
          <el-form-item label="字号"
            ><el-input-number
              v-model="selectedLayer.fontSize"
              :min="6"
              :max="120" /></el-form-item
          ><el-form-item label="最小字号"
            ><el-input-number
              v-model="selectedLayer.minFontSize"
              :min="6"
              :max="selectedLayer.fontSize" /></el-form-item
          ><el-form-item label="行距倍数"
            ><el-input-number
              v-model="selectedLayer.lineHeight"
              :min="1"
              :max="3"
              :step="0.05"
              :precision="2" /></el-form-item
          ><el-form-item label="颜色"
            ><el-color-picker v-model="selectedLayer.color" /></el-form-item
          ><el-form-item label="对齐"
            ><el-segmented
              v-model="selectedLayer.align"
              :options="[
                { label: '左', value: 'left' },
                { label: '中', value: 'center' },
                { label: '右', value: 'right' }
              ]" /></el-form-item
          ><el-form-item label="位置与区域"
            ><div class="coords">
              <el-input-number
                v-model="selectedLayer.x"
                :min="0"
              /><el-input-number
                v-model="selectedLayer.y"
                :min="0"
              /><el-input-number
                v-model="selectedLayer.width"
                :min="1"
              /><el-input-number v-model="selectedLayer.height" :min="1" /></div
          ></el-form-item> </template
        ><template v-else
          ><el-form-item label="对应部门"
            ><el-select v-model="selectedLayer.department"
              ><el-option
                v-for="d in departments"
                :key="d.id"
                :label="d.name"
                :value="d.id" /></el-select></el-form-item
          ><el-form-item label="位置与尺寸"
            ><div class="coords">
              <el-input-number
                v-model="selectedLayer.x"
                :min="0"
              /><el-input-number
                v-model="selectedLayer.y"
                :min="0"
              /><el-input-number
                v-model="selectedLayer.size"
                :min="10"
              /></div></el-form-item
        ></template>
        <el-button type="danger" plain class="full" @click="remove"
          >删除图层</el-button
        > </el-form
      ><el-divider /><el-checkbox
        v-model="canvas.watermark"
        :disabled="!canManage"
        >显示编号水印</el-checkbox
      ><el-button
        type="primary"
        class="full save"
        :loading="saving"
        :disabled="!canManage || layoutBusy || !!layoutError"
        @click="save"
        >保存新版本</el-button
      >
    </aside>
    <el-dialog
      v-model="templateDialog"
      :title="templateForm.copy ? '复制模板' : '新建模板'"
      width="480"
      :close-on-click-modal="!templateSaving"
      :show-close="!templateSaving"
      ><el-form label-position="top"
        ><el-form-item label="模板名称"
          ><el-input v-model.trim="templateForm.name" /></el-form-item
        ><el-form-item label="维护部门"
          ><el-select v-model="templateForm.department"
            ><el-option
              v-for="d in managedDepartments"
              :key="d.id"
              :label="d.name"
              :value="d.id" /></el-select></el-form-item></el-form
      ><template #footer
        ><el-button :disabled="templateSaving" @click="templateDialog = false"
          >取消</el-button
        ><el-button
          type="primary"
          :loading="templateSaving"
          :disabled="!templateForm.name || !templateForm.department"
          @click="createOrCopy"
          >保存到模板库</el-button
        ></template
      ></el-dialog
    >
    <el-dialog
      v-model="fontDialog"
      title="导入授权字体"
      width="520"
      :close-on-click-modal="!fontSaving"
      :show-close="!fontSaving"
      ><el-form label-position="top"
        ><el-form-item label="显示名称"
          ><el-input
            v-model="fontForm.name"
            placeholder="例如：学校授权小标宋" /></el-form-item
        ><el-form-item label="字体文件（静态 TTF/TTC，最多 40 MB）"
          ><el-upload
            :auto-upload="false"
            :limit="1"
            accept=".ttf,.ttc"
            :on-change="file => (fontUpload = file.raw)"
            ><el-button>选择字体</el-button></el-upload
          ></el-form-item
        ><el-checkbox v-model="fontForm.license_confirmed"
          >确认具备此字体在本系统中使用、格式转换、嵌入和展示的授权</el-checkbox
        ></el-form
      ><template #footer
        ><el-button :disabled="fontSaving" @click="fontDialog = false"
          >取消</el-button
        ><el-button
          type="primary"
          :loading="fontSaving"
          :disabled="!fontUpload || !fontForm.license_confirmed"
          @click="uploadFont"
          >导入字体</el-button
        ></template
      ></el-dialog
    >
    <RecordDetail v-model="info" title="模板详情" :data="infoData" />
  </div>
</template>
<style scoped>
.editor {
  display: grid;
  grid-template-columns: 220px minmax(260px, 1fr) 280px;
  min-height: calc(100vh - 125px);
  background: #f5f7fa;
}
.editor aside {
  background: white;
  padding: 18px;
  overflow: auto;
  border-right: 1px solid #e5e7eb;
}
.editor aside:last-of-type {
  border-right: 0;
  border-left: 1px solid #e5e7eb;
}
h3 {
  margin: 0 0 14px;
  letter-spacing: 0;
}
.stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.stack :deep(.el-button) {
  width: 100%;
  margin-left: 0;
  margin-right: 0;
}
.stack :deep(.el-upload) {
  display: block;
  width: 100%;
}
.editor main {
  position: relative;
  display: grid;
  align-content: center;
  justify-items: center;
  overflow: auto;
  min-width: 0;
  padding: 24px;
}
.preview-status {
  width: 100%;
  font-size: 12px;
  color: #73767a;
  margin-bottom: 16px;
}
.canvas-wrap {
  position: relative;
}
.canvas {
  position: absolute;
  left: 0;
  top: 0;
  transform-origin: top left;
  background: white center/100% 100% no-repeat;
  outline: 1px solid #cfd4dc;
  box-shadow: 0 8px 24px #0001;
  overflow: hidden;
}
.layer {
  cursor: grab;
  touch-action: none;
  user-select: none;
  position: absolute;
  overflow: hidden;
  outline: 1px dashed transparent;
}
.layer:active {
  cursor: grabbing;
}
.layer.selected,
.layer:focus-visible {
  outline: 1px dashed #409eff;
  background: #409eff08;
}
.layer svg {
  display: block;
}
.layer.seal {
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px dashed #dc2626;
  border-radius: 50%;
  color: #dc2626;
  box-sizing: border-box;
}
.watermark {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.layers {
  border-top: 1px solid #ebeef5;
  margin-top: 18px;
  padding-top: 8px;
}
.layers button {
  display: block;
  width: 100%;
  border: 0;
  background: transparent;
  text-align: left;
  padding: 8px;
  color: #606266;
}
.layers button.active {
  background: #ecf5ff;
  color: #409eff;
}
.full {
  width: 100%;
  margin: 0 0 12px;
}
.coords {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 8px;
}
.coords :deep(.el-input-number) {
  width: 100%;
}
.save {
  margin-top: 18px;
}
.properties :deep(.el-select) {
  width: 100%;
}
@media (max-width: 1120px) {
  .editor {
    grid-template-columns: 190px minmax(260px, 1fr);
  }
  .properties {
    grid-column: 1/-1;
  }
  .editor main {
    min-height: 500px;
  }
}
@media (max-width: 700px) {
  .editor {
    grid-template-columns: minmax(0, 1fr);
  }
  .properties {
    grid-column: auto;
  }
  .editor main {
    min-height: 380px;
  }
}
</style>
