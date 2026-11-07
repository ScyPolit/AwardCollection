<template>
  <template v-if="ready && slides.length">
    <Editor v-if="!readonly" />
    <div v-else class="readonly">
      <ThumbnailSlide
        :slide="slides[slidesStore.slideIndex]"
        :size="Math.min(width - 32, 1100)"
      />
    </div>
  </template>
  <FullscreenSpin v-else tip="正在载入证书模板…" loading :mask="false" />
</template>
<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, nextTick } from "vue";
import { storeToRefs } from "pinia";
import { useSnapshotStore, useSlidesStore } from "@/store";
import { legacyDocument, registerFonts } from "@/award";
import useImport from "@/hooks/useImport";
import { sanitizeSlides, normalizeMedia } from "@/awardSecurity";
import Editor from "./views/Editor/index.vue";
import ThumbnailSlide from "./views/components/ThumbnailSlide/index.vue";
import FullscreenSpin from "@/components/FullscreenSpin.vue";
const slidesStore = useSlidesStore(),
  snapshotStore = useSnapshotStore();
const { slides } = storeToRefs(slidesStore);
const ready = ref(false),
  readonly = ref(true),
  width = ref(window.innerWidth);
const { importPPTXFile, importJSON, importSpecificFile } = useImport();
let page = { width: 842, height: 595 },
  loading = false;
const send = (type: string, data?: unknown) =>
  window.parent.postMessage({ type, data }, location.origin);
async function receive(event: MessageEvent) {
  if (event.origin !== location.origin || event.source !== window.parent)
    return;
  const { type, data } = event.data || {};
  if (type === "award-handshake") send("award-ready");
  if (type === "award-init") {
    loading = true;
    ready.value = false;
    (window as any).__AWARD_CONTEXT__ = data.context || {};
    registerFonts(data.context?.fonts || []);
    readonly.value = !!data.readonly;
    document.documentElement.classList.toggle("award-dark", !!data.dark);
    const canvas = data.canvas || {},
      doc =
        canvas.engine === "pptist"
          ? canvas.presentation
          : legacyDocument(canvas, data.title);
    page = canvas.page || { width: 842, height: 595 };
    slidesStore.setTitle(data.title || doc.title);
    slidesStore.setViewportSize(doc.viewportSize);
    slidesStore.setViewportRatio(doc.viewportRatio);
    slidesStore.setTheme(doc.theme);
    slidesStore.setSlides(sanitizeSlides(doc.slides));
    slidesStore.updateSlideIndex(
      Math.min(canvas.slideIndex || 0, doc.slides.length - 1)
    );
    await snapshotStore.initSnapshotDatabase();
    ready.value = true;
    await nextTick();
    await document.fonts.ready;
    setTimeout(() => {
      loading = false;
      send("award-clean");
      send("award-initialized");
    }, 100);
  }
  if (type === "award-import") {
    if (data.name.endsWith(".pptx")) importPPTXFile([data], { cover: true });
    else if (data.name.endsWith(".pptist")) importSpecificFile([data], true);
    else importJSON([data], true);
  }
  if (type === "award-save-request") await save();
  if (type === "award-theme")
    document.documentElement.classList.toggle("award-dark", !!data);
  if (type === "award-fonts") registerFonts(data);
}
async function save() {
  if (readonly.value || !ready.value) return;
  try {
    window.dispatchEvent(new Event("award-flush-editors"));
    await nextTick();
    const doc = await normalizeMedia(
      JSON.parse(
        JSON.stringify({
          title: slidesStore.title,
          slides: slidesStore.slides,
          theme: slidesStore.theme,
          viewportSize: slidesStore.viewportSize,
          viewportRatio: slidesStore.viewportRatio
        })
      )
    );
    const canvas = {
      engine: "pptist",
      page: {
        width: page.width,
        height: Math.round(page.width * doc.viewportRatio * 100) / 100
      },
      presentation: doc,
      slideIndex: slidesStore.slideIndex
    };
    send("award-save", canvas);
  } catch (e) {
    send("award-error", String(e));
  }
}
function key(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    save();
  }
}
const resize = () => (width.value = window.innerWidth);
slidesStore.$subscribe(() => {
  if (ready.value && !loading) send("award-dirty");
});
onMounted(() => {
  window.addEventListener("message", receive);
  window.addEventListener("award-save", save);
  window.addEventListener("keydown", key, true);
  window.addEventListener("resize", resize);
  send("award-ready");
});
onBeforeUnmount(() => {
  window.removeEventListener("message", receive);
  window.removeEventListener("award-save", save);
  window.removeEventListener("keydown", key, true);
  window.removeEventListener("resize", resize);
});
</script>
<style lang="scss">
#app {
  height: 100%;
}
.readonly {
  height: 100%;
  overflow: auto;
  display: grid;
  place-content: center;
  background: var(--ppt-fill, #e5e7eb);
}
html.award-dark {
  --ppt-panel: #1d1e1f;
  --ppt-text: #dfe3eb;
  --ppt-border: #414243;
  --ppt-fill: #262727;
  --ppt-secondary: #a3a6ad;
  background: #1d1e1f;
  color: #dfe3eb;
  color-scheme: dark;
}
html.award-dark body {
  background: #1d1e1f;
  color: #dfe3eb;
}
</style>
