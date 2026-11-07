<!-- Cards reuse PPTist's Templates / ThumbnailSlide component structure. -->
<script setup lang="ts">
import { computed, ref } from "vue";
import { storeToRefs } from "pinia";
import { useMainStore, useSlidesStore } from "@/store";
import {
  CERTIFICATE_LAYOUTS,
  certificateLayout
} from "@/configs/certificateLayouts";
import useSlideHandler from "@/hooks/useSlideHandler";
import useHistorySnapshot from "@/hooks/useHistorySnapshot";
import ThumbnailSlide from "@/views/components/ThumbnailSlide/index.vue";
import Button from "@/components/Button.vue";
import Modal from "@/components/Modal.vue";
const props = defineProps<{ compact?: boolean; insertOnly?: boolean }>();
const emit = defineEmits<{ selected: [] }>();
const slides = useSlidesStore(),
  main = useMainStore();
const { viewportSize, viewportRatio } = storeToRefs(slides);
const { createSlideByTemplate } = useSlideHandler();
const { addHistorySnapshot } = useHistorySnapshot();
const replacing = ref("");
const cards = computed(() =>
  CERTIFICATE_LAYOUTS.map(item => ({
    ...item,
    slide: certificateLayout(
      item.id,
      viewportSize.value,
      viewportSize.value * viewportRatio.value
    )
  }))
);
function insert(id: string) {
  createSlideByTemplate(
    certificateLayout(
      id,
      viewportSize.value,
      viewportSize.value * viewportRatio.value
    )
  );
  emit("selected");
}
function replace() {
  const page = certificateLayout(
    replacing.value,
    viewportSize.value,
    viewportSize.value * viewportRatio.value
  );
  main.setActiveElementIdList([]);
  slides.updateSlide({ elements: page.elements, background: page.background });
  addHistorySnapshot();
  replacing.value = "";
  emit("selected");
}
</script>
<template>
  <section class="certificate-layouts" :class="{ compact }">
    <h3>常用奖状排版</h3>
    <p>包含可编辑的证书字段，公章位可按需添加。</p>
    <div class="layout-list">
      <article v-for="item in cards" :key="item.id" class="slide-item">
        <div class="thumbnail">
          <ThumbnailSlide
            :slide="item.slide"
            :size="props.compact ? 204 : 208"
          />
        </div>
        <strong>{{ item.name }}</strong
        ><small>{{ item.description }}</small>
        <div class="btns">
          <Button size="small" type="primary" @click="insert(item.id)"
            >添加新页面</Button
          ><Button v-if="!insertOnly" size="small" @click="replacing = item.id"
            >替换当前页</Button
          >
        </div>
      </article>
    </div>
    <Modal :visible="!!replacing" :width="360" @closed="replacing = ''">
      <h3>替换当前证书页面</h3>
      <p>当前页内容会被选定排版替换，其他页面保留。可以使用撤销恢复。</p>
      <div class="confirm-actions">
        <Button @click="replacing = ''">取消</Button
        ><Button type="primary" @click="replace">确认替换当前页</Button>
      </div>
    </Modal>
  </section>
</template>
<style lang="scss" scoped>
.certificate-layouts {
  width: 470px;
  max-width: 100%;
  color: var(--ppt-text, #333);
}
.certificate-layouts.compact {
  width: 100%;
}
h3 {
  margin: 0 0 8px;
  font-size: 14px;
}
p {
  color: var(--ppt-secondary, #888);
  line-height: 1.6;
  margin: 0 0 12px;
  font-size: 12px;
}
.layout-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.compact .layout-list {
  grid-template-columns: minmax(0, 1fr);
}
.slide-item {
  min-width: 0;
  padding: 8px;
  border: 1px solid var(--ppt-border, #ddd);
  border-radius: 3px;
  background: var(--ppt-panel, #fff);
}
.thumbnail {
  display: grid;
  place-content: center;
  overflow: hidden;
  margin-bottom: 8px;
}
strong,
small {
  display: block;
  font-size: 12px;
  line-height: 1.7;
}
small {
  color: var(--ppt-secondary, #888);
}
.btns,
.confirm-actions {
  display: flex;
  gap: 6px;
  margin-top: 8px;
  flex-wrap: wrap;
}
.confirm-actions {
  justify-content: flex-end;
}
</style>
